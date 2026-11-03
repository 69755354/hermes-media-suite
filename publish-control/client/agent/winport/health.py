"""Per-channel liveness + per-channel drop alerts.

Requirement: every platform has its OWN status light and its OWN drop alert --
the alert must name only the slot that dropped, never a lumped "2 accounts
offline".

The cheap probe here is deliberately dependency-free (TCP connect to the
Chromium debug port + a process scan for the exact profile directory), so it
runs on the real Windows machine AND on the Linux static host.  Login validity
itself needs cookie evidence and comes from ``login_check``; this module only
merges that result in and never upgrades an unverified slot to "online".
"""

from __future__ import annotations

import socket
import time

from .jsonio import read_json, write_json

STATUS_ONLINE = "ONLINE"
STATUS_OFFLINE = "OFFLINE"
STATUS_UNVERIFIED = "UNVERIFIED"
STATUS_DISABLED = "DISABLED"
STATUS_UNKNOWN = "UNKNOWN"

FRESH_SECONDS = 1800  # a login-check older than this is informational only


def tcp_listening(host: str, port: int, timeout: float = 0.6) -> bool:
    if not port:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, int(port))) == 0


def profile_present(layout, channel) -> bool:
    path = channel.profile_dir(layout)
    if not path.exists() or not path.is_dir():
        return False
    try:
        return any(path.iterdir())
    except OSError:
        return False


def probe_channel(layout, channel, *, tcp=tcp_listening, processes=None,
                  last_check=None, now=None) -> dict:
    """Return one status row for a single slot.  Never raises."""
    now = now or time.time()
    tcp = tcp or tcp_listening      # callers may pass None meaning "use default"
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
        "login_url": channel.login_url,
        "status": STATUS_UNKNOWN,
        "reason": "",
        "evidence": {},
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if not channel.enabled:
        row["status"] = STATUS_DISABLED
        row["reason"] = "通道已停用（enabled=false）；停用按号生效，不影响其它平台"
        return row

    row["evidence"]["profile_present"] = profile_present(layout, channel)

    from . import proc
    in_use = bool(proc.profile_processes(channel.profile_dir(layout), processes))
    row["evidence"]["profile_in_use"] = in_use

    if channel.supports_cdp:
        up = tcp("127.0.0.1", channel.debug_port)
    else:
        up = in_use  # WebKit has no CDP port; the live process IS the signal
    row["evidence"]["debug_port_listening"] = bool(
        up and channel.supports_cdp)
    row["evidence"]["engine_process_up"] = bool(up)
    row["evidence"]["browser_running"] = bool(up)

    check = _fresh_check(last_check, now)
    if check:
        row["evidence"]["login_check"] = check
        row["status"] = check.get("status", STATUS_UNVERIFIED)
        row["reason"] = check.get("reason", "")
        # The light answers "is the LOGIN valid", which survives closing the
        # browser (the profile and its cookies stay on disk).  Say so plainly
        # instead of pretending the browser is up.
        if row["status"] == STATUS_ONLINE and not up:
            row["reason"] = ("登录有效（" + row["reason"]
                             + "）；当前浏览器未运行（登录态文件仍在磁盘上）")
            row["evidence"]["browser_running"] = False
        if row["status"] == STATUS_ONLINE:
            return row
        if row["status"] in (STATUS_OFFLINE,):
            return row

    if not up:
        row["status"] = STATUS_OFFLINE
        if channel.supports_cdp:
            row["reason"] = (f"浏览器未运行：调试端口 {channel.debug_port} 未监听"
                             f"（先点『开始登录』拉起该通道的浏览器）")
        else:
            row["reason"] = "浏览器未运行：未发现使用该登录态目录的进程"
        return row

    row["status"] = STATUS_UNVERIFIED
    row["reason"] = ("浏览器在跑，但还没做过登录检查（点『我登录好了』"
                     "跑一次 login-check 才算数）")
    return row


def _fresh_check(last_check, now):
    if not isinstance(last_check, dict):
        return None
    ts = last_check.get("checked_at")
    if not ts:
        return None
    try:
        parsed = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return last_check
    return last_check if abs(now - parsed) <= FRESH_SECONDS else None


