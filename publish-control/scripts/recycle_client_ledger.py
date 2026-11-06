#!/usr/bin/env python3
"""列出/回收客户机 run/stage2-ledger.json 里的僵尸占位。

只回收 RESERVED + reservation_schema=2（从未 mark_submit_intent，必然没点发布）。
SUBMIT_INTENT / UNKNOWN 一律只报告，必须先去平台核对结果，禁止自动回收。

用法：
  python3 scripts/recycle_client_ledger.py --customer c_xxxxxxxx            # 只体检
  python3 scripts/recycle_client_ledger.py --customer c_xxxxxxxx --apply    # 回收 RESERVED
"""
import argparse, base64, json, os, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import remote_pc as rp  # noqa: E402

DEFAULT_DATA = r"C:\Users\huang\AppData\Local\HuolongAgent\publish-worker"
REMOTE_SCRIPT = r"""
import json, os, sys
data = sys.argv[1]
root = os.getcwd()
if not os.path.isdir(os.path.join(root, "agent", "winport")):
    print(json.dumps({"ok": False, "error": "cwd is not install root: " + root}))
    raise SystemExit(3)
sys.path.insert(0, root)
from agent.winport.stage2_ledger import Stage2Ledger
keys = json.loads(sys.argv[2])
led = Stage2Ledger(os.path.join(data, "customers", sys.argv[3], "run", "stage2-ledger.json"))
res = []
for k in keys:
    before = led.state(k)
    ok = led.recycle_zombie(k, reason="manual recycle: pre-submit failure left RESERVED")
    res.append({"key": k, "before": before, "recycled": ok})
print(json.dumps({"results": res}, ensure_ascii=False))
"""


def read_remote(customer, path, timeout=60):
    op = rp.enqueue(customer, "read", {"path": path})
    status, result = rp.wait(op, timeout)
    if status != "done" or not result.get("ok"):
        raise SystemExit("read failed: %s %s" % (status, result))
    return json.loads(base64.b64decode(result["base64"]).decode("utf-8"))


def run_remote(customer, cmd, timeout=90):
    op = rp.enqueue(customer, "exec", {"cmd": cmd, "timeout": timeout})
    return rp.wait(op, timeout + 30)


def blockers(entries, account):
    out = []
    for k, v in entries.items():
        if v.get("account_id") != account:
            continue
        if v.get("publish_confirmed") is True:
            continue
        if v.get("state") in ("SUBMIT_INTENT", "UNKNOWN") or v.get("state") == "RESERVED":
            out.append((k, v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer", required=True)
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--account", default="env_1:douyin")
    ap.add_argument("--apply", action="store_true")
    ns = ap.parse_args()
    cid = ns.customer
    ledger_path = ns.data + r"\customers\%s\run\stage2-ledger.json" % cid
    data = read_remote(cid, ledger_path)
    entries = data.get("entries") or {}
    rows = blockers(entries, ns.account)
    print("ledger entries=%d blocking=%d" % (len(entries), len(rows)))
    recyclable = []
    for k, v in rows:
        ok = v.get("state") == "RESERVED" and v.get("reservation_schema") == 2
        print("  [%s] %s %s %s" % ("可回收" if ok else "需人工核对", v.get("state"),
                                   v.get("reserved_at"), v.get("content_hash", "")[:12]))
        print("      %s" % k)
        if ok:
            recyclable.append(k)
    if not ns.apply or not recyclable:
        return
    script = os.path.join(tempfile.gettempdir(), "recycle_ledger_%d.py" % int(time.time()))
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(REMOTE_SCRIPT)
    remote_script = ns.data + r"\customers\%s\run\recycle_ledger.py" % cid
    payload = base64.b64encode(open(script, "rb").read()).decode()
    op = rp.enqueue(cid, "write", {"path": remote_script, "base64": payload})
    st, res = rp.wait(op, 90)
    if st != "done" or not res.get("ok"):
        raise SystemExit("upload failed: %s %s" % (st, res))
    python = ns.data + r"\.venv\Scripts\python.exe"
    cmd = [python, remote_script, ns.data, json.dumps(recyclable), cid]
    st, res = run_remote(cid, cmd, 90)
    print("recycle:", st, res.get("stdout") or res.get("stderr"))
    after = read_remote(cid, ledger_path)
    left = blockers(after.get("entries") or {}, ns.account)
    print("after: blocking=%d" % len(left))
    for k, v in left:
        print("  [%s] %s" % (v.get("state"), k))


if __name__ == "__main__":
    main()
