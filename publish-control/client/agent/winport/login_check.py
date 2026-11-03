"""Login evidence, per slot.

Requirement: give "登录有效" as *checkable* evidence (cookies / backend
reachable) **per platform**, and on failure give the concrete reason -- "OK"
alone is not acceptable.

The verdict is built from evidence that can actually be observed:

  1. the slot's profile directory exists and is non-empty
     (login state lives ONLY on the customer machine);
  2. the slot's own debug port is listening (Chromium slots);
  3. the profile's cookie jar holds cookies for the platform's domain(s);
  4. the platform backend answers and is not redirected to a login page.

This module NEVER logs in automatically, NEVER types a password and NEVER
refreshes a QR code (hard constraint, background.md section 3): a human scans
the code in the window the panel opened.

Cookie *values* are never printed or stored -- only counts, names and domains.
"""

from __future__ import annotations

import time

from .errors import ConfigError, EXIT_GATE_RED

EVIDENCES = ("avatar_present", "douyin_id_match", "nickname_match",
             "profile_card_present")

STATUS_ONLINE = "ONLINE"
STATUS_OFFLINE = "OFFLINE"
STATUS_UNVERIFIED = "UNVERIFIED"
STATUS_DISABLED = "DISABLED"

LOGIN_PATH_HINTS = ("login", "signin", "sign-in", "passport", "auth", "sso")


def evaluate_evidences(observed: dict) -> dict:
    """Legacy four-evidence judge (Mac parity: avatar / id / nickname / card)."""
    missing = [name for name in EVIDENCES if not observed.get(name)]
    login_controls = observed.get("login_control_count", 0)
    remaining = observed.get("remaining_profile_processes", 0)
    online = (not missing) and login_controls == 0 and remaining == 0
    return {
        "status": "ONLINE" if online else "OFFLINE",
        "missing_evidences": missing,
        "login_control_count": login_controls,
        "remaining_profile_processes": remaining,
        "detail": {name: bool(observed.get(name)) for name in EVIDENCES},
    }


def _domain_matches(host: str, domains) -> bool:
    host = (host or "").lstrip(".").lower()
    for dom in domains or []:
        dom = dom.lstrip(".").lower()
        if host == dom or host.endswith("." + dom):
            return True
    return False


def filter_cookies(cookies, domains) -> list:
    return [c for c in (cookies or [])
            if _domain_matches(c.get("domain", ""), domains)]


def _looks_like_login(url: str) -> bool:
    low = (url or "").lower()
    return any(hint in low for hint in LOGIN_PATH_HINTS)


def evaluate_channel_evidence(channel, evidence: dict) -> tuple:
    """Pure function: evidence dict -> (status, reason).  Unit-testable."""
    ev = evidence or {}
    if ev.get("probe_error"):
        return STATUS_UNVERIFIED, f"检查过程出错：{ev['probe_error']}"
    if ev.get("profile_present") is False:
        return STATUS_OFFLINE, ("登录态目录不存在或为空：这台机器上这个通道还没登录过，"
                                "先点『开始登录』扫码")
    if channel.supports_cdp and ev.get("debug_port_listening") is False:
        return STATUS_OFFLINE, (f"调试端口 {channel.debug_port} 未监听：这个通道的浏览器"
                                "没在跑（先点『开始登录』）")
    if not channel.supports_cdp:
        if not ev.get("engine_process_up"):
            return STATUS_OFFLINE, "未发现使用该登录态目录的浏览器进程（先点『开始登录』）"
        return STATUS_UNVERIFIED, ("WebKit 通道没有 CDP 端口，读不到 cookie 证据；"
                                   "登录有效性必须在窗口内人工确认（真机项 W17）")
    if ev.get("playwright") is False:
        return STATUS_UNVERIFIED, ("本机没有可用的 playwright，读不到 cookie 证据；"
                                   "只有装了依赖的运行环境才能核验登录态")

    cookies = int(ev.get("cookie_count") or 0)
    domains = "、".join(channel.cookie_domains) or "(未配置域名)"
    if cookies <= 0:
        return STATUS_OFFLINE, (f"{domains} 下 0 条 cookie → 未登录或登录态已失效，"
                                "请在该通道窗口里重新扫码")
    if ev.get("backend_reachable") is False:
        return STATUS_OFFLINE, (f"后台不可达：{ev.get('backend_error') or 'HTTP 请求失败'}"
                                f"（目标 {channel.check_url}）")
    if ev.get("redirected_to_login"):
        return STATUS_OFFLINE, (f"后台被重定向到登录页（{ev.get('backend_final_url')}）"
                                "→ 登录态已失效，请重新扫码")
    status = ev.get("backend_status")
    if isinstance(status, int) and 200 <= status < 400:
        return STATUS_ONLINE, (f"cookie {cookies} 条（{domains}）+ "
                               f"{channel.check_url} 可达（HTTP {status}）")
    return STATUS_UNVERIFIED, (f"cookie 有 {cookies} 条，但后台状态未知"
                               f"（HTTP {status}）——不足以判定登录有效")


