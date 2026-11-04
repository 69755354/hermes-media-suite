<#
  uninstall.ps1 -- remove autostart + shortcuts, restore power settings.
  Data (login state / ledger / reports) is KEPT unless -PurgeData is given.
#>
[CmdletBinding()]
param([string]$Program, [string]$DataDir, [switch]$PurgeData)

$ErrorActionPreference = 'Continue'
$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Program) { $Program = Split-Path -Parent $ScriptsDir }
if (-not $DataDir) { $DataDir = Join-Path $env:LOCALAPPDATA 'HuolongAgent\publish-worker' }

# 1.2.49：先结束占用本目录的进程，否则文件夹删不掉（“文件夹正在使用”）
try {
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains($Program) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Milliseconds 600
} catch {}
& (Join-Path $ScriptsDir 'install-autostart.ps1') -Program $Program -Remove | Out-Null
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
  # removes the master + control-panel + one-per-environment icons (1.1.0)
  Remove-Item (Join-Path $dir '漫剧发布助手*.lnk') -ErrorAction SilentlyContinue
}

# Restore power settings we changed, if bootstrap recorded the originals.
$pstate = Join-Path $DataDir 'run\powercfg-original.json'
if (Test-Path $pstate) {
  # encoding-safe read: strip a UTF-8 BOM if the writer left one
  $orig = ([System.IO.File]::ReadAllText($pstate) -replace '^\uFEFF', '') | ConvertFrom-Json
  if ($orig.standby_timeout_ac) { powercfg /change standby-timeout-ac $orig.standby_timeout_ac }
  if ($orig.monitor_timeout_ac) { powercfg /change monitor-timeout-ac $orig.monitor_timeout_ac }
  if ($orig.disk_timeout_ac)    { powercfg /change disk-timeout-ac    $orig.disk_timeout_ac }
  Write-Host "power settings restored"
}

if ($PurgeData) {
  Write-Host "PURGING data area: $DataDir"
  Remove-Item -Recurse -Force $DataDir -ErrorAction SilentlyContinue
} else {
  Write-Host "data kept at $DataDir (login state, ledger, reports)"
}
Write-Host "uninstall done"
