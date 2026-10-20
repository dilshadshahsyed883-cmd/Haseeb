# Haseeb PC — Bootstrap and Deploy

## Prerequisites on the Windows PC

1. Change this GitHub repo from PUBLIC to PRIVATE before storing project code or credentials. This is an owner-level GitHub setting, not changed by these scripts.
2. Open a PowerShell terminal, clone the repo, and run `powershell -NoProfile -File .\ops\windows\Bootstrap-Haseeb.ps1 -InstallTools`.
3. After winget installs, open a NEW PowerShell terminal and re-run the Bootstrap command without `-InstallTools` to check setup.
4. Run `gh auth login` and follow the GitHub browser/device authorization; use the account with access to Haseeb.
5. Run `tailscale up` and authorize this Windows PC in your tailnet. Tailscale is for remote control, not required for GitHub artifact sync.
6. For Google Drive, run `rclone config` and grant access only to the required Drive remote; never commit its config. Drive Agent integration is a separate phase.

## Deploy validated builds

The CI workflow on `main` must be successful first. Then on PC:

    powershell -NoProfile -File "$env:LOCALAPPDATA\Haseeb\repo\ops\windows\Sync-Haseeb.ps1"

Sync refuses to deploy until the exact current `origin/main` SHA has a successful GitHub Actions run triggered by `push` or `workflow_dispatch`. It downloads only the named `haseeb-windows-bundle`, checks every ZIP against its companion SHA-256, executes each app's `--self-test`, and activates validated releases. Previous versions remain for rollback.

To open the first application:

    powershell -NoProfile -File "$env:LOCALAPPDATA\Haseeb\repo\ops\windows\Launch-Haseeb.ps1" -AppId haseeb-control

To roll back that app:

    powershell -NoProfile -File "$env:LOCALAPPDATA\Haseeb\repo\ops\windows\Rollback-Haseeb.ps1" -AppId haseeb-control

## Opt-in hourly sync

Only after the first manual sync is confirmed:

    powershell -NoProfile -File "$env:LOCALAPPDATA\Haseeb\repo\ops\windows\Sync-Haseeb.ps1" -RegisterTask

This creates a Windows Scheduled Task named `HaseebDesktopSync`. No public listener, inbound SSH rule, or self-hosted Actions runner is configured by this project.

## New desktop applications

Place each app in `apps/<folder>/` with `app.json`: `id` (lowercase hyphen slug), `name`, `version` (`x.y.z`), and `entry_point` (Python file path). Entry must support a no-GUI `--self-test` that exits nonzero on failure. All app source and dependencies needed at runtime must be included in its ZIP. The current sample uses Python stdlib only; external dependencies and exe installers require a new reviewed build step.

## Deployment boundaries

User credentials stay on PC: use `gh auth login`, `tailscale up` and `rclone config` interactively. Avoid printing tokens, putting them in PowerShell files, or making a public repo self-hosted runner. Local installs are under `%LOCALAPPDATA%\Haseeb\installed`; the script will not touch other PC or VPS applications. Current implementation requires Python on the PC, not a compiled exe.
