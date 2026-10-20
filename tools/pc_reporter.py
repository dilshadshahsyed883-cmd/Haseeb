#!/usr/bin/env python3
"""Privacy-safe Haseeb PC -> GitHub deployment feedback.

This tool never sends PC logs, paths, usernames, hostnames, secrets or media.
Only an allowlisted deployment outcome is sent to a GitHub Actions dispatch.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

REPOSITORY = "dilshadshahsyed883-cmd/Haseeb"
EVENT_TYPE = "haseeb_pc_deployment_report"
STAGES = frozenset({"preflight", "auth", "git", "ci", "artifact", "install", "complete", "unknown"})
CODES = frozenset({
    "INSTALLED", "MISSING_UPDATER", "MISSING_PREREQUISITE", "AUTH_FAILED",
    "SOURCE_SYNC_FAILED", "CI_NOT_READY", "CI_QUERY_FAILED",
    "ARTIFACT_FAILED", "INSTALL_FAILED", "UPDATER_FAILED", "UNKNOWN_FAILURE",
})
FIELDS = frozenset({
    "schema_version", "event_id", "agent", "status", "stage",
    "error_code", "commit_sha", "run_id", "created_utc",
})
UTC_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_RE = re.compile(r"^[0-9]{1,20}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def validate_report(report):
    if not isinstance(report, dict) or set(report) != FIELDS:
        raise ValueError("Unexpected report fields")
    if type(report["schema_version"]) is not int or report["schema_version"] != 1:
        raise ValueError("Invalid schema")
    if report["agent"] != "haseeb-windows":
        raise ValueError("Invalid agent")
    if report["status"] not in ("success", "failure") or report["stage"] not in STAGES:
        raise ValueError("Invalid outcome")
    if report["error_code"] not in CODES:
        raise ValueError("Invalid error code")
    if (report["status"] == "success") != (report["error_code"] == "INSTALLED"):
        raise ValueError("Outcome and code disagree")
    if report["status"] == "success" and report["stage"] != "complete":
        raise ValueError("Successful report must be complete")
    if not isinstance(report["event_id"], str) or not UUID_RE.fullmatch(report["event_id"]):
        raise ValueError("Invalid event id")
    sha = report["commit_sha"]
    if not isinstance(sha, str) or (sha and not SHA_RE.fullmatch(sha)):
        raise ValueError("Invalid SHA")
    run = report["run_id"]
    if not isinstance(run, str) or (run and not RUN_RE.fullmatch(run)):
        raise ValueError("Invalid run id")
    date = report["created_utc"]
    if not isinstance(date, str) or not UTC_RE.fullmatch(date):
        raise ValueError("Invalid timestamp")
    try:
        datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as e:
        raise ValueError("Invalid timestamp date") from e
    return report


def create_report(status, stage, code, sha="", run_id="", now=None):
    now = now or datetime.now(timezone.utc)
    report = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "agent": "haseeb-windows",
        "status": status,
        "stage": stage,
        "error_code": code,
        "commit_sha": sha,
        "run_id": run_id,
        "created_utc": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return validate_report(report)


def dedupe_id(report):
    # Limit identical failures to one report/day/commit; installs only reported on marker change.
    signature = "|".join((
        report["created_utc"][:10], report["status"], report["stage"],
        report["error_code"], report["commit_sha"], report["run_id"],
    ))
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()


def record(root, status, stage, code, sha="", run_id="", now=None):
    report = create_report(status, stage, code, sha, run_id, now)
    root = Path(root)
    pending = root / "pending"
    sent = root / "sent"
    pending.mkdir(parents=True, exist_ok=True)
    sent.mkdir(parents=True, exist_ok=True)
    fingerprint = dedupe_id(report)
    if (sent / (fingerprint + ".json")).exists():
        return False
    target = pending / (fingerprint + ".json")
    try:
        # Exclusive create avoids duplicates, even if two invocations overlap.
        with target.open("x", encoding="utf-8") as fp:
            json.dump(report, fp, separators=(",", ":"), sort_keys=True)
            fp.write("\n")
    except FileExistsError:
        return False
    return True


def post_dispatch(report):
    data = json.dumps({"event_type": EVENT_TYPE, "client_payload": validate_report(report)}, separators=(",", ":"))
    # Never show gh stderr: it may contain account identifiers or private paths.
    try:
        outcome = subprocess.run(
            ["gh", "api", "--method", "POST", f"repos/{REPOSITORY}/dispatches", "--input", "-"],
            input=data, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=25, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return outcome.returncode == 0


def flush(root, sender=None):
    root = Path(root)
    pending = root / "pending"
    sent = root / "sent"
    if not pending.exists():
        return (0, 0)
    sent.mkdir(parents=True, exist_ok=True)
    sender = sender or post_dispatch
    delivered = 0
    failed = 0
    for path in sorted(pending.glob("*.json"))[:30]:
        try:
            report = validate_report(json.loads(path.read_text(encoding="utf-8")))
            if not sender(report):
                failed += 1
                break  # Avoid repeated remote calls while disconnected.
            # Marker is durable before removing the pending record.
            os.replace(path, sent / path.name)
            delivered += 1
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Invalid local report is retained for inspection, never transmitted.
            failed += 1
            break
    return delivered, failed


def render_summary(report):
    report = validate_report(report)
    state = "SUCCESS" if report["status"] == "success" else "FAILURE"
    return (
        f"## Haseeb Windows PC deployment: {state}\n\n"
        "This is a PC-reported outcome (not independent remote attestation).\n\n"
        "| Field | Value |\n|---|---|\n"
        f"| Result | {report['status']} |\n"
        f"| Stage | {report['stage']} |\n"
        f"| Code | {report['error_code']} |\n"
        f"| Git commit | `{report['commit_sha'] or 'unavailable'}` |\n"
        f"| Build run | `{report['run_id'] or 'unavailable'}` |\n"
        f"| Reported UTC | {report['created_utc']} |\n"
        f"| Event ID | `{report['event_id']}` |\n\n"
        "No PC log text, file paths, media, hostnames or credentials are transmitted.\n"
    )


def export_dispatch(event_path, output_path, summary_path):
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    report = validate_report(event.get("client_payload"))
    Path(output_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(summary_path).write_text(render_summary(report), encoding="utf-8")


def default_root():
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".haseeb")) / "Haseeb" / "reports"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Haseeb privacy-safe deployment telemetry")
    subs = parser.add_subparsers(dest="command", required=True)
    record_cmd = subs.add_parser("record")
    record_cmd.add_argument("--root", type=Path, default=default_root())
    record_cmd.add_argument("--status", choices=["success", "failure"], required=True)
    record_cmd.add_argument("--stage", choices=sorted(STAGES), required=True)
    record_cmd.add_argument("--code", choices=sorted(CODES), required=True)
    record_cmd.add_argument("--sha", default="")
    record_cmd.add_argument("--run-id", default="")
    flush_cmd = subs.add_parser("flush")
    flush_cmd.add_argument("--root", type=Path, default=default_root())
    export_cmd = subs.add_parser("export-dispatch")
    export_cmd.add_argument("--event-path", type=Path, required=True)
    export_cmd.add_argument("--output", type=Path, required=True)
    export_cmd.add_argument("--summary", type=Path, required=True)
    opts = parser.parse_args(argv)
    try:
        if opts.command == "record":
            queued = record(opts.root, opts.status, opts.stage, opts.code, opts.sha, opts.run_id)
            print("Feedback queued" if queued else "Duplicate feedback suppressed")
        elif opts.command == "flush":
            delivered, errors = flush(opts.root)
            print(f"Feedback: {delivered} sent, {errors} deferred")
            return 1 if errors else 0
        else:
            export_dispatch(opts.event_path, opts.output, opts.summary)
            print("Report schema valid")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # Do not echo exception text to CI logs.
        print("Deployment feedback operation failed validation or IO", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
