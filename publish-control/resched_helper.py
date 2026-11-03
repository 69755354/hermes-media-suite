#!/usr/bin/env python3
"""Operator helper: reschedule one prepared item on the client, refresh token, mark batch scheduled."""
import base64, json, os, re, sqlite3, sys, time, urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:18977"
ENV = "/home/ubuntu/workflow/projects/publish_control/.env"
DB = "/home/ubuntu/workflow/projects/publish_control/control.db"
BOT = "/home/ubuntu/workflow/projects/feishu_publish_bot/bot.py"
BATCH_DIR = Path("/home/ubuntu/workflow/projects/feishu_publish_bot/mt_batches")
CID = os.environ.get("PUBLISH_CUSTOMER_ID", "")

def token():
    for line in open(ENV):
        if line.startswith("CONTROL_ADMIN_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no token")

def remote(op, args, timeout=120):
    body = json.dumps({"customer_id": CID, "op": op, "args": args}).encode()
    req = urllib.request.Request(BASE + "/api/remote/exec", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + token()})
    oid = json.load(urllib.request.urlopen(req, timeout=15))["id"]
    for _ in range(timeout + 30):
        row = sqlite3.connect(DB).execute("select status,result from remote_ops where id=?", (oid,)).fetchone()
        if row and row[0] in ("done", "failed"):
            return json.loads(row[1] or "{}")
        time.sleep(1)
    return {"error": "timeout"}

def template():
    src = open(BOT, encoding="utf-8").read()
    m = re.search(r'_MT_RESCHED = r"""(.*?)"""', src, re.S)
    return m.group(1)

def resched(plan, preview, sched):
    code = template() % {"plan": json.dumps(plan, ensure_ascii=True),
                         "sched": json.dumps(sched, ensure_ascii=True),
                         "preview": json.dumps(preview or "", ensure_ascii=True)}
    remote("write", {"path": r"C:\ProgramData\mt_resched.py",
                     "base64": base64.b64encode(code.encode()).decode()}, timeout=60)
    d = remote("exec", {"cmd": ["cmd", "/c", r"C:\ProgramData\mt_resched.bat"], "timeout": 420}, timeout=460)
    out = (d.get("stdout") or "") + "\n" + (d.get("stderr") or "")
    hits = re.findall(r'"confirm_token"\s*:\s*"([^"]+)"', out)
    return (hits[-1] if hits else None), out[-500:]

def main(batch_id, index, sched):
    f = BATCH_DIR / (batch_id + ".json")
    state = json.loads(f.read_text(encoding="utf-8"))
    item = next(i for i in state["items"] if int(i.get("index") or 0) == int(index))
    tok, tail = resched(item["plan_path"], item.get("preview_path"), sched)
    if not tok:
        print("RESCHED FAILED", tail)
        return 2
    item["schedule_at"] = sched
    item["confirm_token"] = tok
    item["status"] = "scheduled"
    item.pop("error", None)
    state["status"] = "scheduled"
    f.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print("OK item", index, sched, "token", tok[:10], "| tail:", tail[-160:].replace("\n", " "))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
