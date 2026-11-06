#!/usr/bin/env python3
"""列出/回收客户机 run/stage2-ledger.json 里的僵尸占位。

只回收 RESERVED + reservation_schema=2（从未 mark_submit_intent，必然没点发布），
并且同时满足：
  1. 控制面上该客户没有在途命令（queued / running / needs_reconcile），也没有
     正在跑的远程 exec——发布进行到一半时账本里本来就是 RESERVED，这时回收会让
     同一素材再发一遍；
  2. 占位已保留超过 --min-age-min 分钟（默认 30），给进行中的发布留足时间；
  3. 到客户机上动手前，在客户机侧再核一遍状态与时长（两次检查之间可能有变化）。
SUBMIT_INTENT / UNKNOWN 一律只报告，必须先去平台核对结果，禁止自动回收。

用法：
  python3 scripts/recycle_client_ledger.py --customer c_xxxxxxxx            # 只体检
  python3 scripts/recycle_client_ledger.py --customer c_xxxxxxxx --apply    # 回收

客户机数据目录默认 %LOCALAPPDATA%\\HuolongAgent\\publish-worker（在客户机上展开），
可用 --data 或环境变量 CLIENT_WORKER_BASE 覆盖。代码里不写任何具体用户名。
"""
import argparse
import base64
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_DATA = (os.environ.get("CLIENT_WORKER_BASE")
                or r"%LOCALAPPDATA%\HuolongAgent\publish-worker")
DEFAULT_MIN_AGE_MIN = 30
INFLIGHT_COMMAND_STATES = ("queued", "running", "claimed", "needs_reconcile")
INFLIGHT_OP_STATES = ("queued", "running", "claimed", "needs_reconcile")
KEYS_FILENAME = "recycle_keys.json"

# 在客户机上运行。数据目录、客户、账本全部从脚本自己的位置推出来
# （<data>\customers\<cid>\run\recycle_ledger.py），不依赖命令行里的路径——
# 远程 exec 的参数列表不会展开 %LOCALAPPDATA%。
REMOTE_SCRIPT = r"""
import json, os, sys
from datetime import datetime, timezone
here = os.path.dirname(os.path.abspath(__file__))
root = os.getcwd()
if not os.path.isdir(os.path.join(root, "agent", "winport")):
    print(json.dumps({"ok": False, "error": "cwd is not install root: " + root}))
    raise SystemExit(3)
sys.path.insert(0, root)
from agent.winport.stage2_ledger import Stage2Ledger, RESERVED
spec = json.load(open(os.path.join(here, "recycle_keys.json"), encoding="utf-8"))
min_age = float(spec.get("min_age_min", 30))
led = Stage2Ledger(os.path.join(here, "stage2-ledger.json"))
now = datetime.now(timezone.utc)
res = []
for k in spec.get("keys") or []:
    entry = (led.data.get("entries") or {}).get(k) or {}
    before = entry.get("state")
    try:
        age = (now - datetime.strptime(entry.get("reserved_at") or "", "%Y-%m-%dT%H:%M:%S%z")).total_seconds() / 60
    except ValueError:
        age = None
    if before != RESERVED or entry.get("reservation_schema") != 2 or age is None or age < min_age:
        res.append({"key": k, "before": before, "age_min": age, "recycled": False,
                    "skipped": "state/age changed since the server-side check"})
        continue
    ok = led.recycle_zombie(k, reason="manual recycle: pre-submit failure left RESERVED")
    res.append({"key": k, "before": before, "age_min": round(age, 1), "recycled": ok})
print(json.dumps({"results": res}, ensure_ascii=False))
"""


