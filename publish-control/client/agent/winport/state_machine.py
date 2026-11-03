"""D · 环境/账号状态机：未登录 / 有效 / 掉线 / 限流 / 封禁 / 未知。

source/design-refs-mainstream.md D: 主流工具把「掉线」和「限流/封禁」混成一个
红灯，客户看到灯红了也不知道是去扫码还是等一会儿还是找我们。这里把它拆成状态机：

    NOT_LOGGED_IN 未登录   —— 这个号还没登录过（cookie 0 条且从没有效过）
    VALID         有效     —— 登录证据 + 后台可达
    DROPPED       掉线     —— 曾经有效，现在 cookie 没了 / 被跳登录页 / 后台不可达
    RATE_LIMITED  限流     —— 登录还在，但平台返回 429 / "操作频繁"（等一会儿会好）
    BANNED        封禁     —— 平台返回 403/451 且带封禁标记（扫码没用，要找我们）
    UNKNOWN       未知     —— 只有装了依赖的运行环境 + 真机才能判定（不猜）

判定口径全部写在下面对应的 ``_*_marker`` / 优先级里，报告里引用同一段代码，
避免「口径在文档里、实现又在另一处」。状态变化：
  * 反映到面板灯（``annotate`` 给每行加 ``account_state`` / ``account_state_label``）；
  * 告警**只提醒受影响的那个环境**（``notify_state_changes`` 按 env 聚合）。

限流/封禁的判定**不靠猜**：平台后台 HTTP 状态码 + 页面/错误码里的明确标记，
两样都没有就只能是 UNKNOWN，绝不把「查不到」说成「正常」或「封禁」。
"""

from __future__ import annotations

from . import health

NOT_LOGGED_IN = "NOT_LOGGED_IN"
VALID = "VALID"
DROPPED = "DROPPED"
RATE_LIMITED = "RATE_LIMITED"
BANNED = "BANNED"
UNKNOWN = "UNKNOWN"
DISABLED = "DISABLED"      # 管理态（enabled=false），不属于 6 个运行态

STATES = (NOT_LOGGED_IN, VALID, DROPPED, RATE_LIMITED, BANNED, UNKNOWN)

LABELS = {
    NOT_LOGGED_IN: "未登录",
    VALID: "有效",
    DROPPED: "掉线",
    RATE_LIMITED: "限流",
    BANNED: "封禁",
    UNKNOWN: "未知",
    DISABLED: "已停用",
}

#: worst-first for aggregating several platforms into one environment light
SEVERITY = (BANNED, DROPPED, RATE_LIMITED, UNKNOWN, NOT_LOGGED_IN, VALID, DISABLED)

BAN_STATUS_CODES = (403, 451)
BAN_TEXT_MARKERS = ("封禁", "封号", "永久封", "账号异常", "账号被限制", "停止使用",
                    "永久限制", "banned", "account suspended")
RATE_STATUS_CODES = (429,)
RATE_TEXT_MARKERS = ("限流", "操作频繁", "请求过于频繁", "访问过于频繁", "稍后",
                     "too many requests", "rate limit")
RATE_ERROR_CODES = ("RATE_LIMITED", "TOO_MANY_REQUESTS", "TOO_FAST")
BAN_ERROR_CODES = ("BANNED", "ACCOUNT_BANNED", "ACCOUNT_SUSPENDED")


def _evidence(row) -> dict:
    return (row or {}).get("evidence") or {}


def _text_blob(row) -> str:
    parts = [str((row or {}).get("reason") or "")]
    ev = _evidence(row)
    for key in ("platform_error", "backend_final_url", "backend_error",
                "note", "state_reason"):
        if ev.get(key):
            parts.append(str(ev[key]))
    return " ".join(parts)


def _ban_marker(row) -> str | None:
    ev = _evidence(row)
    code = str(ev.get("platform_error_code") or "").upper()
    if code in BAN_ERROR_CODES or ev.get("ban_indicator"):
        return f"平台错误码 {code} / ban_indicator"
    status = ev.get("backend_status")
    if status in BAN_STATUS_CODES:
        blob = _text_blob(row).lower()
        if any(marker in blob for marker in BAN_TEXT_MARKERS):
            return f"HTTP {status} + 封禁标记"
    blob = _text_blob(row).lower()
    if any(marker in blob for marker in BAN_TEXT_MARKERS):
        return "页面/日志带封禁标记"
    return None


