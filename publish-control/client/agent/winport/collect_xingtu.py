"""Xingtu creator-backend data collection.

The collector attaches to the already signed-in browser.  It reads the page's
own same-origin endpoints, never stores cookies, and never launches or closes
the customer's browser.  Work-level rows are collected when the task drawer
returns item data; otherwise the result is explicitly marked as task-level.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .errors import ConfigError, EXIT_GATE_RED
from .jsonio import read_json, write_json

SCHEMA = "winport-xingtu/1.0"
TASK_URL = "https://www.xingtu.cn/sup/creator/user/task"
USER_INFO_ENDPOINT = "https://www.xingtu.cn/u/api/user/info"
TASK_LIST_ENDPOINT = ("https://www.xingtu.cn/gw/api/task/"
                      "author_get_performance_list")
MAX_DETAIL_TASKS = 30
ITEM_LIST_ENDPOINT = ("https://www.xingtu.cn/gw/api/challenge/"
                      "author_get_task_item_list")
DETAIL_PAGE_LIMIT = 10
DETAIL_MAX_PAGES = 12
DETAIL_SCROLLS = 8
DETAIL_URL_TMPL = ("https://www.xingtu.cn/sup/creator/star-ad-unite/detail/{tid}"
                   "?task_id={tid}&match_spu_id={tid}&match_spu_type=1"
                   "&front_source=pc_task_list")
DEFAULT_CDP_PORT = 9224

TASK_ID_KEYS = ("task_id", "taskId", "id")
TASK_NAME_KEYS = ("task_name", "task_title", "taskName", "demand_name", "name", "title")
TASK_AMOUNT_KEYS = ("task_amount", "taskAmount", "total_amount", "amount")
REWARD_KEYS = ("author_reward_amount", "authorRewardAmount", "reward_amount",
               "author_income", "income_amount", "share_amount")
CONSUME_KEYS = ("consume_amount", "consumeAmount", "cost_amount",
                "consumption_amount", "consume")
UNIT_PRICE_KEYS = ("unit_price", "unitPrice", "price")
SETTLE_KEYS = ("settlement_method", "settlement_type", "settle_type",
               "settlement", "settle_mode", "pay_method", "pay_type")

ITEM_ID_KEYS = ("item_id", "itemId", "item_id_str", "aweme_id", "video_id",
                "content_id", "work_id", "item_uid", "aweme_item_id",
                "awemeId", "videoId", "contentId", "workId")
ITEM_TITLE_KEYS = ("item_name", "item_title", "itemName", "work_name",
                   "video_title", "aweme_title", "content_title", "title",
                   "work_title", "video_name", "aweme_name", "caption")
ITEM_PUBLISH_KEYS = ("publish_time", "published_at", "create_time",
                     "created_at", "release_time", "publish_timestamp",
                     "create_timestamp")
ITEM_AUDIT_KEYS = ("audit_status", "auditStatus", "status_desc", "check_status",
                   "audit_status_desc", "status_text")
VALID_PLAY_KEYS = ("star_valid_play", "valid_play_count", "valid_play",
                   "valid_play_num", "validPlay", "effective_play_count",
                   "effective_play", "effective_vv", "valid_vv",
                   "play_valid_count", "valid_play_cnt", "valid_play_times",
                   "effective_play_num", "star_play_valid",
                   "star_valid_play_count", "valid_pv", "effective_pv",
                   "share_vv")
PLAY_KEYS = ("play_count", "playCount", "play_num", "view_count", "vv",
             "play_cnt", "view_num", "total_play")
EST_INCOME_KEYS = ("est_income", "estimated_income", "estimate_income",
                   "predict_income", "income_estimate", "pre_income")
ITEM_SPECIFIC_KEYS = ("item_id", "item_name", "item_title", "work_name",
                      "video_title", "aweme_title", "content_title")


def _first(obj, keys, default=None):
    if not isinstance(obj, dict):
        return default
    for key in keys:
        value = obj.get(key)
        if value is not None and value != "":
            return value
    return default


def parse_number(value) -> float:
    """Parse API numbers/currency strings, including 万/亿 suffixes."""
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
    if not match:
        return 0.0
    try:
        return float(match.group(0)) * multiplier
    except ValueError:
        return 0.0


def _string(value) -> str:
    return "" if value is None else str(value).strip()


def _walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_dicts(value)


def normalize_user(payload) -> dict:
    """Return star_id/name/role from the creator identity response."""
    data = payload if isinstance(payload, dict) else {}
    candidates = [data.get("data"), data.get("user"), data]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        nested = candidate.get("user") if isinstance(candidate.get("user"), dict) else candidate
        star_id = _first(nested, ("star_id", "starId", "user_id", "uid"))
        name = _first(nested, ("name", "nickname", "nick_name", "star_name",
                               "user_name", "unique_id"))
        role = _first(nested, ("role", "role_type", "user_role"))
        if star_id or name:
            return {"star_id": _string(star_id), "name": _string(name),
                    "role": int(role) if str(role).lstrip("-").isdigit() else role}
    return {}



PACK_MERGE_KEYS = ("task_base_info", "author_task_fund_info",
                   "author_performance_fund_info", "demander_info",
                   "task_tag_info")


def _flatten_pack(obj):
    """星图 performance_pack_info_list 的元素把字段放在子对象里，
    这里把已知子对象摊平，供 _looks_like_task/normalize_task 识别。"""
    if not isinstance(obj, dict):
        return obj
    view = dict(obj)
    for key in PACK_MERGE_KEYS:
        nested = obj.get(key)
        if isinstance(nested, dict):
            for k, v in nested.items():
                view.setdefault(k, v)
    return view


def _looks_like_task(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    if any(key in obj for key in ITEM_SPECIFIC_KEYS):
        return False
    if _first(obj, ITEM_ID_KEYS) is not None:
        return False
    task_id = _first(obj, TASK_ID_KEYS)
    if task_id is None or task_id == "":
        return False
    # 任务 ID 是 19 位雪花号；demander_info 里的 16 位短 ID 是客户号，不能当任务
    if str(task_id).isdigit() and len(str(task_id)) < 18:
        return False
    return bool(_first(obj, TASK_NAME_KEYS) is not None
                or _first(obj, TASK_AMOUNT_KEYS) is not None
                or _first(obj, REWARD_KEYS) is not None)


def _money(value) -> float:
    """金额统一转成元。

    gw/api 返回的整数金额单位是千分之一元（厘），与页面显示一一对应：
    author_reward_amount=310 → 页面 ￥0.31；248300 → 页面 ￥248.3。
    页面/导出里的字符串已带 ¥ 或小数，本身就是元，不能二次换算。
    """
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("￥", "").replace("¥", "")
        if not text:
            return 0.0
        # 带小数点的字符串已经是元；纯整数串和整数一样按厘处理
        if "." in text:
            return parse_number(text)
        try:
            return round(int(text) / 1000.0, 3)
        except ValueError:
            return parse_number(text)
    if isinstance(value, int):
        return round(value / 1000.0, 3)
    return parse_number(value)


def normalize_task(obj: dict) -> dict:
    valid_value = _first(obj, VALID_PLAY_KEYS)
    return {
        "task_id": _string(_first(obj, TASK_ID_KEYS)),
        "task_name": _string(_first(obj, TASK_NAME_KEYS)),
        "settlement_method": _first(obj, SETTLE_KEYS, ""),
        "task_amount": _money(_first(obj, TASK_AMOUNT_KEYS)),
        "author_reward_amount": _money(_first(obj, REWARD_KEYS)),
        "consume_amount": _money(_first(obj, CONSUME_KEYS)),
        "unit_price": _money(_first(obj, UNIT_PRICE_KEYS)),
        "valid_play": parse_number(valid_value),
        "valid_play_source": "valid_play" if valid_value is not None else "unavailable",
        "play_count": parse_number(_first(obj, PLAY_KEYS)),
        "est_income": parse_number(_first(obj, EST_INCOME_KEYS)),
        "items": [],
    }


def extract_tasks(payload) -> list:
    found = {}
    order = []
    for obj in _walk_dicts(payload):
        view = _flatten_pack(obj)
        if not _looks_like_task(view):
            continue
        task = normalize_task(view)
        key = task["task_id"] or task["task_name"]
        if key not in found:
            found[key] = task
            order.append(key)
        else:
            current = found[key]
            for field, value in task.items():
                if field == "items":
                    continue
                if current.get(field) in (None, "", 0, 0.0) and value not in (None, "", 0, 0.0):
                    current[field] = value
    return [found[key] for key in order]


def _item_payload(obj: dict) -> dict:
    merged = dict(obj)
    for key in ("item_info", "itemInfo", "item", "work", "video", "content",
                "performance", "statistics", "stats", "metrics", "item_data"):
        nested = obj.get(key)
        if isinstance(nested, dict):
            merged = {**nested, **{k: v for k, v in obj.items()
                                   if k != key and v is not None}}
            break
    return merged


def _looks_like_item(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    if _looks_like_task(obj):
        return False
    view = _item_payload(obj)
    item_id = _first(view, ITEM_ID_KEYS)
    title = _first(view, ITEM_TITLE_KEYS)
    has_metric = (_first(view, VALID_PLAY_KEYS) is not None
                  or _first(view, PLAY_KEYS) is not None
                  or _first(view, REWARD_KEYS) is not None)
    return bool((item_id or title) and has_metric)


def normalize_item(obj: dict, task_id=None) -> dict:
    obj = _item_payload(obj)
    item_id = _string(_first(obj, ITEM_ID_KEYS))
    title = _string(_first(obj, ITEM_TITLE_KEYS))
    valid_value = _first(obj, VALID_PLAY_KEYS)
    play_value = _first(obj, PLAY_KEYS)
    # "星图有效播放" is a different metric from total playback.  Never copy
    # play_count into it: doing so would materially overstate the number.
    valid_source = "valid_play" if valid_value is not None else "unavailable"
    return {
        "task_id": _string(task_id or _first(obj, TASK_ID_KEYS)),
        "item_id": item_id,
        "item_name": title,
        "publish_time": _string(_first(obj, ITEM_PUBLISH_KEYS)),
        "audit_status": _string(_first(obj, ITEM_AUDIT_KEYS)),
        "valid_play": parse_number(valid_value) if valid_value is not None else 0.0,
        "valid_play_source": valid_source,
        "play_count": parse_number(play_value),
        "author_reward_amount": _money(_first(obj, REWARD_KEYS)),
        "consume_amount": _money(_first(obj, CONSUME_KEYS)),
        "task_amount": _money(_first(obj, TASK_AMOUNT_KEYS)),
        "est_income": parse_number(_first(obj, EST_INCOME_KEYS)),
    }


def extract_items(payload, *, task_id=None) -> list:
    found = {}
    order = []
    for obj in _walk_dicts(payload):
        if not _looks_like_item(obj):
            continue
        item = normalize_item(obj, task_id=task_id)
        key = (item["task_id"], item["item_id"] or item["item_name"])
        if key not in found:
            found[key] = item
            order.append(key)
        else:
            current = found[key]
            for field, value in item.items():
                if current.get(field) in (None, "", 0, 0.0) and value not in (None, "", 0, 0.0):
                    current[field] = value
    return [found[key] for key in order]


def _detail_pairs(detail_payloads):
    for entry in detail_payloads or ():
        if isinstance(entry, tuple) and len(entry) == 2:
            yield entry[0], entry[1]
        elif isinstance(entry, dict) and "payload" in entry:
            yield entry.get("task_id"), entry.get("payload")
        else:
            yield None, entry


def build_result(user_payload, performance_payload, detail_payloads=(), *,
                 collected_at=None, source="live") -> dict:
    user = normalize_user(user_payload)
    if not user.get("star_id"):
        raise ConfigError("未能读取星图账号信息，请确认已登录达人后台后重试。")

    tasks = extract_tasks(performance_payload)
    all_items = extract_items(performance_payload)

    for context_task_id, payload in _detail_pairs(detail_payloads):
        task_id = context_task_id
        if not task_id and len(tasks) == 1:
            task_id = tasks[0]["task_id"]
        all_items.extend(extract_items(payload, task_id=task_id or None))

    by_task = {task["task_id"]: task for task in tasks if task["task_id"]}
    deduped = {}
    for item in all_items:
        key = (item.get("task_id"), item.get("item_id") or item.get("item_name"))
        if key not in deduped:
            deduped[key] = item
        else:
            current = deduped[key]
            for field, value in item.items():
                if current.get(field) in (None, "", 0, 0.0) and value not in (None, "", 0, 0.0):
                    current[field] = value

    items = list(deduped.values())
    for item in items:
        task = by_task.get(item.get("task_id"))
        if task:
            task["items"].append(item)
            if not item.get("item_name"):
                item["item_name"] = task["task_name"]
            item["task_name"] = task["task_name"]
        else:
            item["task_name"] = item.get("task_name") or item.get("item_name", "")

    for task in tasks:
        if task.get("items"):
            for item in task["items"]:
                item.setdefault("task_name", task["task_name"])

    granularity = "item" if items else "task"
    notes = ([] if items else
             ["未取得作品级数据，已退化为任务级；星图有效播放无法按作品拆分。"])
    if items and any(item.get("valid_play_source") == "unavailable"
                     for item in items):
        notes.append("部分作品未返回星图有效播放字段，该列留空，未用总播放量代替。")
    return {
        "schema": SCHEMA,
        "collected_at": collected_at or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": source,
        "star_id": user.get("star_id", ""),
        "name": user.get("name", ""),
        "role": user.get("role"),
        "account": user,
        "granularity": granularity,
        "item_level_available": bool(items),
        "task_count": len(tasks),
        "item_count": len(items),
        "tasks": tasks,
        "items": items,
        "notes": notes,
    }


def write_outputs(layout, data, *, day=None, suffix="") -> dict:
    day = day or time.strftime("%Y%m%d")
    layout.out_xingtu.mkdir(parents=True, exist_ok=True)
    json_path = layout.out_xingtu / f"星图数据_{day}{suffix}.json"
    write_json(json_path, data)
    return {"json": str(json_path)}


def _existing_site_page(context, host):
    """Reuse the tab this program already opened; never spawn a twin."""
    for page in getattr(context, "pages", None) or []:
        try:
            if host in str(page.url or ""):
                return page
        except Exception:
            continue
    return None


def collect_offline(layout, user_path, performance_path, detail_paths=(), *,
                    day=None) -> dict:
    user_payload = read_json(Path(user_path))
    performance_payload = read_json(Path(performance_path))
    details = [read_json(Path(path)) for path in detail_paths]
    result = build_result(user_payload, performance_payload, details,
                          source="offline")
    return {"data": result, "outputs": write_outputs(layout, result, day=day)}


def _get_json(page, url, *, timeout_ms=30000):
    try:
        response = page.request.get(url, headers={"Referer": TASK_URL},
                                    timeout=timeout_ms)
    except Exception as exc:
        raise ConfigError("星图后台暂时无法连接，请确认工作台已打开并登录。") from exc
    if not getattr(response, "ok", False):
        raise ConfigError("星图后台暂时没有返回数据，请稍后重试。")
    try:
        return response.json()
    except Exception as exc:
        raise ConfigError("星图后台返回的数据无法识别，请稍后重试。") from exc


def collect_via_cdp(layout, cdp_url=None, port=None, *, day=None, suffix="") -> dict:
    """Attach to the open browser and collect task + work-level data."""
    cdp_url = cdp_url or f"http://127.0.0.1:{port or DEFAULT_CDP_PORT}"
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:
        raise ConfigError(
            "当前运行环境缺少浏览器组件，暂时无法取数，请在客户机重试。",
            exit_code=EXIT_GATE_RED) from exc

    captured = []
    page = None
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cdp_url)
        contexts = browser.contexts
        if not contexts:
            raise ConfigError("未检测到已登录的工作台，请先打开并登录后再取数。")
        page = _existing_site_page(contexts[0], "xingtu.cn")
        created_page = page is None
        if page is None:
            page = contexts[0].new_page()
        try:
            def on_response(response):
                url = str(getattr(response, "url", ""))
                if ("/gw/api/task/" not in url
                    and "/gw/api/challenge/" not in url
                    and "/u/api/user/info" not in url):
                    return
                try:
                    if getattr(response, "ok", False):
                        captured.append((url, response.json()))
                except Exception:
                    return

            csrf_token = None

            def on_request(request):
                nonlocal csrf_token
                try:
                    if "/gw/api/" in str(request.url):
                        token = request.headers.get("x-secsdk-csrf-token")
                        if token:
                            csrf_token = token
                except Exception:
                    return

            page.on("request", on_request)
            page.on("response", on_response)
            try:
                page.goto(TASK_URL, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                raise ConfigError(
                    "星图任务页未能加载，请确认工作台已打开并登录。") from exc
            # \u4efb\u52a1\u5217\u8868\u662f\u9875\u9762\u81ea\u5df1\u53d1\u7684 POST\uff0c\u6162\u7684\u65f6\u5019 2 \u79d2\u5185\u62ff\u4e0d\u5230\uff1b\u7b49\u5230\u5b83\u5230\u4e3a\u6b62\u3002
            for _ in range(20):
                if any("author_get_performance_list" in u for u, _ in captured):
                    break
                page.wait_for_timeout(500)
            page.wait_for_timeout(600)

            user_payload = None
            for url, payload in reversed(captured):
                if "/u/api/user/info" in url:
                    user_payload = payload
                    break
            if user_payload is None:
                user_payload = _get_json(page, USER_INFO_ENDPOINT)
            performance_payload = None
            for url, payload in reversed(captured):
                if "author_get_performance_list" in url:
                    performance_payload = payload
                    break
            if performance_payload is None:
                # \u8fd9\u4e2a\u63a5\u53e3\u53ea\u8ba4 POST\uff0cGET \u4f1a\u8fd4\u56de\u7a7a\u5217\u8868\uff08\u65e7\u7248\u5c31\u662f\u8fd9\u91cc\u9000\u5316\u6210 0 \u4e2a\u4efb\u52a1\uff09\u3002
                try:
                    response = page.request.post(
                        TASK_LIST_ENDPOINT,
                        data=json.dumps({
                            "search_condition": {"exist_valid_brand_ad_order": False,
                                                 "only_light_cooperate_task": False},
                            "page": "1", "limit": "50", "search_source": 1}),
                        headers={"content-type": "application/json",
                                 "x-secsdk-csrf-token": csrf_token or "",
                                 "agw-js-conv": "str",
                                 "x-login-source": "1",
                                 "referer": TASK_URL},
                        timeout=30000)
                    performance_payload = response.json()
                except Exception:
                    performance_payload = _get_json(page, TASK_LIST_ENDPOINT)

            tasks = extract_tasks(performance_payload)
            detail_payloads = []
            # 作品级数据只在任务详情接口里：POST challenge/author_get_task_item_list
            # {task_id,page,limit}。这里直接复用已登录页面的会话逐条取，按
            # pagination.has_more 翻页，收下每页 items（含 share_vv 有效播放）。
            for task in tasks[:MAX_DETAIL_TASKS]:
                task_id = _string(task.get("task_id"))
                if not task_id:
                    continue
                for page_no in range(1, DETAIL_MAX_PAGES + 1):
                    try:
                        response = page.request.post(
                            ITEM_LIST_ENDPOINT,
                            data=json.dumps({"task_id": task_id,
                                             "page": page_no,
                                             "limit": DETAIL_PAGE_LIMIT}),
                            headers={"content-type": "application/json",
                                     "x-secsdk-csrf-token": csrf_token or "",
                                     "agw-js-conv": "str",
                                     "x-login-source": "1",
                                     "referer": TASK_URL},
                            timeout=30000)
                    except Exception:
                        break
                    if not getattr(response, "ok", False):
                        break
                    try:
                        payload = response.json()
                    except Exception:
                        break
                    detail_payloads.append((task_id, payload))
                    pagination = payload.get("pagination") or {}
                    if not pagination.get("has_more"):
                        break

            data = build_result(user_payload, performance_payload, detail_payloads)
            try:
                from .collect_cards import apply_cards, reconcile, scrape_cards
                cards = scrape_cards(contexts[0])
                filled = apply_cards(data, cards)
                reconcile(data)
                if filled:
                    data.setdefault("notes", []).append(
                        f"作品级金额已按作品卡补齐 {filled} 条")
            except Exception:
                data.setdefault("notes", []).append(
                    "作品级金额卡片抓取失败，金额留空")
        finally:
            if created_page:
                page.close()
    return {"data": data, "outputs": write_outputs(layout, data, day=day, suffix=suffix)}


def main(argv=None) -> int:
    import argparse
    from .paths import Layout

    parser = argparse.ArgumentParser(prog="winport.collect_xingtu")
    parser.add_argument("--data")
    parser.add_argument("--day")
    parser.add_argument("--offline-user")
    parser.add_argument("--offline-performance")
    parser.add_argument("--offline-detail", action="append", default=[])
    args = parser.parse_args(argv)
    layout = Layout(data=Path(args.data) if args.data else None).ensure()
    if args.offline_user and args.offline_performance:
        result = collect_offline(layout, args.offline_user,
                                 args.offline_performance,
                                 args.offline_detail, day=args.day)
    else:
        result = collect_via_cdp(layout, day=args.day)
    print(json.dumps({"granularity": result["data"].get("granularity"),
                      "tasks": result["data"].get("task_count"),
                      "items": result["data"].get("item_count"),
                      "output": result["outputs"]["json"]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