def _default_probe(layout, channel, *, tcp=None, timeout_ms=15000) -> dict:
    """Observe the four evidence classes.  Real-machine items return reasons."""
    from . import health
    tcp = tcp or health.tcp_listening
    evidence = {"profile_present": health.profile_present(layout, channel)}

    if channel.supports_cdp:
        evidence["debug_port_listening"] = tcp("127.0.0.1", channel.debug_port)
        if not evidence["debug_port_listening"]:
            return evidence
    else:
        from . import proc
        evidence["engine_process_up"] = bool(
            proc.profile_processes(channel.profile_dir(layout)))
        if not evidence["engine_process_up"]:
            return evidence

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        evidence["playwright"] = False
        return evidence

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(channel.cdp_url())
            contexts = browser.contexts
            context = contexts[0] if contexts else browser.new_context()
            cookies = filter_cookies(context.cookies(), channel.cookie_domains)
            evidence["cookie_count"] = len(cookies)
            evidence["cookie_names"] = sorted({c.get("name", "") for c in cookies})
            evidence["cookie_domains_seen"] = sorted(
                {c.get("domain", "") for c in cookies})
            page = context.pages[0] if context.pages else context.new_page()
            try:
                response = page.request.get(channel.check_url,
                                            timeout=timeout_ms)
                evidence["backend_status"] = response.status
                evidence["backend_final_url"] = response.url
                evidence["redirected_to_login"] = _looks_like_login(response.url)
                evidence["backend_reachable"] = True
            except Exception as exc:  # network / TLS / timeout
                evidence["backend_reachable"] = False
                evidence["backend_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        evidence["probe_error"] = f"{type(exc).__name__}: {exc}"
    return evidence


def check_channel(layout, channel, *, probe=None, processes=None) -> dict:
    """One slot -> one verdict with the evidence that produced it."""
    row = {
        "channel_id": channel.channel_id,
        "env_id": getattr(channel, "env_id", None),
        "platform": channel.platform,
        "platform_name": channel.platform_name,
        "nickname": channel.nickname,
        "account_id": channel.account_id,
        "engine": channel.engine,
        "profile": str(channel.profile_dir(layout)),
        "debug_port": channel.debug_port,
        "check_url": channel.check_url,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if not channel.enabled:
        row.update(status=STATUS_DISABLED,
                   reason="该通道已停用（enabled=false），按号停用不影响其它平台",
                   evidence={})
        return row
    probe = probe or _default_probe
    try:
        evidence = probe(layout, channel) if processes is None \
            else probe(layout, channel, processes=processes)
    except TypeError:
        evidence = probe(layout, channel)
    except Exception as exc:
        evidence = {"probe_error": f"{type(exc).__name__}: {exc}"}
    status, reason = evaluate_channel_evidence(channel, evidence)
    row.update(status=status, reason=reason, evidence=evidence)
    if status == STATUS_OFFLINE:
        # B: a failed login check keeps evidence (screenshot/HTML come from the
        # real driver; on the static host they are honestly marked unavailable).
        try:
            from .evidence import EvidenceStore
            EvidenceStore(layout).capture(
                "login_check", env_id=getattr(channel, "env_id", None),
                channel_id=channel.channel_id, platform=channel.platform,
                error=reason, extra={"status": status,
                                     "evidence": _redact_evidence(evidence)})
        except Exception:
            pass
    return row


def _redact_evidence(evidence: dict) -> dict:
    """Never persist cookie VALUES: only counts/names/domains/status."""
    keep = ("profile_present", "debug_port_listening", "engine_process_up",
            "cookie_count", "cookie_names", "cookie_domains_seen",
            "backend_status", "backend_final_url", "backend_reachable",
            "backend_error", "redirected_to_login", "probe_error")
    return {k: evidence.get(k) for k in keep if k in (evidence or {})}


def check_all(layout, channels, *, probe=None, processes=None) -> list:
    return [check_channel(layout, channel, probe=probe, processes=processes)
            for channel in channels]


def persist(layout, rows) -> None:
    """Merge verdicts into run/channel-state.json (per-slot last result)."""
    from .jsonio import read_json, write_json
    path = layout.run / "channel-state.json"
    doc = read_json(path, default=None)
    if not isinstance(doc, dict):
        doc = {}
    channels = doc.setdefault("channels", {})
    for row in rows:
        entry = channels.setdefault(row["channel_id"], {})
        entry.update({"channel_id": row["channel_id"], "platform": row["platform"],
                      "nickname": row["nickname"], "status": row["status"],
                      "reason": row["reason"]})
        entry.setdefault("evidence", {})["login_check"] = {
            "status": row["status"], "reason": row["reason"],
            "checked_at": row["checked_at"],
            "cookie_count": (row.get("evidence") or {}).get("cookie_count"),
            "backend_status": (row.get("evidence") or {}).get("backend_status"),
        }
    doc["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    write_json(path, doc)


def check_via_cdp(cdp_url, account, layout, *, channel=None):
    """CDP-based check kept for Mac parity.  Needs a channel for the evidence
    rules; without one it stays a real-machine item rather than guessing."""
    if channel is None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:
            raise ConfigError("playwright unavailable: login check is a "
                              "real-machine item", exit_code=EXIT_GATE_RED) from exc
        raise ConfigError("login evidence selectors must be confirmed on the "
                          "Windows WebKit/Chrome build (W17)",
                          exit_code=EXIT_GATE_RED)
    return check_channel(layout, channel)


def summary_text(rows) -> str:
    lines = ["通道".ljust(18), "平台".ljust(8), "状态".ljust(12), "原因/证据"]
    for row in rows:
        lines.append(f"{row['channel_id']:<18} {row['platform_name']:<8} "
                     f"{row['status']:<12} {row.get('reason', '')}")
    return "\n".join(lines)
