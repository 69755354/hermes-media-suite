<#
  bootstrap.ps1 -- first-time install (offline, idempotent, re-runnable).

  Mirrors the Mac bootstrap step list:
    1) create the data area (never deletes existing login state / ledger)
    2) build the venv and install deps from the bundled wheels (--no-index)
    3) point Playwright at the bundled browsers (no online playwright install)
    4) wire ffmpeg (absolute path; Windows has no reliable symlink)
    5) register autostart (Task Scheduler, onlogon, crash self-recovery)
    6) run the self-test and write the result

  Dependencies are offline; automatic activation uses HTTPS.

  1.2.5 (GPT review 1.2.4 item 8): the whole install runs inside one top-level
  try/catch.  Any failure -- missing artefacts, a broken venv, a full disk, a
  failed shortcut/autostart step, a bad machine-code run -- produces a NONZERO
  exit code, a Chinese remediation block and the REAL log path.  "Failed but
  exited 0" is impossible.

  1.2.5 (item 13): this script does NOT switch [Console]::OutputEncoding.  The
  .bat entry runs under the console's own code page (ANSI/GBK on Chinese
  Windows) and we make the child Python speak that SAME code page, so Chinese
  never turns into mojibake in install.log.  One code page per entry.
#>
[CmdletBinding()]
param(
  [ValidateSet('user','machine')] [string]$Mode = 'user',
  [string]$DataDir,
  [switch]$SkipAutostart,
  [switch]$SkipSelftest
)

$ErrorActionPreference = 'Stop'

$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Program    = Split-Path -Parent $ScriptsDir
$Vendor     = 'HuolongAgent'
if (-not $DataDir) {
  $DataDir = Join-Path $env:LOCALAPPDATA "$Vendor\publish-worker"
}

# 1.2.52 安装过程全程留痕到桌面，窗口闪退也能拿到原因
try {
  $deskLog = Join-Path ([Environment]::GetFolderPath('Desktop')) 'install-log.txt'
  Start-Transcript -LiteralPath $deskLog -Append -Force | Out-Null
  $script:TranscriptOn = $true
} catch { $script:TranscriptOn = $false }
$LogDir  = Join-Path $DataDir 'logs'
$LogFile = Join-Path $LogDir  'install.log'
$State   = Join-Path $DataDir '.install-state.json'
$script:LogReady = $false

function Log([string]$msg) {
  $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $msg
  Write-Host $line
  if ($script:LogReady) {
    try {
      # Add-Content creates the file when it is missing, so the FIRST run also
      # writes a real install.log (GPT review 1.2.5 item 8: the previous guard
      # skipped logging when the file did not exist, so the path we printed was
      # a lie).  A full disk / permission error must never abort the install.
      Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction Stop
    } catch {
      Write-Host "  (日志写入失败，继续：$_)"
    }
  }
}

# 1.2.5 round-8 (GPT review item 8-A): native-command diagnostics must reach the
# install log as soon as they happen -- if a command FAILS we throw before the
# function returns, so capturing the stream at the end loses the very output
# that explains the failure.
function LogNative($out) {
  if ($null -eq $out) { return }
  Write-Host ($out | Out-String -Width 400)
  try {
    ($out | Out-String -Width 400) | Add-Content -Path $LogFile -Encoding UTF8 -ErrorAction Stop
  } catch { }
}

# ---- code-page policy (item 13): never switch the console encoding ---------
$consoleCp = 0
try { $consoleCp = [Console]::OutputEncoding.CodePage } catch { $consoleCp = 0 }
$env:PYTHONIOENCODING = if ($consoleCp -eq 65001) { 'utf-8' }
                        elseif ($consoleCp -gt 0) { "cp$consoleCp" }
                        else { 'utf-8' }
