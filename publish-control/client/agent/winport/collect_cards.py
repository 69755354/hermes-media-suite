"""Read per-work money from the task detail cards.

The task/item API returns 0 for work-level money on this account, while the
detail page renders real numbers per work card ("已结算收益" / "预估自然流量收益"
/ "投放流量收益").  This module drives the already-logged-in page, opens every
visible task detail, pages through the cards and hands back per-work money.
"""
from __future__ import annotations

import re

TASK_URL = "https://www.xingtu.cn/sup/creator/user/task"

JS_BUTTONS = """() => {const x=document.evaluate("//*[contains(text(),'\u67e5\u770b\u8be6\u60c5')]",document,null,7,null);let n=0;
for(let k=0;k<x.snapshotLength;k++){const e=x.snapshotItem(k); if((e.innerText||'').trim()==='\u67e5\u770b\u8be6\u60c5') n++;} return n;}"""

JS_CLICK = """(i) => {const x=document.evaluate("//*[contains(text(),'\u67e5\u770b\u8be6\u60c5')]",document,null,7,null);const arr=[];
for(let k=0;k<x.snapshotLength;k++){const e=x.snapshotItem(k); if((e.innerText||'').trim()==='\u67e5\u770b\u8be6\u60c5') arr.push(e);}
const e=arr[i]; if(!e) return false; e.scrollIntoView({block:'center'}); e.click(); return true;}"""

JS_CARDS = """() => [...document.querySelectorAll('.star-ad-video-item, .item-list > div')].filter(c=>c.querySelector('.indicator')).map(card => {
  const m = {};
  card.querySelectorAll('.indicator').forEach(x => {
    const k = x.querySelector('.indicator-label')?.innerText.trim();
    const v = x.querySelector('.indicator-value')?.innerText.trim();
    if (k) m[k] = v;
  });
  const t = card.innerText.split('\\n').map(s=>s.trim()).filter(Boolean);
  return { title: t[0] || '', metrics: m };
})"""

JS_NEXT = """() => {const n=document.querySelector('.btn-next'); if(!n||n.disabled||n.classList.contains('is-disabled')) return false; n.click(); return true;}"""


def _num(value) -> float:
    text = str(value or "").replace("\uffe5", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def _norm(title) -> str:
    return re.sub(r"\s+", "", str(title or ""))


def scrape_cards(context, *, max_tasks: int = 12, max_pages: int = 15) -> list:
    """Return [{title, valid_play, share, est}] scraped from task detail cards."""
    page = context.new_page()
    cards = []
    try:
        page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        total = min(int(page.evaluate(JS_BUTTONS) or 0), max_tasks)
        for index in range(total):
            detail = None
            try:
                with context.expect_page(timeout=15000) as opened:
                    if not page.evaluate(JS_CLICK, index):
                        continue
                detail = opened.value
                detail.wait_for_load_state("domcontentloaded", timeout=30000)
                for _ in range(20):
                    detail.wait_for_timeout(700)
                    if detail.evaluate("()=>document.querySelectorAll('.indicator').length") >= 5:
                        break
                seen = set()
                for _ in range(max_pages):
                    for card in detail.evaluate(JS_CARDS):
                        metrics = card.get("metrics") or {}
                        record = {
                            "title": card.get("title") or "",
                            "valid_play": int(_num(metrics.get("\u6709\u6548\u64ad\u653e\u91cf"))),
                            "share": _num(metrics.get("\u5df2\u7ed3\u7b97\u6536\u76ca")),
                            "est": (_num(metrics.get("\u9884\u4f30\u81ea\u7136\u6d41\u91cf\u6536\u76ca"))
                                    + _num(metrics.get("\u6295\u653e\u6d41\u91cf\u6536\u76ca"))),
                        }
                        key = (record["title"], record["valid_play"], record["share"])
                        if key in seen:
                            continue
                        seen.add(key)
                        cards.append(record)
                    if not detail.evaluate(JS_NEXT):
                        break
                    detail.wait_for_timeout(1500)
            except Exception:
                continue
            finally:
                if detail is not None:
                    detail.close()
                try:
                    page.bring_to_front()
                except Exception:
                    pass
    finally:
        page.close()
    return cards


def apply_cards(data: dict, cards: list) -> int:
    """Fill work-level money on data['items']; returns how many rows got money."""
    items = data.get("items") or []
    if not items or not cards:
        return 0
    pool = [dict(card, used=False) for card in cards]
    filled = 0
    for item in items:
        title = _norm(item.get("item_name"))
        play = int(item.get("valid_play") or 0)
        fresh = [c for c in pool if not c["used"]]
        pick = None
        exact = [c for c in fresh if _norm(c["title"]) == title and c["valid_play"] == play]
        if exact:
            pick = exact[0]
        else:
            same = [c for c in fresh if _norm(c["title"]) == title]
            if same:
                pick = min(same, key=lambda c: abs(c["valid_play"] - play))
        if pick is None:
            continue
        pick["used"] = True
        item["author_reward_amount"] = round(pick["share"], 2)
        item["share_amount"] = round(pick["share"], 2)
        item["est_income"] = round(pick["est"], 2)
        filled += 1
    return filled


def reconcile(data: dict) -> None:
    """Trim rounding overflow so work-level money never exceeds the task total."""
    tasks = {str(t.get("task_id") or ""): t for t in (data.get("tasks") or [])}
    for task_id, task in tasks.items():
        target = round(_num(task.get("author_reward_amount")), 2)
        if not target:
            continue
        items = [i for i in (data.get("items") or [])
                 if str(i.get("task_id") or "") == task_id and _num(i.get("share_amount"))]
        current = round(sum(_num(i.get("share_amount")) for i in items), 2)
        if current <= target:
            continue
        diff = round(current - target, 2)
        for item in sorted(items, key=lambda x: _num(x.get("share_amount"))):
            if diff <= 0:
                break
            take = min(diff, _num(item.get("share_amount")))
            left = round(_num(item.get("share_amount")) - take, 2)
            item["share_amount"] = left
            item["author_reward_amount"] = left
            diff = round(diff - take, 2)
