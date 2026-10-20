#requires -Version 5.1
<#
.SYNOPSIS
  Pull ONLY a successful GitHub Actions build for current origin/main, then deploy.
  No inbound ports or self-hosted GitHub runner needed.
#>
[CmdletBinding()]
param(
    [string]$RepoPath = (Join-Path $env:LOCALAPPDATA "Haseeb\repo"),
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Haseeb\installed"),
    [switch]$RegisterTask
)
$ErrorActionPreference = "Stop"
$RepoName = "dilshadshahsyed883-cmd/Haseeb"
$RepoPath = [IO.Path]::GetFullPath($RepoPath)
if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    throw "Missing Haseeb clone at $RepoPath. Run Bootstrap-Haseeb.ps1 first."
}
foreach ($tool in @("git", "gh", "python")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool not available on PATH. Open a fresh terminal after install."
    }
}
if ($RegisterTask) {
    # The runner serializes concurrent invocations and persists per-run logs.
    # The canonical guarded Sync-Haseeb.ps1 continues to own app updates.
    $runner = Join-Path $RepoPath "ops\windows\Run-HaseebSync.ps1"
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw "Haseeb system runner not found: $runner"
    }
    # Near-real-time release readiness detection: check GitHub every 2 minutes.
    # The task runs only when PC is awake/online and calls the exact-main
    # successful-build guarded updater; no inbound PC ports or SSH needed.
    $task = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $runner + '"'
    & schtasks.exe /Create /F /SC MINUTE /MO 2 /TN "HaseebDesktopSync" /TR $task
    if ($LASTEXITCODE -ne 0) { throw "Scheduled task registration failed." }
    Write-Host "HaseebDesktopSync registered: check GitHub every 2 minutes (automatic on successful build)."
    Write-Host "Run Get-ScheduledTaskInfo -TaskName HaseebDesktopSync to verify next run."
    return
}
& gh auth status
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated: gh auth login" }

& git -C $RepoPath fetch --no-tags origin main
if ($LASTEXITCODE -ne 0) { throw "Cannot fetch origin/main" }
$trustedSha = (& git -C $RepoPath rev-parse FETCH_HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $trustedSha -notmatch '^[a-f0-9]{40}$') { throw "Bad main commit SHA" }

# Use GitHub's workflow-run REST endpoint to find a successful artifact by SHA.
# Never use an unrelated PR run or an older release, even after a stale cache hit.
$endpoint = "repos/$RepoName/actions/workflows/build-windows.yml/runs?branch=main&head_sha=$trustedSha&per_page=100"
$json = & gh api --method GET -H "Accept: application/vnd.github+json" $endpoint
if ($LASTEXITCODE -ne 0) { throw "Cannot query GitHub Windows Build workflow runs. No deployment attempted." }
$response = ($json -join "`n") | ConvertFrom-Json
$runs = @($response.workflow_runs)
$run = $null
foreach ($item in $runs) {
    if ($item.head_sha -eq $trustedSha -and
        $item.head_branch -eq "main" -and
        $item.status -eq "completed" -and
        $item.conclusion -eq "success" -and
        $item.event -in @("push", "workflow_dispatch")) {
        $run = $item
        break
    }
}
if (-not $run) {
    # Read-only fallback when GitHub's combined branch and head_sha API filters
    # return empty unexpectedly. Never lower release-identity requirements.
    Write-Host "Exact-SHA query returned no completed successful build; checking recent main workflow runs."
    $fallbackEndpoint = "repos/$RepoName/actions/workflows/build-windows.yml/runs?branch=main&per_page=100"
    $fallbackJson = & gh api --method GET -H "Accept: application/vnd.github+json" $fallbackEndpoint
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot query GitHub Windows Build fallback workflow runs. No deployment attempted."
    }
    $fallbackResponse = ($fallbackJson -join [Environment]::NewLine) | ConvertFrom-Json
    $fallbackRuns = @($fallbackResponse.workflow_runs)
    foreach ($item in $fallbackRuns) {
        if ($item.head_sha -eq $trustedSha -and
            $item.head_branch -eq "main" -and
            $item.status -eq "completed" -and
            $item.conclusion -eq "success" -and
            $item.event -in @("push", "workflow_dispatch")) {
            $run = $item
            Write-Host "Fallback confirmed successful Windows CI for exact main SHA."
            break
        }
    }
}
if (-not $run) {
    throw "No successful Haseeb Windows Build CI run matched current main SHA $trustedSha (including recent-build fallback). No deployment attempted."
}
$runId = [string]$run.id
if ($runId -notmatch '^[0-9]+$') { throw "Invalid build run ID. No deployment attempted." }
Write-Host "Verified successful build: run $runId, SHA $trustedSha"

