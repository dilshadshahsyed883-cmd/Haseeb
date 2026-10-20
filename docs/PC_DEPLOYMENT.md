# Haseeb PC — Bootstrap and Deploy

## Prerequisites on the Windows PC

1. This Haseeb repository is intentionally PUBLIC at the owner's direction. Store only public-safe source and CI configuration; NEVER commit credentials, tokens, private keys, personal media or user files.
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

## Multi-app release safety

System-only `deploy-bundle` validates every packaged app before it updates
ANY active app pointer. It checks per-ZIP SHA-256 companions, archive paths,
manifests, duplicate app IDs and each application's existing `--self-test`.
Only after the entire set passes does it activate new release pointers.
If a pointer write fails during activation, the updater restores saved
`current.json` and `previous.json` pointers for ALL affected apps.
The old working release files are never deleted as part of deployment.

The successful GitHub run ID marker is written only if bundle deployment
completed successfully. Failed runs retry normally on the next scheduled
check, without silently marking the failed release as installed.

CI tests use isolated synthetic archives under temporary directories:
successful multi-app upgrade, failing later app, missing checksum, duplicate
app ID, and simulated pointer-write failure/recovery. No actual Haseeb PC
application source code or owner files are used in these tests.

Note: pointer restoration handles ordinary runtime errors; simultaneous
machine power loss during a multi-file pointer write is not a full
durable database transaction. Backups/previous releases remain available.

## Hourly updater system reliability

The owner's existing PC remains the only installation target. The repository
can stay PUBLIC; the GitHub CLI login stays solely on that Windows PC.

The scheduler invokes `ops/windows/Run-HaseebSync.ps1`, a thin wrapper around
the exact-main-SHA guarded `Sync-Haseeb.ps1`. It prevents overlapping updater
runs, writes logs under `%LOCALAPPDATA%\Haseeb\logs\`, and retains up to
60 log files. No unrelated application or data folders are cleaned.

After the new release is synced, upgrade the already-existing scheduled task once:

    powershell -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Haseeb\repo\ops\windows\Sync-Haseeb.ps1" -RegisterTask

Read installed versions, task's last execution status and next run:

    powershell -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Haseeb\repo\ops\windows\Status-Haseeb.ps1"

For structured local diagnostics append `-Json`.

These system utilities have Windows PowerShell 5.1 self-tests in CI.
GitHub build PASS does not independently prove unattended Windows installation;
confirm installed release pointers and task evidence on the PC.

## New desktop applications

Place each app in `apps/<folder>/` with `app.json`: `id` (lowercase hyphen slug), `name`, `version` (`x.y.z`), and `entry_point` (Python file path). Entry must support a no-GUI `--self-test` that exits nonzero on failure. All app source and dependencies needed at runtime must be included in its ZIP. The current sample uses Python stdlib only; external dependencies and exe installers require a new reviewed build step.

## Deployment boundaries

User credentials stay on PC: use `gh auth login`, `tailscale up` and `rclone config` interactively. Avoid printing tokens, putting them in PowerShell files, or making a public repo self-hosted runner. Local installs are under `%LOCALAPPDATA%\Haseeb\installed`; the script will not touch other PC or VPS applications. Current implementation requires Python on the PC, not a compiled exe.