def state_path(layout):
    return layout.run / "channel-state.json"


def load_state(layout) -> dict:
    raw = read_json(state_path(layout), default=None)
    if not isinstance(raw, dict):
        return {"channels": {}}
    raw.setdefault("channels", {})
    return raw


def save_state(layout, rows) -> dict:
    previous = load_state(layout).get("channels") or {}
    channels = {}
    for row in rows:
        entry = dict(row)
        old = (previous.get(row["channel_id"]) or {}).get("evidence") or {}
        evidence = dict(entry.get("evidence") or {})
        if "login_check" in old and "login_check" not in evidence:
            evidence["login_check"] = old["login_check"]
        entry["evidence"] = evidence
        channels[row["channel_id"]] = entry
    doc = {"updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "channels": channels}
    write_json(state_path(layout), doc)
    return doc


def probe_all(layout, channels, *, tcp=tcp_listening, processes=None) -> list:
    tcp = tcp or tcp_listening
    state = load_state(layout)
    previous = state.get("channels") or {}
    rows = []
    for channel in channels:
        last = (previous.get(channel.channel_id) or {}).get("evidence", {}) \
            .get("login_check")
        rows.append(probe_channel(layout, channel, tcp=tcp, processes=processes,
                                  last_check=last))
    return rows


def notify_transitions(previous_rows, current_rows, notify) -> list:
    """Alert ONLY for slots that just dropped.

    ``notify(title, message)`` is called once per dropped slot, so the customer
    is told exactly which platform went offline -- and is not spammed for the
    other four that are still fine.
    """
    prev = {row["channel_id"]: row for row in (previous_rows or [])}
    dropped = []
    for row in current_rows or []:
        was = prev.get(row["channel_id"])
        was_ok = bool(was) and was.get("status") in (STATUS_ONLINE,)
        now_bad = row.get("status") in (STATUS_OFFLINE,)
        if was_ok and now_bad:
            dropped.append(row)
            title = f"{row['platform_name']} 掉线了"
            notify(title, f"{row['nickname']}（{row['channel_id']}）：{row['reason']}")
    return dropped


def summary_rows(rows) -> list:
    """Compact table for the panel / CLI."""
    return [{"channel_id": r["channel_id"], "platform": r["platform_name"],
             "nickname": r["nickname"], "status": r["status"],
             "reason": r.get("reason", ""), "debug_port": r.get("debug_port"),
             "profile": r.get("profile")} for r in (rows or [])]


# ------------------------------------------------------------------ environments
ENV_STATUS_ORDER = ("OFFLINE", "UNKNOWN", "UNVERIFIED", "ONLINE", "DISABLED")


def aggregate_status(rows) -> str:
    """One light for a whole environment: the worst real state wins.

    DISABLED only if every platform is disabled; otherwise a disabled platform
    never drags the environment light down.
    """
    statuses = [r.get("status") for r in rows if r.get("status")]
    live = [s for s in statuses if s != STATUS_DISABLED]
    pool = live or statuses
    for status in ENV_STATUS_ORDER:
        if status in pool:
            return status
    return STATUS_UNKNOWN


def environments_view(envs, rows) -> list:
    """Group channel rows into the environment cards the panel renders."""
    by_env = {}
    for row in rows or []:
        by_env.setdefault(row.get("env_id"), []).append(row)
    out = []
    if envs:
        for env in envs:
            platforms = by_env.get(env.env_id, [])
            out.append({
                "env_id": env.env_id, "label": env.label,
                "nickname": env.nickname, "profile": env.profile_name,
                "debug_port": env.debug_port, "enabled": env.enabled,
                "proxy": env.proxy, "platforms": env.platforms,
                "status": aggregate_status(platforms),
                "rows": platforms,
            })
    else:
        for env_id, platforms in by_env.items():
            out.append({
                "env_id": env_id or "(默认)", "label": env_id or "(默认)",
                "nickname": env_id or "(默认)", "profile": None,
                "debug_port": platforms[0].get("debug_port") if platforms else None,
                "enabled": True, "proxy": None,
                "platforms": [r.get("platform") for r in platforms],
                "status": aggregate_status(platforms), "rows": platforms,
            })
    return out