def _age_minutes(entry, now):
    try:
        reserved = datetime.strptime(str(entry.get("reserved_at") or ""), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None
    return (now - reserved).total_seconds() / 60


def classify(entries, account, *, now=None, min_age_min=DEFAULT_MIN_AGE_MIN):
    """-> (recyclable, manual, too_young): lists of (key, entry, age_min)."""
    now = now or datetime.now(timezone.utc)
    recyclable, manual, too_young = [], [], []
    for k, v in entries.items():
        if v.get("account_id") != account or v.get("publish_confirmed") is True:
            continue
        state = v.get("state")
        if state not in ("RESERVED", "SUBMIT_INTENT", "UNKNOWN"):
            continue
        age = _age_minutes(v, now)
        if state != "RESERVED" or v.get("reservation_schema") != 2:
            manual.append((k, v, age))
        elif age is None or age < min_age_min:
            too_young.append((k, v, age))
        else:
            recyclable.append((k, v, age))
    return recyclable, manual, too_young


def inflight(db_path, customer):
    """Commands / remote exec ops for this customer that are not finished."""
    con = sqlite3.connect(db_path)
    try:
        cmds = con.execute(
            "SELECT id, kind, status FROM commands WHERE customer_id=? AND status IN (%s)"
            % ",".join("?" * len(INFLIGHT_COMMAND_STATES)),
            (customer, *INFLIGHT_COMMAND_STATES)).fetchall()
        ops = con.execute(
            "SELECT id, op, status FROM remote_ops WHERE customer_id=? AND op='exec' AND status IN (%s)"
            % ",".join("?" * len(INFLIGHT_OP_STATES)),
            (customer, *INFLIGHT_OP_STATES)).fetchall()
    finally:
        con.close()
    return [("command", *r) for r in cmds] + [("remote_exec", *r) for r in ops]


def _win_join(*parts):
    return "\\".join(p.strip("\\") for p in parts if p)


def main(argv=None):
    import remote_pc as rp  # noqa: E402  (needs the control-plane checkout)

    ap = argparse.ArgumentParser()
    ap.add_argument("--customer", required=True)
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--account", default="env_1:douyin")
    ap.add_argument("--device", default="")
    ap.add_argument("--min-age-min", type=float, default=DEFAULT_MIN_AGE_MIN)
    ap.add_argument("--apply", action="store_true")
    ns = ap.parse_args(argv)
    cid = ns.customer

    def call(op, args, timeout=90):
        op_id = rp.enqueue(cid, op, args, device=ns.device)
        return rp.wait(op_id, timeout)

    run_dir = _win_join(ns.data, "customers", cid, "run")
    st, res = call("read", {"path": _win_join(run_dir, "stage2-ledger.json")}, 60)
    if st != "done" or not res.get("ok"):
        raise SystemExit("read failed: %s %s" % (st, res))
    entries = (json.loads(base64.b64decode(res["base64"]).decode("utf-8")).get("entries") or {})
    recyclable, manual, too_young = classify(entries, ns.account, min_age_min=ns.min_age_min)
    print("ledger entries=%d recyclable=%d manual=%d too_young=%d"
          % (len(entries), len(recyclable), len(manual), len(too_young)))
    for tag, rows in (("可回收", recyclable), ("需人工核对", manual),
                      ("太新，暂不回收", too_young)):
        for k, v, age in rows:
            print("  [%s] %s reserved_at=%s age_min=%s %s" % (
                tag, v.get("state"), v.get("reserved_at"),
                "?" if age is None else round(age, 1), (v.get("content_hash") or "")[:12]))
            print("      %s" % k)
    if not ns.apply or not recyclable:
        return 0

    busy = inflight(rp.DB, cid)
    if busy:
        print("拒绝回收：该客户还有在途任务，发布进行中时账本本来就是 RESERVED：")
        for row in busy:
            print("  %s %s %s %s" % row)
        return 4

    spec = {"keys": [k for k, _, _ in recyclable], "min_age_min": ns.min_age_min}
    for name, payload in (("recycle_ledger.py", REMOTE_SCRIPT.encode("utf-8")),
                          (KEYS_FILENAME, json.dumps(spec).encode("utf-8"))):
        st, res = call("write", {"path": _win_join(run_dir, name),
                                 "base64": base64.b64encode(payload).decode()}, 90)
        if st != "done" or not res.get("ok"):
            raise SystemExit("upload failed: %s %s %s" % (name, st, res))
    # 字符串命令走 cmd.exe，%LOCALAPPDATA% 会在客户机上展开。
    python = _win_join(ns.data, ".venv", "Scripts", "python.exe")
    cmd = '"%s" "%s"' % (python, _win_join(run_dir, "recycle_ledger.py"))
    st, res = call("exec", {"cmd": cmd, "timeout": 90}, 120)
    print("recycle:", st, res.get("stdout") or res.get("stderr"))
    st, res = call("read", {"path": _win_join(run_dir, "stage2-ledger.json")}, 60)
    if st == "done" and res.get("ok"):
        after = json.loads(base64.b64decode(res["base64"]).decode("utf-8")).get("entries") or {}
        left = classify(after, ns.account, min_age_min=ns.min_age_min)
        print("after: recyclable=%d manual=%d too_young=%d" % tuple(len(x) for x in left))
    return 0


if __name__ == "__main__":
    sys.exit(main())
