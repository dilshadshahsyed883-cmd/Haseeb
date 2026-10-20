#requires -Version 5.1
<#
.SYNOPSIS
  Open an installed Haseeb desktop app by id, using its active release pointer.
.EXAMPLE
  .\ops\windows\Launch-Haseeb.ps1 -AppId haseeb-control
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$AppId,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Haseeb\installed")
)
$ErrorActionPreference = "Stop"
if ($AppId -notmatch '^[a-z][a-z0-9-]{1,39}$') { throw "Invalid app id" }
$root = [IO.Path]::GetFullPath($InstallRoot)
$pointer = Join-Path $root ("apps\" + $AppId + "\current.json")
if (-not (Test-Path $pointer)) { throw "App not deployed yet: $AppId" }
$active = Get-Content $pointer -Raw | ConvertFrom-Json
$release = [IO.Path]::GetFullPath((Join-Path $root $active.release))
$allowed = [IO.Path]::GetFullPath((Join-Path $root ("releases\" + $AppId))) + [IO.Path]::DirectorySeparatorChar
if (-not $release.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Invalid active release path."
}
$manifestPath = Join-Path $release "app.json"
if (-not (Test-Path $manifestPath)) { throw "Installed app manifest missing" }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
if ($manifest.id -ne $AppId -or $manifest.entry_point -notmatch '^[a-zA-Z0-9_\-/]+\.py$') {
    throw "Unsafe or mismatched app manifest"
}
$entry = [IO.Path]::GetFullPath((Join-Path $release $manifest.entry_point))
if (-not $entry.StartsWith(($release + [IO.Path]::DirectorySeparatorChar), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Entry point outside release"
}
if (-not (Test-Path $entry)) { throw "App entry point missing" }
& python $entry
if ($LASTEXITCODE -ne 0) { throw "App exited with code $LASTEXITCODE" }
