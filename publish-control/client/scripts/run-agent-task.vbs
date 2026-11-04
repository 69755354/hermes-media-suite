' run-agent-task.vbs -- SUPERVISOR used by the autostart entry.
'
' The supervisor runs the resident agent SYNCHRONOUSLY.  It never exits while
' an agent is alive: if another launcher started the agent it waits for that
' process, then starts its own supervised instance.
'
' 1.2.162: HKCU Run executes this file directly.  HKCU Run has no
' RestartOnFailure policy, so an unexpected agent exit is logged and retried
' here after a short delay instead of ending the supervisor.
Option Explicit
Dim shell, fso, here, program, dataDir, agentDir, py, cmd, rc, logFile, readyFile
Dim cleanExitFile, runningPid, msg, keepGoing, restartDelay, supervisorToken
Dim lockDir, lockOwner, afterLockWait, waitStarted, supervisorPid, lockFailure

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
program = fso.GetParentFolderName(here)
agentDir = program & "\agent"
dataDir = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\HuolongAgent\publish-worker"
logFile = dataDir & "\logs\autostart-supervisor.log"
readyFile = dataDir & "\run\agent-ready.json"
cleanExitFile = dataDir & "\run\agent-clean-exit.json"
lockDir = dataDir & "\run\supervisor.lock"
lockOwner = lockDir & "\owner.txt"
supervisorPid = 0

' ---- interpreter discovery -------------------------------------------------
py = dataDir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then py = dataDir & "\.venv\Scripts\python.exe"
If Not fso.FileExists(py) Then
  msg = "Manju Publish Assistant: the background agent could not start " & _
        "because the bundled Python runtime is missing." & vbCrLf & vbCrLf & _
        "Fix: run bootstrap.bat from the installation package again." & vbCrLf & _
        "Log: " & logFile
  LogLine "FATAL interpreter missing; tried " & dataDir & "\.venv\Scripts\ and " & program & "\runtime\"
  MsgBox msg, vbCritical, "Manju Publish Assistant"
  WriteDiagnostic "interpreter missing: " & py, 5
  WScript.Quit 5
End If

shell.Environment("Process")("PYTHONPATH") = agentDir
shell.Environment("Process")("PYTHONUTF8") = "1"
shell.Environment("Process")("PYTHONIOENCODING") = "utf-8"
shell.Environment("Process")("PYTHONDONTWRITEBYTECODE") = "1"
shell.Environment("Process")("PLAYWRIGHT_BROWSERS_PATH") = program & "\browsers"
cmd = Chr(34) & py & Chr(34) & " -m winport --data " & Chr(34) & dataDir & Chr(34)

' One supervisor owns the resident agent.  HKCU Run and the ONLOGON task can
' both start this file; the loser exits before touching any marker, so two
' masters can never fight over the agent.
supervisorPid = processId()
If supervisorPid <= 0 Then
  LogLine "Supervisor PID lookup failed; retrying once."
  WScript.Sleep 1000
  supervisorPid = processId()
End If
If supervisorPid <= 0 Then
  LogLine "FATAL: cannot establish a valid supervisor PID; refusing to claim the lock."
  WriteDiagnostic "cannot establish supervisor PID", 6
  WScript.Quit 6
End If
Dim lockAcquired, lockAttempt
lockAcquired = False
' A stopped same-path owner can leave a lock younger than the 30-second
' grace period. Retry through that window; only the guarded acquisition may
' reclaim it, and a live owner is never displaced by this loop.
For lockAttempt = 0 To 35
  If AcquireSupervisorLock() Then
    lockAcquired = True
    Exit For
  End If
  If lockAttempt < 35 Then WScript.Sleep 1000
Next
If Not lockAcquired Then
  LogLine "Supervisor lock unavailable after retry: " & lockDir & "; check owner PID and abandoned guard."
  WriteDiagnostic "lock unavailable after 36 attempts: " & lockFailure, 0
  WScript.Quit 0
End If

