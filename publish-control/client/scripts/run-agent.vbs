' run-agent.vbs -- silent single-shot start of the resident agent (used by
' "check now" and the installer self-check).  Hidden.
'
' Same G2 interpreter rule as launcher.vbs: the venv python is the ONLY
' interpreter; the bundled runtime has no playwright/pystray.  
' PLAYWRIGHT_BROWSERS_PATH is also set here -- it was missing from
' the 1.0.0 version of this script, which broke browser paths for any process
' started through it.
'
' 1.2.5 round-7 (GPT review item 8-C): this wrapper no longer reports a failed
' start as success.  The old code did `shell.Run cmd, 0, False` then a fixed
' `WScript.Quit 0`, so a Python argument/parse/bind failure was invisible.
' Now:
'   * with an argument (e.g. `--once`) it runs SYNCHRONOUSLY and returns the
'     real exit code;
'   * with no argument it starts the resident agent hidden and does the SAME
'     timed readiness handshake as launcher.vbs (the agent writes
'     run\agent-ready.json), returning 0 only once the agent is really up and
'     6 when it never comes up.
Option Explicit
Dim shell, fso, here, program, dataDir, agentDir, pythonw, cmd, extra, readyFile
Dim i, ok, rc
Dim gPanelPort
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
program = fso.GetParentFolderName(here)
agentDir = program & "\agent"
dataDir = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\HuolongAgent\publish-worker"
readyFile = dataDir & "\run\agent-ready.json"

pythonw = dataDir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonw) Then pythonw = dataDir & "\.venv\Scripts\python.exe"
If Not fso.FileExists(pythonw) Then WScript.Quit 5

extra = ""
If WScript.Arguments.Count > 0 Then extra = " " & WScript.Arguments(0)
shell.Environment("Process")("PYTHONPATH") = agentDir
shell.Environment("Process")("PYTHONUTF8") = "1"
shell.Environment("Process")("PYTHONIOENCODING") = "utf-8"
' 1.2.5 round-3 (GPT review item 5): the startup-chain integrity check rejects
' any file the shipped MANIFEST.json does not list, and the package ships no
' __pycache__.  Disable bytecode writing (env + -B) so this entry never creates
' a stray .pyc that would later look like tampering.
shell.Environment("Process")("PYTHONDONTWRITEBYTECODE") = "1"
shell.Environment("Process")("PLAYWRIGHT_BROWSERS_PATH") = program & "\browsers"
cmd = """" & pythonw & """ -B -m winport --data """ & dataDir & """" & extra

' Single-shot / diagnostic call (an argument was given): wait and propagate.
If extra <> "" Then
  rc = shell.Run(cmd, 0, True)
  WScript.Quit rc
End If

' Resident start: already up?  A live ready pid means there is nothing to do.
If ReadyPid(readyFile) > 0 Then WScript.Quit 0
shell.Run cmd, 0, False

' Timed readiness handshake (same marker launcher.vbs uses).
ok = False
For i = 1 To 40
  WScript.Sleep CInt(800 + (Rnd() * 400))
  If ReadyPid(readyFile) > 0 Then ok = True : Exit For
Next
If ok Then WScript.Quit 0
WScript.Quit 6

