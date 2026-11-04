<#
  show-machine-code.ps1 -- self-service: show + save this machine's 机器码.

  The customer double-clicks the desktop icon 「漫剧发布助手 查看机器码」 (or runs
  this script).  It asks the agent for the machine code, prints it in a message
  box and also writes <Data>\logs\机器码.txt so the customer can attach the file
  instead of retyping the code.

  Pure display: it never sends anything anywhere and never touches a private key.
#>
[CmdletBinding()]
param([string]$DataDir, [string]$Program)

$ErrorActionPreference = 'Continue'
$ScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Program) { $Program = Split-Path -Parent $ScriptsDir }
if (-not $DataDir) { $DataDir = Join-Path $env:LOCALAPPDATA 'HuolongAgent\publish-worker' }

$env:PYTHONPATH = Join-Path $Program 'agent'
$env:PYTHONUTF8 = '1'
# 1.2.5 (item 5): never leave a stray .pyc in the program tree -- the startup
# integrity check rejects any file the shipped MANIFEST.json does not list.
$env:PYTHONDONTWRITEBYTECODE = '1'
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
# 1.2.5 round-3 (GPT review item 8): missing interpreter -> a real nonzero
# failure, never a silent success.
if (-not (Test-Path $py)) {
  $msg = "找不到 Python 解释器：$py`n安装可能未完成，或被杀毒软件隔离。请重新运行安装程序后再试。"
  Write-Host $msg
  try {
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    [System.Windows.Forms.MessageBox]::Show($msg, '漫剧发布助手 - 机器码', 'OK',
      [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
  } catch { }
  exit 5
}

$out = Join-Path $DataDir 'logs\机器码.txt'
$args = @('-m', 'winport', 'machine-code', '--data', $DataDir, '--program', $Program, '--out', $out)
$text = (& $py @args 2>&1 | Out-String)
$rc = $LASTEXITCODE
if ($null -eq $rc) { $rc = 5 }
if (-not $text.Trim()) { $text = "无法读取机器码（exit $rc）。请把这一页截图发给我们。" }

Write-Host $text
try {
  Add-Type -AssemblyName System.Windows.Forms | Out-Null
  [System.Windows.Forms.MessageBox]::Show($text, '漫剧发布助手 - 机器码', 'OK',
    [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
} catch {
  Write-Host "(无法弹出窗口，请直接看上面的文字)"
}
exit $rc
