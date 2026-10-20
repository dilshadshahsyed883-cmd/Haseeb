#!/usr/bin/env python3
"""Package and install independent Haseeb desktop apps. No network or secrets."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

BASE = Path(__file__).resolve().parents[1]
ID = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
EXCLUDE = {"__pycache__", ".venv", "venv", ".git", "node_modules", "data", "outputs",
           ".env", ".env.local", "credentials.json", "secrets.json", "token.json"}
BAD_SUFFIXES = {".pem", ".p12", ".pfx", ".key", ".pyc"}


def manifest(folder):
    obj = json.loads((folder / "app.json").read_text(encoding="utf-8"))
    slug, version, entry = obj.get("id"), obj.get("version"), obj.get("entry_point")
    if not isinstance(slug, str) or not ID.fullmatch(slug):
        raise ValueError("Invalid app id")
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("Invalid app version")
    if not isinstance(entry, str) or not entry.endswith(".py"):
        raise ValueError("Invalid entry point")
    relative = PurePosixPath(entry)
    if (relative.is_absolute() or "\\" in entry or ":" in entry or
            any(p in (".", "..") for p in relative.parts)):
        raise ValueError("Unsafe entry point")
    file = (folder / entry).resolve()
    if not file.is_relative_to(folder.resolve()) or not file.is_file():
        raise ValueError("Entry point not found")
    if not isinstance(obj.get("name"), str) or not obj["name"].strip():
        raise ValueError("Missing application name")
    return obj


def apps(folder):
    found = sorted(p for p in folder.iterdir() if p.is_dir() and (p / "app.json").is_file())
    if not found:
        raise ValueError("No app manifests")
    for p in found:
        yield p, manifest(p)


def sha256(file):
    h = hashlib.sha256()
    with file.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def package(apps_dir, out):
    out.mkdir(parents=True, exist_ok=True)
    built = []
    for folder, spec in apps(apps_dir):
        file = out / (spec["id"] + "-" + spec["version"] + ".zip")
        with zipfile.ZipFile(file, "w", zipfile.ZIP_DEFLATED) as z:
            for source in sorted(folder.rglob("*")):
                relative = source.relative_to(folder)
                if any(x in EXCLUDE or x.startswith(".") for x in relative.parts):
                    continue
                if source.is_symlink():
                    raise ValueError("Symlinks cannot be packaged")
                if source.is_file() and source.suffix.lower() not in BAD_SUFFIXES:
                    z.write(source, relative.as_posix())
        Path(str(file) + ".sha256").write_text(
            sha256(file) + "  " + file.name + "\n", encoding="utf-8")
        built.append(file)
    return built


def checksum(archive):
    chk = Path(str(archive) + ".sha256")
    if not chk.is_file():
        raise ValueError("Missing SHA-256 companion file")
    value = chk.read_text(encoding="utf-8").strip().split()
    if not value or not re.fullmatch(r"[a-fA-F0-9]{64}", value[0]):
        raise ValueError("Invalid SHA-256 file")
    actual = sha256(archive)
    if actual != value[0].lower():
        raise ValueError("Checksum mismatch")
    return actual


def extract(archive, dest):
    seen = set()
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            raw = member.filename
            parts = PurePosixPath(raw).parts
            if (not raw or raw.startswith("/") or "\\" in raw or ":" in raw or
                    any(p in (".", "..") for p in parts) or raw in seen):
                raise ValueError("Unsafe ZIP path: " + raw)
            seen.add(raw)
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("ZIP symlink is unsupported")
            target = (dest / Path(*parts)).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise ValueError("ZIP path outside staging")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        json.dump(value, f, indent=2)
        f.write("\n")
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def pointer(root, slug, which="current"):
    path = root / "apps" / slug / (which + ".json")
    if not path.exists():
        return None
    obj = json.loads(path.read_text(encoding="utf-8"))
    dest = (root / obj["release"]).resolve()
    if not dest.is_relative_to((root / "releases" / slug).resolve()) or not dest.is_dir():
        raise ValueError("Invalid local release pointer")
    return obj


def deploy(root, archive):
    root = root.resolve()
    archive = archive.resolve()
    digest = checksum(archive)
    releases = root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=releases))
    try:
        extract(archive, stage)
        spec = manifest(stage)
        slug = spec["id"]
        dest = releases / slug / (spec["version"] + "-" + digest[:12])
        smoke = subprocess.run(
            [sys.executable, str(stage / spec["entry_point"]), "--self-test"],
            cwd=stage, capture_output=True, text=True, timeout=40)
        if smoke.returncode:
            raise RuntimeError("Smoke test failed: " + smoke.stderr[-1200:])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            stage.rename(dest)
        record = {"app_id": slug, "version": spec["version"],
                  "release": dest.relative_to(root).as_posix(), "sha256": digest}
        active = pointer(root, slug)
        if active != record:
            if active:
                save(root / "apps" / slug / "previous.json", active)
            save(root / "apps" / slug / "current.json", record)
        return record
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def rollback(root, slug):
    if not ID.fullmatch(slug):
        raise ValueError("Invalid app id")
    root = root.resolve()
    old = pointer(root, slug, "previous")
    if not old:
        raise ValueError("No previous release")
    active = pointer(root, slug)
    save(root / "apps" / slug / "current.json", old)
    if active:
        save(root / "apps" / slug / "previous.json", active)
    return old


def main():
    ap = argparse.ArgumentParser(description="Haseeb Windows desktop app deployment")
    cmd = ap.add_subparsers(dest="cmd", required=True)
    validate = cmd.add_parser("validate")
    validate.add_argument("--apps", type=Path, default=BASE / "apps")
    bundle = cmd.add_parser("package")
    bundle.add_argument("--apps", type=Path, default=BASE / "apps")
    bundle.add_argument("--out", type=Path, default=BASE / "dist")
    install = cmd.add_parser("deploy")
    install.add_argument("archive", type=Path)
    install.add_argument("--root", type=Path, required=True)
    revert = cmd.add_parser("rollback")
    revert.add_argument("app_id")
    revert.add_argument("--root", type=Path, required=True)
    status = cmd.add_parser("status")
    status.add_argument("--root", type=Path, required=True)
    arg = ap.parse_args()
    if arg.cmd == "validate":
        print("Validated: " + ", ".join(spec["id"] for _, spec in apps(arg.apps)))
    elif arg.cmd == "package":
        print("\n".join(map(str, package(arg.apps, arg.out))))
    elif arg.cmd == "deploy":
        print(json.dumps(deploy(arg.root, arg.archive), indent=2))
    elif arg.cmd == "rollback":
        print(json.dumps(rollback(arg.root, arg.app_id), indent=2))
    else:
        for p in sorted((arg.root / "apps").glob("*/current.json")):
            print(p.parent.name + ": " + p.read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired,
            zipfile.BadZipFile, KeyError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
