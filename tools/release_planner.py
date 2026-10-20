#!/usr/bin/env python3
"""Fail-closed Haseeb source-only release planner.

Exit 0: exact-main CI verified and only allowed system paths changed, installed
        app release pointers exist, so unchanged application archives can skip.
Exit 10: app/package change or missing/unverifiable legacy metadata; full
         guarded artifact download and app self-test required.
Exit 2: unexpected runtime error; caller must not mark release installed.

Old Haseeb app installs recorded a successful GitHub run ID but did not
persist its head SHA. Bootstrap that SHA only from GitHub's verified run API.
No secrets, machine paths, or private logs are published.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

REPOSITORY = "dilshadshahsyed883-cmd/Haseeb"
WORKFLOW = ".github/workflows/build-windows.yml"
SHA = re.compile(r"^[a-f0-9]{40}$")
RUN_ID = re.compile(r"^[0-9]{1,20}$")
APP_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
SOURCE_ONLY_FILES = frozenset({
    "tools/download_artifact.py",
    "tools/pc_reporter.py",
    "tools/release_planner.py",
    ".github/workflows/pc-deployment-report.yml",
    ".github/workflows/haseeb-tailscale-oidc.yml",
    "README.md",
    ".gitignore",
})
SOURCE_ONLY_DIRS = ("ops/windows/", "docs/", "tests/")


def safe_system_path(path):
    return path in SOURCE_ONLY_FILES or any(
        path.startswith(prefix) for prefix in SOURCE_ONLY_DIRS
    )


def changed_paths(repo, previous_sha, current_sha):
    """Identify changes only when the old installed SHA is in target history."""
    if not SHA.fullmatch(previous_sha) or not SHA.fullmatch(current_sha):
        return None
    if previous_sha == current_sha:
        return []
    repo = Path(repo).resolve()
    base = ["git", "-C", str(repo)]
    ancestor = subprocess.run(
        base + ["merge-base", "--is-ancestor", previous_sha, current_sha],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=20, check=False,
    )
    if ancestor.returncode != 0:
        return None
    result = subprocess.run(
        base + ["diff", "--name-only", "--no-renames", "-z",
                previous_sha, current_sha, "--"],
        capture_output=True, timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError("Cannot verify installed-to-target git changes")
    return [
        item.decode("utf-8", "surrogateescape")
        for item in result.stdout.split(b"\0") if item
    ]


def source_only_update(repo, previous_sha, current_sha):
    paths = changed_paths(repo, previous_sha, current_sha)
    return paths is not None and all(safe_system_path(item) for item in paths)


def verify_previous_run_response(report, run_id):
    """Accept only a completed successful Haseeb/main Windows Build job."""
    if not isinstance(report, dict) or not RUN_ID.fullmatch(run_id):
        return None
    try:
        ok = (
            str(report.get("id")) == run_id
            and report.get("path") == WORKFLOW
            and report.get("head_branch") == "main"
            and report.get("event") in ("push", "workflow_dispatch")
            and report.get("status") == "completed"
            and report.get("conclusion") == "success"
            and report.get("repository", {}).get("full_name") == REPOSITORY
            and report.get("head_repository", {}).get("full_name") == REPOSITORY
        )
        sha = report.get("head_sha")
        return sha if ok and isinstance(sha, str) and SHA.fullmatch(sha) else None
    except (AttributeError, TypeError, ValueError):
        return None


def previous_sha_for_run(run_id):
    """Read trusted old installed run identity without using any build assets."""
    if not RUN_ID.fullmatch(run_id):
        return None
    try:
        proc = subprocess.run(
            ["gh", "api", "--method", "GET",
             f"repos/{REPOSITORY}/actions/runs/{run_id}"],
            text=True, capture_output=True, timeout=30, check=False,
        )
        if proc.returncode:
            return None
        return verify_previous_run_response(json.loads(proc.stdout), run_id)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def installed_apps_intact(repo, installed_root):
    """Never skip a bundle if any declared app has no valid active release."""
    repo = Path(repo).resolve()
    installed_root = Path(installed_root).resolve()
    source_apps = repo / "apps"
    if not source_apps.is_dir() or not installed_root.is_dir():
        return False
    app_dirs = sorted(path for path in source_apps.iterdir()
                      if path.is_dir() and (path / "app.json").is_file())
    if not app_dirs:
        return False
    for app_dir in app_dirs:
        try:
            manifest = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
            slug = manifest["id"]
            if (not isinstance(slug, str) or not APP_ID.fullmatch(slug)
                    or app_dir.name.replace("_", "-") != slug):
                # app folder names may be snake_case, IDs use kebab-case
                return False
            pointer = installed_root / "apps" / slug / "current.json"
            record = json.loads(pointer.read_text(encoding="utf-8-sig"))
            if record.get("app_id") != slug or not VERSION.fullmatch(
                    str(record.get("version", ""))):
                return False
            release_name = record.get("release")
            if not isinstance(release_name, str):
                return False
            release = (installed_root / release_name).resolve()
            base = (installed_root / "releases" / slug).resolve()
            if not release.is_relative_to(base) or release == base:
                return False
            release_manifest = json.loads(
                (release / "app.json").read_text(encoding="utf-8-sig"))
            if (release_manifest.get("id") != slug
                    or release_manifest.get("version") != record["version"]):
                return False
        except (OSError, KeyError, ValueError, TypeError, AttributeError):
            return False
    return True


def evaluate(repo, installed_root, previous_sha, current_sha):
    return installed_apps_intact(repo, installed_root) and source_only_update(
        repo, previous_sha, current_sha
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--install-root", type=Path, required=True)
    old = parser.add_mutually_exclusive_group(required=True)
    old.add_argument("--previous-sha")
    old.add_argument("--previous-run-id")
    parser.add_argument("--current-sha", required=True)
    args = parser.parse_args(argv)
    try:
        previous_sha = args.previous_sha
        if args.previous_run_id is not None:
            previous_sha = previous_sha_for_run(args.previous_run_id)
        if not previous_sha:
            print("[HASEEB] Last app release SHA could not be verified; full artifact required.")
            return 10
        if evaluate(args.repo, args.install_root, previous_sha, args.current_sha):
            print("[HASEEB] Verified unchanged application packages; no artifact download needed.")
            if args.previous_run_id is not None:
                print("[HASEEB] Verified legacy installed run against GitHub main Windows Build.")
            return 0
        print("[HASEEB] App/package changed or installed state unverified; full artifact required.")
        return 10
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        print("[HASEEB] Release planner failed; no deployment marker advanced.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
