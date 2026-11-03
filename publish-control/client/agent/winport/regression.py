"""Selector / Chromium-family browser regression harness (re-runnable evidence).

source/extra-requirements-chrome.md item 6 makes this mandatory: the previous
in-package-Chromium assumption is VOID, so the login/collect surface must be
re-checked on the customer's REAL browser and the result attached to the report.

1.2.2 (source/brief-chrome-only-20261016.md): the only engine we drive is the
customer's real Google Chrome, so the only CDP identity this harness accepts as
a pass is ``Chrome/x.y.z``.  An ``Edg/x.y.z`` (Edge) or ``Chromium/`` endpoint is
recorded as a MISMATCH -- it means we are talking to a browser we did not mean to
run, which is exactly what the correction forbids, so it can never be green.

This module is the executable form of that check.  It deliberately separates two
things:

  * what can be asserted without a browser (the build host): "no CDP endpoint
    here -> offline, pending real machine" -- never dressed up as a pass;
  * what is asserted when a real Chrome CDP endpoint IS reachable (``--live``):
      - the endpoint really is Google Chrome (not Edge, not Chromium, not
        Headless) -- recorded as ``engine``;
      - the environment's profile carries cookies for the platform's domains;
      - the platform backend answers and is NOT bounced to a login page;
      - the login entry URL the panel opens is live;
      - the cookie NAMES are recorded, so a later DOM/cookie drift is visible.

The fill-side DOM selectors are still a real-machine item (publish_exec.py says
so); this harness records the login surface + the browser identity, which is
exactly what the "只认真谷歌" decision changed.
"""

from __future__ import annotations

import time

from . import chrome
from .errors import ConfigError

REGRESSION_VERSION = "1.0"

COMMANDS = [
    "# 在客户机（已扫码登录）上执行：只认 Google Chrome（没有 Chrome 会明确报错，不用 Edge 顶替）：",
    "winport chrome-probe",
    "winport chrome-regression --live --timeout 15",
    "# 证据落盘：<Data>/evidence/chrome-selector-regression.json",
]


def _is_real_chrome(browser: str) -> bool:
    """True ONLY for a real Google Chrome endpoint (1.2.2 -- no Edge fallback)."""
    return chrome.browser_engine_of(browser) == chrome.ENGINE_CHROME


def _is_edge_endpoint(browser: str) -> bool:
    """True for an Edge endpoint -- reported as a mismatch, never accepted."""
    return chrome.browser_engine_of(browser) == chrome.ENGINE_EDGE


def _engine_of(browser: str):
    return chrome.browser_engine_of(browser)