Function ReadyPid(path)
  Dim txt, url, port, p, n, ch, token
  ReadyPid = 0
  If Not fso.FileExists(path) Then Exit Function
  On Error Resume Next
  txt = fso.OpenTextFile(path, 1).ReadAll
  On Error Goto 0
  If InStr(txt, """ready"": true") = 0 Then Exit Function
  url = PanelUrl(txt)
  If url = "" Then Exit Function
  ' 1.2.5 round-11 (item 8-C): bind readiness to THIS launch's instance
  ' token -- the panel must echo the same secret via /healthz, so a
  ' recycled pid or a stranger HTTP 200 cannot read as ready.
  token = MarkerField(txt, "instance")
  If token = "" Then Exit Function
  If Not IsHexToken(token) Then Exit Function
  ' Prefer the process that actually owns the panel: an updater-supervised
  ' launch writes the venv redirector pid in "pid" and the runtime child in
  ' "agent_pid".  Older markers have only "pid".
  p = InStr(txt, """agent_pid"":")
  If p = 0 Then p = InStr(txt, """pid"":")
  If p = 0 Then Exit Function
  p = InStr(p, txt, ":")
  If p = 0 Then Exit Function
  p = p + 1
  ' skip whitespace: jsonio.write_json writes indented JSON ("pid": 123)
  Do While p <= Len(txt)
    ch = Mid(txt, p, 1)
    If ch = " " Or ch = Chr(9) Or ch = Chr(13) Or ch = Chr(10) Then
      p = p + 1
    Else
      Exit Do
    End If
  Loop
  n = ""
  Do While p <= Len(txt)
    ch = Mid(txt, p, 1)
    If ch >= "0" And ch <= "9" Then
      n = n & ch
      p = p + 1
    Else
      Exit Do
    End If
  Loop
  If n = "" Then Exit Function
  port = gPanelPort
  ' 1.2.5 round-8 (item 8-C): a live PID alone is not enough -- a stale
  ' marker whose PID was recycled by an unrelated process must never read
  ' as ready.  Require the live process to really be our winport agent AND
  ' its control-panel socket to be listening.
  If Not PidIsAgent(CLng(n), dataDir, pythonw) Then Exit Function
  If Not PanelListening(port, CLng(n)) Then Exit Function
  If Not PanelAnswers(url, token) Then Exit Function
  ReadyPid = CLng(n)
End Function

' 1.2.5 round-8 (item 8-C): the live PID must be OUR winport agent, not a
' recycled PID of some other process.
Function PidIsAgent(pid, dataDir, interp)
  Dim svc, col, proc, cl, ep, home, toks
  PidIsAgent = False
  home = BaseHome(interp)
  On Error Resume Next
  Set svc = GetObject("winmgmts:\\.\root\cimv2")
  If Not svc Is Nothing Then
    Set col = svc.ExecQuery("SELECT ExecutablePath, CommandLine FROM Win32_Process WHERE ProcessId=" & pid)
    If Not col Is Nothing Then
      If col.Count > 0 Then
        cl = ""
        ep = ""
        For Each proc In col
          If Not IsNull(proc.CommandLine) Then cl = "" & proc.CommandLine
          If Not IsNull(proc.ExecutablePath) Then ep = "" & proc.ExecutablePath
        Next
        ' 1.2.5 round-10 (item 8-C): bind to the REAL agent invocation --
        ' the exact interpreter, the "-m winport" TOKEN (space-delimited,
        ' so "winport_probe" fails), and "\"--data \"<this data dir>\"" with
        ' its closing quote (so a "...publish-worker-other" prefix fails).
        ' 1.2.5 round-12 (item 8-C): a Windows venv launches its BASE
        ' interpreter through a redirector stub (Lib\venv\...\pythonw.exe),
        ' so the live agent image is EITHER the chosen launcher OR the base
        ' interpreter named by pyvenv.cfg 'home'.  Accept exactly one of
        ' those two images -- not a loose substring.  The per-launch
        ' instance token checked in PanelAnswers is the decisive binding.
        If ImageIs(ep, interp, home) Then
          ' 1.2.5 round-18 (M1): parse the REAL argv.  The live process
          ' must be running "-m winport" (not "-c code" or a script) AND
          ' its LAST --data value must equal this data dir -- the same
          ' "last value wins" rule argparse uses, so a second
          ' "--data <other>" cannot hide behind an earlier one.
          toks = WinArgs(cl)
          If RunsModule(toks, "winport") And EffectiveDataArg(toks) = dataDir Then
            PidIsAgent = True
          End If
        End If
      End If
    End If
  End If
  On Error Goto 0
End Function

' 1.2.5 round-13 (item 8-C-R2): read a UTF-8 text file.  CPython's venv writes
' pyvenv.cfg as UTF-8 (Lib/venv/__init__.py), so reading it with
' fso.OpenTextFile (system ANSI = CP936 on Chinese Windows) mangles non-ASCII
' install paths.  Prefer ADODB.Stream (utf-8); fall back to an ANSI read only
' if that object is unavailable.
Function ReadUtf8(path)
  Dim st, txt, ans
  ReadUtf8 = ""
  txt = ""
  On Error Resume Next
  Set st = CreateObject("ADODB.Stream")
  If Err.Number = 0 And Not st Is Nothing Then
    st.Type = 2
    st.Charset = "utf-8"
    st.Open
    st.LoadFromFile path
    txt = st.ReadText
    If Err.Number <> 0 Then txt = ""
    st.Close
  End If
  Err.Clear
  On Error Goto 0
  If txt = "" Then
    ans = ""
    On Error Resume Next
    ans = fso.OpenTextFile(path, 1).ReadAll
    On Error Goto 0
    ' 1.2.5 round-16 (review advice): an ANSI read of a UTF-8 file turns a
    ' non-ASCII (e.g. Chinese) path into mojibake.  Fail closed instead.
    If HasNonAscii(ans) Then ans = ""
    txt = ans
  End If
  ReadUtf8 = txt
End Function

' 1.2.5 round-12 (item 8-C): a Windows venv's Scripts\python[w].exe is a
' redirector stub; it re-executes the BASE interpreter in pyvenv.cfg 'home'.
' Return that base directory so the live agent image can be matched.
Function BaseHome(interp)
  Dim scriptsDir, venvDir, cfg, txt, lines, i, ln, p, home
  BaseHome = ""
  scriptsDir = fso.GetParentFolderName(interp)
  venvDir = fso.GetParentFolderName(scriptsDir)
  cfg = venvDir & "\pyvenv.cfg"
  If Not fso.FileExists(cfg) Then Exit Function
  txt = ReadUtf8(cfg)
  If txt = "" Then Exit Function
  lines = Split(Replace(txt, vbCrLf, vbLf), vbLf)
  home = ""
  For i = 0 To UBound(lines)
    ln = Trim(lines(i))
    p = InStr(ln, "=")
    If p > 0 Then
      If LCase(Trim(Left(ln, p - 1))) = "home" Then
        home = Trim(Mid(ln, p + 1))
        Exit For
      End If
    End If
  Next
  BaseHome = home
End Function

' 1.2.5 round-12 (item 8-C): the live image must be EXACTLY the chosen
' interpreter, or the base interpreter (python[w].exe) in pyvenv.cfg home.
Function ImageIs(ep, interp, home)
  Dim nm
  ImageIs = False
  If ep = "" Then Exit Function
  If LCase(ep) = LCase(interp) Then
    ImageIs = True
    Exit Function
  End If
  If home = "" Then Exit Function
  If LCase(fso.GetParentFolderName(ep)) <> LCase(home) Then Exit Function
  nm = LCase(fso.GetFileName(ep))
  If nm = "python.exe" Or nm = "pythonw.exe" Then ImageIs = True
End Function

' 1.2.5 round-8 (item 8-C): verify the control panel is actually serving:
' the live agent PID must own a TCP socket on the panel port (proxy-free).
Function PanelListening(port, pid)
  Dim svc, col
  PanelListening = False
  If port < 1 Then Exit Function
  On Error Resume Next
  Set svc = GetObject("winmgmts:\\.\root\StandardCimv2")
  If Not svc Is Nothing Then
    ' State=2 is TCP_LISTEN: a mere connection owned by the pid is not
    ' proof the panel is serving.
    Set col = svc.ExecQuery("SELECT LocalPort FROM MSFT_NetTCPConnection WHERE LocalPort=" & port & " AND OwningProcess=" & pid & " AND State=2")
    If Not col Is Nothing Then
      If col.Count > 0 Then PanelListening = True
    End If
  End If
  On Error Goto 0
End Function

Function PanelUrl(txt)
  Dim key, p, e, url, re, m, port
  PanelUrl = ""
  gPanelPort = 0
  key = Chr(34) & "panel_url" & Chr(34) & ": " & Chr(34)
  p = InStr(txt, key)
  If p = 0 Then Exit Function
  p = p + Len(key)
  e = InStr(p, txt, Chr(34))
  If e = 0 Then Exit Function
  url = Mid(txt, p, e - p)
  On Error Resume Next
  Set re = CreateObject("VBScript.RegExp")
  If re Is Nothing Then
    On Error Goto 0
    Exit Function
  End If
  re.Pattern = "^https?://(127\.0\.0\.1|localhost|\[::1\]):([0-9]{1,5})/"
  re.IgnoreCase = True
  Set m = re.Execute(url)
  On Error Goto 0
  If m Is Nothing Then Exit Function
  If m.Count <> 1 Then Exit Function
  port = CLng(m(0).SubMatches(1))
  If port < 1 Or port > 65535 Then Exit Function
  gPanelPort = port
  PanelUrl = url
End Function

' 1.2.5 round-11 (item 8-C): pull a named string field out of the readiness
' JSON written by jsonio.write_json (which is indented, hence ': "').
Function MarkerField(txt, name)
  Dim key, p, e
  MarkerField = ""
  key = Chr(34) & name & Chr(34) & ": " & Chr(34)
  p = InStr(txt, key)
  If p = 0 Then Exit Function
  p = p + Len(key)
  e = InStr(p, txt, Chr(34))
  If e = 0 Then Exit Function
  MarkerField = Mid(txt, p, e - p)
End Function

' 1.2.5 round-11 (item 8-C): the instance token is 32 lowercase hex chars.
Function IsHexToken(t)
  Dim i, c, want
  IsHexToken = False
  If Len(t) <> 32 Then Exit Function
  want = True
  For i = 1 To Len(t)
    c = LCase(Mid(t, i, 1))
    If InStr("0123456789abcdef", c) = 0 Then want = False
  Next
  If want Then IsHexToken = True
End Function

' 1.2.5 round-9 (item 8-C): prove the panel really answers on the URL
' the marker names -- a listening socket alone is not an HTTP service.
Function PanelAnswers(url, token)
  Dim http, body
  PanelAnswers = False
  On Error Resume Next
  Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
  If Err.Number <> 0 Or http Is Nothing Then
    Err.Clear
    On Error Goto 0
    ' 1.2.5 round-10 (item 8-C): fail CLOSED -- an unavailable probe
    ' engine must not be read as 'panel is up'.
    Exit Function
  End If
  http.SetProxy 2, "", ""      ' 2 = DIRECT: never proxy a loopback probe
  http.SetTimeouts 1500, 1500, 1500, 1500
  ' 1.2.5 round-11 (item 8-C): the panel must answer /healthz AND echo the
  ' per-launch instance token from the marker -- a bare HTTP 200 from some
  ' other process on a recycled pid is not proof the agent is up.
  http.Open "GET", url & "healthz", False
  http.Send
  If Err.Number = 0 Then
    If http.Status >= 200 And http.Status < 400 Then
      body = "" & http.ResponseText
      If InStr(body, Chr(34) & token & Chr(34)) > 0 Then PanelAnswers = True
    End If
  End If
  Err.Clear
  On Error Goto 0
End Function

' 1.2.5 round-18 (M1): split a Windows command line into argv the way the
' Windows CRT / Python does (spaces separate; "..." groups; a backslash run
' before a quote is halved and the quote is toggled, an odd run escapes it).
Function WinArgs(cl)
  Dim out(), cnt, i, n, ch, nbs, inq, arg
  cnt = -1
  ReDim out(0)
  n = Len(cl)
  i = 1
  Do While i <= n
    Do While i <= n
      ch = Mid(cl, i, 1)
      If ch = " " Or ch = Chr(9) Then
        i = i + 1
      Else
        Exit Do
      End If
    Loop
    If i > n Then Exit Do
    arg = ""
    inq = False
    Do While i <= n
      ch = Mid(cl, i, 1)
      If ch = Chr(92) Then
        nbs = 0
        Do While i <= n And Mid(cl, i, 1) = Chr(92)
          nbs = nbs + 1
          i = i + 1
        Loop
        If i <= n And Mid(cl, i, 1) = Chr(34) Then
          If nbs Mod 2 = 0 Then
            arg = arg & String(nbs \ 2, Chr(92))
            inq = Not inq
          Else
            arg = arg & String((nbs - 1) \ 2, Chr(92)) & Chr(34)
          End If
          i = i + 1
        Else
          arg = arg & String(nbs, Chr(92))
        End If
      ElseIf ch = Chr(34) Then
        If inq Then
          If i < n And Mid(cl, i + 1, 1) = Chr(34) Then
            arg = arg & Chr(34)
            i = i + 2
          Else
            inq = False
            i = i + 1
          End If
        Else
          inq = True
          i = i + 1
        End If
      ElseIf (ch = " " Or ch = Chr(9)) And Not inq Then
        Exit Do
      Else
        arg = arg & ch
        i = i + 1
      End If
    Loop
    cnt = cnt + 1
    ReDim Preserve out(cnt)
    out(cnt) = arg
  Loop
  WinArgs = out
End Function

' 1.2.5 round-18 (M1): is the FIRST execution target "-m <modname>"?  "-c code",
' a script path, "-" (stdin) or "--" all mean Python is NOT running our module.
Function RunsModule(toks, modname)
  Dim i, t, v
  RunsModule = False
  i = LBound(toks) + 1
  Do While i <= UBound(toks)
    t = toks(i)
    If LCase(Left(t, 2)) = "-m" Then
      v = Mid(t, 3)
      If v = "" And i + 1 <= UBound(toks) Then v = toks(i + 1)
      If LCase(v) = LCase(modname) Then RunsModule = True
      Exit Function
    ElseIf LCase(Left(t, 2)) = "-c" Then
      Exit Function
    ElseIf t = "-" Or t = "--" Then
      Exit Function
    ElseIf Left(t, 1) = "-" Then
      If t = "-W" Or t = "-X" Or t = "--check-hash-based-pycs" Then i = i + 1
      i = i + 1
    Else
      Exit Function
    End If
  Loop
End Function

' 1.2.5 round-18 (M1): the --data value Python's argparse will ACTUALLY use --
' the LAST one wins, exactly like the application entry point (both the bare
' form and --data=VALUE).  "" when absent or missing its value.
Function EffectiveDataArg(toks)
  Dim i, t
  EffectiveDataArg = ""
  For i = LBound(toks) To UBound(toks)
    t = toks(i)
    If t = "--data" Then
      If i + 1 <= UBound(toks) Then
        EffectiveDataArg = toks(i + 1)
      Else
        EffectiveDataArg = ""
      End If
    ElseIf Left(t, 7) = "--data=" Then
      EffectiveDataArg = Mid(t, 8)
    End If
  Next
End Function

' 1.2.5 round-16 (review advice): true if a string holds any non-ASCII char.
Function HasNonAscii(s)
  Dim i
  HasNonAscii = False
  For i = 1 To Len(s)
    If AscW(Mid(s, i, 1)) > 127 Or AscW(Mid(s, i, 1)) < 0 Then
      HasNonAscii = True
      Exit Function
    End If
  Next
End Function
