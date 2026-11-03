#!/usr/bin/env python3
"""从 Hermes agent.log 统计某日 LLM API 消耗（含轮转文件），按高峰/空闲算钱。

用法:
    python3 analyze_agent_log_cost.py <agent.log路径> [agent.log.1路径 ...] [--date 2026-08-18]

示例:
    python3 analyze_agent_log_cost.py ~/.hermes/logs/agent.log ~/.hermes/logs/agent.log.1
    # 广州小鹿:
    ssh -p 2222 ubuntu@127.0.0.1 "python3 ~/.hermes/scripts/analyze_agent_log_cost.py ~/.hermes/profiles/customer/logs/agent.log ~/.hermes/profiles/customer/logs/agent.log.1"

输出: 每文件调用数/in/out/hit/total，合计后按高峰(9-12,14-18)与空闲分价格估算成本。
价格: Flash 空闲 0.05/1.5/4.5 元每百万, 高峰 0.10/3.0/9.0 (命中/未命中/输出)。
"""
import re
import sys
from datetime import datetime


# DeepSeek V4 Flash 价格 (元/百万 tokens): (缓存命中, 未命中, 输出)
PRICES = {
    "idle": (0.05, 1.5, 4.5),
    "peak": (0.10, 3.0, 9.0),
}


def is_peak(dt: datetime) -> bool:
    return (9 <= dt.hour < 12) or (14 <= dt.hour < 18)


def stat_file(path: str, date_prefix: str):
    """返回 {calls, in, out, hit, total, peak_calls, peak_in, peak_hit, peak_out, idle_calls, idle_in, idle_hit, idle_out}"""
    agg = {k: 0 for k in
           ["calls", "in", "out", "hit", "total",
            "peak_calls", "peak_in", "peak_hit", "peak_out",
            "idle_calls", "idle_in", "idle_hit", "idle_out"]}
    pat_call = re.compile(r"API call #\d+:")
    pat_in = re.compile(r"in=(\d+)")
    pat_out = re.compile(r"out=(\d+)")
    pat_cache = re.compile(r"cache=(\d+)/")
    pat_time = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d\d):(\d\d)")

    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if date_prefix not in line or "API call" not in line:
                    continue
                if not pat_call.search(line):
                    continue
                agg["calls"] += 1
                tm = pat_time.match(line)
                peak = is_peak(datetime(2026, 1, 1, int(tm.group(2)), int(tm.group(3)))) if tm else False
                m_in = pat_in.search(line)
                m_out = pat_out.search(line)
                m_cache = pat_cache.search(line)
                in_tok = int(m_in.group(1)) if m_in else 0
                out_tok = int(m_out.group(1)) if m_out else 0
                hit_tok = int(m_cache.group(1)) if m_cache else 0
                agg["in"] += in_tok
                agg["out"] += out_tok
                agg["hit"] += hit_tok
                agg["total"] += in_tok + out_tok
                bucket = "peak" if peak else "idle"
                agg[f"{bucket}_calls"] += 1
                agg[f"{bucket}_in"] += in_tok
                agg[f"{bucket}_hit"] += hit_tok
                agg[f"{bucket}_out"] += out_tok
    except FileNotFoundError:
        print(f"[skip] {path} 不存在")
        return None
    return agg


def cost_for(bucket: str, agg: dict):
    hp, mp, op = PRICES[bucket]
    in_tok = agg[f"{bucket}_in"]
    hit = agg[f"{bucket}_hit"]
    out = agg[f"{bucket}_out"]
    miss = in_tok - hit
    return hit / 1e6 * hp + miss / 1e6 * mp + out / 1e6 * op


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--date")]
    date_prefix = "2026-08-18"
    for a in sys.argv[1:]:
        if a.startswith("--date"):
            idx = sys.argv.index(a)
            if idx + 1 < len(sys.argv):
                date_prefix = sys.argv[idx + 1]

    if not args:
        print(__doc__)
        sys.exit(1)

    tot = {k: 0 for k in ["calls", "in", "out", "hit", "total",
                          "peak_calls", "peak_in", "peak_hit", "peak_out",
                          "idle_calls", "idle_in", "idle_hit", "idle_out"]}
    for path in args:
        agg = stat_file(path, date_prefix)
        if not agg:
            continue
        print(f"{path}: 调用={agg['calls']} in={agg['in']:,} out={agg['out']:,} hit={agg['hit']:,} total={agg['total']:,}")
        for k in tot:
            tot[k] += agg[k]

    peak_cost = cost_for("peak", tot)
    idle_cost = cost_for("idle", tot)
    print("=== 合计 ===")
    print(f"调用={tot['calls']} in={tot['in']:,} out={tot['out']:,} hit={tot['hit']:,} total={tot['total']:,} miss={tot['in']-tot['hit']:,}")
    print(f"高峰({tot['peak_calls']}次)≈{peak_cost:.2f}元  空闲({tot['idle_calls']}次)≈{idle_cost:.2f}元  合计≈{peak_cost+idle_cost:.2f}元")


if __name__ == "__main__":
    main()
