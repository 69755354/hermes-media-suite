[CmdletBinding()]
param(
  [string]$Program,
  [string]$DataDir,
  [string]$Name = '漫剧发布助手',
  [string]$LogFile
)

$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Program) { $Program = Split-Path -Parent $ScriptsDir }
if (-not $DataDir) { $DataDir = Join-Path $env:LOCALAPPDATA 'HuolongAgent\publish-worker' }
if (-not $LogFile) { $LogFile = Join-Path $DataDir 'logs\install.log' }

$panel        = Join-Path $Program 'scripts\panel.ps1'
$machine      = Join-Path $Program 'scripts\show-machine-code.ps1'
$importer     = Join-Path $Program 'scripts\import-license.ps1'
$importShim   = Join-Path $Program 'scripts\import-license-shortcut.cmd'
$icon         = Join-Path $Program 'assets\app.ico'
$powerShell   = 'powershell.exe'

$script:ShortcutErrors = New-Object System.Collections.ArrayList
$script:Created = 0

function Write-ShortcutLog([string]$Message) {
  $line = "{0} [shortcut] {1}" -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $Message
  Write-Host $line
  try {
    $logDir = Split-Path -Parent $LogFile
    if ($logDir -and -not (Test-Path -LiteralPath $logDir)) {
      New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 -ErrorAction Stop
  } catch {
    Write-Host "  (shortcut log write failed: $_)"
  }
}

function Add-ShortcutError([string]$Message) {
  [void]$script:ShortcutErrors.Add($Message)
  Write-ShortcutLog "ERROR: $Message"
}

function Test-ShortcutTarget([string]$Target) {
  if (-not $Target) { return $false }
  if (Test-Path -LiteralPath $Target) { return $true }
  if (-not [System.IO.Path]::IsPathRooted($Target)) {
    $cmd = Get-Command $Target -ErrorAction SilentlyContinue
    if ($cmd) { return $true }
  }
  return $false
}

if (Test-Path -LiteralPath $icon) {
  $iconLoc = $icon
} else {
  $iconLoc = "$env:SystemRoot\System32\shell32.dll,13"
  Write-ShortcutLog "icon MISSING: $icon  (fallback -> $iconLoc)"
}

if (-not (Get-Command $powerShell -ErrorAction SilentlyContinue)) {
  Add-ShortcutError "找不到 powershell.exe，无法创建快捷方式。"
}

$panelArgs   = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $panel + '"'
$machineArgs = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $machine + '"'

$specs = @(
  @{
    File = "$Name.lnk"
    Target = 'powershell.exe'
    Arguments = $panelArgs
    Required = @($panel)
    Desc = '漫剧发布助手'
  }
)

$desktop  = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')
# 1.2.45：桌面被安全软件/OneDrive 拦住时，公共桌面通常仍可写，且同样显示在用户桌面上
$commonDesktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
$folders = @($desktop, $commonDesktop, $programs) | Where-Object { $_ } | Select-Object -Unique

if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) {
  Add-ShortcutError "找不到桌面目录，无法创建快捷方式。"
}

$shell = $null
try { $shell = New-Object -ComObject WScript.Shell } catch { Add-ShortcutError "无法创建 WScript.Shell（COM 被限制）：$_" }

