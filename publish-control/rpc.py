#!/usr/bin/env python3
"""Run a command on the customer PC with an explicit cwd (inherited cwd is stale)."""
import json, os, sqlite3, sys, time, urllib.request

CUST = os.environ.get("PUBLISH_CUSTOMER_ID", "")
ROOT = os.environ.get(
    "PUBLISH_CONTROL_HOME",
    "/home/ubuntu/workflow/projects/publish_control",
)
DB = os.path.join(ROOT, "control.db")
TOK = [l.split("=", 1)[1].strip() for l in open(os.path.join(ROOT, ".env"))
       if l.startswith("CONTROL_ADMIN_TOKEN=")][0]


def fire(op, args, wait=90):
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
        time.sleep(1)
    return "timeout", {}


if __name__ == "__main__":
    ns = sys.argv[1:]
    if ns and ns[0] == "put":
        import base64 as b64
        data = open(ns[1], "rb").read()
        st, res = fire("write", {"path": ns[2], "base64": b64.b64encode(data).decode()}, wait=120)
        print(st, res.get("ok"), res.get("bytes"), res.get("error") or "")
    elif ns and ns[0] == "save":
        st, res = fire("read", {"path": ns[1]}, wait=120)
        if st == "done" and res.get("base64"):
            import base64 as b64
            data = b64.b64decode(res["base64"])
            open(ns[2], "wb").write(data)
            print("saved", ns[2], len(data), "bytes")
        else:
            print(st, res.get("error") or "no data")
    elif ns and ns[0] in ("ping", "ls", "read"):
        print(json.dumps(fire(ns[0], {"path": ns[1]} if len(ns) > 1 and ns[0] != "ping" else {}), ensure_ascii=False)[:8000])
    else:
        cwd = "C:\\Windows"
        if ns and ns[0].startswith("cwd="):
            cwd = ns[0][4:]
            ns = ns[1:]
        status, res = fire("exec", {"cmd": ns, "cwd": cwd, "timeout": 60})
        print(status, res.get("returncode"))
        print((res.get("stdout") or "")[:8000])
        if res.get("stderr"):
            print("STDERR:", (res.get("stderr") or "")[:2000])
        if res.get("error"):
            print("ERROR:", res["error"])
