"""Feishu confirmation gate for publishing.

The customer machine NEVER holds the vendor Feishu app secret.  It talks to a
small approval service (``output/approval_server/``) with a low-privilege,
per-install token; the service owns the Feishu credentials, sends the card,
receives the answer and exposes a query API.

This module keeps the *client* side: build the pending confirmation record from
the already validated dry-run preview, submit it, persist the answer locally,
and refuse to publish unless the answer is an in-time ``confirmed`` for the
exact same preview (confirm_token / idempotency key).

Statuses (fail closed):
  pending       -> 等待飞书确认
  confirmed     -> 已确认
  rejected      -> 已拒绝
  timeout       -> 超时未确认
  disabled      -> 审批服务已关闭，未确认不发
  submit_failed -> 审批服务不可达，未确认不发
"""

from __future__ import annotations

import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .errors import GateRed
from .jsonio import read_json, write_json

SCHEMA = "feishu-approval/1.0"

PENDING = "pending"
CONFIRMED = "confirmed"
REJECTED = "rejected"
TIMEOUT = "timeout"
DISABLED = "disabled"
SUBMIT_FAILED = "submit_failed"
BLOCKED = "blocked"

DEFAULT_TIMEOUT_MINUTES = 30
DEFAULT_POLL_SECONDS = 15

STATUS_LABELS = {
    PENDING: "等待飞书确认",
    CONFIRMED: "已确认",
    REJECTED: "已拒绝",
    TIMEOUT: "超时未确认",
    DISABLED: "审批服务已关闭，未确认不发",
    SUBMIT_FAILED: "审批服务不可达，未确认不发",
    BLOCKED: "确认信息不一致，拒绝发布",
}


def _utcnow(now=None):
    return now or datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def approval_id_for(preview: dict) -> str:
    """Stable id: same idempotency key + same preview = same approval."""
    key = preview.get("idempotency_key")
    token = preview.get("confirm_token")
    if not key or not token:
        raise GateRed("审批单缺少幂等键或确认 token，拒绝生成待确认单")
    digest = hashlib.sha256(f"{key}|{token}".encode("utf-8")).hexdigest()
    return "fa_" + digest[:24]


def approval_config(settings: dict) -> dict:
    cfg = dict((settings or {}).get("feishu_approval") or {})
    cfg.setdefault("enabled", True)
    cfg.setdefault("endpoint", "")
    cfg.setdefault("client_token", "")
    cfg.setdefault("timeout_minutes", DEFAULT_TIMEOUT_MINUTES)
    cfg.setdefault("poll_interval_seconds", DEFAULT_POLL_SECONDS)
    try:
        cfg["timeout_minutes"] = int(cfg["timeout_minutes"])
    except (TypeError, ValueError):
        cfg["timeout_minutes"] = DEFAULT_TIMEOUT_MINUTES
    return cfg


def build_pending(plan: dict, preview: dict, settings: dict, now=None) -> dict:
    """Create the customer-side pending record from a validated preview."""
    if not preview.get("ok"):
        raise GateRed("dry-run 未通过，不生成飞书待确认单")
    cfg = approval_config(settings)
    now = _utcnow(now)
    timeout_minutes = max(1, int(cfg.get("timeout_minutes") or
                                 DEFAULT_TIMEOUT_MINUTES))
    row = (preview.get("rows") or [{}])[0]
    account = (
        plan.get("account")
        or plan.get("account_name")
        or plan.get("account_nickname")
        or row.get("account")
        or row.get("account_name")
        or row.get("account_nickname")
        or ""
    )
    return {
        "schema": SCHEMA,
        "approval_id": approval_id_for(preview),
        "status": PENDING,
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(minutes=timeout_minutes)),
        "timeout_minutes": timeout_minutes,
        "plan_id": plan.get("plan_id"),
        "env_id": preview.get("env"),
        "env_label": preview.get("env_label"),
        "platform": preview.get("platform"),
        "platform_name": preview.get("platform_name"),
        "account_id": row.get("account_id"),
        "account": account,
        "title": preview.get("title"),
        "topics": preview.get("topics") or [],
        "cover": preview.get("cover"),
        "has_cover": bool(preview.get("has_cover")),
        "media_sha256": row.get("media_sha256"),
        "rows": list(preview.get("rows") or []),
        "material_fingerprint": preview.get("material_fingerprint"),
        "idempotency_key": preview.get("idempotency_key"),
        "schedule_at": preview.get("schedule_at"),
        "time_window": preview.get("time_window"),
        "confirm_token": preview.get("confirm_token"),
        "confirm_ref": preview.get("confirm_ref"),
        "decided_at": None,
        "decided_by": None,
        "reason": None,
    }


