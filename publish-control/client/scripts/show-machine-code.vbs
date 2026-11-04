' show-machine-code.vbs -- desktop entry: run the PowerShell machine-code page
' with no console window.  Kept as a .vbs so the shortcut shows one message box
' (never a black console) exactly like the panel/launcher do.
Option Explicit
Dim shell, fso, here, program, cmd, rc
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
program = fso.GetParentFolderName(here)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & here & _
      "\show-machine-code.ps1"" -Program """ & program & """"
' 1.2.5 round-6 (GPT review item 8 / N3): WAIT for the PowerShell tool and
' propagate its exit code instead of a fixed Quit 0.
rc = shell.Run(cmd, 0, True)
WScript.Quit rc
