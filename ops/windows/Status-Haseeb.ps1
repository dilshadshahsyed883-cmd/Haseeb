#requires -Version 5.1
<#
.SYNOPSIS
  Read-only Haseeb PC deployment status: task, releases, logs and last run.
.EXAMPLE
  .\Status-Haseeb.ps1
  .\Status-Haseeb.ps1 -Json
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Haseeb\installed"),
    [switch]$Json,
    [switch]$SkipTask,
    [switch]$SelfTest
)
$ErrorActionPreference = "Stop"

function Read-HaseebStatus {
    param([string]$Root, [bool]$ReadTask)

    $record = Join-Path $Root "last-successful-run.txt"
    $lastRun = $null
    if (Test-Path -LiteralPath $record -PathType Leaf) {
        $lastRun = (Get-Content -LiteralPath $record -Raw).Trim()
    }
    $sourceRecord = Join-Path $Root "last-verified-source-run.txt"
    $lastSourceRun = $null
    if (Test-Path -LiteralPath $sourceRecord -PathType Leaf) {
        $candidate = (Get-Content -LiteralPath $sourceRecord -Raw).Trim()
        if ($candidate -match '^[0-9]{1,20}
    $releasesDir = [IO.Path]::GetFullPath((Join-Path $rootFull "releases"))
    $apps = @()
    $pointerDir = Join-Path $rootFull "apps"
    if (Test-Path -LiteralPath $pointerDir -PathType Container) {
        foreach ($folder in @(Get-ChildItem -LiteralPath $pointerDir -Directory)) {
            $current = Join-Path $folder.FullName "current.json"
            if (-not (Test-Path -LiteralPath $current -PathType Leaf)) { continue }
            try {
                $active = Get-Content -LiteralPath $current -Raw | ConvertFrom-Json
                if ($active.app_id -ne $folder.Name -or $active.version -notmatch '^\d+\.\d+\.\d+$') {
                    throw "Invalid current release manifest"
                }
                $release = [IO.Path]::GetFullPath((Join-Path $rootFull $active.release))
                $allowed = [IO.Path]::GetFullPath((Join-Path $releasesDir $folder.Name)) +
                    [IO.Path]::DirectorySeparatorChar
                if (-not $release.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Release path outside allowed app folder"
                }
                $exists = Test-Path -LiteralPath (Join-Path $release "app.json") -PathType Leaf
                $apps += [pscustomobject]@{
                    app_id = $active.app_id
                    version = $active.version
                    release_present = [bool]$exists
                    state = $(if ($exists) { "installed" } else { "missing-release" })
                }
            }
            catch {
                $apps += [pscustomobject]@{
                    app_id = $folder.Name
                    version = $null
                    release_present = $false
                    state = "invalid-release-pointer"
                }
            }
        }
    }

    $scheduler = [ordered]@{
        found = $false
        state = "unknown"
        last_result = $null
        last_run = $null
        next_run = $null
    }
    if ($ReadTask) {
        try {
            $task = Get-ScheduledTask -TaskName "HaseebDesktopSync" -ErrorAction SilentlyContinue
            if ($null -ne $task) {
                $info = Get-ScheduledTaskInfo -TaskName "HaseebDesktopSync" -ErrorAction Stop
                $scheduler.found = $true
                $scheduler.state = [string]$task.State
                $scheduler.last_result = $info.LastTaskResult
                $scheduler.last_run = $info.LastRunTime.ToString("o")
                $scheduler.next_run = $info.NextRunTime.ToString("o")
            }
        }
        catch {
            $scheduler.state = "unavailable"
        }
    }

    $logs = Join-Path $env:LOCALAPPDATA "Haseeb\logs"
    $latest = $null
    if (Test-Path -LiteralPath $logs -PathType Container) {
        $recent = Get-ChildItem -LiteralPath $logs -Filter "sync-*.log" -File |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($recent) { $latest = $recent.FullName }
    }

    return [pscustomobject]@{
        status = "Haseeb PC deployment status"
        installed_root = $rootFull
        last_successful_run = $lastRun
        last_verified_source_run = $lastSourceRun
        scheduled_task = [pscustomobject]$scheduler
        installed_apps = @($apps | Sort-Object app_id)
        latest_log_path = $latest
    }
}

if ($SelfTest) {
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("haseeb-health-" + [guid]::NewGuid().ToString("N"))
    try {
        $dir = Join-Path $temp "apps\example-app"
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $release = Join-Path $temp "releases\example-app\1.2.3-demo"
        New-Item -ItemType Directory -Path $release -Force | Out-Null
        '{"id":"example-app"}' | Set-Content -LiteralPath (Join-Path $release "app.json") -Encoding UTF8
        '{"app_id":"example-app","version":"1.2.3","release":"releases/example-app/1.2.3-demo"}' |
            Set-Content -LiteralPath (Join-Path $dir "current.json") -Encoding UTF8
        "123456" | Set-Content -LiteralPath (Join-Path $temp "last-successful-run.txt") -Encoding ASCII
        "123457" | Set-Content -LiteralPath (Join-Path $temp "last-verified-source-run.txt") -Encoding ASCII
        $health = Read-HaseebStatus -Root $temp -ReadTask $false
        if ($health.last_successful_run -ne "123456" -or
            $health.last_verified_source_run -ne "123457" -or
            $health.installed_apps.Count -ne 1 -or
            $health.installed_apps[0].state -ne "installed" -or
            $health.installed_apps[0].version -ne "1.2.3") {
            throw "Status reader self-test failed"
        }
        Write-Host "Haseeb deployment status SELF-TEST PASS"
    }
    finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
    }
    return
}

$report = Read-HaseebStatus -Root $InstallRoot -ReadTask (-not $SkipTask)
if ($Json) {
    $report | ConvertTo-Json -Depth 6
}
else {
    Write-Host "HASEEB / DEPLOYMENT SYSTEM" -ForegroundColor Cyan
    Write-Host "Last installed app bundle run: $($report.last_successful_run)"
    Write-Host "Last verified source-only run: $($report.last_verified_source_run)"
    Write-Host "Scheduled auto-deploy task: $($report.scheduled_task.state)"
    Write-Host "Last scheduler result: $($report.scheduled_task.last_result)"
    Write-Host "Next scheduled run: $($report.scheduled_task.next_run)"
    foreach ($app in @($report.installed_apps)) {
        Write-Host ("App: {0} | v{1} | {2}" -f $app.app_id, $app.version, $app.state)
    }
    Write-Host "Latest sync log: $($report.latest_log_path)"
}
) { $lastSourceRun = $candidate }
    }
    $rootFull = [IO.Path]::GetFullPath($Root)
    $releasesDir = [IO.Path]::GetFullPath((Join-Path $rootFull "releases"))
    $apps = @()
    $pointerDir = Join-Path $rootFull "apps"
    if (Test-Path -LiteralPath $pointerDir -PathType Container) {
        foreach ($folder in @(Get-ChildItem -LiteralPath $pointerDir -Directory)) {
            $current = Join-Path $folder.FullName "current.json"
            if (-not (Test-Path -LiteralPath $current -PathType Leaf)) { continue }
            try {
                $active = Get-Content -LiteralPath $current -Raw | ConvertFrom-Json
                if ($active.app_id -ne $folder.Name -or $active.version -notmatch '^\d+\.\d+\.\d+$') {
                    throw "Invalid current release manifest"
                }
                $release = [IO.Path]::GetFullPath((Join-Path $rootFull $active.release))
                $allowed = [IO.Path]::GetFullPath((Join-Path $releasesDir $folder.Name)) +
                    [IO.Path]::DirectorySeparatorChar
                if (-not $release.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Release path outside allowed app folder"
                }
                $exists = Test-Path -LiteralPath (Join-Path $release "app.json") -PathType Leaf
                $apps += [pscustomobject]@{
                    app_id = $active.app_id
                    version = $active.version
                    release_present = [bool]$exists
                    state = $(if ($exists) { "installed" } else { "missing-release" })
                }
            }
            catch {
                $apps += [pscustomobject]@{
                    app_id = $folder.Name
                    version = $null
                    release_present = $false
                    state = "invalid-release-pointer"
                }
            }
        }
    }

    $scheduler = [ordered]@{
        found = $false
        state = "unknown"
        last_result = $null
        last_run = $null
        next_run = $null
    }
    if ($ReadTask) {
        try {
            $task = Get-ScheduledTask -TaskName "HaseebDesktopSync" -ErrorAction SilentlyContinue
            if ($null -ne $task) {
                $info = Get-ScheduledTaskInfo -TaskName "HaseebDesktopSync" -ErrorAction Stop
                $scheduler.found = $true
                $scheduler.state = [string]$task.State
                $scheduler.last_result = $info.LastTaskResult
                $scheduler.last_run = $info.LastRunTime.ToString("o")
                $scheduler.next_run = $info.NextRunTime.ToString("o")
            }
        }
        catch {
            $scheduler.state = "unavailable"
        }
    }

    $logs = Join-Path $env:LOCALAPPDATA "Haseeb\logs"
    $latest = $null
    if (Test-Path -LiteralPath $logs -PathType Container) {
        $recent = Get-ChildItem -LiteralPath $logs -Filter "sync-*.log" -File |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($recent) { $latest = $recent.FullName }
    }

    return [pscustomobject]@{
        status = "Haseeb PC deployment status"
        installed_root = $rootFull
        last_successful_run = $lastRun
        scheduled_task = [pscustomobject]$scheduler
        installed_apps = @($apps | Sort-Object app_id)
        latest_log_path = $latest
    }
}