' ===========================================================================
' Supervision loop.  Invariant: this process never exits while an agent is
' alive somewhere.
'   * an agent someone ELSE started -> wait for it to exit, then start ours;
'   * our instance exits 3 (lock held) -> wait and take over;
'   * our instance exits 0 -> clean shutdown, exit;
'   * our instance exits any other code -> log, wait 60s, retry.
' ===========================================================================
keepGoing = True
afterLockWait = False
Do While keepGoing
  runningPid = LiveAgentPid(readyFile)
  If runningPid > 0 Then
    ClearCleanExit
    LogLine "Agent already running (PID " & runningPid & "); supervising and waiting for exit."
    Do While ProcessAlive(runningPid)
      WScript.Sleep 1600 + Int(Rnd() * 800)
    Loop
    If CleanExitMatches("", runningPid) Then
      LogLine "Existing agent (PID " & runningPid & ") exited normally; supervisor exiting."
      keepGoing = False
      Exit Do
    End If
    LogLine "Existing agent (PID " & runningPid & ") exited without a clean-exit marker; restarting under supervision."
    WScript.Sleep 1600 + Int(Rnd() * 800)
    afterLockWait = False
  End If

  ' If we were only waiting for the previous agent's single-instance lock,
  ' re-check its clean-exit marker BEFORE clearing it and starting again.  A
  ' normal shutdown must not be resurrected just because both autostart paths
  ' exist.
  If afterLockWait Then
    If CleanExitAfter(waitStarted) Then
      LogLine "Agent that held the lock exited normally while we waited; supervisor exiting."
      keepGoing = False
      Exit Do
    End If
    afterLockWait = False
  End If

  ClearCleanExit
  supervisorToken = NewSupervisorToken()
  shell.Environment("Process")("WINPORT_SUPERVISOR_TOKEN") = supervisorToken
  LogLine "Starting supervised agent: " & py
  ' True = WAIT: stay alive as long as the agent so a crash is observed.
  On Error Resume Next
  rc = shell.Run(cmd, 0, True)
  If Err.Number <> 0 Then
    msg = "start failed (error " & Err.Number & ": " & Err.Description & "): " & py
    WriteDiagnostic msg, 5
    LogLine msg
    MsgBox "Manju Publish Assistant: the background agent failed to start." & vbCrLf & vbCrLf & _
           msg & vbCrLf & _
           "Fix: open the panel and click Retry, or run bootstrap.bat again." & vbCrLf & _
           "Log: " & logFile, vbCritical, "Manju Publish Assistant"
    Err.Clear
    On Error GoTo 0
    ReleaseSupervisorLock
    WScript.Quit 5
  End If
  On Error GoTo 0
  shell.Environment("Process")("WINPORT_SUPERVISOR_TOKEN") = ""

  If rc = 0 Then
    If CleanExitMatches(supervisorToken, 0) Then
      keepGoing = False
    Else
      LogLine "Agent exited 0 without a matching clean-exit marker; treating as a crash."
      WScript.Sleep 60000
      keepGoing = True
    End If
  ElseIf rc = 3 Then
    LogLine "Agent exited 3 (single-instance lock held); waiting to take over."
    waitStarted = Now
    afterLockWait = True
    WScript.Sleep 10000
  Else
    restartDelay = 60
    LogLine "Agent crashed (exit " & rc & "); restarting in " & restartDelay & " seconds."
    WScript.Sleep 60000
    keepGoing = True
  End If
Loop

WriteDiagnostic "supervised agent exited cleanly", 0
LogLine "Supervised agent exited cleanly."
ReleaseSupervisorLock
WScript.Quit 0

' ---------------------------------------------------------------- helpers ---
Sub EnsureFolder(p)
  Dim parent
  On Error Resume Next
  If p = "" Then Exit Sub
  If fso.FolderExists(p) Then Exit Sub
  parent = fso.GetParentFolderName(p)
  If parent <> "" And Not fso.FolderExists(parent) Then EnsureFolder parent
  fso.CreateFolder p
  On Error GoTo 0
End Sub

Sub LogLine(text)
  Dim f
  On Error Resume Next
  EnsureFolder fso.GetParentFolderName(logFile)
  Set f = fso.OpenTextFile(logFile, 8, True, -1)
  f.WriteLine Now & "  " & text
  f.Close
  On Error GoTo 0
End Sub

Function FolderEvidence(path)
  Dim folder, age
  FolderEvidence = path & "; exists=False"
  On Error Resume Next
  If fso.FolderExists(path) Then
    Set folder = fso.GetFolder(path)
    age = DateDiff("s", folder.DateCreated, Now)
    FolderEvidence = path & "; exists=True; age_seconds=" & age
  End If
  If Err.Number <> 0 Then FolderEvidence = path & "; unreadable: " & Err.Description
  On Error GoTo 0
End Function

