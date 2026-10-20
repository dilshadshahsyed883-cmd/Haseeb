#!/usr/bin/env python3
"""Guarded and observable Haseeb GitHub Actions artifact download.

The GitHub CLI writes diagnostic output to a LOCAL file. We never send its
output, machine data, filesystem paths or account information to GitHub.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

REPOSITORY = "dilshadshahsyed883-cmd/Haseeb"
RUN_ID = re.compile(r"^[0-9]{1,20}$")
ARTIFACT = "haseeb-windows-bundle"
DEFAULT_TIMEOUT = 600
HEARTBEAT_SECONDS = 30


def download(run_id, destination, *, launcher=None, log_root=None,
             timeout_seconds=DEFAULT_TIMEOUT, heartbeat_seconds=HEARTBEAT_SECONDS):
    """Return downloaded ZIP paths or fail without modifying installed apps.

    All downloads go to an attempt-specific empty directory. A terminated or
    interrupted previous download is never reused or prompted for overwrite.
    """
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid verified build run ID")
    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        raise ValueError("Timeout must be positive")
    if not isinstance(heartbeat_seconds, (int, float)) or heartbeat_seconds <= 0:
        raise ValueError("Heartbeat must be positive")
    target = Path(destination)
    if target.exists() and any(target.iterdir()):
        raise ValueError("Refusing nonempty download destination")
    target.mkdir(parents=True, exist_ok=True)
    if launcher is None:
        gh = shutil.which("gh")
        if not gh:
            raise RuntimeError("GitHub CLI is unavailable")
        launcher = [gh]
    if not launcher:
        raise ValueError("Missing GitHub CLI launcher")

    if log_root is None:
        log_root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Haseeb" / "logs"
    log_root = Path(log_root)
    log_root.mkdir(parents=True, exist_ok=True)
    log = log_root / ("artifact-" + run_id + "-" + target.name + ".log")
    cmd = [*launcher, "run", "download", run_id, "--repo", REPOSITORY,
           "--name", ARTIFACT, "--dir", str(target)]
    print("[HASEEB] Downloading verified build artifact for run " + run_id, flush=True)
    print("[HASEEB] Download timeout: " + str(round(timeout_seconds)) + " seconds", flush=True)

    with log.open("w", encoding="utf-8") as local_log:
        # Do not allow interactive overwrite or confirmation prompts to stall
        # the unattended scheduled task.
        process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=local_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            remaining = timeout_seconds - elapsed
            if remaining <= 0:
                process.kill()
                process.wait()
                raise TimeoutError("Artifact download exceeded timeout")
            try:
                code = process.wait(timeout=min(heartbeat_seconds, remaining))
                break
            except subprocess.TimeoutExpired:
                waited = round(time.monotonic() - started)
                print("[HASEEB] Artifact download still running after "
                      + str(waited) + " seconds", flush=True)
        if code != 0:
            raise RuntimeError("GitHub artifact download returned nonzero exit code")

    archives = sorted(target.glob("*.zip"))
    if not archives:
        raise ValueError("Downloaded build contained no application ZIPs")
    if not all(Path(str(archive) + ".sha256").is_file() for archive in archives):
        raise ValueError("Downloaded build is missing SHA-256 companion files")
    print("[HASEEB] Artifact download finished; ZIP files: " + str(len(archives)), flush=True)
    print("[HASEEB] Checksums and smoke tests run in the existing guarded installer", flush=True)
    return archives


def main(argv=None):
    parser = argparse.ArgumentParser(description="Haseeb guarded GitHub artifact download")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    try:
        download(args.run_id, args.dir, timeout_seconds=args.timeout_seconds)
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        # Error messages only include fixed diagnostic codes, never GH output.
        if isinstance(exc, TimeoutError):
            code = "DOWNLOAD_TIMEOUT"
        elif isinstance(exc, ValueError):
            code = "DOWNLOAD_CONTENT_INVALID"
        else:
            code = "DOWNLOAD_FAILED"
        print("[HASEEB] ERROR " + code + ": see local artifact diagnostic log", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