if ($SelfTest) {
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("haseeb-health-" + [guid]::NewGuid().ToString("N"))
    try {
        $dir = Join-Path $temp "apps\example-app"
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $release = Join-Path $temp "releases\example-app\1.2.3-demo"
        New-Item -ItemType Directory -Path $release -Force | Out-Null
        '{"id":"example-app"}' | Set-Content -LiteralPath (Join-Path $release "app.json") -Encoding UTF8
        '{"app_id":"example-app","version":"1.2.3","release":"releases/example-app/1.2.3-demo"}' |
            Set-Content -LiteralPath (Join-Path $dir "current.json") -Encoding UTF8
        "123456" | Set-Content -LiteralPath (Join-Path $temp "last-successful-run.txt") -Encoding ASCII
        $health = Read-HaseebStatus -Root $temp -ReadTask $false
        if ($health.last_successful_run -ne "123456" -or
            $health.installed_apps.Count -ne 1 -or
            $health.installed_apps[0].state -ne "installed" -or
            $health.installed_apps[0].version -ne "1.2.3") {
            throw "Status reader self-test failed"
        }
        Write-Host "Haseeb deployment status SELF-TEST PASS"
    }
    finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
    }
    return
}

$report = Read-HaseebStatus -Root $InstallRoot -ReadTask (-not $SkipTask)
if ($Json) {
    $report | ConvertTo-Json -Depth 6
}
else {
    Write-Host "HASEEB / DEPLOYMENT SYSTEM" -ForegroundColor Cyan
    Write-Host "Last installed GitHub run: $($report.last_successful_run)"
    Write-Host "Hourly scheduled task: $($report.scheduled_task.state)"
    Write-Host "Last scheduler result: $($report.scheduled_task.last_result)"
    Write-Host "Next scheduled run: $($report.scheduled_task.next_run)"
    foreach ($app in @($report.installed_apps)) {
        Write-Host ("App: {0} | v{1} | {2}" -f $app.app_id, $app.version, $app.state)
    }
    Write-Host "Latest sync log: $($report.latest_log_path)"
}