# Update the local script source only after successful CI for the exact main SHA.
& git -C $RepoPath merge --ff-only $trustedSha
if ($LASTEXITCODE -ne 0) { throw "Local checkout diverged; refusing to overwrite changes." }
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
$marker = Join-Path $InstallRoot "last-successful-run.txt"
if ((Test-Path $marker) -and ((Get-Content $marker -Raw).Trim() -eq $runId)) {
    Write-Host "Already deployed run $($runId). No download needed."
    return
}

# Confirm no app payload/recipe changed since the last installed app source SHA.
# Unknown or divergent changes always require the original guarded download.
$installedShaPath = Join-Path $InstallRoot "last-successful-sha.txt"
$planner = Join-Path $RepoPath "tools\release_planner.py"
if ((Test-Path -LiteralPath $installedShaPath -PathType Leaf) -and
    (Test-Path -LiteralPath $planner -PathType Leaf)) {
    $installedSha = (Get-Content -LiteralPath $installedShaPath -Raw).Trim()
    if ($installedSha -match '^[a-f0-9]{40}$') {
        & python $planner --repo $RepoPath --previous-sha $installedSha --current-sha $trustedSha
        $planResult = $LASTEXITCODE
        if ($planResult -eq 0) {
            Write-Host "[HASEEB] Source-only build $runId verified against exact main SHA."
            Write-Host "[HASEEB] No app/package changes. Skipping redundant artifact download."
            # This marker identifies only the verified source update, NOT installed apps.
            Set-Content -Path (Join-Path $InstallRoot "last-verified-source-run.txt") -Value $runId -Encoding ASCII
            return
        }
        if ($planResult -ne 10) {
            throw "Cannot validate release delta. Existing installed apps preserved."
        }
    }
}
# A unique attempt directory avoids GH CLI overwrite prompts when an earlier
# scheduled task was interrupted mid-download.
$download = Join-Path $env:LOCALAPPDATA ("Haseeb\downloads\run-" + $runId + "-" + [guid]::NewGuid().ToString("N"))
try {
    Write-Host "[HASEEB] Download phase: starting guarded release artifact fetch."
    & python (Join-Path $RepoPath "tools\download_artifact.py") --run-id $runId --dir $download --timeout-seconds 600
    if ($LASTEXITCODE -ne 0) { throw "Artifact download failed" }
    $archives = @(Get-ChildItem -LiteralPath $download -Filter "*.zip" -File)
    if ($archives.Count -eq 0) { throw "Downloaded build contained no application ZIPs." }
    Write-Host "[HASEEB] Download phase PASS. Starting checksum and bundled app smoke tests."
    # All app ZIPs must pass checksum + self-test before ANY active app is switched.
    # If a later app fails, previous installed app pointers stay unchanged.
    $archivePaths = @($archives | ForEach-Object { $_.FullName })
    Write-Host "Validating and activating $($archivePaths.Count) app packages as one bundle"
    & python (Join-Path $RepoPath "tools\haseeb.py") deploy-bundle --root $InstallRoot @archivePaths
    if ($LASTEXITCODE -ne 0) { throw "Bundle deployment failed; successful-run marker not advanced." }
    # Preserve the exact installed source SHA for trusted PC->GitHub reporting.
    Write-Host "[HASEEB] Bundle validation and installation PASS. Recording verified release."
    Set-Content -Path (Join-Path $InstallRoot "last-successful-sha.txt") -Value $trustedSha -Encoding ASCII
    Set-Content -Path $marker -Value ($runId) -Encoding ASCII
    Write-Host "Haseeb PC deployment complete for run $($runId)"
}
finally {
    # Delete only this job's downloaded build data. Installed releases are preserved.
    if (Test-Path $download) { Remove-Item -LiteralPath $download -Recurse -Force }
}
