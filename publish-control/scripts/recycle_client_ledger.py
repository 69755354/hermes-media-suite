#!/usr/bin/env python3
"""列出/回收客户机 run/stage2-ledger.json 里的僵尸占位。

只回收 RESERVED + reservation_schema=2（从未 mark_submit_intent，必然没点发布）。
SUBMIT_INTENT / UNKNOWN 一律只报告，必须先去平台核对结果，禁止自动回收。

用法：
  python3 scripts/recycle_client_ledger.py --customer c_xxxxxxxx            # 只体检
  python3 scripts/recycle_client_ledger.py --customer c_xxxxxxxx --apply    # 回收 RESERVED
"""
import argparse, base64, datetime, json, os, sqlite3, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import remote_pc as rp  # noqa: E402

# 客户机数据根：不写死用户名。WORKER_BASE 优先，其次当前机器的 %LOCALAPPDATA%。
DEFAULT_DATA = (os.environ.get("WORKER_BASE")
                or os.path.expandvars(r"%LOCALAPPDATA%\HuolongAgent\publish-worker"))
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
min_age = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
led = Stage2Ledger(os.path.join(data, "customers", sys.argv[3], "run", "stage2-ledger.json"))
res = []
for k in keys:
    before = led.state(k)
    ok = led.recycle_zombie(k, reason="manual recycle: pre-submit failure left RESERVED",
                            min_age_seconds=min_age)
    res.append({"key": k, "before": before, "recycled": ok})
print(json.dumps({"results": res}, ensure_ascii=False))
"""


def read_remote(customer, path, timeout=60, device=""):
    op = rp.enqueue(customer, "read", {"path": path}, device=device)
    status, result = rp.wait(op, timeout)
    if status != "done" or not result.get("ok"):
        raise SystemExit("read failed: %s %s" % (status, result))
    return json.loads(base64.b64decode(result["base64"]).decode("utf-8"))


def run_remote(customer, cmd, timeout=90, device=""):
    op = rp.enqueue(customer, "exec", {"cmd": cmd, "timeout": timeout}, device=device)
    return rp.wait(op, timeout + 30)


def inflight(customer, db_path=None):
    """控制面里还有没有在途命令。有就别回收——占位可能正被 fill 用着。"""
    db = db_path or os.environ.get("CONTROL_DB") or os.path.join(ROOT, "control.db")
    if not os.path.isfile(db):
        raise SystemExit("找不到控制面数据库 %s，无法确认有无在途命令，已拒绝 --apply" % db)
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    rows = []
    try:
        rows += [(r[0], "command", r[1], r[2]) for r in con.execute(
            "select id, kind, status from commands"
            " where customer_id=? and status not in ('done','failed','cancelled')",
            (customer,))]
        rows += [(r[0], "remote_op", r[1], r[2]) for r in con.execute(
            "select id, op, status from remote_ops"
            " where customer_id=? and status not in ('done','failed')",
            (customer,))]
    except sqlite3.Error as exc:
        raise SystemExit("读控制面数据库失败（%s），已拒绝 --apply" % exc)
    finally:
        con.close()
    return rows


def _age_seconds(value):
    """reserved_at 是 %Y-%m-%dT%H:%M:%S%z 格式；解析不了就当作很老。"""
    try:
        ts = datetime.datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%S%z")
    except (TypeError, ValueError):
        return None
    return (datetime.datetime.now(ts.tzinfo) - ts).total_seconds()


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
    ap.add_argument("--device", default="", help="多设备客户的目标机器")
    ap.add_argument("--min-age-min", type=int, default=30,
                    help="只回收保留超过 N 分钟的占位（默认 30）")
    ap.add_argument("--force", action="store_true",
                    help="控制面存在在途命令时仍强制回收（仅确认过无在途才可用）")
    ns = ap.parse_args()
    cid = ns.customer
    ledger_path = ns.data + r"\customers\%s\run\stage2-ledger.json" % cid
    data = read_remote(cid, ledger_path, device=ns.device)
    entries = data.get("entries") or {}
    rows = blockers(entries, ns.account)
    print("ledger entries=%d blocking=%d" % (len(entries), len(rows)))
    recyclable = []
    for k, v in rows:
        struct_ok = v.get("state") == "RESERVED" and v.get("reservation_schema") == 2
        age = _age_seconds(v.get("reserved_at"))
        young = age is not None and age < ns.min_age_min * 60
        ok = struct_ok and not young
        tag = "可回收" if ok else ("太新，先不动" if struct_ok and young else "需人工核对")
        print("  [%s] %s %s %s" % (tag, v.get("state"),
                                   v.get("reserved_at"), v.get("content_hash", "")[:12]))
        print("      %s" % k)
        if ok:
            recyclable.append(k)
    if not ns.apply or not recyclable:
        return
    live = inflight(cid)
    if live and not ns.force:
        print("拒绝回收：控制面还有 %d 条在途命令" % len(live))
        for row in live[:10]:
            print("  %s %s %s" % (row[1], row[2], row[0]))
        print("确认这些不是发布中的批次后，可加 --force 重跑。")
        raise SystemExit(2)
    script = os.path.join(tempfile.gettempdir(), "recycle_ledger_%d.py" % int(time.time()))
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(REMOTE_SCRIPT)
    remote_script = ns.data + r"\customers\%s\run\recycle_ledger.py" % cid
    payload = base64.b64encode(open(script, "rb").read()).decode()
    op = rp.enqueue(cid, "write", {"path": remote_script, "base64": payload}, device=ns.device)
    st, res = rp.wait(op, 90)
    if st != "done" or not res.get("ok"):
        raise SystemExit("upload failed: %s %s" % (st, res))
    python = ns.data + r"\.venv\Scripts\python.exe"
    cmd = [python, remote_script, ns.data, json.dumps(recyclable), cid,
           str(ns.min_age_min * 60)]
    st, res = run_remote(cid, cmd, 90, device=ns.device)
    print("recycle:", st, res.get("stdout") or res.get("stderr"))
    after = read_remote(cid, ledger_path, device=ns.device)
    left = blockers(after.get("entries") or {}, ns.account)
    print("after: blocking=%d" % len(left))
    for k, v in left:
        print("  [%s] %s" % (v.get("state"), k))


if __name__ == "__main__":
    main()
