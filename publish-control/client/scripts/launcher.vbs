' launcher.vbs -- double-click entry point for the resident agent.
' Starts the resident agent in a HIDDEN window.  1.2.5 (GPT review item 8): it
' no longer just fires and forgets -- it does a TIMED READINESS HANDSHAKE with
' the agent (the agent writes run\agent-ready.json with its pid) and reports a
' visible, plain-language error + a nonzero exit code when startup fails, so
' "I clicked and nothing happened" cannot occur silently.
'
' Usage:  wscript.exe launcher.vbs [quiet] [--run-id <32 hex>]
'         (quiet = no message box; the caller -- panel.vbs -- shows its own
'          message and reads the exit code; --open-panel makes THIS process
'          verify the live instance and open that address; --env adds the env anchor)
Option Explicit
Dim shell, fso, here, program, dataDir, agentDir, py, cmd, readyFile, args
Dim verifiedFile
Dim quiet, started, i, ok
Dim gPanelPort, gPanelUrl
Dim runId, wantRunId, seenRunId, badArgs, ai, av, av2
Dim gOpenPanel, gEnvId
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
program = fso.GetParentFolderName(here)
agentDir = program & "\agent"
dataDir = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\HuolongAgent\publish-worker"
readyFile = dataDir & "\run\agent-ready.json"
verifiedFile = dataDir & "\run\panel-url.verified.txt"

' ---- arguments: [quiet] [--run-id <32 hex>] [--open-panel] [--env <id>] ---
quiet = False
wantRunId = ""
seenRunId = False
badArgs = False
gOpenPanel = False
gEnvId = ""
ai = 0
Do While ai < WScript.Arguments.Count
  av = WScript.Arguments(ai)
  If LCase(av) = "quiet" Then
    quiet = True
  ElseIf LCase(av) = "--run-id" Then
    ' 1.2.5 round-17 (8-B-R3): validate EVERY --run-id where it appears.  A
    ' missing / empty / malformed value, or a repeated option, is remembered as
    ' bad immediately -- the old code only set the value when a value was
    ' present, so "quiet --run-id R --run-id" silently kept the earlier R.
    If seenRunId Then
      badArgs = True
    End If
    seenRunId = True
    If ai + 1 >= WScript.Arguments.Count Then
      badArgs = True
    Else
      wantRunId = WScript.Arguments(ai + 1)
      ai = ai + 1
      If Not IsHexToken(wantRunId) Then badArgs = True
    End If
  ElseIf LCase(av) = "--open-panel" Then
    gOpenPanel = True
  ElseIf LCase(av) = "--env" Then
    ' 1.2.5 round-18 (M2): "--env" must carry a real, safe env id.  The old
    ' code swallowed whatever followed -- even another option ("--env
    ' --run-id") -- so a later "--run-id" could hide inside it and never be
    ' validated.  Missing / empty / option-like values are a hard argument
    ' error (exit 9), and the value is NOT consumed, so the hidden option is
    ' still parsed on the next iteration.
    If ai + 1 >= WScript.Arguments.Count Then
      badArgs = True
    Else
      av2 = WScript.Arguments(ai + 1)
      If IsEnvId(av2) Then
        gEnvId = av2
        ai = ai + 1
      Else
        badArgs = True
      End If
    End If
  End If
  ai = ai + 1
Loop

' 1.2.5 round-14 (8-B-R2): every launch carries a per-launch run id.  panel.vbs
' mints it, passes it here, and only accepts a confirmed URL whose file begins
' with that same id -- so a leftover or substituted confirmation file can never
' read as "this launch is ready".  A stand-alone launch mints its own id.
' 1.2.5 round-16 (8-B-R3): distinguish "option absent" (stand-alone launch ->
' mint our own id) from "option GIVEN but missing / empty / malformed" (always
' Quit 9).  Never silently auto-generate an id the caller asked to supply.
If badArgs Or (seenRunId And Not IsHexToken(wantRunId)) Then
  If Not quiet Then
    MsgBox "启动参数无效（run-id 必须是 32 位十六进制；--env 必须带合法环境 ID），已按失败处理。", 16, "漫剧发布助手"
  End If
  WScript.Quit 9
End If
runId = wantRunId
If Not seenRunId Then runId = NewRunId()

' Drop any stale confirmed URL and FAIL (nonzero) if it cannot be removed: a
' locked leftover address from an earlier launch must never survive as this
' run's confirmation.  (round-14, 8-B-R2)
If fso.FileExists(verifiedFile) Then
  On Error Resume Next
  Err.Clear
  fso.DeleteFile verifiedFile, True
  If Err.Number <> 0 Then
    On Error Goto 0
    If Not quiet Then
      MsgBox "无法清理上一次的面板地址确认文件（可能被占用或只读），已按失败处理（退出码 8）。请关闭占用的程序后重试。", 16, "漫剧发布助手"
    End If
    WScript.Quit 8
  End If
  On Error Goto 0