Sub WriteDiagnostic(reason, exitCode)
  Dim f, folder, entry, staging, body, diagnosticPath, writeError
  On Error Resume Next
  EnsureFolder dataDir & "\run"
  staging = "none"
  Set folder = fso.GetFolder(dataDir & "\run")
  For Each entry In folder.SubFolders
    If InStr(1, entry.Name, "supervisor.lock.new.", vbTextCompare) = 1 Then
      staging = staging & " | " & FolderEvidence(entry.Path)
    End If
  Next
  body = "{""time"":""" & JsonEscape(CStr(Now)) & """,""reason"":""" & _
      JsonEscape(reason) & """,""pid"":""" & supervisorPid & """,""version"":""" & _
      JsonEscape(ReadVersion()) & """,""program"":""" & JsonEscape(program) & _
      """,""owner_path"":""" & JsonEscape(lockOwner) & """,""owner"":""" & _
      JsonEscape(ReadAllText(lockOwner)) & """,""guard"":""" & _
      JsonEscape(FolderEvidence(lockDir & ".guard")) & """,""lock"":""" & _
      JsonEscape(FolderEvidence(lockDir)) & """,""staging"":""" & _
      JsonEscape(staging) & """,""exit_code"":" & exitCode & "}"
  diagnosticPath = dataDir & "\run\supervisor-exit.json"
  Err.Clear
  ' UTF-16 preserves customer paths; Python readers detect the BOM.
  Set f = fso.CreateTextFile(diagnosticPath, True, True)
  f.WriteLine body
  f.Close
  writeError = Err.Description
  On Error GoTo 0
  LogLine "supervisor diagnostic: " & body
  If writeError <> "" Then LogLine "diagnostic write failed: " & writeError
End Sub

Sub ClearCleanExit()
  On Error Resume Next
  If fso.FileExists(cleanExitFile) Then fso.DeleteFile cleanExitFile, True
  On Error GoTo 0
End Sub

' ------------------------------------------------------------- single instance
' A directory is used as an atomic create: exactly one supervisor wins, even
' when HKCU Run and Task Scheduler fire together.  The owner file carries pid,
' version and program path so a stale lock can be told from a live one.
Function AcquireSupervisorLock()
  Dim guard
  AcquireSupervisorLock = False
  lockFailure = "lock acquisition incomplete"
  If supervisorPid <= 0 Then Exit Function
  EnsureFolder dataDir & "\run"
  guard = lockDir & ".guard"
  On Error Resume Next
  Err.Clear
  fso.CreateFolder guard
  If Err.Number <> 0 Then
    lockFailure = "guard create failed: " & guard & "; error " & Err.Number & ": " & Err.Description
    Err.Clear
    On Error GoTo 0
    Exit Function
  End If
  On Error GoTo 0
  AcquireSupervisorLock = AcquireSupervisorLockInner()
  On Error Resume Next
  fso.DeleteFolder guard, True
  On Error GoTo 0
End Function

Function AcquireSupervisorLockInner()
  Dim ownerPid, txt, f, staging, age
  AcquireSupervisorLockInner = False
  staging = lockDir & ".new." & supervisorPid
  On Error Resume Next
  If fso.FolderExists(lockDir) Then
    Err.Clear
    Set f = fso.GetFolder(lockDir)
    age = DateDiff("s", f.DateCreated, Now)
    If Err.Number <> 0 Or age < 30 Then
      lockFailure = "lock age below 30 seconds or unreadable: age=" & age & "; " & Err.Description
      Err.Clear
      On Error GoTo 0
      Exit Function
    End If
    txt = ReadAllText(lockOwner)
    ownerPid = JsonNumberField(txt, "pid")
    ' Unknown ownership is never evidence of death. An abandoned guard or
    ' incomplete legacy owner requires manual recovery, not a second master.
    If ownerPid <= 0 Then
      lockFailure = "owner PID missing/unreadable; refusing reclamation"
      Exit Function
    End If
    If SupervisorAlive(ownerPid) Then
      lockFailure = "owner alive or liveness uncertain: pid=" & ownerPid & "; version=" & JsonStringField(txt, "version")
      Exit Function
    End If
    Err.Clear
    fso.DeleteFolder lockDir, True
    If Err.Number <> 0 Then
      lockFailure = "stale lock removal failed: error " & Err.Number & ": " & Err.Description
      Err.Clear
      On Error GoTo 0
      Exit Function
    End If
  End If
  Err.Clear
  fso.CreateFolder staging
  If Err.Number <> 0 Then
    lockFailure = "staging create failed: error " & Err.Number & ": " & Err.Description
    Err.Clear
    On Error GoTo 0
    Exit Function
  End If
  Set f = fso.CreateTextFile(staging & "\owner.txt", False)
  f.WriteLine "{""pid"":" & supervisorPid & ",""version"":""" & _
      JsonEscape(ReadVersion()) & """,""program"":""" & _
      JsonEscape(program) & """}"
  f.Close
  If Err.Number <> 0 Then
    lockFailure = "owner staging write failed: error " & Err.Number & ": " & Err.Description
    Err.Clear
    fso.DeleteFolder staging, True
    On Error GoTo 0
    Exit Function
  End If
  ' Complete owner first; atomic rename publishes the lock. The guard also
  ' serializes stale reclamation, preventing two reclaimers deleting a winner.
  fso.MoveFolder staging, lockDir
  If Err.Number <> 0 Then
    lockFailure = "lock publish failed: error " & Err.Number & ": " & Err.Description
    Err.Clear
    fso.DeleteFolder staging, True
    On Error GoTo 0
    Exit Function
  End If
  On Error GoTo 0
  AcquireSupervisorLockInner = True
End Function

Sub ReleaseSupervisorLock()
  On Error Resume Next
  If fso.FolderExists(lockDir) Then
    If fso.FileExists(lockOwner) Then
      If JsonNumberField(ReadAllText(lockOwner), "pid") = supervisorPid Then
        fso.DeleteFolder lockDir, True
      End If
    End If
  End If
  On Error GoTo 0
End Sub

' A supervisor is alive only while its command line still names this script;
' pid recycling alone must not keep a stale lock forever.
Function SupervisorAlive(pid)
  Dim wmi, procs, proc, found
  SupervisorAlive = True
  If pid <= 0 Then SupervisorAlive = False : Exit Function
  On Error Resume Next
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  If Err.Number <> 0 Then
    Err.Clear
    Exit Function
  End If
  found = False
  Set procs = wmi.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE ProcessId=" & pid)
  For Each proc In procs
    found = True
    ' If the command line is readable and names something else, this is a
    ' recycled PID, not our supervisor.  An unreadable command line is kept as
    ' alive (conservative: a stale lock is cheaper than two masters).
    If Len(proc.CommandLine & "") > 0 Then
      If InStr(LCase(proc.CommandLine), "run-agent-task.vbs") = 0 Then found = False
    End If
  Next
  If Err.Number = 0 Then SupervisorAlive = found
  On Error GoTo 0
End Function

Function CleanExitAfter(whenTs)
  Dim f, txt, pid
  CleanExitAfter = False
  On Error Resume Next
  If Not fso.FileExists(cleanExitFile) Then Exit Function
  Set f = fso.GetFile(cleanExitFile)
  ' VBS dates have one-second resolution; allow a small window so an exit
  ' that races the lock failure is still recognised as the same shutdown.
  If f.DateLastModified < DateAdd("s", -3, whenTs) Then Exit Function
  txt = ReadAllText(cleanExitFile)
  pid = JsonNumberField(txt, "pid")
  If pid <= 0 Then Exit Function
  If Not ProcessAlive(pid) Then CleanExitAfter = True
  On Error GoTo 0
End Function

Function ReadAllText(path)
  Dim ts
  ReadAllText = ""
  On Error Resume Next
  Set ts = fso.OpenTextFile(path, 1)
  ReadAllText = ts.ReadAll
  ts.Close
  On Error GoTo 0
End Function

Function ReadVersion()
  Dim path, ts
  ReadVersion = ""
  path = program & "\VERSION"
  On Error Resume Next
  If Not fso.FileExists(path) Then Exit Function
  Set ts = fso.OpenTextFile(path, 1)
  ReadVersion = Trim(ts.ReadLine)
  ts.Close
  On Error GoTo 0
End Function

Function JsonEscape(value)
  Dim text
  text = Replace(CStr(value), "\", "\\")
  text = Replace(text, """", "\""")
  text = Replace(text, vbCr, "\r")
  text = Replace(text, vbLf, "\n")
  text = Replace(text, vbTab, "\t")
  JsonEscape = text
End Function

Function processId()
  Dim exec, childPid, wmi, procs, proc
  processId = CLng(0)
  On Error Resume Next
  ' WScript exposes no PID.  Start a short-lived child, then read its parent
  ' PID from WMI; that parent is this wscript.exe process.
  Set exec = shell.Exec("cmd /c ping -n 2 127.0.0.1 >nul")
  If Err.Number <> 0 Then
    Err.Clear
    Exit Function
  End If
  childPid = CLng(exec.ProcessID)
  WScript.Sleep 100
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  Set procs = wmi.ExecQuery("SELECT ProcessId, ParentProcessId FROM Win32_Process WHERE ProcessId=" & childPid)
  For Each proc In procs
    processId = CLng(proc.ParentProcessId)
  Next
  On Error GoTo 0
End Function

Function NewSupervisorToken()
  Dim i, value, chars
  chars = "0123456789abcdef"
  value = ""
  Randomize
  For i = 1 To 32
    value = value & Mid(chars, Int(Rnd() * 16) + 1, 1)
  Next
  NewSupervisorToken = value
End Function

' The agent writes this marker only after an orderly shutdown.  A matching
' token proves it belongs to THIS launch; a matching pid covers an agent that
' was started by an older launcher and taken over by this supervisor.
Function CleanExitMatches(wantToken, wantPid)
  Dim ts, txt, token, pid
  CleanExitMatches = False
  On Error Resume Next
  If Not fso.FileExists(cleanExitFile) Then Exit Function
  Set ts = fso.OpenTextFile(cleanExitFile, 1)
  txt = ts.ReadAll
  ts.Close
  token = JsonStringField(txt, "token")
  pid = JsonNumberField(txt, "pid")
  If Err.Number <> 0 Then
    Err.Clear
    Exit Function
  End If
  If wantToken <> "" Then
    If token = wantToken Then CleanExitMatches = True
  ElseIf wantPid > 0 Then
    If pid = wantPid Then CleanExitMatches = True
  End If
  On Error GoTo 0
End Function

Function JsonNumberField(text, name)
  Dim p, q, i, ch, digits
  JsonNumberField = 0
  p = InStr(text, Chr(34) & name & Chr(34))
  If p = 0 Then Exit Function
  q = InStr(p, text, ":")
  If q = 0 Then Exit Function
  digits = ""
  For i = q + 1 To Len(text)
    ch = Mid(text, i, 1)
    If ch >= "0" And ch <= "9" Then
      digits = digits & ch
    ElseIf digits <> "" Then
      Exit For
    ElseIf ch <> " " Then
      Exit Function
    End If
  Next
  If digits <> "" Then JsonNumberField = CLng(digits)
End Function

Function JsonStringField(text, name)
  Dim p, q, r
  JsonStringField = ""
  p = InStr(text, Chr(34) & name & Chr(34))
  If p = 0 Then Exit Function
  q = InStr(p, text, ":")
  If q = 0 Then Exit Function
  q = InStr(q, text, Chr(34))
  If q = 0 Then Exit Function
  r = InStr(q + 1, text, Chr(34))
  If r = 0 Then Exit Function
  JsonStringField = Mid(text, q + 1, r - q - 1)
End Function

' Read run\agent-ready.json and confirm the recorded pid is a live process
' whose command line runs our own module.  Returns 0 when unconfirmed; the
' single-instance lock and exit code 3 are handled by the loop above.
Function LiveAgentPid(readyPath)
  Dim ts, txt, p, q, i, ch, pid, digits, wmi, procs, proc
  LiveAgentPid = 0
  On Error Resume Next
  If Not fso.FileExists(readyPath) Then Exit Function
  Set ts = fso.OpenTextFile(readyPath, 1)
  txt = ts.ReadAll
  ts.Close
  If InStr(txt, Chr(34) & "ready" & Chr(34) & ": true") = 0 Then Exit Function
  p = InStr(txt, Chr(34) & "pid" & Chr(34))
  If p = 0 Then Exit Function
  q = InStr(p, txt, ":")
  If q = 0 Then Exit Function
  digits = ""
  For i = q + 1 To Len(txt)
    ch = Mid(txt, i, 1)
    If ch >= "0" And ch <= "9" Then
      digits = digits & ch
    ElseIf digits <> "" Then
      Exit For
    ElseIf ch <> " " Then
      Exit Function
    End If
  Next
  If digits = "" Then Exit Function
  pid = CLng(digits)
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  If Err.Number <> 0 Then
    Err.Clear
    Exit Function
  End If
  Set procs = wmi.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE ProcessId=" & pid)
  For Each proc In procs
    If InStr(proc.CommandLine, "winport") > 0 Then LiveAgentPid = pid
  Next
  On Error GoTo 0
End Function

' A pid only counts as alive while its command line still holds "winport", so
' pid recycling cannot make the supervisor wait forever.  If WMI is unavailable
' keep supervising rather than abandoning an agent we cannot observe.
Function ProcessAlive(pid)
  Dim wmi, procs, proc, found
  ProcessAlive = True
  On Error Resume Next
  Set wmi = GetObject("winmgmts:\\.\root\cimv2")
  If Err.Number <> 0 Then Exit Function
  Set procs = wmi.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE ProcessId=" & pid)
  found = False
  For Each proc In procs
    found = True
    If Len(proc.CommandLine & "") > 0 Then
      If InStr(proc.CommandLine, "winport") = 0 Then found = False
    End If
  Next
  If Err.Number = 0 Then ProcessAlive = found
  On Error GoTo 0
End Function