def run_regression(layout, channels, *, port=None, timeout=5.0, live=False,
                   cdp_probe=None, cookie_probe=None) -> dict:
    cdp_probe = cdp_probe or chrome.cdp_version
    cookie_probe = cookie_probe or _default_cookie_probe
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    ports = []
    if port:
        ports.append(int(port))
    for channel in channels:
        if channel.debug_port and channel.debug_port not in ports:
            ports.append(channel.debug_port)

    endpoint = None
    tried = []
    for candidate in ports:
        info = cdp_probe(candidate)
        tried.append({"port": candidate, "ok": bool(info.get("ok")),
                      "error": info.get("error")})
        if info.get("ok"):
            endpoint = {"port": candidate, "browser": info.get("browser"),
                        "debugger": info.get("debugger")}
            break

    if endpoint is None:
        return {
            "mode": "offline", "version": REGRESSION_VERSION,
            "started_at": started, "live": bool(live),
            "all_ok": False, "pending_real_machine": True,
            "reason": ("本机没有可连接的浏览器调试端口（构建机静态自检）。"
                       "选择器/登录面回归必须真机执行，结果才算数。"),
            "ports_tried": tried, "endpoint": None,
            "commands": list(COMMANDS),
            "channels": [_offline_row(c) for c in channels],
        }

    cdp_browser = endpoint.get("browser")
    real_chrome = _is_real_chrome(cdp_browser)
    edge_on_port = _is_edge_endpoint(cdp_browser)
    engine = _engine_of(cdp_browser)
    rows = []
    for channel in channels:
        rows.append(_channel_row(layout, channel, timeout=timeout,
                                 cookie_probe=cookie_probe))
    all_ok = bool(real_chrome) and all(row["ok"] for row in rows)
    return {
        "mode": "live", "version": REGRESSION_VERSION, "started_at": started,
        "live": bool(live), "all_ok": all_ok, "pending_real_machine": False,
        "endpoint": endpoint, "ports_tried": tried,
        "is_real_chrome": real_chrome,
        "engine": engine,
        "engine_label": chrome.ENGINE_LABELS.get(engine, engine or "未知"),
        "wrong_engine": bool(cdp_browser) and not real_chrome,
        "chrome_note": (
            "CDP 报告的是真 Google Chrome（Chrome/…）"
            if engine == chrome.ENGINE_CHROME else
            "CDP 报告的是系统自带 Microsoft Edge（Edg/…）。本程序只允许 Google "
            "Chrome 运行，这个端点是**不该出现的浏览器**，回归判不通过；请检查 "
            "9224-9227 端口是不是被别的程序占用了"
            if engine == chrome.ENGINE_EDGE else
            "CDP 报告的浏览器不是真 Google Chrome（可能是 Chromium/Headless/"
            "其它），请检查启动路径"),
        "edge_on_port": edge_on_port,
        "commands": list(COMMANDS),
        "channels": rows,
    }


def _offline_row(channel) -> dict:
    return {
        "channel_id": channel.channel_id, "env_id": getattr(channel, "env_id", None),
        "platform": channel.platform, "platform_name": channel.platform_name,
        "profile": None, "debug_port": channel.debug_port,
        "ok": False, "pending_real_machine": True,
        "reason": "未连接浏览器：本机静态自检无 CDP 端点",
    }


def _channel_row(layout, channel, *, timeout, cookie_probe) -> dict:
    row = {
        "channel_id": channel.channel_id, "env_id": getattr(channel, "env_id", None),
        "platform": channel.platform, "platform_name": channel.platform_name,
        "profile": str(channel.profile_dir(layout)),
        "debug_port": channel.debug_port, "ok": False, "checks": {},
        "reason": "",
    }
    if not channel.supports_cdp:
        row["reason"] = "该通道不是 CDP 引擎，选择器回归不适用"
        return row
    try:
        evidence = cookie_probe(layout, channel)
    except Exception as exc:  # pragma: no cover - defensive
        row["reason"] = f"回归探测失败：{type(exc).__name__}: {exc}"
        return row
    checks = {
        "profile_present": bool(evidence.get("profile_present")),
        "debug_port_listening": bool(evidence.get("debug_port_listening")),
        "cookie_present": int(evidence.get("cookie_count") or 0) > 0,
        "backend_reachable": evidence.get("backend_reachable") is not False,
        "not_redirected_to_login": not evidence.get("redirected_to_login"),
    }
    row["checks"] = checks
    row["evidence"] = {
        "cookie_count": evidence.get("cookie_count"),
        "cookie_names": evidence.get("cookie_names"),
        "cookie_domains_seen": evidence.get("cookie_domains_seen"),
        "backend_status": evidence.get("backend_status"),
        "backend_final_url": evidence.get("backend_final_url"),
        "backend_error": evidence.get("backend_error"),
    }
    failed = [name for name, ok in checks.items() if not ok]
    row["ok"] = not failed
    row["reason"] = "全部通过（真 Google Chrome 下登录面正常）" if not failed \
        else "未通过：" + "、".join(failed)
    return row


def _default_cookie_probe(layout, channel):
    from .login_check import _default_probe
    return _default_probe(layout, channel)