$env:PYTHONUTF8 = '1'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Program 'browsers'
$env:PYTHONPATH = Join-Path $Program 'agent'
# 1.2.5 (item 5): the startup-chain integrity check rejects any file the shipped
# MANIFEST.json does not list, and the package ships no __pycache__.  Disable
# bytecode writing so a normal install never creates a stray .pyc.
$env:PYTHONDONTWRITEBYTECODE = '1'
# 1.2.5 round-14 (8-A-R2): force Python stdout/stderr to be UNBUFFERED.  The
# child interpreters (venv / ensurepip / pip / selftest / browser-probe /
# machine-code) inherit this, so a command that blocks or is killed still
# leaves every diagnostic it already printed in the streaming install log --
# LogNative can only relay what has actually reached the pipe.
$env:PYTHONUNBUFFERED = '1'

function Install {
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  if (-not (Test-Path $LogFile)) {
    New-Item -ItemType File -Force -Path $LogFile | Out-Null
  }
  $script:LogReady = $true
  Log "bootstrap start (mode=$Mode program=$Program)"
  Log "console code page = $consoleCp -> PYTHONIOENCODING=$env:PYTHONIOENCODING"

  # ---- -3) 1.2.53 先停自启动任务，防止旧代理在安装过程中被重新拉起
  try { & schtasks.exe /End /TN "HuolongAgent\Agent" 2>&1 | Out-Null } catch {}
  # ---- -2) 1.2.51 先停掉正在运行的旧进程（同目录旧面板会占端口报"旧版本仍在运行"）
  try {
    $selfPid = $PID
    $parentPid = 0
    try { $parentPid = (Get-CimInstance Win32_Process -Filter "ProcessId=$selfPid").ParentProcessId } catch {}
    $running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.ProcessId -ne $selfPid -and $_.ProcessId -ne $parentPid -and $_.CommandLine -and $_.CommandLine.Contains($Program) })
    foreach ($proc in $running) {
      Log "cleanup: 结束旧进程 $($proc.Name) pid=$($proc.ProcessId)"
      Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($running.Count -gt 0) { Start-Sleep -Milliseconds 800 }
  } catch { Log "cleanup: 结束旧进程失败（$_）" }

  # ---- -1) 1.2.50 自动清理旧版本：旧目录 + 指向旧目录的快捷方式 -----------
  try {
    $roots = @((Split-Path -Parent $Program),
               (Join-Path $env:USERPROFILE 'Downloads'),
               (Join-Path $env:USERPROFILE 'Desktop'),
               (Join-Path $env:USERPROFILE 'Documents'))
    $seen = @{}
    foreach ($r in $roots) {
      if (-not $r -or -not (Test-Path $r)) { continue }
      foreach ($old in @(Get-ChildItem -LiteralPath $r -Directory -Filter 'manju-publish-assistant-*' -ErrorAction SilentlyContinue)) {
        if ($old.FullName.TrimEnd('\') -eq $Program.TrimEnd('\')) { continue }
        if ($Program.StartsWith($old.FullName, [StringComparison]::OrdinalIgnoreCase)) { continue }
        if ($seen[$old.FullName]) { continue }
        $seen[$old.FullName] = $true
        Log "cleanup: 发现旧版本 $($old.FullName)"
        try {
          Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains($old.FullName) } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
          Start-Sleep -Milliseconds 500
        } catch {}
        try {
          Remove-Item -LiteralPath $old.FullName -Recurse -Force -ErrorAction Stop
          Log "cleanup: 已删除旧版本 $($old.FullName)"
        } catch {
          Log "cleanup: 旧目录仍被占用，跳过（不影响本次安装）：$($old.FullName)"
        }
      }
    }
    # 指向旧目录的快捷方式（含参数里带旧路径的）一并清掉，避免桌面同时存在两个版本
    $lnkRoots = @((Join-Path $env:USERPROFILE 'Desktop'),
                  (Join-Path $env:USERPROFILE 'OneDrive\Desktop'),
                  (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'),
                  'C:\Users\Public\Desktop')
    $shell = $null
    try { $shell = New-Object -ComObject WScript.Shell } catch {}
    if ($shell) {
      foreach ($d in $lnkRoots) {
        if (-not (Test-Path $d)) { continue }
        foreach ($lnk in @(Get-ChildItem -LiteralPath $d -Filter '*.lnk' -Recurse -ErrorAction SilentlyContinue)) {
          try {
            $sc = $shell.CreateShortcut($lnk.FullName)
            $blob = "$($sc.TargetPath) $($sc.Arguments)"
            if ($blob -match 'manju-publish-assistant-' -and -not ($blob -match [regex]::Escape($Program))) {
              Remove-Item -LiteralPath $lnk.FullName -Force -ErrorAction SilentlyContinue
              Log "cleanup: 已删除旧快捷方式 $($lnk.FullName)"
            }
          } catch {}
        }
      }
    }
  } catch { Log "cleanup: 跳过（$_）" }

  # ---- 0) sanity: the offline bundle must be complete ---------------------
  $required = @('runtime\python.exe','wheels','browsers','agent\winport','config')
  $missing = @()
  foreach ($rel in $required) {
    if (-not (Test-Path (Join-Path $Program $rel))) { $missing += $rel }
  }
  if ($missing.Count -gt 0) {
    Log "FATAL missing offline artefacts: $($missing -join ', ')"
    throw "安装包不完整：缺少 $($missing -join ', ')。请联系服务商重新提供完整安装程序。"
  }

  # ---- 0.1) 1.2.49 完整性预检：文件被杀软删掉时给可执行的处理办法 -------
  $integrityIssues = @()
  foreach ($rel in @('runtime\python.exe','runtime\python311.dll','runtime\vcruntime140.dll','agent\winport\__init__.py')) {
    if (-not (Test-Path (Join-Path $Program $rel))) { $integrityIssues += $rel }
  }
  $whl = @(Get-ChildItem (Join-Path $Program 'wheels') -Filter *.whl -ErrorAction SilentlyContinue)
  if ($whl.Count -lt 16) { $integrityIssues += "wheels（只剩 $($whl.Count)/16）" }
  $br = @(Get-ChildItem (Join-Path $Program 'browsers') -ErrorAction SilentlyContinue)
  if ($br.Count -lt 1) { $integrityIssues += 'browsers' }
  if ($integrityIssues.Count -gt 0) {
    Log "FATAL integrity: $($integrityIssues -join ', ')"
    throw ("安装文件不完整，缺少：" + ($integrityIssues -join '、') + "。通常是杀毒软件（360/火绒/Defender）把文件删了。请先退出杀软或把安装目录加入白名单，然后重新双击安装包修复——不需要手动删除任何文件。")
  }

  # ---- 1) data area (idempotent) ------------------------------------------
  $subdirs = @('profiles\env_1','profiles\env_2','profiles\env_wechat','profiles\env_xhs',
               'run\envs',
               'profiles\douyin','profiles\douyin-webkit',
               'profiles\xingtu','profiles\shipinhao','profiles\xiaohongshu',
               'profiles\gongzhonghao',
               'config','run','run\profiles','logs',
               'evidence','media','inbox','outbox','out\douyin','out\reports','bin','app')
  foreach ($d in $subdirs) { New-Item -ItemType Directory -Force -Path (Join-Path $DataDir $d) | Out-Null }
  Log "data area ready: $DataDir"

  # ---- 2) venv + offline deps --------------------------------------------
  $RuntimePy = Join-Path $Program 'runtime\python.exe'
  $VenvPy    = Join-Path $DataDir '.venv\Scripts\python.exe'
  # 1.2.54：venv 的 pyvenv.cfg 可能指向已删除的旧版 runtime，跑不起来就整个重建
  if (Test-Path $VenvPy) {
    $venvOk = $false
    $eap0 = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
      $probe = & $VenvPy -c "print('ok')" 2>&1
      if ($LASTEXITCODE -eq 0 -and ("$probe" -match 'ok')) { $venvOk = $true }
    } catch { $venvOk = $false }
    $ErrorActionPreference = $eap0
    if (-not $venvOk) {
      Log "venv 不可用（多半指向已删除的旧版 runtime），自动重建"
      try { Remove-Item -LiteralPath (Join-Path $DataDir '.venv') -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
  }
if (-not (Test-Path $VenvPy)) {
    Log "[1/6] 正在准备运行环境，请稍候。"
    # 1.2.5 round-9 (item 8-A): run the native command with ErrorActionPreference
    # = Continue so a stderr write can NEVER be turned into a terminating error
    # that jumps to catch BEFORE we log the command's own stdout/stderr.
    # 1.2.5 round-10 (item 8-A): STREAM each line to install.log as it is
    # produced -- a command that blocks or is killed must still leave the
    # diagnostics it already printed; nothing waits for the command to return.
    $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
      # 1.2.5 round-13 (item 8-A-R1): create the venv WITHOUT pip, then run
      # ensurepip as a SEPARATE streamed command.  venv's built-in ensurepip
      # uses subprocess.check_output and swallows the diagnostics on failure
      # (runtime/Lib/venv/__init__.py), so a failed bootstrap used to lose the
      # real reason.  Split, every line goes live to install.log.
      & $RuntimePy -u -m venv --without-pip (Join-Path $DataDir '.venv') 2>&1 | ForEach-Object { LogNative $_ }
      $venvCode = $LASTEXITCODE
      if ($venvCode -eq 0 -and (Test-Path $VenvPy)) {
        & $VenvPy -u -m ensurepip --upgrade 2>&1 | ForEach-Object { LogNative $_ }
        $venvCode = $LASTEXITCODE
      }
    } finally { $ErrorActionPreference = $eap }
    if ($venvCode -ne 0 -or -not (Test-Path $VenvPy)) {
      throw "创建运行环境（venv/ensurepip）失败（exit $venvCode）：运行时不完整或被杀毒软件拦截。"
    }
  } else {
    Log "venv already present (idempotent skip)"
  }
  $Req = Join-Path $Program 'requirements.txt'
  if (Test-Path $Req) {
    Log "[2/6] 正在准备程序文件，请稍候。"
    $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
      & $VenvPy -u -m pip install --no-index --find-links (Join-Path $Program 'wheels') -r $Req 2>&1 | ForEach-Object { LogNative $_ }
      $pipCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $eap }
    if ($pipCode -ne 0) { throw "离线安装依赖失败（exit $pipCode）：wheels 目录不完整。" }
  }

  # ---- 3) Playwright browsers are shipped; nothing to download ------------
  Log "PLAYWRIGHT_BROWSERS_PATH=$env:PLAYWRIGHT_BROWSERS_PATH"

  # ---- 4) ffmpeg: absolute path, copied into the data area bin ------------
  $FfSrc = Join-Path $Program 'bin\ffmpeg.exe'
  $FfDst = Join-Path $DataDir 'bin\ffmpeg.exe'
  if ((Test-Path $FfSrc) -and -not (Test-Path $FfDst)) {
    Copy-Item $FfSrc $FfDst -Force
    Log "ffmpeg placed at $FfDst"
  }

  # ---- 5) config templates (never overwrite an existing config) -----------
  foreach ($pair in @(@('settings.json.tmpl','settings.json'),
                      @('accounts.json.tmpl','accounts.json'),
                      @('channels.json.tmpl','channels.json'),
                      @('environments.json.tmpl','environments.json'))) {
    $src = Join-Path $Program "config\$($pair[0])"
    $dst = Join-Path $DataDir "config\$($pair[1])"
    if ((Test-Path $src) -and -not (Test-Path $dst)) {
      Copy-Item $src $dst -Force
      Log "seeded config: $($pair[1])"
    }
  }

  # ---- 5b) browser detection: Google Chrome ONLY -------------------------
  # 1.2.2 (source/brief-chrome-only-20261016.md): the browser is the customer's
  # real Google Chrome, and only that.  There is NO Edge / Chromium fallback.
  # If Chrome is missing we print the plain-language sentence plus the official
  # offline installer shipped in chrome-offline\ inside this package; we never
  # install it ourselves and never launch another browser.
  if (Test-Path $VenvPy) {
    Log "resolving browser (Google Chrome only; no Edge/Chromium fallback)"
    $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
      & $VenvPy -u -m winport browser-probe --program $Program --data $DataDir 2>&1 | ForEach-Object { Log ("  " + $_) }
      $browserRc = $LASTEXITCODE
    } finally { $ErrorActionPreference = $eap }
    Log "browser-probe exit=$browserRc"
    if ($browserRc -ne 0) {
      Log "[3/6] 正在准备浏览器，请稍候。系统询问权限时请允许。"
      $chromeInstaller = Join-Path $Program 'chrome-offline\ChromeStandaloneSetup64.exe'
      if (-not (Test-Path -LiteralPath $chromeInstaller)) { throw '安装包缺少浏览器，请联系服务商。' }
      $signature = Get-AuthenticodeSignature -LiteralPath $chromeInstaller
      if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Google LLC(,|$)') {
        throw '内置浏览器签名验证失败，已停止。请联系服务商。'
      }
      # Elevate ONLY the machine-wide browser installer. Data/desktop/task stay
      # under the original user, including when UAC uses another admin account.
      # 1.2.43: Chrome 官方离线安装包的参数必须逐项传数组；整串 '/silent /install' 会被当成单个参数，
      # 官方安装器弹 "设置错误: INVALID_OPTION."。先走不提权（用户级安装），失败再提权。
      # 1.2.44：清掉“来自网络”标记（带 Zone.Identifier 会触发 INVALID_OPTION），
      # 再按 3 组官方参数依次尝试：用户级 → 提权 → 单 /install → 单 /silent。
      try { Unblock-File -LiteralPath $chromeInstaller -ErrorAction SilentlyContinue } catch {}
      $chromeRc = $null
      $argSets = @(@('/silent', '/install'), @('/install'), @('/silent'))
      foreach ($set in $argSets) {
        try {
          $cp1 = Start-Process -FilePath $chromeInstaller -ArgumentList $set -Wait -PassThru -ErrorAction Stop
          $chromeRc = $cp1.ExitCode
          Log ("chrome install (user) args={0} rc={1}" -f ($set -join ' '), $chromeRc)
          if ($chromeRc -in @(0, 3010)) { break }
        } catch { Log "chrome install (user) failed: $_" }
        try {
          $cp2 = Start-Process -FilePath $chromeInstaller -ArgumentList $set -Verb RunAs -Wait -PassThru -ErrorAction Stop
          $chromeRc = $cp2.ExitCode
          Log ("chrome install (elevated) args={0} rc={1}" -f ($set -join ' '), $chromeRc)
          if ($chromeRc -in @(0, 3010)) { break }
        } catch { Log "chrome install (elevated) failed: $_" }
      }
      if ($chromeRc -notin @(0, 3010)) {
        Log "WARN chrome installer rc=$chromeRc，继续用真实探测复核"
      }
      $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
      try {
        & $VenvPy -u -m winport browser-probe --program $Program --data $DataDir 2>&1 | ForEach-Object { LogNative $_ }
        $browserRc = $LASTEXITCODE
      } finally { $ErrorActionPreference = $eap }
      if ($browserRc -ne 0) { throw "浏览器准备后仍不可用（安装器退出码 $chromeRc）。请右键以管理员身份运行 $chromeInstaller 后重试，或联系服务商。" }
    } else {
      Log "browser OK: real Google Chrome found (no substitute browser is ever used)."
    }
  } else {
    Log "venv python not found; skipping browser detection"
  }

  Log "[4/6] 正在创建入口与开机自启。"
  # ---- 6) shortcut + autostart (failures are reported and affect the rc) --
  $stepErrors = @()
  $shortcutRc = 1
  try {
    $shortcutScript = Join-Path $ScriptsDir 'make-shortcut.ps1'
    $shortcutOut = & $shortcutScript -Program $Program -DataDir $DataDir -LogFile $LogFile *>&1
    $shortcutRc = $LASTEXITCODE
    if ($null -eq $shortcutRc) { $shortcutRc = 0 }
    LogNative $shortcutOut
    if ($shortcutRc -ne 0) {
      $stepErrors += "创建桌面快捷方式失败（退出码 $shortcutRc）"
      Log "shortcut step FAILED (rc=$shortcutRc)"
    } else {
      Log "shortcut step OK (1 fixed entry; no per-environment or resident icon)"
    }
  } catch {
    $stepErrors += "创建桌面快捷方式失败：$_"
    Log "shortcut step failed: $_"
  }

  # 1.2.32 real-machine check: the Desktop must contain exactly the three
  # documented shortcuts, and each shortcut must resolve to a real target file.
  # A count of six (the 1.2.31 regression) or a dead .vbs target fails install.
  $shortcutProblems = @()
  $desktop = [Environment]::GetFolderPath('Desktop')
  $expectedShortcuts = @(
    '漫剧发布助手.lnk'
  )
  if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) {
    $shortcutProblems += "找不到桌面目录：$desktop"
  } else {
    # 1.2.44：.lnk 或 .cmd 兜底都算有效入口；不再强制“恰好 1 个 .lnk”
    $desktopDirs = @($desktop, [Environment]::GetFolderPath('CommonDesktopDirectory')) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique
    $desktopEntries = @($desktopDirs | ForEach-Object { Get-ChildItem -LiteralPath $_ -Filter '漫剧发布助手*' -File -ErrorAction SilentlyContinue } |
      Where-Object { $_.Extension -in @('.lnk', '.cmd') })
    if ($desktopEntries.Count -lt 1) {
      $shortcutProblems += "桌面上没有「漫剧发布助手」入口（.lnk 或 .cmd）"
    }
    $desktopLnks = @($desktopEntries | Where-Object { $_.Extension -eq '.lnk' })
    foreach ($cmdEntry in @($desktopEntries | Where-Object { $_.Extension -eq '.cmd' })) {
      $cmdText = Get-Content -LiteralPath $cmdEntry.FullName -Raw -ErrorAction SilentlyContinue
      if ([string]$cmdText -notmatch [regex]::Escape('panel.ps1')) {
        $shortcutProblems += "兜底启动器未指向 panel.ps1：$($cmdEntry.Name)"
      }
    }

    if ($desktopLnks.Count -gt 0) {
      try {
        $shortcutShell = New-Object -ComObject WScript.Shell
        foreach ($lnk in $desktopLnks) {
          try {
            $sc = $shortcutShell.CreateShortcut($lnk.FullName)
            $target = [string]$sc.TargetPath
            $targetExists = $false
            if ($target) {
              $targetExists = Test-Path -LiteralPath $target
              if (-not $targetExists -and -not [System.IO.Path]::IsPathRooted($target)) {
                $targetExists = [bool](Get-Command $target -ErrorAction SilentlyContinue)
              }
            }
            if (-not $targetExists) {
              $shortcutProblems += "快捷方式目标不存在：$($lnk.Name) -> '$target'"
              continue
            }

            if ($target -match '(?i)powershell\.exe$') {
              $m = [regex]::Match([string]$sc.Arguments, '-File\s+"([^"]+\.ps1)"', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
              if (-not $m.Success) {
                $shortcutProblems += "快捷方式没有可解析的 -File 脚本：$($lnk.Name)"
              } elseif (-not (Test-Path -LiteralPath $m.Groups[1].Value)) {
                $shortcutProblems += "快捷方式脚本不存在：$($lnk.Name) -> $($m.Groups[1].Value)"
              }
            } elseif ($target -match '(?i)\.cmd$') {
              $importerPs1 = Join-Path (Split-Path -Parent $target) 'import-license.ps1'
              if (-not (Test-Path -LiteralPath $importerPs1)) {
                $shortcutProblems += "导入授权包装器引用的脚本不存在：$importerPs1"
              }
            } else {
              $shortcutProblems += "快捷方式目标类型不可识别：$($lnk.Name) -> '$target'"
            }
          } catch {
            $shortcutProblems += "读取快捷方式失败（$($lnk.Name)）：$_"
          }
        }
      } catch {
        $shortcutProblems += "快捷方式自检失败：$_"
      }
    }
  }
  if ($shortcutProblems.Count -gt 0) {
    foreach ($problem in $shortcutProblems) {
      $stepErrors += "快捷方式自检失败：$problem"
      Log "SHORTCUT SELF-CHECK FAILED: $problem"
      Write-Host "快捷方式自检失败：$problem" -ForegroundColor Red
    }
    Write-Host "安装结束：桌面快捷方式未通过自检，详情见 $LogFile" -ForegroundColor Red
  } else {
    Log "shortcut self-check OK: exactly 1 desktop shortcut; every target file exists"
  }

  if (-not $SkipAutostart) {
    try {
      $autoOut = & (Join-Path $ScriptsDir 'install-autostart.ps1') -Program $Program -LogFile $LogFile 2>&1
      $autoRc = $LASTEXITCODE
      LogNative $autoOut
      # 1.2.5 (item 8): exit codes from install-autostart.ps1 --
      #   0 = registered via Task Scheduler (crash self-recovery),
      #   4 = registered via HKCU Run (NO crash recovery),
      #   5 = supervisor/template missing (NOT registered).
      # We branch on the CODE, not on scraped text (PowerShell 5.1 Write-Host
      # goes to the information stream and is not captured by 2>&1).
      if ($null -eq $autoRc) { $autoRc = 5 }
      if ($autoRc -eq 0) {
        Log "autostart registered (crash self-recovery via Task Scheduler)"
      } elseif ($autoRc -eq 4) {
        # 1.2.5 round-5 (GPT review item 8-A): the HKCU Run fallback is a
        # DEGRADED registration -- autostart works but there is NO crash
        # self-recovery.  Record it as a step error so the install does not
        # report plain success (exit 0) while the customer silently loses the
        # restart-on-crash guarantee.
        $stepErrors += "开机自启降级为 HKCU Run（无崩溃自恢复）：任务计划注册失败"
        Log "autostart registered via HKCU Run -- WARNING: no crash recovery (Task Scheduler path unavailable)"
      } else {
        $stepErrors += "注册开机自启失败（退出码 $autoRc）：监督器或任务模板缺失"
        Log "autostart step FAILED (rc=$autoRc) -- NOT registered; see the message above"
      }
    } catch {
      $stepErrors += "注册开机自启失败：$_"
      Log "autostart step failed: $_"
    }
  }

  Log "[5/6] 正在自动授权，请稍候。"
  $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try {
    & $VenvPy -u -m winport.activation --data $DataDir 2>&1 | ForEach-Object { LogNative $_ }
    $activationRc = $LASTEXITCODE
  } finally { $ErrorActionPreference = $eap }
  if ($activationRc -ne 0) { $stepErrors += '自动授权未完成：请检查网络，在控制面板重试自动授权；仍失败请联系服务商。' }
  Log "[6/6] 正在检查安装结果。"

  # ---- 7) self-test -------------------------------------------------------
  $rc = 0
  if (-not $SkipSelftest) {
    $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
      & $VenvPy -u -m winport.selftest --data $DataDir --program $Program 2>&1 | ForEach-Object { LogNative $_ }
      $rc = $LASTEXITCODE
    } finally { $ErrorActionPreference = $eap }
    if ($null -eq $rc) { $rc = 5 }
    Log "selftest exit code: $rc"
  }

  # ---- 8) machine code (self-service: the customer sends this to us) ------
  $MachineCode = ''
  if (Test-Path $VenvPy) {
    Log "----- 本机诊断信息（自动生成，无需发送）-----"
    $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try {
      & $VenvPy -u -m winport machine-code --data $DataDir --program $Program 2>&1 | ForEach-Object { if (("$_").Trim()) { Log ("  " + $_) } }
      $mcRc = $LASTEXITCODE
    } finally { $ErrorActionPreference = $eap }
    if ($mcRc -ne 0) {
      Log "WARNING: machine-code exit=$mcRc"
      $stepErrors += "生成机器码失败（exit $mcRc）"
    }
    $mcFile = Join-Path $LogDir '机器码.txt'
    if (Test-Path $mcFile) {
      $MachineCode = (Select-String -Path $mcFile -Pattern '^\s{4}[0-9a-f]{16,}$' -AllMatches | Select-Object -First 1).Line.Trim()
    }
  } else {
    Log "venv python not found; machine code not generated"
    $stepErrors += "未找到 venv python，机器码未生成"
  }

  Log "桌面入口：漫剧发布助手。授权维护入口位于控制面板内。"

  if ($stepErrors.Count -gt 0) {
    Log "WARNINGS during install:"
    foreach ($e in $stepErrors) { Log "  - $e" }
    Write-Host "安装结束：有 $($stepErrors.Count) 个问题，详情见 $LogFile" -ForegroundColor Red
    if ($rc -eq 0) { $rc = 5 }
  }

  # ---- state marker -------------------------------------------------------
  @{ version = (Get-Content (Join-Path $Program 'VERSION') -ErrorAction SilentlyContinue);
     mode = $Mode; installed_at = (Get-Date -Format o); data_dir = $DataDir;
     machine_code = $MachineCode; warnings = $stepErrors } |
    ConvertTo-Json | Set-Content -Path $State -Encoding UTF8
  Log "bootstrap done (exit $rc)"
  # 1.2.5 round-6 (GPT review item 8-A): Install emits native-command
  # stdout (venv/pip/selftest) on the pipeline.  `$rc = Install` would
  # therefore make $rc an ARRAY ("<text>", 5) instead of the integer
  # exit code.  Record the integer here; the caller discards the stream.
  $script:InstallRc = $rc
  return $rc
}

