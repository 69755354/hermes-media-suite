#!/usr/bin/env python3
r"""Operator CLI for the customer-machine remote channel.

  python3 remote_pc.py ping  --customer c_xxxx
  python3 remote_pc.py exec  --customer c_xxxx -- cmd /c dir
  python3 remote_pc.py read  --customer c_xxxx --path C:/Users\x\f.txt --out f.txt
  python3 remote_pc.py write --customer c_xxxx --path C:/Users\x\f --file local
  python3 remote_pc.py ls    --customer c_xxxx --path C:/Users
  python3 remote_pc.py ops   --customer c_xxxx
"""
import argparse, base64, json, os, sqlite3, sys, time, urllib.request

BASE = os.environ.get("CONTROL_URL", "http://127.0.0.1:18977").rstrip("/")
ROOT = os.environ.get(
    "PUBLISH_CONTROL_HOME",
    "/home/ubuntu/workflow/projects/publish_control",
)
ENV = os.path.join(ROOT, ".env")
DB = os.path.join(ROOT, "control.db")


def admin_token():
    for line in open(ENV, encoding="utf-8"):
        if line.startswith("CONTROL_ADMIN_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no admin token")


def enqueue(customer, op, args):
    body = json.dumps({"customer_id": customer, "op": op, "args": args}).encode()
    req = urllib.request.Request(BASE + "/api/remote/exec", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + admin_token())
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    if not data.get("ok"):
        raise SystemExit(str(data))
    return data["id"]


def wait(op_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        row = sqlite3.connect(DB).execute(
            "select status,result from remote_ops where id=?", (op_id,)).fetchone()
        if row and row[0] in ("done", "failed"):
            return row[0], json.loads(row[1] or "{}")
        time.sleep(1)
    return "timeout", {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("op", choices=["ping", "exec", "read", "write", "ls", "ops"])
    ap.add_argument("--customer", required=True)
    ap.add_argument("--path")
    ap.add_argument("--file")
    ap.add_argument("--out")
    ap.add_argument("--timeout", type=int, default=60)
    ns, extra = ap.parse_known_args()
    # argparse keeps the '--' separator in parse_known_args; the agent would
    # try to exec a program literally named '--' (WinError 2).
    while extra and extra[0] == "--":
        extra = extra[1:]

    if ns.op == "ops":
        rows = sqlite3.connect(DB).execute(
            "select id,op,status,created from remote_ops where customer_id=?"
            " order by created desc limit 20", (ns.customer,)).fetchall()
        for r in rows:
            print(r[0], r[1], r[2], time.strftime("%H:%M:%S", time.localtime(r[3])))
        return

    if ns.op == "exec":
        cmd = list(extra)
        if not cmd:
            raise SystemExit("give a command after --")
        args = {"cmd": cmd if len(cmd) > 1 else cmd[0], "timeout": ns.timeout}
    elif ns.op in ("read", "write"):
        args = {"path": ns.path}
        if ns.op == "write":
            args["base64"] = base64.b64encode(open(ns.file, "rb").read()).decode()
    elif ns.op == "ls":
        args = {"path": ns.path or "."}
    else:
        args = {}

    op_id = enqueue(ns.customer, ns.op, args)
    status, result = wait(op_id, timeout=ns.timeout + 30)
    if ns.op == "read" and status == "done" and result.get("base64"):
        data = base64.b64decode(result["base64"])
        if ns.out:
            open(ns.out, "wb").write(data)
            print("saved", ns.out, len(data), "bytes")
        else:
            sys.stdout.write(data.decode("utf-8", "replace"))
        return
    print(json.dumps({"status": status, **result}, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    main()