def _rate_marker(row) -> str | None:
    ev = _evidence(row)
    code = str(ev.get("platform_error_code") or "").upper()
    if code in RATE_ERROR_CODES:
        return f"平台错误码 {code}"
    if ev.get("retry_after") is not None:
        return f"平台 Retry-After={ev.get('retry_after')}"
    if ev.get("backend_status") in RATE_STATUS_CODES:
        return f"HTTP {ev.get('backend_status')}"
    blob = _text_blob(row).lower()
    if any(marker in blob for marker in RATE_TEXT_MARKERS):
        return "页面/日志带限流标记"
    return None


def classify(row, *, previous=None) -> dict:
    """One channel row -> one account state + the criteria that produced it.

    ``previous`` is the previous verdict dict for the same channel (with a
    ``state`` key); used to tell 未登录 (never logged in) from 掉线 (was valid).
    """
    row = row or {}
    ev = _evidence(row)
    previous_state = (previous or {}).get("state")
    status = row.get("status")
    criteria = []

    if not row.get("enabled", True) or status == health.STATUS_DISABLED:
        return _state(DISABLED, "通道已停用（enabled=false）",
                      ["enabled=false / status=DISABLED"], previous)

    if ev.get("probe_error"):
        criteria.append(f"检查过程出错：{ev['probe_error']}")
        return _state(UNKNOWN, f"检查过程出错：{ev['probe_error']}", criteria, previous)

    ban = _ban_marker(row)
    if ban:
        criteria.append(ban)
        return _state(BANNED,
                      f"平台判定封禁（依据：{ban}）；扫码无法解决，请联系我们处理",
                      criteria, previous)

    rate = _rate_marker(row)
    if rate:
        criteria.append(rate)
        return _state(RATE_LIMITED,
                      f"平台限流（依据：{rate}）；登录还在，等恢复后会自动继续，不必重扫",
                      criteria, previous)

    if status == health.STATUS_ONLINE:
        criteria.append(f"登录检查 {status}")
        return _state(VALID, row.get("reason") or "登录有效", criteria, previous)

    cookies = ev.get("cookie_count")
    if ev.get("redirected_to_login"):
        criteria.append(f"后台跳登录页（{ev.get('backend_final_url')}）")
        return _state(DROPPED, "登录态已失效（后台被跳转到登录页），请重新扫码",
                      criteria, previous)

    if cookies == 0:
        if previous_state in (VALID, DROPPED, RATE_LIMITED, UNKNOWN):
            criteria.append("cookie 从有到无")
            return _state(DROPPED, "登录态已失效（cookie 0 条），请重新扫码",
                          criteria, previous)
        criteria.append("cookie 0 条且从未有效")
        return _state(NOT_LOGGED_IN, "这个号还没登录过，请扫码登录",
                      criteria, previous)

    if status == health.STATUS_OFFLINE and previous_state == VALID:
        criteria.append(f"由 {VALID} 转为 {status}")
        return _state(DROPPED, row.get("reason") or "登录态已失效，请重新扫码",
                      criteria, previous)

    if isinstance(cookies, int) and cookies > 0:
        criteria.append(f"cookie {cookies} 条，但后端状态未知"
                        f"（HTTP {ev.get('backend_status')}）")
        return _state(UNKNOWN, row.get("reason") or "cookie 在，但后台状态不明，"
                      "需要装了依赖的运行环境再做一次登录检查", criteria, previous)

    criteria.append(f"证据不足（status={status}）")
    return _state(UNKNOWN, row.get("reason") or "证据不足，无法判定",
                  criteria, previous)


def _state(state, reason, criteria, previous) -> dict:
    changed = bool(previous) and previous.get("state") != state
    return {"state": state, "label": LABELS.get(state, state), "reason": reason,
            "criteria": criteria, "changed": changed,
            "previous": (previous or {}).get("state")}


def load_previous(layout) -> dict:
    """channel_id -> previous state record (from run/channel-state.json)."""
    state = health.load_state(layout).get("channels") or {}
    out = {}
    for channel_id, entry in state.items():
        record = entry.get("account_state_record") or {}
        if not record and entry.get("account_state"):
            record = {"state": entry["account_state"]}
        if record:
            out[channel_id] = record
    return out


