#!/usr/bin/env python3
"""Push local video files to the customer PC in <=3MB chunks via remote_ops write."""
import base64, hashlib, json, os, sqlite3, sys, time, urllib.request

ROOT = os.environ.get(
    "PUBLISH_CONTROL_HOME",
    "/home/ubuntu/workflow/projects/publish_control",
)
DB = os.path.join(ROOT, "control.db")
CUST = os.environ.get("PUBLISH_CUSTOMER_ID", "")
TOK = [l.split("=", 1)[1].strip() for l in open(os.path.join(ROOT, ".env"))
       if l.startswith("CONTROL_ADMIN_TOKEN=")][0]
CHUNK = 3_000_000
WORKER_BASE = (os.environ.get("WORKER_BASE")
               or os.path.expandvars(r"%LOCALAPPDATA%\HuolongAgent\publish-worker"))
TMPDIR = os.path.join(WORKER_BASE, "tmp", "upload")
USER_HOME = os.environ.get("USER_HOME") or os.path.expanduser("~")


def fire(op, args, wait=180):
    body = json.dumps({"customer_id": CUST, "op": op, "args": args}).encode()
    r = urllib.request.Request("http://127.0.0.1:18977/api/remote/exec", data=body, method="POST")
    r.add_header("Content-Type", "application/json")
    r.add_header("Authorization", "Bearer " + TOK)
    oid = json.loads(urllib.request.urlopen(r, timeout=15).read())["id"]
    end = time.time() + wait
    while time.time() < end:
        row = sqlite3.connect(DB).execute("select status,result from remote_ops where id=?", (oid,)).fetchone()
        if row[0] in ("done", "failed"):
            return row[0], json.loads(row[1] or "{}")
        time.sleep(0.5)
    return "timeout", {}


def push(src, dst, name):
    data = open(src, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    parts = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
    part_paths = []
    for i, chunk in enumerate(parts):
        p = TMPDIR + "\\" + name + ".p%02d" % i
        st, res = fire("write", {"path": p, "base64": base64.b64encode(chunk).decode()})
        if st != "done" or not res.get("ok"):
            print("chunk fail", name, i, st, str(res)[:200]); return False
        part_paths.append(p)
    ps = ("$o=[IO.File]::Create('%s'); " % dst +
          "".join("$b=[IO.File]::ReadAllBytes('%s'); $o.Write($b,0,$b.Length); " % p for p in part_paths) +
          "$o.Close(); (Get-FileHash -Algorithm SHA256 -LiteralPath '%s').Hash" % dst)
    st, res = fire("exec", {"cmd": ["powershell", "-NoProfile", "-Command", ps], "cwd": USER_HOME, "timeout": 300})
    got = (res.get("stdout") or "").strip().upper()
    ok = got == sha.upper()
    print(("OK  " if ok else "BAD ") + name, "bytes=%d" % len(data), "remote_sha=" + (got or "none")[:16], "expect=" + sha[:16])
    if ok:
        rm = "".join("Remove-Item -LiteralPath '%s' -Force; " % p for p in part_paths)
        fire("exec", {"cmd": ["powershell", "-NoProfile", "-Command", rm], "cwd": USER_HOME, "timeout": 120})
    return ok


if __name__ == "__main__":
    pairs = json.loads(sys.argv[1])
    for src, dst, name in pairs:
        if not push(src, dst, name):
            print("ABORT"); sys.exit(1)