End If

py = dataDir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then py = dataDir & "\.venv\Scripts\python.exe"
' 1.2.63: never fall back to the bundled runtime; it lacks required packages.
If Not fso.FileExists(py) Then
  If Not quiet Then
    MsgBox "缺少运行环境（.venv）：安装不完整，请重新运行 bootstrap.bat 修复安装。", 16, "漫剧发布助手"
  End If
  WScript.Quit 5
End If

' Already up?  If the recorded agent pid is still alive we are done.
If ReadyPid(readyFile) > 0 Then
  FinishOrExit
  WScript.Quit 0
End If

' Force UTF-8 for every child process; never trust the GBK console code page.
shell.Environment("Process")("PYTHONPATH") = agentDir
shell.Environment("Process")("PYTHONUTF8") = "1"
shell.Environment("Process")("PYTHONIOENCODING") = "utf-8" : shell.Environment("Process")("PYTHONDONTWRITEBYTECODE") = "1"
shell.Environment("Process")("PLAYWRIGHT_BROWSERS_PATH") = program & "\browsers"
cmd = """" & py & """ -m winport --data """ & dataDir & """"
' 0 = hidden window, False = do not wait (the agent becomes the resident process).
shell.Run cmd, 0, False

' Timed readiness handshake: wait up to 40s for the agent to publish a live pid.
ok = False
For i = 1 To 40
  WScript.Sleep CInt(800 + (Rnd() * 400))
  If ReadyPid(readyFile) > 0 Then ok = True : Exit For
Next
If Not ok Then
  If Not quiet Then
    MsgBox "漫剧发布助手没有成功启动。请：1) 确认磁盘有空间、杀毒软件没有隔离本程序；" & _
           "2) 双击「漫剧发布助手 控制面板」重试；3) 仍失败请把日志 logs\agent.out 发给我们。", 16, "漫剧发布助手"
  End If
  WScript.Quit 6
End If
FinishOrExit
WScript.Quit 0

' 1.2.5 round-17 (8-B-R2 residual): finish a successful handshake.  THIS process
' has just verified the LIVE instance -- interpreter image, exact command line,
' LISTEN ownership by that pid, and a /healthz body echoing the marker's
' per-launch instance token (see ReadyPid).  When --open-panel is given we open
' that very URL here, in the SAME process, so the address never crosses a file
' boundary a same-privilege process could rewrite between the check and the use.
' The confirmation file is still written, as an audit record bound to this run id.
Function Finish()
  ' 1.2.5 round-18 (M3): return the ACTUAL cause instead of a shared True/False --
  ' 0 = ok, 7 = the verified address could not be opened in the default browser,
  ' 8 = the audit record could not be written.  The old code blamed a write
  ' failure (exit 8) for a browser/Shell failure too.
  Dim u
  Finish = 0
  If gPanelUrl = "" Then
    Finish = 7
    Exit Function
  End If
  If Not WriteVerified(gPanelUrl, runId) Then
    Finish = 8
    Exit Function
  End If
  If gOpenPanel Then
    u = gPanelUrl
    If gEnvId <> "" Then u = u & "?env=" & gEnvId & "#" & gEnvId
    On Error Resume Next
    Err.Clear
    shell.Run u, 1, False
    If Err.Number <> 0 Then
      Err.Clear
      Finish = 7
    End If
    On Error Goto 0
  End If
End Function

' 1.2.5 round-18 (M3): turn Finish()'s code into the right plain-language
' message and a distinct exit code (7 = cannot open the panel address,
' 8 = cannot write the audit record), instead of mislabelling both as 8.
Sub FinishOrExit()
  Dim fr
  fr = Finish()
  If fr = 7 Then
    If Not quiet Then
      MsgBox "服务已就绪，但无法用默认浏览器打开控制面板（退出码 7）。请检查默认浏览器是否可用，然后从桌面快捷方式重新打开「漫剧发布助手」；仍不行请联系服务商。", 16, "漫剧发布助手"
    End If
    WScript.Quit 7
  ElseIf fr = 8 Then
    If Not quiet Then
      MsgBox "无法写入面板地址确认文件，已按失败处理（退出码 8）。请确认数据目录可写、杀毒软件没有隔离本程序，然后重试。", 16, "漫剧发布助手"
    End If
    WScript.Quit 8
  End If
End Sub

