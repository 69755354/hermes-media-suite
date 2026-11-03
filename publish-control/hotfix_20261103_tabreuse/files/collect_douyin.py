"""Douyin creator-backend data collection.

Interface parity with the Mac side (attribution/douyin_creator_collect.py):
  * same-origin export endpoint via CDP  -> --mode api
  * DOM/XHR fallback                     -> --mode xhr / download
  * attach to an ALREADY OPEN browser over CDP; never launch/close the
    customer's browser (login-state reuse discipline)
  * never read, print or persist cookies; the audit layer redacts
  * output out/douyin/作品列表导出_<YYYYMMDD>.json|csv

Column contract: the source documents require "13 columns" but do not enumerate
them, so the collector is data-driven -- it reads the real header, records the
count and header to evidence/ for cross-check, and never invents column names.
The live creator backend currently returns 16 columns, so the online path
accepts header drift while the offline importer remains strict unless
``allow_drift`` is explicitly set.  Offline mode lets this be exercised without
a browser.
"""

from __future__ import annotations

import csv
import io
import re
import json
import time
from pathlib import Path

from .errors import ConfigError, EXIT_GATE_RED
from .jsonio import write_json, write_text_atomic
from .minimal_xlsx import read_xlsx

EXPECTED_COLUMNS = 13
DEFAULT_CDP_PORT = 9224
EXPORT_ENDPOINT = "creator.douyin.com/web/api/creator/item/list/download"
ACCOUNT_INFO_ENDPOINT = "creator.douyin.com/web/api/media/user/info/"


def _header_of(rows):
    for row in rows:
        if any(str(c).strip() for c in row):
            return [str(c).strip() for c in row]
    return []


def normalize_export(rows, *, expected_columns=EXPECTED_COLUMNS,
                     allow_drift=False) -> dict:
    header = _header_of(rows)
    if not header:
        raise ConfigError("export has no header row")
    data_rows = rows[1:] if rows and _header_of(rows[:1]) else rows
    column_count = len(header)
    column_ok = column_count == expected_columns
    if not column_ok and not allow_drift:
        raise ConfigError(
            f"export has {column_count} columns, expected {expected_columns}; "
            f"header={header!r}", exit_code=EXIT_GATE_RED)
    records = []
    for row in data_rows:
        if not any(str(c).strip() for c in row):
            continue
        padded = list(row) + [""] * (column_count - len(row))
        records.append({header[i]: str(padded[i]) for i in range(column_count)})
    return {"header": header, "column_count": column_count,
            "column_count_ok": column_ok, "row_count": len(records),
            "records": records}


