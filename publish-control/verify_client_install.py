#!/usr/bin/env python3
"""Fail-fast check that a Windows client really runs the freshly installed build.

Exit 0 only when all three hold:
  1. the process listening on 9223 lives inside %LOCALAPPDATA%\\Programs\\HuolongAgent\\publish-assistant-*
  2. .venv\\pyvenv.cfg 'home' is that program dir's runtime
  3. run\\program-path.txt points at that same program dir (not %TEMP%, not Downloads)

Usage: python3 verify_client_install.py --customer c_xxxx [--timeout 90]
"""
import argparse, base64, json, os, sqlite3, sys, time, urllib.request

BASE = os.environ.get("CONTROL_URL", "http://127.0.0.1:18977").rstrip("/")
ROOT = "/home/ubuntu/workflow/projects/publish_control"
DB = os.path.join(ROOT, "control.db")

PS = r'''$ErrorActionPreference='SilentlyContinue'
$lp = (Get-NetTCPConnection -LocalPort 9223 -State Listen).OwningProcess
"LISTEN_PID:$lp"
if ($lp) { "LISTEN_PATH:" + (Get-Process -Id $lp).Path }
$cfg = "$env:LOCALAPPDATA\HuolongAgent\publish-worker\.venv\pyvenv.cfg"
"VENVCFG:" + (((Get-Content $cfg) | Where-Object { $_ -match '^\s*home' }) -join '')
"PROGPATH:" + (Get-Content "$env:LOCALAPPDATA\HuolongAgent\publish-worker\run\program-path.txt")
try { "HEALTH:" + (Invoke-WebRequest -UseBasicParsing -TimeoutSec 6 http://127.0.0.1:9223/healthz).Content } catch { "HEALTH:ERR" }
'''


def token():
    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
        if line.startswith("CONTROL_ADMIN_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no admin token")


def fire(customer, op, args, wait=120):
    body = json.dumps({"customer_id": customer, "op": op, "args": args}).encode()
    req = urllib.request.Request(BASE + "/api/remote/exec", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token())
    oid = json.loads(urllib.request.urlopen(req, timeout=15).read())["id"]
    end = time.time() + wait
    while time.time() < end:
        row = sqlite3.connect(DB).execute(
            "select status,result from remote_ops where id=?", (oid,)).fetchone()
        if row and row[0] in ("done", "failed"):
            return row[0], json.loads(row[1] or "{}")
        time.sleep(1)
    return "timeout", {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer", required=True)
    ap.add_argument("--timeout", type=int, default=90)
    ns = ap.parse_args()

    st, res = fire(ns.customer, "write", {
        "path": "C:/Windows/Temp/verify_install.ps1",
        "base64": base64.b64encode(PS.encode()).decode()}, wait=ns.timeout)
    if st != "done" or not res.get("ok"):
        print("FAIL write ps1: %s %s" % (st, res.get("error")))
        return 2
    st, res = fire(ns.customer, "exec", {
        "cmd": "powershell -NoProfile -ExecutionPolicy Bypass -File C:\\Windows\\Temp\\verify_install.ps1",
        "cwd": "C:\\Windows", "timeout": ns.timeout}, wait=ns.timeout + 30)
    out = (res or {}).get("stdout", "") or ""
    print(out.strip() or json.dumps(res, ensure_ascii=False))

    vals = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            if k in ("LISTEN_PID", "LISTEN_PATH", "VENVCFG", "PROGPATH", "HEALTH"):
                vals[k] = v.strip()

    exe = vals.get("LISTEN_PATH", "").lower()
    cfg = vals.get("VENVCFG", "").lower()
    progpath = vals.get("PROGPATH", "").rstrip("\\").lower()

    def version_dir(text):
        import re
        m = re.search(r"publish-assistant-[0-9][^\\/\s\"]*", text or "")
        return m.group(0).lower() if m else ""

    problems = []
    if "\\programs\\huolongagent\\publish-assistant-" not in exe:
        problems.append("9223 listener is not the installed program: %r" % exe)
    exe_ver, cfg_ver = version_dir(exe), version_dir(cfg)
    if not cfg_ver or cfg_ver != exe_ver:
        problems.append("pyvenv.cfg home (%s) does not match the live program dir (%s)"
                        % (cfg_ver or cfg, exe_ver or exe))
    if "\\programs\\huolongagent\\publish-assistant-" not in progpath:
        problems.append("program-path.txt is not a permanent install dir: %r" % progpath)
    if version_dir(progpath) != exe_ver:
        problems.append("program-path.txt (%s) points at another build than the listener (%s)"
                        % (version_dir(progpath) or progpath, exe_ver))
    if '"version"' not in out:
        problems.append("healthz did not return a version")

    if problems:
        print("\nFAIL")
        for p in problems:
            print(" -", p)
        return 1
    print("\nPASS: listener, venv base and program-path all point at the installed build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