function Remove-LegacyVbsShortcuts([string]$Folder) {
  if (-not $Folder -or -not (Test-Path -LiteralPath $Folder)) { return }
  $items = @(Get-ChildItem -LiteralPath $Folder -Filter "$Name*.lnk" -File -ErrorAction SilentlyContinue)
  foreach ($item in $items) {
    $isNewName = $false
    foreach ($spec in $specs) {
      if ($item.Name -eq $spec.File) { $isNewName = $true; break }
    }
    if ($isNewName) { continue }  # Save() below overwrites the current entry.
    try {
      $old = $shell.CreateShortcut($item.FullName)
      $target = [string]$old.TargetPath
      $argText = [string]$old.Arguments
      $isVbsTarget = (
        ($target -match '(?i)(^|\\)wscript(\.exe)?$') -or
        ($target -match '(?i)\.vbs$') -or
        ($argText -match '(?i)\.vbs([" ]|$)')
      )
      # Match our four old VBS entry names regardless of the old install path,
      # so moving the unzipped folder does not leave 1.2.31 icons behind.
      $isOldProductEntry = (
        ($target -match '(?i)(launcher|panel|show-machine-code|import-license)\.vbs$') -or
        ($argText -match '(?i)(launcher|panel|show-machine-code|import-license)\.vbs')
      )
      $isOldPsEntry = ($item.Name -in @("$Name 控制面板.lnk", "$Name 查看机器码.lnk", "$Name 导入授权.lnk")) -and
        (($argText -match '(?i)(panel|show-machine-code)\.ps1') -or ($target -match '(?i)import-license-shortcut\.cmd$'))
      if (($isVbsTarget -and $isOldProductEntry) -or $isOldPsEntry) {
        Remove-Item -LiteralPath $item.FullName -Force -ErrorAction Stop
        Write-ShortcutLog "removed legacy VBS shortcut: $($item.FullName)"
      }
    } catch {
      Add-ShortcutError "无法清理旧快捷方式（$($item.FullName)）：$_"
    }
  }
}

foreach ($folder in $folders) {
  Remove-LegacyVbsShortcuts $folder
}

foreach ($spec in $specs) {
  foreach ($required in @($spec.Required)) {
    if (-not (Test-Path -LiteralPath $required)) {
      Add-ShortcutError "目标文件不存在：$required（快捷方式「$($spec.File)」未可靠创建）"
    }
  }

  foreach ($folder in $folders) {
    if (-not $shell) { break }
    $lnkPath = Join-Path $folder $spec.File
    try {
      $lnk = $shell.CreateShortcut($lnkPath)
      $lnk.TargetPath = $spec.Target
      $lnk.Arguments = $spec.Arguments
      $lnk.WorkingDirectory = $Program
      $lnk.IconLocation = $iconLoc
      $lnk.Description = $spec.Desc
      $lnk.Save()
      Write-ShortcutLog "shortcut: $lnkPath -> $($spec.Target)"
      $script:Created += 1

      # Re-read the .lnk from disk: creation is not success by itself.
      $check = $shell.CreateShortcut($lnkPath)
      $readTarget = [string]$check.TargetPath
      if (-not (Test-ShortcutTarget $readTarget)) {
        Add-ShortcutError "快捷方式目标不可用：$lnkPath -> '$readTarget'"
      }
      if ($spec.Arguments -and ([string]$check.Arguments).IndexOf($spec.Arguments, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        Add-ShortcutError "快捷方式参数未落盘：$lnkPath"
      }
    } catch {
      Add-ShortcutError "创建快捷方式失败（$lnkPath）：$_"
    }
  }
}

# 1.2.44 兜底：COM 或桌面写入被安全软件拦住时，退化成 .cmd 启动器（不依赖 COM）
if ($script:Created -lt $specs.Count) {
  $launcherLines = @('@echo off', ('start "" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $panel + '"'))
  foreach ($spec in $specs) {
    foreach ($folder in $folders) {
      if (-not $folder -or -not (Test-Path -LiteralPath $folder)) { continue }
      $cmdPath = Join-Path $folder ([System.IO.Path]::GetFileNameWithoutExtension($spec.File) + '.cmd')
      try {
        Set-Content -LiteralPath $cmdPath -Value $launcherLines -Encoding Default -ErrorAction Stop
        if (Test-Path -LiteralPath $cmdPath) {
          Write-ShortcutLog "fallback launcher: $cmdPath"
          $script:Created += 1
          break
        }
      } catch { Add-ShortcutError "创建兜底启动器失败（$cmdPath）：$_" }
    }
  }
}

if ($script:Created -lt 1) {
  Write-ShortcutLog "FAILED: no usable entry created ($($script:ShortcutErrors.Count) problem(s)); see install.log"
  exit 1
}

Write-ShortcutLog "created and verified $($script:Created) entry(ies); fallback used if any COM attempt failed"
exit 0
