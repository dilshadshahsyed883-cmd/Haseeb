#requires -Version 5.1
<#
.SYNOPSIS
  Haseeb unattended updater runner: serialized execution, durable diagnostic logs.
.DESCRIPTION
  Invoked by HaseebDesktopSync scheduled task. Never exposes credentials or
  opens remote management ports. The existing guarded Sync-Haseeb.ps1 remains
  the only code allowed to update releases.
#>
[CmdletBinding()]
param(
    [string]$RepoPath = (Join-Path $env:LOCALAPPDATA "Haseeb\repo"),
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Haseeb\installed"),
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$mutex = New-Object -TypeName System.Threading.Mutex -ArgumentList @($false, "Local\HaseebDesktopSync")
$locked = $false
$transcribing = $false
$exitCode = 0
$logRoot = Join-Path $env:LOCALAPPDATA "Haseeb\logs"

try {
    $locked = $mutex.WaitOne(0)
    if (-not $locked) {
        Write-Host "Haseeb sync already running. No overlapping deployment attempted."
        return
    }
    if ($SelfTest) {
        if (-not $locked) { throw "Updater lock not acquired" }
        Write-Host "Haseeb updater runner SELF-TEST PASS (single-instance lock)"
        return
    }

    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $logFile = Join-Path $logRoot ("sync-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + $PID + ".log")
    Start-Transcript -Path $logFile -ErrorAction Stop | Out-Null
    $transcribing = $true

    Write-Host "[HASEEB] Scheduled sync started: $(Get-Date -Format o)"
    Write-Host "[HASEEB] Diagnostics: $logFile"
    $syncFile = Join-Path $RepoPath "ops\windows\Sync-Haseeb.ps1"
    if (-not (Test-Path -LiteralPath $syncFile -PathType Leaf)) {
        throw "Missing canonical Haseeb Sync-Haseeb.ps1 at $syncFile"
    }
    & $syncFile -RepoPath $RepoPath -InstallRoot $InstallRoot
    Write-Host "[HASEEB] Scheduled sync finished successfully: $(Get-Date -Format o)"
}
catch {
    $exitCode = 1
    Write-Warning ("[HASEEB] Scheduled sync FAILED: " + $_.Exception.Message)
}
finally {
    if ($transcribing) {
        Stop-Transcript | Out-Null
        # Retain up to the latest 60 runs, never delete app files.
        try {
            @(Get-ChildItem -LiteralPath $logRoot -Filter "sync-*.log" -File |
                Sort-Object LastWriteTimeUtc -Descending |
                Select-Object -Skip 60) | ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
            }
        }
        catch {
            Write-Warning ("Haseeb log rotation skipped: " + $_.Exception.Message)
        }
    }
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}

if ($exitCode -ne 0) { exit $exitCode }
