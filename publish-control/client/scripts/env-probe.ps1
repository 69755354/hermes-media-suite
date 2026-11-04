<#
  env-probe.ps1 -- W1 environment probe.  Read-only; writes env-probe.json.
  Answers the five unknowns the plan needs before it can choose a route:
  Windows edition, admin rights, Defender/firewall, sleep modes, battery/desktop.
#>
[CmdletBinding()]
param([string]$OutDir)

$ErrorActionPreference = 'Continue'
if (-not $OutDir) { $OutDir = Join-Path $env:LOCALAPPDATA 'HuolongAgent\publish-worker\evidence' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Try-Command($script) {
  try { return (& $script 2>&1 | Out-String).Trim() } catch { return "ERROR: $_" }
}

$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$isAdmin = ([Security.Principal.WindowsPrincipal] `
  [Security.Principal.WindowsIdentity]::GetCurrent()
  ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

$report = [ordered]@{
  generated_at        = (Get-Date -Format o)
  windows_caption     = $os.Caption
  windows_version     = $os.Version
  windows_build       = $os.BuildNumber
  os_architecture     = $os.OSArchitecture
  is_admin            = $isAdmin
  is_laptop           = ($cs.PCSystemType -eq 2)
  has_battery         = ((Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue) -ne $null)
  powercfg_available  = Try-Command { powercfg /a }
  defender_status     = Try-Command { Get-MpComputerStatus | Select-Object -Property AMServiceEnabled,RealTimeProtectionEnabled,AntivirusEnabled | Format-List }
  installed_av        = Try-Command { Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | Select-Object displayName,productState | Format-Table }
  screens             = (Get-CimInstance Win32_VideoController | Measure-Object).Count
  username_has_nonascii = [bool]($env:USERNAME -match '[^\x00-\x7F]')
  userprofile_path    = $env:USERPROFILE
  onedrive_redirect   = [bool]$env:OneDrive
}

$json = $report | ConvertTo-Json -Depth 4
$path = Join-Path $OutDir 'env-probe.json'
$json | Set-Content -Path $path -Encoding UTF8
Write-Host $json
Write-Host "`nwritten: $path"
