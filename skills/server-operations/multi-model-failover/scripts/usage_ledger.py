#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""usage_ledger.py — 执行器 usage 只读聚合器（2026-08-24 合并版 P1-3）

只读，不改任何文件。从已有数据聚合成本报表：
  - claude: ~/.claude/projects/**/*.jsonl 的 message.usage
  - codex:  ~/.codex/sessions/**/*.jsonl 的 payload.type=token_count
  - DS 侧:  Hermes state.db session_model_usage（可选 --ds）

用法:
  python3 usage_ledger.py [--days 7] [--json]

输出: 按天汇总 + 执行器明细（claude 折 USD/RMB，codex 只报 token）
价格: claude opus-5 $5/$25/$0.5缓存读/$1.25缓存写（可在 PRICES 调整）
"""
import argparse
import glob
import json
import os
import pathlib
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

HOME = pathlib.Path.home()

PRICES = {
    "claude": {"input": 5.0, "output": 25.0, "cache_read": 0.5, "cache_write": 1.25},
}
RATE = 7.2  # USD -> RMB 估算


def load_claude(days: int):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    agg = defaultdict(lambda: {"in": 0, "out": 0, "cr": 0, "cw": 0, "cost": 0.0, "sessions": set()})
    files = glob.glob(str(HOME / ".claude/projects" / "*" / "*.jsonl"))
    for f in files:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(f), timezone.utc)
            if mtime < cutoff:
                continue
            sess = pathlib.Path(f).stem
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    u = (d.get("message") or {}).get("usage") or {}   # 注意：usage 在 message 里，不在顶层！
                    if not u:
                        continue
                    ts = d.get("timestamp", "")
                    date = ts[:10] if ts else mtime.strftime("%Y-%m-%d")
                    tin = u.get("input_tokens", 0) or 0
                    tout = u.get("output_tokens", 0) or 0
                    cr = u.get("cache_read_input_tokens", 0) or 0
                    cw = u.get("cache_creation_input_tokens", 0) or 0
                    a = agg[date]
                    a["in"] += tin
                    a["out"] += tout
                    a["cr"] += cr
                    a["cw"] += cw
                    a["sessions"].add(sess)
                    a["cost"] += (tin * PRICES["claude"]["input"] + tout * PRICES["claude"]["output"]
                                  + cr * PRICES["claude"]["cache_read"] + cw * PRICES["claude"]["cache_write"]) / 1e6
        except Exception:
            continue
    return agg


def load_codex(days: int):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    agg = defaultdict(lambda: {"in": 0, "out": 0, "cached": 0, "reasoning": 0, "total": 0, "sessions": set()})
    files = glob.glob(str(HOME / ".codex/sessions" / "**" / "rollout-*.jsonl"), recursive=True)
    for f in files:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(f), timezone.utc)
            if mtime < cutoff:
                continue
            sess = pathlib.Path(f).stem[:30]
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or "token_count" not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    p = d.get("payload") or {}
                    if p.get("type") != "token_count":
                        continue
                    info = p.get("info") or {}
                    tu = info.get("total_token_usage") or {}
                    ts = d.get("timestamp", "")
                    date = ts[:10] if ts else mtime.strftime("%Y-%m-%d")
                    a = agg[date]
                    a["in"] += tu.get("input_tokens", 0) or 0
                    a["out"] += tu.get("output_tokens", 0) or 0
                    a["cached"] += tu.get("cached_input_tokens", 0) or 0
                    a["reasoning"] += tu.get("reasoning_output_tokens", 0) or 0
                    a["total"] += tu.get("total_tokens", 0) or 0
                    a["sessions"].add(sess)
        except Exception:
            continue
    return agg


def load_ds(days: int):
    db = HOME / ".hermes/state.db"
    if not db.exists():
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    agg = defaultdict(lambda: {"in": 0, "out": 0, "cache": 0, "calls": 0})
    try:
        conn = sqlite3.connect(str(db))
        rows = conn.execute(
            "SELECT model, api_call_count, input_tokens, output_tokens, cache_read_tokens, first_seen FROM session_model_usage"
        ).fetchall()
        conn.close()
        for model, calls, tin, tout, cache, fs in rows:
            if not fs:
                continue
            t = datetime.fromtimestamp(fs, timezone.utc)
            if t < cutoff:
                continue
            date = t.strftime("%Y-%m-%d")
            a = agg[date]
            a["calls"] += calls or 0
            a["in"] += tin or 0
            a["out"] += tout or 0
            a["cache"] += cache or 0
    except Exception:
        return {}
    return agg


def fmt(n):
    return f"{n:,}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ca = load_claude(args.days)
    xa = load_codex(args.days)
    da = load_ds(args.days)

    if args.json:
        print(json.dumps({
            "claude": {k: {**v, "sessions": sorted(v["sessions"])} for k, v in sorted(ca.items())},
            "codex": {k: {**v, "sessions": sorted(v["sessions"])} for k, v in sorted(xa.items())},
            "ds": {k: v for k, v in sorted(da.items())},
        }, ensure_ascii=False, indent=1))
        return

    dates = sorted(set(ca) | set(xa) | set(da))
    if not dates:
        print("近 %d 天无 usage 数据" % args.days)
        return

    print(f"# usage ledger（近 {args.days} 天，只读聚合）\n")
    print("| 日期 | claude 输入 | claude 输出 | claude 缓存读/写 | claude 成本(USD/RMB) | codex 总token | DS 输入/输出 |")
    print("|---|---|---|---|---|---|---|")
    for date in dates:
        c = ca.get(date)
        x = xa.get(date)
        d = da.get(date)
        c_in = fmt(c["in"]) if c else "-"
        c_out = fmt(c["out"]) if c else "-"
        c_cr = fmt(c["cr"]) if c else "-"
        c_cost = f"{c['cost']:.2f}/{c['cost']*RATE:.1f}" if c else "-"
        x_tot = fmt(x["total"]) if x else "-"
        d_in = fmt(d["in"]) if d else "-"
        d_out = fmt(d["out"]) if d else "-"
        print(f"| {date} | {c_in} | {c_out} | {c_cr} | {c_cost} | {x_tot} | {d_in}/{d_out} |")

    tc = sum(v["cost"] for v in ca.values())
    tx = sum(v["total"] for v in xa.values())
    print(f"\n## 汇总\n- claude 估算成本: ${tc:.2f} ≈ ¥{tc*RATE:.1f}")
    print(f"- codex 总 token: {fmt(tx)}（订阅制，不折钱）")
    print(f"- 会话数: claude {len(set(s for v in ca.values() for s in v['sessions']))} / codex {len(set(s for v in xa.values() for s in v['sessions']))}")


if __name__ == "__main__":
    main()