def annotate(rows, *, previous=None) -> list:
    """Add ``account_state`` / ``account_state_label`` / criteria to each row."""
    previous = previous if previous is not None else {}
    out = []
    for row in rows or []:
        record = classify(row, previous=previous.get(row.get("channel_id")))
        merged = dict(row)
        merged["account_state"] = record["state"]
        merged["account_state_label"] = record["label"]
        merged["account_state_reason"] = record["reason"]
        merged["account_state_changed"] = record["changed"]
        merged["account_state_criteria"] = record["criteria"]
        out.append(merged)
    return out


def persist_records(layout, annotated_rows) -> None:
    """Store each row's state record into run/channel-state.json (additive)."""
    from .jsonio import read_json, write_json
    path = health.state_path(layout)
    doc = read_json(path, default=None)
    if not isinstance(doc, dict):
        doc = {"channels": {}}
    channels = doc.setdefault("channels", {})
    for row in annotated_rows or []:
        entry = channels.setdefault(row["channel_id"], {})
        entry.update({"channel_id": row["channel_id"], "platform": row.get("platform"),
                      "env_id": row.get("env_id"), "nickname": row.get("nickname"),
                      "account_state": row.get("account_state"),
                      "account_state_reason": row.get("account_state_reason")})
        entry["account_state_record"] = {
            "state": row.get("account_state"),
            "reason": row.get("account_state_reason"),
            "criteria": row.get("account_state_criteria"),
            "checked_at": row.get("checked_at"),
        }
    write_json(path, doc)


def aggregate_state(rows) -> str:
    """One state for a whole environment: the worst real state wins."""
    states = [r.get("account_state") for r in rows or [] if r.get("account_state")]
    live = [s for s in states if s != DISABLED]
    pool = live or states
    for state in SEVERITY:
        if state in pool:
            return state
    return UNKNOWN


def env_alerts(previous_rows, current_rows, env_labels=None) -> list:
    """Group state changes by ENVIRONMENT; one alert per affected environment.

    The requirement is explicit: 只提醒受影响的那个环境 -- not "2 accounts
    offline" across the whole panel.
    """
    env_labels = env_labels or {}
    previous = {r.get("channel_id"): r for r in (previous_rows or [])}
    grouped = {}
    for row in current_rows or []:
        was = previous.get(row.get("channel_id"))
        was_state = was.get("account_state") if was else None
        now_state = row.get("account_state")
        if now_state and now_state != was_state:
            grouped.setdefault(row.get("env_id") or "(默认)", []).append(row)
    alerts = []
    for env_id, rows in grouped.items():
        label = env_labels.get(env_id) or (
            env_id if env_id and env_id != "(默认)"
            else (rows[0].get("platform_name") or rows[0].get("platform") or "默认"))
        parts = [f"{r.get('platform_name') or r.get('platform')}→"
                 f"{r.get('account_state_label')}（{r.get('account_state_reason')}）"
                 for r in rows]
        alerts.append({
            "env_id": env_id,
            "title": f"{label} 状态变化",
            "message": "；".join(parts),
            "rows": rows,
            "states": sorted({r.get("account_state") for r in rows}),
        })
    return alerts


def notify_state_changes(previous_rows, current_rows, notify, *, env_labels=None):
    alerts = env_alerts(previous_rows, current_rows, env_labels=env_labels)
    for alert in alerts:
        notify(alert["title"], alert["message"])
    return alerts


def view(rows, envs=None) -> dict:
    """Panel/CLI friendly view: environments -> state, plus state counts."""
    from .environments import Environment  # noqa: F401 (typing only)
    by_env, counts = {}, {}
    for row in rows or []:
        state = row.get("account_state") or UNKNOWN
        counts[state] = counts.get(state, 0) + 1
        by_env.setdefault(row.get("env_id"), []).append(row)
    environments = []
    labels = {e.env_id: e.label for e in (envs or [])}
    for env_id, items in by_env.items():
        environments.append({
            "env_id": env_id, "label": labels.get(env_id, env_id),
            "state": aggregate_state(items),
            "state_label": LABELS.get(aggregate_state(items)),
            "rows": items,
        })
    return {"counts": counts, "environments": environments,
            "totals": {LABELS.get(k, k): v for k, v in counts.items()}}
