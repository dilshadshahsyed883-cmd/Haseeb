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

## Automatic near-real-time update checks

Only after the first manual sync is confirmed:

    powershell -NoProfile -File "$env:LOCALAPPDATA\Haseeb\repo\ops\windows\Sync-Haseeb.ps1" -RegisterTask

This registers the existing Windows Scheduled Task named `HaseebDesktopSync` to check GitHub every **2 minutes**, rather than hourly. On a matching successful `main` Windows Build, it downloads and activates the validated bundle automatically. The PC must be awake and connected to the internet; a build ready just after a check waits until the next check (usually within about 2 minutes), plus normal download/install time. This is fast periodic polling, **not an instantaneous GitHub push**. No public listener, inbound SSH rule, or self-hosted Actions runner is configured.

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

The 2-minute scheduler invokes `ops/windows/Run-HaseebSync.ps1`, a thin
wrapper around the exact-main-SHA guarded `Sync-Haseeb.ps1`. It prevents
overlapping updater runs, writes logs under `%LOCALAPPDATA%\Haseeb\logs\`,
and retains the latest 720 check logs (about 24 hours). A no-change check
skips download and reinstallation. No unrelated application or data folders
are cleaned.

To replace an existing HOURLY task with automatic TWO-MINUTE checks, do this one-time task registration after new source has reached the PC:

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


## PC -> GitHub deployment feedback (two-way reporting)

After this feature is merged into main and the scheduled updater has fetched the new scripts,
the existing `HaseebDesktopSync` task also sends deployment outcomes back to GitHub.
No new open ports, self-hosted runner, SSH service, secrets, or separate Windows service are needed.

- PC install success: the runner records the successfully installed GitHub run ID and,
  for new releases, the exact installed main commit SHA.
- PC install/update failure: only a predefined stage and error code are reported.
  Raw PowerShell transcripts, exception text, usernames, hostnames, filesystem paths,
  credentials and all app/owner data stay on the PC.
- Feedback sends through authenticated `gh api` `repository_dispatch`.
  GitHub's `Haseeb PC Deployment Feedback` Actions workflow validates the fixed schema,
  shows a run summary, and stores a JSON artifact for 30 days.
- With a public repository, these status-only reports are public. Do **not** enable
  uploading local logs or private diagnostics to this workflow.
- Offline, unauthenticated and transient API failures leave JSON reports in
  `%LOCALAPPDATA%\Haseeb\reports\pending` to retry on the next updater check.
  Successfully delivered records move to `...\reports\sent`.
- Duplicate success reports are suppressed by installed run ID; repeated identical
  failures are capped to one per date/commit/stage/reason. No-change checks send nothing.
- Reporting is best-effort and cannot block the guarded installer or automatic rollback.
  A GitHub report means **the PC agent reported** success, not independent remote verification.

PC-only diagnostics continue in `%LOCALAPPDATA%\Haseeb\logs`.
View remote status in repository Actions -> `Haseeb PC Deployment Feedback`.
No report will appear until a real PC installation or a meaningful updater failure
occurs after the updated runner is loaded. GitHub CI PASS by itself is not PC deployment PASS.
