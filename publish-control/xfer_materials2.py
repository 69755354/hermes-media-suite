#!/usr/bin/env python3
"""Push local videos to the customer PC in <=3MB chunks, assembling with the
client's own Python so non-ASCII (Chinese) file names are safe."""
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
DATA = r"C:\Users\huang\AppData\Local\HuolongAgent\publish-worker"
TMPDIR = DATA + r"\tmp\upload"
INBOX = os.path.join(DATA, "customers", CUST, "inbox")
PY = DATA + r"\.venv\Scripts\python.exe"

ASSEMBLE = (
    "import sys,hashlib,shutil\n"
    "out=sys.argv[1]\n"
    "h=hashlib.sha256()\n"
    "o=open(out,'wb')\n"
    "for p in sys.argv[2:]:\n"
    "    with open(p,'rb') as f:\n"
    "        while True:\n"
    "            b=f.read(1<<20)\n"
    "            if not b: break\n"
    "            o.write(b); h.update(b)\n"
    "o.close()\n"
    "print(h.hexdigest())\n"
)


def fire(op, args, wait=180):
    body = json.dumps({"customer_id": CUST, "op": op, "args": args}).encode()
    r = urllib.request.Request("http://127.0.0.1:18977/api/remote/exec", data=body, method="POST")
    r.add_header("Content-Type", "application/json")
    r.add_header("Authorization", "Bearer " + TOK)
    oid = json.loads(urllib.request.urlopen(r, timeout=20).read())["id"]
    end = time.time() + wait
    while time.time() < end:
        row = sqlite3.connect(DB).execute(
            "select status,result from remote_ops where id=?", (oid,)).fetchone()
        if row[0] in ("done", "failed"):
            return row[0], json.loads(row[1] or "{}")
        time.sleep(0.5)
    return "timeout", {}


def push(src, name, dst_dir=INBOX):
    data = open(src, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    parts = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
    tag = hashlib.md5(name.encode()).hexdigest()[:10]
    part_paths = []
    for i, chunk in enumerate(parts):
        p = "%s\\_up_%s.p%02d" % (TMPDIR, tag, i)
        st, res = fire("write", {"path": p, "base64": base64.b64encode(chunk).decode()}, wait=120)
        if st != "done" or not res.get("ok"):
            print("chunk fail", name, i, st, str(res)[:160]); return False
        part_paths.append(p)
    dst = dst_dir + "\\" + name
    cmd = [PY, "-c", ASSEMBLE, dst] + part_paths
    st, res = fire("exec", {"cmd": cmd, "timeout": 300}, wait=330)
    got = (res.get("stdout") or "").strip().splitlines()
    got = got[-1].strip().lower() if got else ""
    ok = got == sha.lower()
    print(("OK  " if ok else "BAD ") + name, "bytes=%d" % len(data),
          "remote=" + (got or "none")[:16], "expect=" + sha[:16])
    if ok:
        fire("exec", {"cmd": [PY, "-c",
                              "import os,sys\nfor p in sys.argv[1:]:\n    try: os.remove(p)\n    except OSError: pass\n"] + part_paths}, wait=120)
    return ok


if __name__ == "__main__":
    pairs = json.loads(sys.argv[1])
    for src, name in pairs:
        if not push(src, name):
            print("ABORT"); sys.exit(1)
    print("ALL_OK")
