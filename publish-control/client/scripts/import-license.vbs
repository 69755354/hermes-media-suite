' import-license.vbs -- desktop entry: run the licence importer with no console.
' Accepts a dropped/typed path in WScript.Arguments(0) and forwards it as -Src.
Option Explicit
Dim shell, fso, here, program, cmd, extra, rc
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
program = fso.GetParentFolderName(here)
extra = ""
If WScript.Arguments.Count > 0 Then extra = " -Src """ & WScript.Arguments(0) & """"
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & here & _
      "\import-license.ps1"" -Program """ & program & """" & extra
' 1.2.5 round-6 (GPT review item 8 / N3): WAIT for the PowerShell tool and
' propagate its exit code -- the old shell.Run(...,0,False) + Quit 0 hid a
' missing-interpreter (exit 5) failure behind a success status.
rc = shell.Run(cmd, 0, True)
WScript.Quit rc
