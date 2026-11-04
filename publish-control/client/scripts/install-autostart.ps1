<#
  install-autostart.ps1 -- register the onlogon task WITH CRASH SELF-RECOVERY.

  1.2.5 (GPT review 1.2.4 item 7): the previous version registered
  ``wscript.exe launcher.vbs``.  launcher.vbs exits the instant it has spawned
  the hidden agent, so Task Scheduler never saw the Python process and its
  RestartOnFailure could never fire.  Here we import a real Task Scheduler XML
  (config\task-agent.xml.tmpl) whose action runs the SYNCHRONOUS supervisor
  ``scripts\run-agent-task.vbs``: that wrapper stays alive exactly as long as
  the agent's Python process, so the task observes the process and restarts it
  after a crash / kill (RestartOnFailure Interval PT1M, Count 999).

  Fallback: if Task Scheduler refuses the XML (locked-down policy), we fall back
  to HKCU\...\Run -- and SAY so, because that fallback has NO crash recovery.
  Removal: -Remove.
#>
[CmdletBinding()]
param(
  [string]$Program,
  [string]$DataDir,
  [string]$TaskName = 'HuolongAgent\Agent',
  [string]$LogFile,
  [switch]$UseRegistry,
  [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Program) { $Program = Split-Path -Parent $ScriptsDir }
if (-not $DataDir) { $DataDir = Join-Path $env:LOCALAPPDATA 'HuolongAgent\publish-worker' }

$supervisor = Join-Path $Program 'scripts\run-agent-task.vbs'
$RunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

# 1.2.5 round-9 (GPT review item 8-A): schtasks diagnostics must reach the
# installer's log, not only the (uncapturable) host stream.
function Write-Log([string]$m) {
  Write-Host $m
  if ($LogFile) {
    try { Add-Content -Path $LogFile -Value $m -Encoding UTF8 -ErrorAction Stop } catch { }
  }
}

function Remove-Autostart {
  schtasks /delete /f /tn $TaskName 2>$null | Out-Null
  Remove-ItemProperty -Path $RunKey -Name 'HuolongAgentAgent' -ErrorAction SilentlyContinue
}

if ($Remove) {
  Remove-Autostart
  Write-Log "autostart removed"
  exit 0
}

if ($UseRegistry) {
  Set-ItemProperty -Path $RunKey -Name 'HuolongAgentAgent' `
    -Value ('wscript.exe "' + $supervisor + '"')
  Write-Log "autostart registered via HKCU Run (中文提示：本机策略不允许计划任务，已降级为登录启动；【无崩溃自恢复】，Agent 被结束后不会自动拉起)"
  # 1.2.5 round-3 (GPT review item 8): exit 4 = registered WITHOUT crash
  # recovery, so the caller can report the degraded mode by EXIT CODE instead of
  # scraping Write-Host text across a PowerShell stream boundary.
  exit 4
}

if (-not (Test-Path $supervisor)) {
  Write-Log "FATAL: 监督脚本缺失（supervisor missing）: $supervisor"
  exit 5
}

$tmpl = Join-Path $Program 'config\task-agent.xml.tmpl'
if (-not (Test-Path $tmpl)) {
  Write-Log "FATAL: task template missing: $tmpl"
  exit 5
}

$user = "$env:USERDOMAIN\$env:USERNAME"
if (-not $env:USERDOMAIN) { $user = "$env:COMPUTERNAME\$env:USERNAME" }
# 1.2.11 (WIN_REALTEST_REPORT_1.2.10 must-fix 1): read the template with BOM
# auto-detection.  config\task-agent.xml.tmpl ships as UTF-16LE+BOM and
# declares encoding="UTF-16"; reading it as UTF-8 (Get-Content -Encoding UTF8)
# would corrupt it and leave a declaration that no longer matches the bytes we
# hand to schtasks.  .NET's StreamReader honours the BOM, so the placeholders
# are substituted on correctly-decoded text and the bytes written below stay
# UTF-16LE+BOM: the declaration and the bytes schtasks parses cannot disagree.
$xml = [System.IO.File]::ReadAllText($tmpl)
$xml = $xml.Replace('%USERDOMAIN%\%USERNAME%', $user)
$xml = $xml.Replace('${SUPERVISOR}', $supervisor)

# schtasks /create /xml needs UTF-16LE WITH BOM (matches the XML declaration).
$xmlPath = Join-Path $env:TEMP ("huolong-agent-task-{0}.xml" -f $PID)
$utf16 = New-Object System.Text.UnicodeEncoding $false, $true
[System.IO.File]::WriteAllText($xmlPath, $xml, $utf16)

$rc = 1
try {
  # 1.2.5 round-9 (item 8-A): a schtasks stderr write must not become a
  # terminating error (ErrorActionPreference=Stop) that skips the diagnostics.
  $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  try {
    schtasks /create /f /tn $TaskName /xml $xmlPath 2>&1 | ForEach-Object { Write-Log ("  schtasks: " + $_) }
    $rc = $LASTEXITCODE
  } finally { $ErrorActionPreference = $eap }
} finally {
  Remove-Item $xmlPath -ErrorAction SilentlyContinue
}

if ($rc -eq 0) {
  Write-Log "autostart task registered with RestartOnFailure: $TaskName（中文提示：已注册自启动，崩溃后 1 分钟自动拉起）"
  Write-Log "supervisor (synchronous, task observes the python process): $supervisor"
  exit 0
}

Write-Log "schtasks /xml failed ($rc)（中文提示：计划任务注册失败）; falling back to HKCU Run (NO crash recovery / 无崩溃自恢复)"
Set-ItemProperty -Path $RunKey -Name 'HuolongAgentAgent' `
  -Value ('wscript.exe "' + $supervisor + '"')
exit 4