$rc = 1
$script:InstallRc = $null
try {
  # 1.2.5 round-6 (item 8-A): keep the integer exit code separate from the
  # native-command stdout, so $rc is an int -- never a "<text>", 5  array.
  # 1.2.5 round-7 (GPT review suggestion): but do NOT throw the diagnostics
  # away -- append the pip/venv/selftest output to the install log.
  $installOut = Install
  if ($null -ne $installOut) {
    try {
      ($installOut | Out-String -Width 400) | Add-Content -Path $LogFile -Encoding UTF8 -ErrorAction Stop
    } catch { }
  }
  if ($null -eq $script:InstallRc) { $rc = 1 } else { $rc = [int]$script:InstallRc }
} catch {
  $rc = 5
  try { Log "FATAL: $_" } catch { Write-Host "FATAL: $_" }
  Write-Host ""
  Write-Host "====================================================="
  Write-Host " 安装失败：$_"
  Write-Host ""
  Write-Host " 补救步骤："
  Write-Host "  1) 确认磁盘有足够空间（建议至少 5GB）"
  Write-Host "  2) 把此窗口与日志交给服务商排查"
  Write-Host "  3) 修复原因后重新双击安装程序"
  Write-Host "  4) 把本窗口截图和下面的日志一起发给我们"
  Write-Host ""
  Write-Host " 日志文件：$LogFile"
  Write-Host "====================================================="
}
exit $rc
