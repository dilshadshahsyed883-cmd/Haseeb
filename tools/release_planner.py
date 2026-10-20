#!/usr/bin/env python3
"""Conservative release planner for source-only Haseeb system updates.

Exit 0: verified source-only delta (no app artifact is needed).
Exit 10: app/package-affecting change, or absent/unusable prior release SHA.
Exit 2: unexpected git/IO error (do not mark a release installed).

Only a narrowly allowed set of deployment-system paths can avoid downloading
application binaries; any new or unrecognized path defaults to full validation.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys

SHA = re.compile(r"^[a-f0-9]{40}$")
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
    return (
        path in SOURCE_ONLY_FILES
        or any(path.startswith(prefix) for prefix in SOURCE_ONLY_DIRS)
    )


def changed_paths(repo, previous_sha, current_sha):
    """Return changed file paths only when prior SHA is an ancestor."""
    if not SHA.fullmatch(previous_sha) or not SHA.fullmatch(current_sha):
        return None
    if previous_sha == current_sha:
        return []
    repo = Path(repo).resolve()
    base = ["git", "-C", str(repo)]
    ancestor = subprocess.run(
        base + ["merge-base", "--is-ancestor", previous_sha, current_sha],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
        check=False,
    )
    if ancestor.returncode != 0:
        return None
    result = subprocess.run(
        base + [
            "diff", "--name-only", "--no-renames", "-z",
            previous_sha, current_sha, "--",
        ],
        capture_output=True, timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError("Git diff unavailable")
    return [
        path.decode("utf-8", "surrogateescape")
        for path in result.stdout.split(b"\0") if path
    ]


def source_only_update(repo, previous_sha, current_sha):
    paths = changed_paths(repo, previous_sha, current_sha)
    return paths is not None and all(safe_system_path(path) for path in paths)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--previous-sha", required=True)
    parser.add_argument("--current-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if source_only_update(args.repo, args.previous_sha, args.current_sha):
            print("[HASEEB] Source-only release verified. App packages unchanged.")
            return 0
        print("[HASEEB] App/package change or unknown prior SHA: full bundle required.")
        return 10
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        print("[HASEEB] Release planner unavailable; no release marked installed.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
