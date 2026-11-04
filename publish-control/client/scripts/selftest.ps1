<#
  selftest.ps1 -- run the agent self-test and show the four lights in a GUI
  message box (customers never see a console).  Same exit codes as the agent.
#>
[CmdletBinding()]
param([string]$DataDir, [string]$Program)

$ErrorActionPreference = 'Continue'
$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Program) { $Program = Split-Path -Parent $ScriptsDir }
if (-not $DataDir) { $DataDir = Join-Path $env:LOCALAPPDATA 'HuolongAgent\publish-worker' }
$env:PYTHONPATH = Join-Path $Program 'agent'
$env:PYTHONUTF8 = '1'
# 1.2.5 (GPT review item 5): the startup-chain integrity check rejects ANY file
# the shipped MANIFEST.json does not list, and the package ships no __pycache__.
# Disable bytecode writing BEFORE the interpreter starts so a double-clicked
# self-test never creates a stray .pyc that would look like tampering.
$env:PYTHONDONTWRITEBYTECODE = '1'
# 1.2.5 round-14 (8-A-R2): run the self-test unbuffered, so the whole report is
# flushed line by line (never left inside the interpreter when it is killed).
$env:PYTHONUNBUFFERED = '1'
# 1.2.5 code-page policy (GPT review item 13): do NOT switch
# [Console]::OutputEncoding; make python emit the console's OWN code page so the
# captured child output decodes correctly (no GBK/UTF-8 mixing).
$consoleCp = 0
try { $consoleCp = [Console]::OutputEncoding.CodePage } catch { $consoleCp = 0 }
$env:PYTHONIOENCODING = if ($consoleCp -eq 65001) { 'utf-8' }
                        elseif ($consoleCp -gt 0) { "cp$consoleCp" }
                        else { 'utf-8' }

$py = Join-Path $DataDir '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = Join-Path $Program 'runtime\python.exe' }
# 1.2.5 round-3 (GPT review item 8): a missing interpreter must be a NONZERO,
# plain-language failure, never a silent success.
if (-not (Test-Path $py)) {
  $msg = "找不到 Python 解释器：$py`n安装可能未完成，或被杀毒软件隔离。请重新运行安装程序后再试。"
  Write-Host $msg
  try {
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    [System.Windows.Forms.MessageBox]::Show($msg, '漫剧发布助手 - 自检', 'OK',
      [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
  } catch { }
  exit 5
}

$log = Join-Path $DataDir 'logs\selftest.log'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null
# 1.2.5 round-16 (review advice): stream the report to selftest.log LINE BY LINE
# WHILE it is produced, so a blocked / killed self-test still leaves the lines it
# already printed (the same reason bootstrap.ps1 streams its native calls).
$output = @()
& $py -u -B -m winport.selftest --data $DataDir --program $Program 2>&1 |
  ForEach-Object {
    $output += $_
    Add-Content -Path $log -Value $_ -Encoding UTF8
  }
$rc = $LASTEXITCODE
if ($null -eq $rc) { $rc = 5 }
$text = ($output | Out-String)

try {
  Add-Type -AssemblyName System.Windows.Forms | Out-Null
  $icon = if ($rc -eq 0) { [System.Windows.Forms.MessageBoxIcon]::Information }
          else { [System.Windows.Forms.MessageBoxIcon]::Warning }
  [System.Windows.Forms.MessageBox]::Show($text, '漫剧发布助手 - 自检', 'OK', $icon) | Out-Null
} catch {
  Write-Host $text
}
exit $rc
