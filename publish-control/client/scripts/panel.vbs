' panel.vbs -- "控制面板" entry point (double-click, no console).
'
' 1.1.0: accepts an optional environment argument so a per-environment desktop
' icon opens the panel focused on that environment:
'     wscript.exe panel.vbs env=env_1
' With no argument it opens the master overview (all four environment cards).
'
' 1.2.5 round-17 (8-B-R2 residual): this entry no longer reads a URL back out of
' a file.  It asks launcher.vbs (synchronously) to both ensure the resident agent
' is up AND open the panel, so the "verify the LIVE instance" step and the "open
' that address" step happen in ONE process with no inter-process file handoff for
' the URL.  launcher.vbs returns nonzero when the agent cannot be verified; this
' entry shows the plain-language message and forwards that exact code.
Option Explicit
Dim shell, fso, here, arg, envId, rc, runId, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)

envId = ""
If WScript.Arguments.Count > 0 Then
  arg = WScript.Arguments(0)
  If LCase(Left(arg, 4)) = "env=" Then envId = Mid(arg, 5)
End If

' A fresh per-invocation run id; launcher.vbs writes it into the confirmation
' file it records, so a leftover file from an earlier launch can never read as
' this invocation's result.
runId = NewRunId()
cmd = "wscript.exe " & Chr(34) & here & "\launcher.vbs" & Chr(34) & _
      " quiet --run-id " & runId & " --open-panel"
If envId <> "" Then cmd = cmd & " --env " & Chr(34) & envId & Chr(34)
rc = shell.Run(cmd, 0, True)
If rc <> 0 Then
  MsgBox "漫剧发布助手没有成功启动（错误码 " & rc & "）。请：1) 确认磁盘有空间、" & _
         "杀毒软件没有隔离本程序；2) 再双击一次本图标；3) 仍失败请把日志 " & _
         "logs\agent.out 发给我们。", 16, "漫剧发布助手"
  WScript.Quit rc
End If
WScript.Quit 0

' 1.2.5 round-14 (8-B-R2): mint a fresh 32-hex-char run id for THIS panel
' invocation (GUID if available, randomised fallback otherwise).
Function NewRunId()
  Dim t, g, i, s, c
  NewRunId = ""
  On Error Resume Next
  Set t = CreateObject("Scriptlet.TypeLib")
  If Err.Number = 0 Then
    If Not t Is Nothing Then g = "" & t.Guid
  End If
  Err.Clear
  On Error Goto 0
  g = LCase(Trim(g))
  g = Replace(g, "{", "")
  g = Replace(g, "}", "")
  g = Replace(g, "-", "")
  If Len(g) = 32 Then
    NewRunId = g
    Exit Function
  End If
  Randomize (CLng(Timer * 1000) + Second(Now) * 60 + Minute(Now))
  s = ""
  For i = 1 To 32
    c = Int(Rnd() * 16)
    s = s & Mid("0123456789abcdef", c + 1, 1)
  Next
  NewRunId = s
End Function
