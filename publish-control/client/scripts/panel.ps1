<#
  panel.ps1 -- control panel entry point (PowerShell 5.1, no VBS dependency).

  1.2.32: the desktop shortcut targets this script instead of panel.vbs.  It
  starts the resident agent when needed, waits for the agent's readiness marker,
  verifies the loopback /healthz response carries the same per-launch instance
  token, and only then opens that exact URL in the default browser.

  A missing interpreter, a broken marker, a failed health check or a browser
  launch failure is shown in a message box and returned as a nonzero exit code;
  there is no silent "clicked and nothing happened" path.
#>
[CmdletBinding()]
param(
  [string]$Program,
  [string]$DataDir,
  [string]$EnvId
)

$ErrorActionPreference = 'Stop'
$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Program) { $Program = Split-Path -Parent $ScriptsDir }
if (-not $DataDir) { $DataDir = Join-Path $env:LOCALAPPDATA 'HuolongAgent\publish-worker' }

$env:PYTHONPATH = Join-Path $Program 'agent'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Program 'browsers'

$readyFile = Join-Path $DataDir 'run\agent-ready.json'
$logDir = Join-Path $DataDir 'logs'
$entryLog = Join-Path $logDir 'panel-entry.log'
$agentLog = Join-Path $logDir 'agent.out'

