#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$AppId,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Haseeb\installed"),
    [string]$RepoPath = (Join-Path $env:LOCALAPPDATA "Haseeb\repo")
)
$ErrorActionPreference = "Stop"
& python (Join-Path $RepoPath "tools\haseeb.py") rollback $AppId --root $InstallRoot
if ($LASTEXITCODE -ne 0) { throw "Rollback failed" }
Write-Host "Active version rolled back. Use Launch-Haseeb.ps1 to start the app."