def normalize_account(payload) -> dict:
    """Read the signed-in creator identity from the page's own account API.

    The response shape has changed before; accept the user object both at the
    top level and under ``data``/``user``.  Only identity metadata is kept.
    """
    def walk(value):
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from walk(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from walk(nested)

    for nested in walk(payload if isinstance(payload, dict) else {}):
        uid = nested.get("uid") or nested.get("user_id") or nested.get("sec_uid")
        name = (nested.get("nickname") or nested.get("name")
                or nested.get("user_name") or nested.get("unique_id"))
        if uid or name:
            return {
                "account_id": str(uid or ""),
                "account_name": str(name or ""),
                "uid": str(nested.get("uid") or ""),
                "sec_uid": str(nested.get("sec_uid") or ""),
            }
    return {}


def _account_suffix(normalized) -> str:
    """多号共机时按账号分开落盘，避免后一个号覆盖前一个号。"""
    account = normalized.get("account") if isinstance(normalized, dict) else None
    name = ""
    if isinstance(account, dict):
        name = str(account.get("account_name") or "").strip()
    if not name:
        return ""
    safe = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", name)[:20]
    return ("_" + safe) if safe else ""


def write_outputs(layout, normalized, *, day=None):
    day = day or time.strftime("%Y%m%d")
    suffix = _account_suffix(normalized)
    layout.out_douyin.mkdir(parents=True, exist_ok=True)
    json_path = layout.out_douyin / f"作品列表导出_{day}{suffix}.json"
    csv_path = layout.out_douyin / f"作品列表导出_{day}{suffix}.csv"
    write_json(json_path, normalized)
    # 1.2.5: build the CSV in memory and write it atomically -- a plain "w" open
    # truncates the day's file before the first row is written (GPT item 12).
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(normalized["header"])
    for record in normalized["records"]:
        writer.writerow([record.get(col, "") for col in normalized["header"]])
    write_text_atomic(csv_path, buffer.getvalue(), encoding="utf-8-sig",
                      newline="")
    evidence = layout.evidence / "export-header.json"
    write_json(evidence, {"header": normalized["header"],
                          "column_count": normalized["column_count"],
                          "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    return {"json": str(json_path), "csv": str(csv_path), "evidence": str(evidence)}


def _existing_site_page(context, host):
    """Reuse the tab this program already opened; never spawn a twin."""
    for page in getattr(context, "pages", None) or []:
        try:
            if host in str(page.url or ""):
                return page
        except Exception:
            continue
    return None


def collect_offline(layout, xlsx_path, *, day=None, account=None, **kw):
    rows = read_xlsx(xlsx_path)
    normalized = normalize_export(rows, **kw)
    if isinstance(account, dict) and account:
        normalized["account"] = account
        normalized["account_name"] = account.get("account_name", "")
        normalized["account_id"] = account.get("account_id", "")
    return {"normalized": normalized,
            "outputs": write_outputs(layout, normalized, day=day)}


def collect_via_cdp(layout, cdp_url=None, port=None, **kw):
    """Attach over CDP via Playwright and pull the same-origin export.

    Requires the customer's browser to already be open with the dedicated
    --user-data-dir; this function NEVER launches or closes a browser and never
    touches cookies.  Playwright is a Windows-machine dependency, so this path
    is a real-machine verification item.
    """
    cdp_url = cdp_url or f"http://127.0.0.1:{port or DEFAULT_CDP_PORT}"
    # The creator backend has shipped both 13- and 16-column exports.  The
    # offline importer stays strict by default, but the live path must accept
    # the real header and record it in evidence instead of refusing to collect.
    kw.setdefault("allow_drift", True)
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:
        raise ConfigError(
            "当前运行环境缺少浏览器组件，暂时无法取数，请在客户机重试。",
            exit_code=EXIT_GATE_RED) from exc
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(cdp_url)
        except Exception as exc:
            raise ConfigError(
                "未检测到已登录的工作台，请先打开并登录后再取数。") from exc
        contexts = browser.contexts
        if not contexts:
            raise ConfigError("未检测到已登录的工作台，请先打开并登录后再取数。")
        page = _existing_site_page(contexts[0], "creator.douyin.com")
        created_page = page is None
        if page is None:
            page = contexts[0].new_page()
        try:
            account = {}
            try:
                info = page.request.get(
                    f"https://{ACCOUNT_INFO_ENDPOINT}", timeout=15000)
                if getattr(info, "ok", False):
                    account = normalize_account(info.json())
            except Exception:
                account = {}
            try:
                response = page.request.get(
                    f"https://{EXPORT_ENDPOINT}", timeout=120000)
            except Exception as exc:
                raise ConfigError(
                    "作品列表下载失败，请确认工作台已打开并登录。") from exc
            body = response.body()
            tmp = layout.run / "douyin-export.xlsx"
            tmp.write_bytes(body)
        finally:
            if created_page:
                page.close()
    result = collect_offline(layout, tmp, account=account, **kw)
    if account:
        result["normalized"]["account"] = account
        result["normalized"]["account_name"] = account.get("account_name", "")
        result["normalized"]["account_id"] = account.get("account_id", "")
        from .jsonio import write_json
        write_json(result["outputs"]["json"], result["normalized"])
    return result