function Write-EntryLog([string]$Message) {
  $line = "{0} [panel] {1}" -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $Message
  Write-Host $line
  try {
    if (-not (Test-Path -LiteralPath $logDir)) {
      New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    Add-Content -LiteralPath $entryLog -Value $line -Encoding UTF8 -ErrorAction Stop
  } catch {
    Write-Host "  (panel log write failed: $_)"
  }
}

function Show-EntryError([string]$Message, [int]$Code) {
  Write-EntryLog "ERROR($Code): $Message"
  try {
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    [System.Windows.Forms.MessageBox]::Show($Message, '漫剧发布助手 - 控制面板', 'OK',
      [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
  } catch { }
}

function Get-AgentPython {
  $candidates = @(
    (Join-Path $DataDir '.venv\Scripts\pythonw.exe'),
    (Join-Path $DataDir '.venv\Scripts\python.exe'),
    (Join-Path $Program 'runtime\pythonw.exe'),
    (Join-Path $Program 'runtime\python.exe')
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  return ''
}

function Stop-StaleAgent {
  # 结束残留的旧代理（按 ready 标记 pid / 端口占用 / winport 进程三重兜底），并清掉标记
  try {
    if (Test-Path -LiteralPath $readyFile) {
      try {
        $doc = Get-Content -LiteralPath $readyFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $livePid = 0
        try { $livePid = [int]$doc.agent_pid } catch { }
        if ($livePid -le 0) { try { $livePid = [int]$doc.pid } catch { } }
        if ($livePid -gt 0) { Stop-Process -Id $livePid -Force -ErrorAction SilentlyContinue }
        if ("$($doc.panel_url)" -match ':(\d{1,5})/') {
          $port = [int]$Matches[1]
          Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
        }
      } catch {}
    }
  } catch {}
  try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and ($_.CommandLine -match 'winport' -or $_.CommandLine.Contains($DataDir)) } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  } catch {}
  try { Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue } catch {}
  Start-Sleep -Milliseconds 700
}

function Test-PanelHealth([string]$Url, [string]$Token) {
  $response = $null
  $reader = $null
  try {
    $request = [System.Net.WebRequest]::Create($Url + 'healthz')
    $request.Method = 'GET'
    $request.Proxy = $null
    $request.Timeout = 2000
    $response = $request.GetResponse()
    $status = [int]$response.StatusCode
    if ($status -lt 200 -or $status -ge 400) { return $false }
    $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
    $body = $reader.ReadToEnd()
    $health = $body | ConvertFrom-Json
    if ($health.ok -ne $true) { return $false }
    $expectedVersion = (Get-Content -LiteralPath (Join-Path $Program 'VERSION') -Raw).Trim()
    if ([string]$health.version -ne $expectedVersion) {
      # 1.2.53：端口上是旧版本 → 结束它并清标记，本次启动自己的新代理
      Write-EntryLog "detected stale agent version=$($health.version) expected=$expectedVersion, restarting"
      Stop-StaleAgent
      return $false
    }
    return ([string]$health.instance -eq $Token)
  } catch {
    if (("$_") -match '旧版本仍在运行') { throw }
    return $false
  } finally {
    if ($reader) { $reader.Dispose() }
    if ($response) { $response.Close() }
  }
}

function Get-ReadyPanel {
  if (-not (Test-Path -LiteralPath $readyFile)) { return $null }
  try {
    $raw = Get-Content -LiteralPath $readyFile -Raw -Encoding UTF8 -ErrorAction Stop
    $doc = $raw | ConvertFrom-Json
  } catch {
    return $null
  }
  if ($doc.ready -ne $true) { return $null }

  $url = [string]$doc.panel_url
  if ($url -notmatch '^(?i)https?://(127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})/$') {
    return $null
  }
  $port = [int]$Matches[2]
  if ($port -lt 1 -or $port -gt 65535) { return $null }

  $token = [string]$doc.instance
  if ($token -notmatch '^[0-9a-fA-F]{32}$') { return $null }

  $agentPid = 0
  try { $agentPid = [int]$doc.agent_pid } catch { }
  if ($agentPid -le 0) { try { $agentPid = [int]$doc.pid } catch { return $null } }
  if ($agentPid -le 0) { return $null }
  if (-not (Get-Process -Id $agentPid -ErrorAction SilentlyContinue)) { return $null }
  if (-not (Test-PanelHealth $url $token)) { return $null }

  return [pscustomobject]@{ Url = $url; Token = $token; Pid = $agentPid }
}

try {
  $panel = Get-ReadyPanel
  if (-not $panel) {
    $py = Get-AgentPython
    if (-not $py) {
      Show-EntryError "找不到 Python 解释器，控制面板无法启动。请重新运行安装程序，或联系服务商。" 5
      exit 5
    }

    # 1.2.53：启动前先清掉任何残留代理/标记，避免新面板撞旧进程
    if (Test-Path -LiteralPath $readyFile) { Stop-StaleAgent }
    $argLine = '-m winport --data "' + $DataDir + '"'
    Write-EntryLog "starting agent: $py $argLine"
    try {
      Start-Process -FilePath $py -ArgumentList $argLine -WorkingDirectory $Program `
        -WindowStyle Hidden -ErrorAction Stop | Out-Null
    } catch {
      Show-EntryError "控制面板启动失败：$_`n日志：$agentLog" 6
      exit 6
    }

    for ($i = 0; $i -lt 50; $i++) {
      Start-Sleep -Milliseconds 800
      $panel = Get-ReadyPanel
      if ($panel) { break }
    }
  }

  if (-not $panel) {
    Show-EntryError "控制面板没有启动成功。`n补救：1) 确认磁盘有空间、杀毒软件没有隔离本程序；2) 再双击「漫剧发布助手 控制面板」；3) 若仍失败，把日志发给服务商。`n日志：$agentLog" 6
    exit 6
  }

  $openUrl = $panel.Url
  if ($EnvId) {
    if ($EnvId -notmatch '^[A-Za-z0-9_.-]{1,64}$') {
      Show-EntryError "环境参数无效，控制面板没有打开。" 9
      exit 9
    }
    $escaped = [System.Uri]::EscapeDataString($EnvId)
    $openUrl = $openUrl + '?env=' + $escaped + '#' + $escaped
  }

  try {
    Start-Process -FilePath $openUrl -ErrorAction Stop | Out-Null
  } catch {
    Show-EntryError "控制面板已经启动，但无法打开默认浏览器。请检查默认浏览器设置。`n地址：$openUrl" 7
    exit 7
  }

  Write-EntryLog "opened $openUrl (agent pid $($panel.Pid))"
  exit 0
} catch {
  Show-EntryError "控制面板启动失败：$_`n日志：$agentLog" 8
  exit 8
}
