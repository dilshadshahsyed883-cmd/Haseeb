#requires -Version 5.1
<#
.SYNOPSIS
  Set up Haseeb PC basics without storing credentials or enabling remote access.
.EXAMPLE
  powershell -NoProfile -File .\ops\windows\Bootstrap-Haseeb.ps1 -InstallTools
#>
[CmdletBinding()]
param([switch]$InstallTools)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/dilshadshahsyed883-cmd/Haseeb.git"
$HomePath = Join-Path $env:LOCALAPPDATA "Haseeb"
$RepoPath = Join-Path $HomePath "repo"
New-Item -ItemType Directory -Path $HomePath -Force | Out-Null

$dependencies = @(
    @{ Name = "Git"; Command = "git"; WingetId = "Git.Git" },
    @{ Name = "Python 3.11"; Command = "py"; WingetId = "Python.Python.3.11" },
    @{ Name = "GitHub CLI"; Command = "gh"; WingetId = "GitHub.cli" },
    @{ Name = "Tailscale"; Command = "tailscale"; WingetId = "Tailscale.Tailscale" },
    @{ Name = "rclone"; Command = "rclone"; WingetId = "Rclone.Rclone" }
)
foreach ($dependency in $dependencies) {
    $command = Get-Command $dependency.Command -ErrorAction SilentlyContinue
    if ($command) {
        Write-Host "[OK] $($dependency.Name)" -ForegroundColor Green
    } elseif ($InstallTools) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw "winget not available. Install App Installer from Microsoft, then rerun."
        }
        Write-Host "[INSTALL] $($dependency.Name)"
        & winget install --exact --id $dependency.WingetId --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not install $($dependency.Name); check winget output."
        }
    } else {
        Write-Warning "$($dependency.Name) is missing. Run with -InstallTools."
    }
}
if (Get-Command git -ErrorAction SilentlyContinue) {
    if (-not (Test-Path $RepoPath)) {
        & git clone --branch main --single-branch $RepoUrl $RepoPath
        if ($LASTEXITCODE -ne 0) { throw "Git clone failed. Authenticate via GitHub CLI for private repos." }
    } else {
        Write-Host "[OK] Existing repository kept at $RepoPath (not overwritten)"
    }
} else {
    Write-Warning "Git was not found in this terminal. Open a NEW PowerShell terminal and run Bootstrap again."
}
Write-Host ""
Write-Host "PC home: $HomePath"
Write-Host "Next manual sign-ins (never enter passwords in this script):"
Write-Host "  gh auth login            # GitHub access on this PC"
Write-Host "  tailscale up             # authorize Haseeb PC in your tailnet"
Write-Host "  rclone config            # Google Drive OAuth, only if Drive sync is needed"
Write-Host "Then use ops\windows\Sync-Haseeb.ps1 (see docs\PC_DEPLOYMENT.md)."