Function ReadyPid(path)
  Dim txt, url, port, p, n, ch, token
  ReadyPid = 0
  If Not fso.FileExists(path) Then Exit Function
  On Error Resume Next
  txt = fso.OpenTextFile(path, 1).ReadAll
  On Error Goto 0
  ' 1.2.5/item8: a live pid is not enough -- the marker must say ready:true with a real panel_url
  If InStr(txt, """ready"": true") = 0 Then Exit Function
  ' 1.2.5 round-5 (item 8-B): a plain substring test is NOT enough.
  ' "http://127.0.0.1:" has no port; "http://127.0.0.1:9223@evil.invalid/"
  ' has host evil.invalid with 127.0.0.1:9223 as USERINFO -- both matched
  ' the old prefix test.  Validate the URL VALUE (see PanelUrl below).
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
  If Not PidIsAgent(CLng(n), dataDir, py) Then Exit Function
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
    ' 1.2.5 round-16 (review 建议): an ANSI read of a UTF-8 file turns a
    ' non-ASCII (e.g. Chinese) path into mojibake, which then fails the image
    ' comparison for the WRONG reason.  Fail closed: only an ASCII fallback is
    ' trusted, so a Chinese path with no ADODB.Stream is reported unreadable
    ' instead of silently mis-decoded.
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


' 1.2.5 round-5 (item 8-B): validate the panel_url VALUE, not a prefix.  Accept
' only http(s)://<loopback>:<1..65535>/ -- exactly what panel.panel_url() emits
' (host from config/channels.json.tmpl, default 127.0.0.1).  Reject "no port" and
' userinfo tricks such as http://127.0.0.1:9223@evil.invalid/ .
Function PanelUrl(txt)
  Dim key, p, e, url, re, m, port
  PanelUrl = ""
  gPanelPort = 0
  gPanelUrl = ""
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
  gPanelUrl = url
  PanelUrl = url
End Function

' 1.2.5 round-14 (8-B-R2): record "<run id>\r\n<url>" for THIS launch and
' PROVE the write took -- every step (create / write / close) and a read-back
' are checked, and any failure returns False so the caller exits nonzero.  A
' stale or partial confirmation file can therefore never be read as "ready".
Function WriteVerified(u, rid)
  Dim fh, back
  WriteVerified = False
  If u = "" Or rid = "" Then Exit Function
  On Error Resume Next
  Err.Clear
  Set fh = fso.CreateTextFile(verifiedFile, True)
  If Err.Number <> 0 Then
    Err.Clear
    On Error Goto 0
    Exit Function
  End If
  fh.Write rid & vbCrLf & u
  If Err.Number <> 0 Then
    Err.Clear
    fh.Close
    On Error Goto 0
    Exit Function
  End If
  fh.Close
  If Err.Number <> 0 Then
    Err.Clear
    On Error Goto 0
    Exit Function
  End If
  Err.Clear
  back = fso.OpenTextFile(verifiedFile, 1).ReadAll
  If Err.Number <> 0 Then
    Err.Clear
    On Error Goto 0
    Exit Function
  End If
  On Error Goto 0
  back = Replace(Replace(back, vbCrLf, vbLf), vbCr, vbLf)
  If back <> (rid & vbLf & u) Then Exit Function
  WriteVerified = True
End Function

' 1.2.5 round-14 (8-B-R2): a fresh 32-hex-char launch id.  Prefer a GUID from
' Scriptlet.TypeLib; if that object is unavailable fall back to a value drawn
' from a randomised generator, so successive launches still differ.
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
    If IsHexToken(g) Then
      NewRunId = g
      Exit Function
    End If
  End If
  ' 1.2.5 round-16 (review 建议): a millisecond seed plus the wall clock's
  ' second/minute is stronger than the bare seconds-of-day Timer.  The GUID
  ' path above is the primary source on every supported Windows.
  Randomize (CLng(Timer * 1000) + Second(Now) * 60 + Minute(Now))
  s = ""
  For i = 1 To 32
    c = Int(Rnd() * 16)
    s = s & Mid("0123456789abcdef", c + 1, 1)
  Next
  NewRunId = s
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

' 1.2.5 round-18 (M2): a real env id is 1..64 chars of [A-Za-z0-9_.-].  Anything
' else -- empty, a leading "-" (i.e. another option), spaces, quotes, "&"/"#"/
' "?" -- is rejected, so it can never be swallowed as a --env value nor injected
' into the panel URL.
Function IsEnvId(s)
  Dim i, c
  IsEnvId = False
  If Len(s) < 1 Or Len(s) > 64 Then Exit Function
  For i = 1 To Len(s)
    c = Mid(s, i, 1)
    If InStr("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_.-", c) = 0 Then Exit Function
  Next
  IsEnvId = True
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

' 1.2.5 round-16 (review 建议): true if a string holds any non-ASCII char.
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
