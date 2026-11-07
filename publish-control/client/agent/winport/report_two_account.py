"""两个号作品 + 星图 → 固定 20 列老板表（用户 2026-10-20 拍板的格式）。"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

HEADERS = ["号", "作品名称", "发布时间", "审核状态", "播放量", "星图有效播放", "分成(元)",
           "预估收益(元)", "体裁", "完播率", "5s完播率", "封面点击率", "2s跳出率",
           "平均播放时长", "点赞量", "分享量", "评论量", "收藏量", "主页访问量", "粉丝增量"]

_ORDINALS = ("一号", "二号", "三号", "四号", "五号",
             "六号", "七号", "八号", "九号", "十号")


def _ordinal_label(index: int) -> str:
    if 0 <= index < len(_ORDINALS):
        return _ORDINALS[index]
    return "第%d号" % (index + 1)


def _norm(text) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _num(value) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _load(path: Path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("records") or data.get("items") or []
    return data or []


def _write_xlsx(path: Path, rows: list, header: list) -> None:
    from .minimal_xlsx import write_xlsx
    write_xlsx(path, [header] + rows, sheet_name="两个号作品+星图")


_DAY_TOKEN = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{8})")


def _day_forms(day: str) -> set:
    """Collectors write YYYYMMDD; older callers pass YYYY-MM-DD.  Accept both."""
    compact = str(day).replace("-", "")
    forms = {str(day), compact}
    if len(compact) == 8 and compact.isdigit():
        forms.add(f"{compact[:4]}-{compact[4:6]}-{compact[6:]}")
    return forms


def _star_files(folder: Path, day: str) -> list:
    """Every account's Xingtu file for ``day`` (one per account since 1.2.188).

    No file for that day -> all files of the most recent day on disk, never a
    single arbitrary file: picking one file is what left an account at 0.
    """
    files = set()
    for form in _day_forms(day):
        files.update(folder.glob(f"星图数据_{form}*.json"))
    if files:
        return sorted(files)
    by_day = {}
    for path in folder.glob("星图数据_*.json"):
        found = _DAY_TOKEN.search(path.name)
        if found:
            by_day.setdefault(found.group(1).replace("-", ""), []).append(path)
    return sorted(by_day[max(by_day)]) if by_day else []


def _star_pool(paths) -> list:
    pool, seen = [], set()
    for path in paths:
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        owner = _norm(doc.get("name")) if isinstance(doc, dict) else ""
        for item in _load(path):
            vv = _num(item.get("valid_play"))
            share = _num(item.get("share_amount") or item.get("author_reward_amount"))
            title = _norm(item.get("item_name"))
            # Same work seen twice (rerun, or a pre-1.2.188 unsuffixed file
            # next to the per-account ones) must count once.
            key = str(item.get("item_id") or "") or (title, vv, share)
            if key in seen or (title, vv, share) in seen:
                continue
            seen.add(key)
            seen.add((title, vv, share))
            pool.append({"title": title, "raw": item.get("item_name"), "owner": owner,
                         "vv": vv, "share": share, "used": False})
    return pool


def build(layout, day: str | None = None, *, today: str | None = None) -> dict:
    day = day or today or datetime.now().strftime("%Y%m%d")
    pool = _star_pool(_star_files(layout.out_xingtu, day))

    douyin_files = sorted({p for form in _day_forms(day)
                           for p in layout.out_douyin.glob(f"作品列表导出_*{form}*.json")})
    account_order = []
    for path in douyin_files:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        account = str(data.get("account_name") or "")
        if account not in account_order:
            account_order.append(account)
    labels = {name: _ordinal_label(index)
              for index, name in enumerate(account_order)}
    rows = []
    for path in douyin_files:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        account = str(data.get("account_name") or "")
        label = labels.get(account) or account or _ordinal_label(len(account_order))
        owner = _norm(account)
        for r in data.get("records") or []:
            title = _norm(r.get("作品名称"))
            match = None
            # Prefer this account's own Xingtu items, then any account's.
            for cands in ([c for c in pool if c["owner"] and c["owner"] == owner], pool):
                exact = [c for c in cands if not c["used"] and c["title"] == title]
                if exact:
                    match = exact[0]
                    break
                near = [c for c in cands if not c["used"] and title[:14] and c["title"][:14] == title[:14]]
                if len(near) == 1:
                    match = near[0]
                    break
            if match:
                match["used"] = True
            rows.append([label, r.get("作品名称", ""), r.get("发布时间", ""), r.get("审核状态", ""),
                         _num(r.get("播放量")), match["vv"] if match else 0,
                         match["share"] if match else 0.0, 0, r.get("体裁", ""),
                         _num(r.get("完播率")), _num(r.get("5s完播率")), r.get("封面点击率", ""),
                         _num(r.get("2s跳出率")), _num(r.get("平均播放时长")), _num(r.get("点赞量")),
                         _num(r.get("分享量")), _num(r.get("评论量")), _num(r.get("收藏量")),
                         _num(r.get("主页访问量")), _num(r.get("粉丝增量"))])
    star_label = (labels.get(account_order[1]) if len(account_order) > 1
                  else "未匹配")
    owner_labels = {_norm(name): lab for name, lab in labels.items()}
    for c in [x for x in pool if not x["used"] and x["share"] > 0]:
        rows.append([owner_labels.get(c["owner"], star_label), c["raw"], "", "", 0, c["vv"], c["share"], 0,
                     "", "", "", "", "", "", "", "", "", "", "", ""])
    rows.sort(key=lambda x: x[4], reverse=True)
    label_counts = {}
    for row in rows:
        label_counts[row[0]] = label_counts.get(row[0], 0) + 1
    summary = "/".join("%s%d" % (name, count)
                       for name, count in label_counts.items())
    rows.append(["合计", f"共{len(rows)}行（{summary}）", "", "",
                 sum(r[4] for r in rows), sum(r[5] for r in rows),
                 round(sum(r[6] for r in rows), 2), 0,
                 "", "", "", "", "", "", "", "", "", "", "", ""])
    shown = max(_day_forms(day), key=lambda f: ("-" in f, len(f)))  # 文件名保持 YYYY-MM-DD
    out = layout.out_reports / f"两个号作品_星图_{shown}.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_xlsx(out, rows, HEADERS)
    return {"xlsx": str(out), "rows": len(rows) - 1,
            "play": sum(r[4] for r in rows[:-1]), "valid": sum(r[5] for r in rows[:-1]),
            "share": round(sum(r[6] for r in rows[:-1]), 2)}
