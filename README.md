# Haseeb — Windows PC Desktop Applications

Haseeb is the independent Windows PC application and deployment repository. It is NOT VPS_1 and does not modify Scene Builder, Short Maker or existing YouTube accounts.

## What is in the repository

- `apps/haseeb_control/`: small working local status desktop application (Tkinter). Other apps each get their own directory and `app.json`.
- `tools/haseeb.py`: no-dependencies manifest validation, ZIP packaging, SHA-256 verification, smoke tests, versioned installs and rollback.
- `.github/workflows/build-windows.yml`: GitHub-hosted Windows unit tests and package artifact for successful main builds.
- `ops/windows/`: one-time PC bootstrap, verified build sync, launcher and rollback.
- `docs/PC_DEPLOYMENT.md`: exact PC setup and manual steps.

## Repo privacy is not yet configured

**Verified at setup: this repository is PUBLIC.** Before adding business code, credentials or deployment configuration, change repository visibility to PRIVATE under GitHub repository Settings > General > Danger Zone. Never commit secrets, rclone configs, GitHub tokens, SSH keys, Drive OAuth tokens or local app data.

## Run locally

Requires Python 3.11 or later. To validate and produce a package:

    python -m unittest discover -s tests -v
    python tools/haseeb.py validate
    python tools/haseeb.py package

To test locally without GitHub: `python tools/haseeb.py deploy dist/haseeb-control-0.1.0.zip --root ./test-installed` (requires companion `.sha256`).

For actual Haseeb PC install, follow [PC deployment guide](docs/PC_DEPLOYMENT.md). The repo is deployment-capable at code level; a connected PC and successful CI are required for live deployment.

## Isolation

Every app has its own versioned releases and active pointer. A broken smoke test cannot replace the active pointer; rollback restores the previously activated version. Deployment does not install a self-hosted GitHub Actions runner or open inbound ports.
