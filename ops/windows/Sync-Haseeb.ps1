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
    $task = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
    & schtasks.exe /Create /F /SC HOURLY /TN "HaseebDesktopSync" /TR $task
    if ($LASTEXITCODE -ne 0) { throw "Scheduled task creation failed." }
    Write-Host "HaseebDesktopSync registered hourly. Start it manually once to verify."
    return
}
& gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated: gh auth login" }

& git -C $RepoPath fetch --no-tags origin main
if ($LASTEXITCODE -ne 0) { throw "Cannot fetch origin/main" }
$trustedSha = (& git -C $RepoPath rev-parse FETCH_HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $trustedSha -notmatch '^[a-f0-9]{40}$') { throw "Bad main commit SHA" }

$json = & gh run list --repo $RepoName --workflow build-windows.yml --branch main --status success --json databaseId,headSha,event --limit 20
if ($LASTEXITCODE -ne 0) { throw "Cannot read workflow runs" }
$runs = @($json | ConvertFrom-Json)
$run = $null
foreach ($item in $runs) {
    if ($item.headSha -eq $trustedSha -and $item.event -in @("push", "workflow_dispatch")) {
        $run = $item
        break
    }
}
if (-not $run) {
    throw "No successful main-branch CI build for current SHA $trustedSha. No deployment attempted."
}
Write-Host "Verified successful build: run $($run.databaseId), SHA $trustedSha"

# Update the local script source only after successful CI for the exact main SHA.
& git -C $RepoPath merge --ff-only $trustedSha
if ($LASTEXITCODE -ne 0) { throw "Local checkout diverged; refusing to overwrite changes." }
$download = Join-Path $env:LOCALAPPDATA ("Haseeb\downloads\run-" + $run.databaseId)
New-Item -ItemType Directory -Path $download -Force | Out-Null
& gh run download $run.databaseId --repo $RepoName --name haseeb-windows-bundle --dir $download
if ($LASTEXITCODE -ne 0) { throw "Artifact download failed" }
$archives = @(Get-ChildItem -Path $download -Filter "*.zip" -File)
if ($archives.Count -eq 0) { throw "Downloaded build contained no application ZIPs." }
foreach ($archive in $archives) {
    Write-Host "Deploying $($archive.Name)"
    & python (Join-Path $RepoPath "tools\haseeb.py") deploy $archive.FullName --root $InstallRoot
    if ($LASTEXITCODE -ne 0) { throw "Deployment stopped; existing app pointer unchanged." }
}
Write-Host "Haseeb PC deployment complete for run $($run.databaseId)"
