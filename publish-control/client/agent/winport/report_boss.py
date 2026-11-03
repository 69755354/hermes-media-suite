"""Build the single-sheet boss report from collected Douyin/Xingtu JSON.

The report is intentionally flat: eight columns, playback descending, one
totals row.  No third-party spreadsheet library is used.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from .jsonio import read_json, write_json
from .minimal_xlsx import write_xlsx

HEADERS = ["抖音号", "作品名称", "发布时间", "审核状态", "播放量",
           "星图有效播放", "分成(元)", "预估收益(元)"]
MONEY_FORMATS = {7: "0.00", 8: "0.00"}  # 1-based XLSX columns

TITLE_KEYS = ("作品名称", "作品标题", "视频标题", "作品", "标题",
              "item_title", "item_name", "work_name", "title")
PUBLISH_KEYS = ("发布时间", "发布日期", "创建时间", "publish_time",
                "published_at", "create_time")
AUDIT_KEYS = ("审核状态", "审核结果", "状态", "audit_status", "audit")
PLAY_KEYS = ("播放量", "播放数", "播放", "play_count", "play_num", "vv")
ACCOUNT_NAME_KEYS = ("抖音号", "账号名称", "账号", "昵称", "account_name",
                     "nickname", "author_name", "name")
ACCOUNT_ID_KEYS = ("抖音号ID", "账号ID", "账号id", "uid", "sec_uid",
                   "account_id", "user_id")
ITEM_ID_KEYS = ("作品ID", "作品id", "视频ID", "item_id", "aweme_id",
                "video_id", "work_id")


def _num(value) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("¥", "").replace("￥", "")
    text = text.replace("元", "").replace(" ", "")
    if not text:
        return 0.0
    multiplier = 1.0
    if text.endswith("万"):
        multiplier, text = 10000.0, text[:-1]
    elif text.endswith("亿"):
        multiplier, text = 100000000.0, text[:-1]
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) * multiplier if match else 0.0


def _display_time(value) -> str:
    """Render Unix seconds/milliseconds as a readable local timestamp."""
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{10}(?:\d{3})?", text):
        return text
    try:
        stamp = float(text)
        if len(text) == 13:
            stamp /= 1000.0
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stamp))
    except (ValueError, OSError, OverflowError):
        return text


def _norm_title(value) -> str:
    text = str(value or "").strip().lstrip("\ufeff")
    text = re.sub(r"\.(mp4|mov|m4v|avi|mkv|webm|flv)$", "", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"[\s\u200b\u200c\u200d]+", "", text)
    return text.casefold()


def _norm_key(value) -> str:
    return re.sub(r"[\s_\-:：/\\()（）]+", "", str(value or "")).casefold()


def _pick(record, aliases, *, exclude_substrings=()):
    if not isinstance(record, dict):
        return None
    normalized_values = {}
    for key, value in record.items():
        normalized_values.setdefault(_norm_key(key), (key, value))
    for alias in aliases:
        hit = normalized_values.get(_norm_key(alias))
        if hit and not any(part in str(hit[0]) for part in exclude_substrings):
            return hit[1]
    for key, value in record.items():
        normalized = _norm_key(key)
        if any(_norm_key(alias) in normalized for alias in aliases):
            if not any(part in str(key) for part in exclude_substrings):
                return value
    return None


def _account_label(name, account_id) -> str:
    name = str(name or "").strip()
    account_id = str(account_id or "").strip()
    if name and account_id and account_id not in name:
        return f"{name}（{account_id}）"
    return name or account_id or "未登记"


def _doc_account(doc) -> tuple[str, str]:
    if not isinstance(doc, dict):
        return "", ""
    nested = doc.get("account") if isinstance(doc.get("account"), dict) else {}
    name = (doc.get("account_name") or doc.get("nickname") or
            doc.get("name") or nested.get("account_name") or
            nested.get("name") or "")
    account_id = (doc.get("account_id") or doc.get("uid") or
                  doc.get("star_id") or nested.get("account_id") or
                  nested.get("star_id") or "")
    return str(name), str(account_id)


def _load_json_docs(directory: Path, *, sources: list, errors: list):
    docs = []
    if not directory.exists():
        return docs
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        try:
            doc = read_json(path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            errors.append({"file": str(path), "error": type(exc).__name__})
            continue
        if isinstance(doc, dict):
            docs.append((path, doc, path.stat().st_mtime))
            sources.append(str(path))
    return docs


def load_douyin(layout, *, sources=None, errors=None) -> list:
    sources = sources if sources is not None else []
    errors = errors if errors is not None else []
    rows = {}
    for path, doc, mtime in _load_json_docs(layout.out_douyin, sources=sources,
                                            errors=errors):
        normalized = doc.get("normalized") if isinstance(doc.get("normalized"), dict) else doc
        records = normalized.get("records") if isinstance(normalized, dict) else None
        if not isinstance(records, list):
            continue
        doc_name, doc_id = _doc_account(normalized)
        for record in records:
            if not isinstance(record, dict):
                continue
            title = _pick(record, TITLE_KEYS)
            if not title:
                continue
            record_name = _pick(record, ACCOUNT_NAME_KEYS,
                                exclude_substrings=("ID", "id"))
            record_id = _pick(record, ACCOUNT_ID_KEYS)
            label = _account_label(record_name or doc_name,
                                   record_id or doc_id)
            publish = _pick(record, PUBLISH_KEYS)
            audit = _pick(record, AUDIT_KEYS)
            play = _pick(record, PLAY_KEYS,
                         exclude_substrings=("星图", "有效"))
            item_id = _pick(record, ITEM_ID_KEYS)
            row = {
                "account": label,
                "account_name": str(record_name or doc_name or ""),
                "title": str(title).strip(),
                "publish_time": _display_time(publish),
                "audit_status": str(audit or ""),
                "play_count": _num(play),
                "star_valid_play": 0.0,
                "share_amount": 0.0,
                "est_income": 0.0,
                "item_id": str(item_id or ""),
                "granularity": "",
                "source": str(path),
            }
            key = (row["account"], _norm_title(row["title"]),
                   row["publish_time"])
            if key not in rows or mtime >= rows[key][0]:
                rows[key] = (mtime, row)
    return [item[1] for item in sorted(rows.values(), key=lambda x: x[0])]


def load_xingtu(layout, *, sources=None, errors=None) -> dict:
    sources = sources if sources is not None else []
    errors = errors if errors is not None else []
    entries = {}
    granularities = set()
    notes = []
    for path, doc, mtime in _load_json_docs(layout.out_xingtu, sources=sources,
                                            errors=errors):
        if not isinstance(doc, dict):
            continue
        name = str(doc.get("name") or (doc.get("account") or {}).get("name") or "")
        star_id = str(doc.get("star_id") or (doc.get("account") or {}).get("star_id") or "")
        account = _account_label(name, star_id)
        tasks = doc.get("tasks") if isinstance(doc.get("tasks"), list) else []
        task_by_id = {str(t.get("task_id") or ""): t for t in tasks
                      if isinstance(t, dict)}
        items = doc.get("items") if isinstance(doc.get("items"), list) else []
        item_counts = {}
        for item in items:
            if isinstance(item, dict):
                task_id = str(item.get("task_id") or "")
                item_counts[task_id] = item_counts.get(task_id, 0) + 1
        item_task_ids = {str(item.get("task_id") or "") for item in items
                         if isinstance(item, dict)}
        item_reward_sum = {}
        for item in items:
            if isinstance(item, dict):
                tid = str(item.get("task_id") or "")
                item_reward_sum[tid] = item_reward_sum.get(tid, 0.0) + _num(
                    item.get("author_reward_amount"))
        records = []
        for item in items:
            if not isinstance(item, dict):
                continue
            task = task_by_id.get(str(item.get("task_id") or ""), {})
            title = (item.get("item_name") or item.get("item_title")
                     or item.get("task_name") or task.get("task_name"))
            if not title:
                continue
            item_reward = item.get("author_reward_amount")
            item_income = item.get("est_income")
            task_id = str(item.get("task_id") or task.get("task_id") or "")
            if item_reward in (None, "") and item_counts.get(task_id) == 1:
                item_reward = task.get("author_reward_amount")
            if item_income in (None, "") and item_counts.get(task_id) == 1:
                item_income = task.get("est_income")
            if (item.get("author_reward_amount") in (None, "")
                    and item_counts.get(task_id, 0) > 1
                    and task.get("author_reward_amount") not in (None, "", 0, 0.0)):
                notes.append("同一任务含多个作品且未返回作品级分成，未重复分摊任务总额。")
            records.append({
                "account": account,
                "account_name": name,
                "star_id": star_id,
                "title": str(title).strip(),
                "task_id": task_id,
                "item_id": str(item.get("item_id") or ""),
                "publish_time": _display_time(item.get("publish_time")
                                              or task.get("publish_time")),
                "audit_status": str(item.get("audit_status") or task.get("audit_status") or ""),
                "play_count": _num(item.get("play_count")),
                "star_valid_play": _num(item.get("valid_play")),
                "share_amount": _num(item_reward),
                "est_income": _num(item_income),
                "granularity": "item",
                "valid_play_source": item.get("valid_play_source", ""),
                "source": str(path),
            })
            granularities.add("item")
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id_str = str(task.get("task_id") or "")
            has_items = task_id_str in item_task_ids
            if task.get("items") and not has_items:
                continue
            # 任务有作品、但作品级未返回分成：把任务级结算额单独挂一条
            # granularity=task 的记录，只计金额不计播放，避免合计丢失这笔钱。
            task_money_only = False
            if has_items:
                task_reward = _num(task.get("author_reward_amount"))
                if not task_reward or item_reward_sum.get(task_id_str):
                    continue
                task_money_only = True
            title = task.get("task_name")
            if not title:
                continue
            records.append({
                "account": account,
                "account_name": name,
                "star_id": star_id,
                "title": str(title).strip(),
                "task_id": str(task.get("task_id") or ""),
                "item_id": "",
                "publish_time": _display_time(task.get("publish_time")),
                "audit_status": str(task.get("audit_status") or ""),
                "play_count": 0 if task_money_only else _num(task.get("play_count")),
                "star_valid_play": 0 if task_money_only else _num(task.get("valid_play")),
                "share_amount": _num(task.get("author_reward_amount")),
                "est_income": _num(task.get("est_income")),
                "granularity": "task",
                "valid_play_source": "",
                "source": str(path),
            })
            granularities.add("task")
        for record in records:
            key = (record["star_id"], record["task_id"],
                   record["item_id"] or _norm_title(record["title"]))
            if key not in entries or mtime >= entries[key][0]:
                entries[key] = (mtime, record)
    return {
        "entries": [item[1] for item in sorted(entries.values(), key=lambda x: x[0])],
        "granularities": sorted(granularities),
        "notes": sorted(set(notes)),
    }


def _merge_entry(row, entry):
    row["star_valid_play"] += _num(entry.get("star_valid_play"))
    row["share_amount"] += _num(entry.get("share_amount"))
    row["est_income"] += _num(entry.get("est_income"))
    if not row.get("play_count"):
        row["play_count"] = _num(entry.get("play_count"))
    if not row.get("publish_time"):
        row["publish_time"] = entry.get("publish_time", "")
    if not row.get("audit_status"):
        row["audit_status"] = entry.get("audit_status", "")
    row["granularity"] = entry.get("granularity", "")
    row["xingtu_matched"] = True


def build_rows(layout, *, sources=None, errors=None) -> tuple[list, dict]:
    sources = sources if sources is not None else []
    errors = errors if errors is not None else []
    rows = load_douyin(layout, sources=sources, errors=errors)
    xingtu = load_xingtu(layout, sources=sources, errors=errors)
    entries = xingtu["entries"]
    used = set()
    matched = 0
    unmatched = 0
    by_title = {}
    by_item = {}
    for index, row in enumerate(rows):
        by_title.setdefault(_norm_title(row["title"]), []).append(index)
        if row.get("item_id"):
            by_item.setdefault(str(row["item_id"]), []).append(index)

    for entry in entries:
        candidates = []
        if entry.get("item_id") and str(entry["item_id"]) in by_item:
            candidates = [index for index in by_item[str(entry["item_id"])] if index not in used]
        if not candidates:
            candidates = [index for index in by_title.get(_norm_title(entry["title"]), [])
                          if index not in used]
        if len(candidates) > 1 and entry.get("account_name"):
            account_matches = [index for index in candidates
                               if entry["account_name"] in rows[index]["account"]]
            if account_matches:
                candidates = account_matches
        if candidates:
            index = candidates[0]
            used.add(index)
            _merge_entry(rows[index], entry)
            matched += 1
            continue
        if not (_num(entry.get("play_count"))
                or _num(entry.get("star_valid_play"))
                or _num(entry.get("share_amount"))
                or _num(entry.get("est_income"))):
            # 没匹配到抖音作品、且全零的星图条目不再单列，避免表里多出空行
            unmatched += 1
            continue
        rows.append({
            "account": entry["account"],
            "account_name": entry.get("account_name", ""),
            "title": entry["title"],
            "publish_time": entry.get("publish_time", ""),
            "audit_status": entry.get("audit_status", ""),
            "play_count": _num(entry.get("play_count")),
            "star_valid_play": _num(entry.get("star_valid_play")),
            "share_amount": _num(entry.get("share_amount")),
            "est_income": _num(entry.get("est_income")),
            "item_id": entry.get("item_id", ""),
            "granularity": entry.get("granularity", ""),
            "source": entry.get("source", ""),
            "xingtu_matched": False,
        })
        unmatched += 1

    rows.sort(key=lambda row: (-_num(row.get("play_count")), row.get("title", "")))
    granularities = list(xingtu["granularities"])
    if not granularities:
        granularity = "none"
    elif len(granularities) == 1:
        granularity = granularities[0]
    else:
        granularity = "item+task"
    if "task" in granularities and "item" in granularities:
        notes = ["部分星图任务未返回作品级数据，这些任务按任务级粒度呈现。"]
    elif "task" in granularities:
        notes = ["星图未返回作品级数据，星图有效播放按任务级粒度呈现。"]
    else:
        notes = []
    meta = {
        "schema": "winport-boss-report/1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "row_count": len(rows),
        "granularity": granularity,
        "item_level_available": "item" in granularities,
        "matched_xingtu": matched,
        "xingtu_only_rows": unmatched,
        "sources": sources,
        "errors": errors,
        "notes": list(xingtu["notes"]) + notes,
    }
    return rows, meta


def table_rows(rows) -> list:
    # 星图只给到任务级时，任务本身不是一个作品：不单独占一行（否则抖音号位置
    # 会出现 star_id、播放量恒为 0），但金额仍计入合计。
    visible = [row for row in rows if row.get("granularity") != "task"]
    # Task-level money rows only count when the task has no visible work rows;
    # otherwise the same money is already on the work rows and totals double.
    seen_tasks = {row.get("task_id") for row in visible if row.get("task_id")}
    extra_task_rows = [row for row in rows
                       if row.get("granularity") == "task"
                       and row.get("task_id") not in seen_tasks]
    has_item_money = any(_num(row.get("share_amount")) for row in visible)
    money_rows = list(visible) if has_item_money else visible + extra_task_rows
    table = [list(HEADERS)]
    for row in visible:
        table.append([
            row.get("account", ""),
            row.get("title", ""),
            row.get("publish_time", ""),
            row.get("audit_status", ""),
            _num(row.get("play_count")),
            _num(row.get("star_valid_play")),
            round(_num(row.get("share_amount")), 2),
            ("" if not _num(row.get("est_income")) else round(_num(row.get("est_income")), 2)),
        ])
    table.append([
        "合计", f"{len(visible)} 条", "", "",
        sum(_num(row.get("play_count")) for row in money_rows),
        sum(_num(row.get("star_valid_play")) for row in money_rows),
        round(sum(_num(row.get("share_amount")) for row in money_rows), 2),
        round(sum(_num(row.get("est_income")) for row in money_rows), 2),
    ])
    return table


def write_boss_report(layout, *, day=None, out=None) -> dict:
    day = day or time.strftime("%Y%m%d")
    rows, meta = build_rows(layout)
    path = Path(out) if out else (layout.out_reports / f"老板表_{day}.xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_xlsx(path, table_rows(rows), sheet_name="老板表",
               number_formats=MONEY_FORMATS)
    meta_path = path.with_suffix(".meta.json")
    meta["xlsx"] = str(path)
    meta["meta"] = str(meta_path)
    write_json(meta_path, meta)
    return {"xlsx": str(path), "meta": str(meta_path), "row_count": len(rows),
            "granularity": meta["granularity"],
            "item_level_available": meta["item_level_available"],
            "notes": meta["notes"], "errors": meta["errors"]}
