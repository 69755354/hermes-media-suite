"""Local report: out/reports/日报_<date>.xlsx + .md  (Mac parity, section 7.2).

Every number is derived from a ledger or an explicit input.  A field we cannot
obtain is written as None plus a reason -- never back-filled from an old
snapshot (skill-publish-worker-deployment acceptance rule).
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .jsonio import read_json, read_jsonl, write_text_atomic
from .minimal_xlsx import write_xlsx


def _counts(rows, key, flt=None):
    out = {}
    for row in rows:
        value = row.get(key)
        if flt and not flt(row):
            continue
        out[value] = out.get(value, 0) + 1
    return out


def build_daily(layout, *, day=None, collection=None) -> dict:
    day = day or time.strftime("%Y-%m-%d")
    downlink_rows = read_jsonl(layout.downlink_ledger)
    stage2 = read_json(layout.stage2_ledger, default={"entries": {}})
    entries = (stage2 or {}).get("entries", {})

    today_downlink = [r for r in downlink_rows if str(r.get("ts", "")).startswith(day)]
    states = _counts([{"state": v.get("state")} for v in entries.values()], "state")

    published = sum(1 for v in entries.values() if v.get("state") == "CONSUMED")
    unknown = sum(1 for v in entries.values() if v.get("state") == "UNKNOWN")
    reserved = sum(1 for v in entries.values() if v.get("state") == "RESERVED")

    summary = {
        "day": day,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "downlink_events_today": len(today_downlink),
        "downlink_actions_today": _counts(today_downlink, "action"),
        "batches_ready": sum(1 for r in today_downlink if r.get("action") == "READY"),
        "publish_states": states,
        "published_total": published,
        "unknown_total": unknown,
        "reserved_total": reserved,
        "collection": collection,
        "consumption": {"value": None,
                        "reason": "no consumption ledger in this data area"},
    }
    return summary


def render_markdown(summary: dict) -> str:
    lines = [f"# 日报 {summary['day']}", "",
             f"- 生成时间: {summary['generated_at']}",
             f"- 取件事件(今日): {summary['downlink_events_today']}",
             f"- 今日批次就绪(READY): {summary['batches_ready']}"
             f" / 累计已发布: {summary['published_total']}"
             f" / 结果不明: {summary['unknown_total']}"
             f" / 占位未决: {summary['reserved_total']}", ""]
    lines.append("## 取件动作分布（今日）")
    for action, count in sorted(summary["downlink_actions_today"].items()):
        lines.append(f"- {action}: {count}")
    lines.append("")
    collection = summary.get("collection")
    lines.append("## 数据采集")
    if collection:
        lines.append(f"- 作品条数: {collection.get('row_count')}")
        lines.append(f"- 列数: {collection.get('column_count')} "
                     f"(期望 13)")
        lines.append(f"- header: {collection.get('header')}")
    else:
        lines.append("- 本日未采集（None）")
    lines.append("")
    lines.append("## 消耗")
    consumption = summary.get("consumption") or {}
    lines.append(f"- 消耗: {consumption.get('value')} "
                 f"（原因: {consumption.get('reason')}）")
    return "\n".join(lines) + "\n"


def write_report(layout, *, day=None, collection=None) -> dict:
    summary = build_daily(layout, day=day, collection=collection)
    md_path = layout.out_reports / f"日报_{summary['day']}.md"
    xlsx_path = layout.out_reports / f"日报_{summary['day']}.xlsx"
    # 1.2.5: atomic write keeps the previous report if this one is cut short
    write_text_atomic(md_path, render_markdown(summary), encoding="utf-8")

    rows = [
        ["指标", "值"],
        ["日期", summary["day"]],
        ["生成时间", summary["generated_at"]],
        ["取件事件(今日)", summary["downlink_events_today"]],
        ["批次就绪(今日)", summary["batches_ready"]],
        ["累计已发布", summary["published_total"]],
        ["结果不明(UNKNOWN)", summary["unknown_total"]],
        ["占位未决(RESERVED)", summary["reserved_total"]],
    ]
    for action, count in sorted(summary["downlink_actions_today"].items()):
        rows.append([f"动作 {action}", count])
    if collection:
        rows.append(["采集作品条数", collection.get("row_count")])
        rows.append(["采集列数", collection.get("column_count")])
    write_xlsx(xlsx_path, rows, sheet_name="日报")
    return {"summary": summary, "md": str(md_path), "xlsx": str(xlsx_path)}
