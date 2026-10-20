#requires -Version 5.1
<#
.SYNOPSIS
  Haseeb unattended updater and private, durable PC->GitHub deployment feedback.
.DESCRIPTION
  A serialized task calls the guarded updater, then records allowlisted
  deployment outcomes. Raw logs remain PC-local; offline dispatch retries.
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
$reportRoot = Join-Path $env:LOCALAPPDATA "Haseeb\reports"
$reporter = Join-Path $RepoPath "tools\pc_reporter.py"
$lastReported = Join-Path $reportRoot "last-reported-run.txt"

function Invoke-Feedback {
    param([string[]]$Arguments)
    if (-not (Test-Path -LiteralPath $reporter -PathType Leaf)) { return $false }
    try {
        & python $reporter @Arguments
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "PC feedback unavailable; queued reports stay local for retry."
            return $false
        }
        return $true
    }
    catch {
        Write-Warning "PC feedback unavailable; updater continues."
        return $false
    }
}

function Read-Text {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return (Get-Content -LiteralPath $Path -Raw).Trim()
    }
    return ""
}

function Record-InstalledRelease {
    $marker = Join-Path $InstallRoot "last-successful-run.txt"
    $runId = Read-Text -Path $marker
    if ($runId -notmatch '^[0-9]{1,20}$') { return }
    if ((Read-Text -Path $lastReported) -eq $runId) { return }
    $sha = Read-Text -Path (Join-Path $InstallRoot "last-successful-sha.txt")
    if ($sha -notmatch '^[a-f0-9]{40}$') { $sha = "" }
    $ok = Invoke-Feedback -Arguments @("record", "--status", "success",
        "--stage", "complete", "--code", "INSTALLED", "--run-id", $runId, "--sha", $sha)
    if ($ok) {
        New-Item -ItemType Directory -Path $reportRoot -Force | Out-Null
        Set-Content -LiteralPath $lastReported -Value $runId -Encoding ASCII
    }
}

function Record-Failure {
    param([string]$Message)
    # Do NOT send exception content. Map it to a small public-safe code list.
    $stage = "unknown"
    $code = "UNKNOWN_FAILURE"
    switch -Regex ($Message) {
        'Missing canonical.*Sync-Haseeb' { $stage = "preflight"; $code = "MISSING_UPDATER"; break }
        'not available on PATH|Missing Haseeb clone' { $stage = "preflight"; $code = "MISSING_PREREQUISITE"; break }
        'not authenticated' { $stage = "auth"; $code = "AUTH_FAILED"; break }
        'Cannot fetch origin|Local checkout diverged|Bad main commit SHA' { $stage = "git"; $code = "SOURCE_SYNC_FAILED"; break }
        'No successful Haseeb Windows Build' { $stage = "ci"; $code = "CI_NOT_READY"; break }
        'Cannot query GitHub Windows Build' { $stage = "ci"; $code = "CI_QUERY_FAILED"; break }
        'Artifact download failed|contained no application ZIPs' { $stage = "artifact"; $code = "ARTIFACT_FAILED"; break }
        'Bundle deployment failed' { $stage = "install"; $code = "INSTALL_FAILED"; break }
        'nonzero exit code' { $stage = "unknown"; $code = "UPDATER_FAILED"; break }
    }
    $sha = ""
    if (Get-Command git -ErrorAction SilentlyContinue) {
        try {
            $candidate = (& git -C $RepoPath rev-parse refs/remotes/origin/main 2>$null)
            if ($candidate -match '^[a-f0-9]{40}$') { $sha = [string]$candidate }
        } catch {}
    }
    [void](Invoke-Feedback -Arguments @("record", "--status", "failure",
        "--stage", $stage, "--code", $code, "--sha", $sha))
}

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

    # Retry earlier offline telemetry first; it never blocks application updates.
    [void](Invoke-Feedback -Arguments @("flush"))
    $syncFile = Join-Path $RepoPath "ops\windows\Sync-Haseeb.ps1"
    if (-not (Test-Path -LiteralPath $syncFile -PathType Leaf)) {
        throw "Missing canonical Haseeb Sync-Haseeb.ps1 at $syncFile"
    }

    $global:LASTEXITCODE = 0
    & $syncFile -RepoPath $RepoPath -InstallRoot $InstallRoot
    if ($LASTEXITCODE -ne 0) { throw "Haseeb updater nonzero exit code" }

    # Also catches the first successful upgrade from the old runner version.
    Record-InstalledRelease
    Write-Host "[HASEEB] Scheduled sync finished successfully: $(Get-Date -Format o)"
}
catch {
    $exitCode = 1
    $reason = $_.Exception.Message
    Write-Warning ("[HASEEB] Scheduled sync FAILED: " + $reason)
    Record-Failure -Message $reason
}
finally {
    if ($locked -and -not $SelfTest) {
        [void](Invoke-Feedback -Arguments @("flush"))
    }
    if ($transcribing) {
        Stop-Transcript | Out-Null
        # Retain recent checks; no application files or report queue deleted.
        try {
            @(Get-ChildItem -LiteralPath $logRoot -Filter "sync-*.log" -File |
                Sort-Object LastWriteTimeUtc -Descending |
                Select-Object -Skip 720) | ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
            }
        }
        catch { Write-Warning ("Haseeb log rotation skipped: " + $_.Exception.Message) }
    }
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}

if ($exitCode -ne 0) { exit $exitCode }