def approval_dir(layout) -> Path:
    return layout.run / "approvals"


def record_path(layout, approval_id: str) -> Path:
    if not approval_id or not approval_id.replace("_", "").isalnum():
        raise GateRed("审批单编号不合法")
    return approval_dir(layout) / f"{approval_id}.json"


def save_record(layout, record: dict) -> Path:
    path = record_path(layout, record["approval_id"])
    write_json(path, record)
    write_json(approval_dir(layout) / "latest.json",
               {"approval_id": record["approval_id"],
                "updated_at": _iso(_utcnow())})
    return path


def load_record(layout, approval_id=None) -> dict | None:
    if not approval_id:
        latest = read_json(approval_dir(layout) / "latest.json", default=None)
        approval_id = (latest or {}).get("approval_id")
    if not approval_id:
        return None
    return read_json(record_path(layout, approval_id), default=None)


def _redact(message: str, cfg: dict) -> str:
    text = str(message)
    secret = str(cfg.get("client_token") or "")
    if secret:
        text = text.replace(secret, "***")
    return text


class ApprovalClient:
    """Tiny HTTP client.  No vendor secret, only the install token."""

    def __init__(self, endpoint: str, client_token: str, *, timeout=10):
        self.endpoint = (endpoint or "").rstrip("/")
        self.client_token = client_token or ""
        self.timeout = timeout

    def _request(self, method, path, *, body=None, token=None):
        if not self.endpoint:
            raise GateRed("审批服务地址未配置（feishu_approval.endpoint）")
        parsed = urllib.parse.urlsplit(self.endpoint)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")):
            raise GateRed("远程审批服务必须使用 HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise GateRed("审批服务地址包含非法凭据或参数")
        url = self.endpoint + path
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        auth = token or self.client_token
        if auth:
            headers["X-Approval-Token"] = auth
        request = urllib.request.Request(url, data=data, headers=headers,
                                         method=method)
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return resp.status, json.loads(raw or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw or "{}")
            except ValueError:
                payload = {"ok": False, "error": f"HTTP {exc.code}"}
            return exc.code, payload
        except (urllib.error.URLError, OSError) as exc:
            raise GateRed(f"审批服务不可达：{exc}") from exc

    def submit(self, record: dict) -> dict:
        body = {k: record.get(k) for k in (
            "approval_id", "plan_id", "env_id", "env_label", "platform",
            "platform_name", "account_id", "account", "title", "topics",
            "cover", "has_cover", "media_sha256", "material_fingerprint",
            "idempotency_key", "schedule_at", "time_window", "confirm_token",
            "confirm_ref", "timeout_minutes", "created_at", "expires_at")}
        status, payload = self._request("POST", "/api/approvals", body=body)
        if status not in (200, 201, 202):
            raise GateRed("审批服务拒绝接单："
                          + str(payload.get("error") or payload.get("reason")
                                or f"HTTP {status}"))
        return payload

    def query(self, approval_id: str, approval_token: str) -> dict:
        path = "/api/approvals/" + urllib.parse.quote(approval_id)
        status, payload = self._request("GET", path, token=approval_token)
        if status != 200:
            raise GateRed("查询审批状态失败："
                          + str(payload.get("error") or payload.get("reason")
                                or f"HTTP {status}"))
        return payload


def submit_pending(layout, plan: dict, preview: dict, settings: dict, *,
                   client=None, now=None, extra: dict | None = None) -> dict:
    """Build, persist and submit a pending card.  Fails closed.

    ``extra`` lets a batch consent card carry its own scope (one confirmation
    covering several works) without weakening the per-work binding.
    """
    record = build_pending(plan, preview, settings, now=now)
    if extra:
        record.update({k: v for k, v in extra.items() if v is not None})
    cfg = approval_config(settings)
    record["timeout_minutes"] = cfg["timeout_minutes"]
    if not cfg.get("enabled"):
        record.update(status=DISABLED, reason=STATUS_LABELS[DISABLED])
        save_record(layout, record)
        return record
    if not cfg.get("endpoint") or not cfg.get("client_token"):
        record.update(status=SUBMIT_FAILED,
                      reason="审批服务未配置（地址或客户机令牌为空），未确认不发")
        save_record(layout, record)
        return record

    existing = load_record(layout, record["approval_id"])
    if existing and existing.get("status") in (PENDING, CONFIRMED, REJECTED,
                                               TIMEOUT):
        return existing

    save_record(layout, record)
    client = client or ApprovalClient(cfg["endpoint"], cfg["client_token"])
    try:
        response = client.submit(record)
    except GateRed as exc:
        record.update(status=SUBMIT_FAILED,
                      reason=_redact(str(exc), cfg))
        save_record(layout, record)
        return record
    record["approval_token"] = response.get("approval_token")
    record["status"] = response.get("status") or PENDING
    record["expires_at"] = response.get("expires_at") or record["expires_at"]
    record["feishu"] = response.get("feishu")
    record["submitted"] = True
    save_record(layout, record)
    return record


def refresh(layout, record: dict, settings: dict, *, client=None,
            now=None) -> dict:
    """Refresh one record from the approval service; expire locally if needed."""
    if not isinstance(record, dict):
        return {"status": BLOCKED, "reason": "没有待确认单"}
    cfg = approval_config(settings)
    now = _utcnow(now)
    status = record.get("status")
    if status in (PENDING, CONFIRMED):
        try:
            expired = now >= _parse(record["expires_at"])
        except (KeyError, ValueError):
            expired = True
        if expired:
            record.update(status=TIMEOUT, reason=STATUS_LABELS[TIMEOUT])
            save_record(layout, record)
            return record
    if not cfg.get("enabled"):
        record.update(status=DISABLED, reason=STATUS_LABELS[DISABLED])
        save_record(layout, record)
        return record
    if not record.get("submitted"):
        record.update(status=BLOCKED, reason="确认未提交到服务，拒绝使用本地状态")
        save_record(layout, record)
        return record
    client = client or ApprovalClient(cfg["endpoint"], cfg["client_token"])
    try:
        payload = client.query(record["approval_id"],
                               record.get("approval_token")
                               or cfg["client_token"])
    except Exception as exc:
        record.update(status=BLOCKED, refresh_error=_redact(str(exc), cfg),
                      reason="无法重新查询飞书确认，拒绝使用缓存确认")
        save_record(layout, record)
        return record
    remote = payload.get("approval") or payload
    if not isinstance(remote, dict) or any(
            remote.get(k) != record.get(k) for k in
            ("approval_id", "confirm_token", "idempotency_key")):
        record.update(status=BLOCKED, reason="审批服务返回的确认绑定不一致")
        save_record(layout, record)
        return record
    record.pop("refresh_error", None)
    record["refreshed_at"] = _iso(now)
    record["status"] = remote.get("status") or BLOCKED
    record["feishu"] = remote.get("feishu")
    record["decided_at"] = remote.get("decided_at")
    record["decided_by"] = remote.get("decided_by")
    record["expires_at"] = remote.get("expires_at") or record.get("expires_at")
    if record["status"] == TIMEOUT:
        record["reason"] = STATUS_LABELS[TIMEOUT]
    elif record["status"] == REJECTED:
        record["reason"] = STATUS_LABELS[REJECTED]
    elif record["status"] == CONFIRMED:
        record["reason"] = STATUS_LABELS[CONFIRMED]
    save_record(layout, record)
    return record


def gate(record: dict, preview: dict, *, now=None) -> dict:
    """Return {'ok','status','reason'} for the publish gate.

    A confirmed answer only counts when it is bound to the SAME preview bytes.
    """
    if not isinstance(record, dict):
        return {"ok": False, "status": BLOCKED, "reason": "没有飞书确认记录"}
    status = record.get("status")
    if status == PENDING:
        return {"ok": False, "status": PENDING,
                "reason": STATUS_LABELS[PENDING]}
    if status in (REJECTED, TIMEOUT, DISABLED, SUBMIT_FAILED, BLOCKED):
        return {"ok": False, "status": status,
                "reason": record.get("reason") or STATUS_LABELS.get(status, status)}
    if status != CONFIRMED:
        return {"ok": False, "status": BLOCKED,
                "reason": f"未知审批状态 {status!r}"}
    try:
        if _utcnow(now) >= _parse(record["expires_at"]):
            return {"ok": False, "status": TIMEOUT, "reason": STATUS_LABELS[TIMEOUT]}
    except (KeyError, ValueError, TypeError):
        return {"ok": False, "status": BLOCKED, "reason": "确认有效期缺失或无效"}
    if record.get("refresh_error"):
        return {"ok": False, "status": BLOCKED, "reason": "审批服务重新查询失败"}
    if str(record.get("scope") or "").strip().lower() == "batch":
        bound = str(record.get("account_id") or "")
        account = str((preview or {}).get("account_id") or "")
        if bound and account and bound != account:
            return {"ok": False, "status": BLOCKED,
                    "reason": "本批授权不覆盖当前账号，需要单独确认"}
        try:
            cap = int(record.get("batch_cap") or 1)
        except (TypeError, ValueError):
            cap = 1
        try:
            used = int((preview or {}).get("batch_used") or 0)
        except (TypeError, ValueError):
            used = 0
        if used >= cap:
            return {"ok": False, "status": BLOCKED,
                    "reason": f"本批授权已用完（{used}/{cap}），需要重新确认"}
        return {"ok": True, "status": CONFIRMED,
                "reason": f"本批授权有效（已用 {used}/{cap}）"}
    expected = (preview or {}).get("confirm_token")
    if not expected or not (preview or {}).get("idempotency_key"):
        return {"ok": False, "status": BLOCKED, "reason": "确认清单缺少绑定"}
    if record.get("confirm_token") != expected:
        return {"ok": False, "status": BLOCKED,
                "reason": "确认 token 与当前清单不一致（清单被改过），拒绝发布"}
    if record.get("idempotency_key") != (preview or {}).get("idempotency_key"):
        return {"ok": False, "status": BLOCKED,
                "reason": "幂等键与当前清单不一致，拒绝发布"}
    return {"ok": True, "status": CONFIRMED,
            "reason": "飞书已确认，且确认的就是当前清单"}


def batch_usage_file(layout):
    from pathlib import Path
    base = getattr(layout, "state_dir", None) or getattr(layout, "root", None)
    return Path(base) / "batch-usage.json"


def batch_used(layout, approval_id: str) -> int:
    import json
    path = batch_usage_file(layout)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    try:
        return int((data or {}).get(approval_id) or 0)
    except (TypeError, ValueError):
        return 0


def bump_batch_usage(layout, approval_id: str, step: int = 1) -> int:
    import json
    path = batch_usage_file(layout)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    data[approval_id] = batch_used(layout, approval_id) + step
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data[approval_id]


def require_confirmed(record: dict, preview: dict, *, now=None) -> dict:
    verdict = gate(record, preview, now=now)
    if not verdict["ok"]:
        raise GateRed(f"飞书发布确认未通过：{verdict['reason']}")
    return verdict


def notify_manual_intervention(layout, settings: dict, *, title: str,
                               message: str, kind: str = "manual",
                               client=None) -> dict:
    """Tell the customer in Feishu that a one-time on-PC action is required.

    Used only for captcha / login-lost / risk-control state changes.  Failure is
    non-fatal: a heartbeat must not die because Feishu is unreachable.
    """
    cfg = approval_config(settings)
    if not cfg.get("enabled") or not cfg.get("endpoint") or not cfg.get("client_token"):
        return {"ok": False, "status": DISABLED,
                "reason": "审批服务未启用或未配置"}
    client = client or ApprovalClient(cfg["endpoint"], cfg["client_token"])
    body = {"kind": str(kind), "title": str(title)[:120],
            "message": str(message)[:1500], "created_at": _iso(_utcnow())}
    try:
        status, payload = client._request("POST", "/api/alerts", body=body)
    except GateRed as exc:
        return {"ok": False, "status": SUBMIT_FAILED,
                "reason": _redact(str(exc), cfg)}
    ok = status in (200, 201, 202) and payload.get("ok", False)
    return {"ok": ok, "status": "sent" if ok else SUBMIT_FAILED,
            "dry_run": (payload.get("feishu") or {}).get("dry_run"),
            "reason": payload.get("error")}


def new_install_token() -> str:
    """Only used when provisioning a customer install; never a Feishu secret."""
    return secrets.token_urlsafe(24)
