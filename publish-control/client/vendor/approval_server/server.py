#!/usr/bin/env python3
"""Feishu publish-approval service.

The customer agent submits a pending publish.  This service sends an
interactive Feishu card, records the card callback, and exposes a query
endpoint.  No Feishu app secret ever leaves the server.

Endpoints
  POST /api/approvals                  create a pending approval (idempotent)
  GET  /api/approvals/<approval_id>    query status (per-approval token)
  POST /api/approvals/<id>/decision    manual decision (service token)
  POST /api/feishu/events              Feishu URL verification + card callback
  POST /api/alerts                     one-off operator alert
  GET  /health                         liveness/config summary

Production startup intentionally refuses to run without all of: install token,
decision token, Feishu app credentials, receive target, and callback
verification token.  There is no permissive default.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PENDING = "pending"
CONFIRMED = "confirmed"
REJECTED = "rejected"
TIMEOUT = "timeout"
SEND_FAILED = "send_failed"

SCHEMA = "feishu-approval/1.0"
MAX_BODY = 64 * 1024
ID_RE = re.compile(r"^fa_[0-9a-f]{24}$")

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
#: Overridable for tests; production always resolves to the program root that
#: holds ``config/receipt_pubkey.hex``.
PROGRAM_ROOT = PACKAGE_ROOT
CONTROL_PLANE_SIGNATURE_HEADER = "X-Control-Plane-Signature"
CONTROL_PLANE_ISSUED_AT_HEADER = "X-Control-Plane-Issued-At"
CONTROL_PLANE_MAX_SKEW_SECONDS = 120
_ED25519_MODULE = None


def _ed25519_module():
    """Load the package's existing pure-Python Ed25519 verifier."""
    global _ED25519_MODULE
    if _ED25519_MODULE is None:
        path = PACKAGE_ROOT / "agent" / "winport" / "ed25519_pure.py"
        spec = importlib.util.spec_from_file_location(
            "winport_ed25519_pure_verify", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"ed25519 verifier unavailable: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _ED25519_MODULE = module
    return _ED25519_MODULE


def control_plane_public_key():
    """Read the receipt trust root used for control-plane signatures."""
    path = Path(PROGRAM_ROOT) / "config" / "receipt_pubkey.hex"
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
        public = bytes.fromhex(text)
    except (OSError, ValueError) as exc:
        raise ValueError(f"control-plane public key unreadable: {path}") from exc
    if len(public) != 32:
        raise ValueError(
            f"control-plane public key must be 32 bytes, got {len(public)}")
    ok, reason = _ed25519_module().public_key_valid(public)
    if not ok:
        raise ValueError(f"control-plane public key invalid: {reason}")
    return public


def verify_control_plane_signature(approval_id, signature, issued_at,
                                   *, now=None):
    """Return True only for a fresh, valid control-plane confirmation."""
    signature = str(signature or "").strip()
    issued_at = str(issued_at or "").strip()
    if not signature or not issued_at:
        raise ValueError("control-plane signature headers missing")
    try:
        issued = parse_time(issued_at)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid control-plane issued-at") from exc
    current = now or utcnow()
    if abs((current - issued).total_seconds()) > CONTROL_PLANE_MAX_SKEW_SECONDS:
        raise ValueError("control-plane issued-at outside 120s window")
    try:
        raw = bytes.fromhex(signature)
    except ValueError as exc:
        raise ValueError("control-plane signature is not hex") from exc
    if len(raw) != 64:
        raise ValueError("control-plane signature must be 64 bytes")
    message = f"{approval_id}|confirm|{issued_at}".encode("utf-8")
    if not _ed25519_module().verify(raw, message, control_plane_public_key()):
        raise ValueError("control-plane signature mismatch")
    return True


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def parse_time(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def approval_id_for(payload):
    key = payload.get("idempotency_key")
    token = payload.get("confirm_token")
    if not key or not token:
        raise ValueError("idempotency_key / confirm_token missing")
    return "fa_" + hashlib.sha256(f"{key}|{token}".encode("utf-8")).hexdigest()[:24]


def normalize_decision(value):
    text = str(value or "").strip().lower()
    if text in ("confirm", "confirmed", "approve", "approved", "ok",
                "确认", "确认发布", "同意"):
        return "confirm"
    if text in ("reject", "rejected", "deny", "denied", "驳回", "拒绝"):
        return "reject"
    return ""


def _extract_operator(body):
    candidates = [body]
    event = body.get("event") if isinstance(body, dict) else None
    if isinstance(event, dict):
        candidates.extend([event, event.get("operator"),
                           ((event.get("sender") or {}).get("sender_id"))])
    if isinstance(body, dict):
        candidates.extend([body.get("operator"), body.get("sender")])
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("open_id", "user_id", "union_id"):
            value = candidate.get(key)
            if value:
                return str(value)
    return ""


def extract_decision(body):
    """Return (approval_id, decision, operator) from a Feishu callback."""
    if not isinstance(body, dict):
        return None, None, ""
    operator = _extract_operator(body)
    event = body.get("event") if isinstance(body.get("event"), dict) else {}
    action = body.get("action") or event.get("action") or {}
    value = action.get("value") if isinstance(action, dict) else None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = {}
    if isinstance(value, dict):
        approval_id = value.get("approval_id")
        decision = normalize_decision(value.get("decision") or value.get("action"))
        if approval_id and decision:
            return str(approval_id), decision, operator

    message = (event.get("message") or body.get("message") or {})
    raw = message.get("content") if isinstance(message, dict) else "{}"
    try:
        content = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        content = {}
    text = str((content or {}).get("text") or "")
    match = re.search(r"(确认发布|确认|驳回|拒绝)\s*(fa_[0-9a-f]{24})", text)
    if match:
        return match.group(2), normalize_decision(match.group(1)), operator
    return None, None, operator


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8795
    state_dir: Path = Path("state")
    client_token: str = ""
    decision_token: str = ""
    verification_token: str = ""
    timeout_minutes: int = 30
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_receive_id: str = ""
    feishu_receive_id_type: str = "open_id"
    feishu_base: str = "https://open.feishu.cn"
    allowed_open_ids: tuple = ()
    test_mode: bool = False
    dry_run: bool = False
    sweep_seconds: int = 30

    def __post_init__(self):
        if self.dry_run:
            self.test_mode = True

    @classmethod
    def from_env(cls):
        receive = (os.environ.get("FEISHU_RECEIVE_ID")
                   or os.environ.get("FEISHU_HOME_CHANNEL") or "")
        receive_type = os.environ.get("FEISHU_RECEIVE_ID_TYPE")
        if not receive_type:
            receive_type = "chat_id" if os.environ.get("FEISHU_HOME_CHANNEL") else "open_id"
        allowed = tuple(item.strip() for item in
                        os.environ.get("APPROVAL_ALLOWED_OPEN_IDS", "").split(",")
                        if item.strip())
        return cls(
            host=os.environ.get("APPROVAL_HOST", "127.0.0.1"),
            port=int(os.environ.get("APPROVAL_PORT", "8795")),
            state_dir=Path(os.environ.get("APPROVAL_STATE_DIR", "state")),
            client_token=os.environ.get("APPROVAL_CLIENT_TOKEN", ""),
            decision_token=os.environ.get("APPROVAL_DECISION_TOKEN", ""),
            verification_token=os.environ.get("FEISHU_VERIFICATION_TOKEN", ""),
            timeout_minutes=int(os.environ.get("APPROVAL_TIMEOUT_MINUTES", "30")),
            feishu_app_id=os.environ.get("FEISHU_APP_ID", ""),
            feishu_app_secret=os.environ.get("FEISHU_APP_SECRET", ""),
            feishu_receive_id=receive,
            feishu_receive_id_type=receive_type,
            feishu_base=os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn"),
            allowed_open_ids=allowed,
            test_mode=os.environ.get("APPROVAL_TEST_MODE", "") == "1",
            dry_run=os.environ.get("APPROVAL_FEISHU_DRY_RUN", "") == "1",
            sweep_seconds=int(os.environ.get("APPROVAL_SWEEP_SECONDS", "30")),
        )

    def missing_required(self):
        required = {
            "APPROVAL_CLIENT_TOKEN": self.client_token,
            "APPROVAL_DECISION_TOKEN": self.decision_token,
        }
        if not self.test_mode:
            required.update({
                "FEISHU_APP_ID": self.feishu_app_id,
                "FEISHU_APP_SECRET": self.feishu_app_secret,
                "FEISHU_RECEIVE_ID": self.feishu_receive_id,
                "FEISHU_VERIFICATION_TOKEN": self.verification_token,
            })
        return [key for key, value in required.items() if not str(value or "").strip()]


class Store:
    def __init__(self, state_dir: Path, timeout_minutes: int):
        self.state_dir = Path(state_dir)
        self.timeout_minutes = max(1, int(timeout_minutes))
        self.lock = threading.RLock()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "outbox").mkdir(parents=True, exist_ok=True)

    def _path(self, approval_id):
        return self.state_dir / f"{approval_id}.json"

    def _read(self, approval_id):
        try:
            data = json.loads(self._path(approval_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _write(self, record):
        path = self._path(record["approval_id"])
        tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        try:
            tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

    def _expire(self, record, now=None):
        if record.get("status") != PENDING:
            return record
        now = now or utcnow()
        try:
            expired = now >= parse_time(record["expires_at"])
        except (KeyError, ValueError, TypeError):
            expired = True
        if expired:
            record.update(status=TIMEOUT, reason="超时未确认", decided_at=iso(now))
            self._write(record)
        return record

    def get(self, approval_id, *, now=None):
        if not ID_RE.fullmatch(str(approval_id or "")):
            return None
        with self.lock:
            record = self._read(approval_id)
            return self._expire(record, now=now) if record else None

    def create(self, payload):
        approval_id = approval_id_for(payload)
        provided = payload.get("approval_id")
        if provided and provided != approval_id:
            raise ValueError("approval_id does not match idempotency key")
        with self.lock:
            existing = self._read(approval_id)
            if existing:
                # A retry may repeat the same request, but it must never
                # silently rebind an existing card to different content.
                for field in ("confirm_token", "idempotency_key",
                              "material_fingerprint", "media_sha256",
                              "schedule_at", "env_id", "platform", "title",
                              "account_id", "account", "topics", "cover",
                              "has_cover", "confirm_ref", "time_window"):
                    incoming = payload.get(field)
                    if (incoming not in (None, "") and existing.get(field) not in (None, "")
                            and incoming != existing.get(field)):
                        raise ValueError("approval binding changed; create a new confirmation")
                return self._expire(existing), False
            now = utcnow()
            record = dict(payload)
            record.update({
                "schema": SCHEMA,
                "approval_id": approval_id,
                "approval_token": secrets.token_urlsafe(32),
                "status": PENDING,
                "created_at": iso(now),
                "expires_at": iso(now + timedelta(minutes=(
                    min(1440, max(1, int(payload.get("timeout_minutes") or 0)))
                    if str(payload.get("scope") or "") == "batch"
                    and payload.get("timeout_minutes") else self.timeout_minutes))),
                "timeout_minutes": self.timeout_minutes,
                "decided_at": None,
                "decided_by": None,
                "reason": None,
                "feishu": None,
            })
            self._write(record)
            return record, True

    def update(self, approval_id, **fields):
        with self.lock:
            record = self._read(approval_id)
            if record:
                record.update(fields)
                self._write(record)
            return record

    def mark_send_failed(self, approval_id, reason="确认卡发送失败"):
        return self.update(approval_id, status=SEND_FAILED, reason=reason)

    def prepare_send(self, approval_id):
        with self.lock:
            record = self._read(approval_id)
            if record and record.get("status") == SEND_FAILED:
                record.update(status=PENDING, reason=None, feishu=None)
                self._write(record)
            return record

    def decide(self, approval_id, decision, operator="", *, now=None,
               feishu=None):
        with self.lock:
            record = self._read(approval_id)
            if not record:
                return None, "approval not found", 404
            record = self._expire(record, now=now)
            if record.get("status") != PENDING:
                return record, f"already {record.get('status')}; replay refused", 409
            fields = {
                "status": CONFIRMED if decision == "confirm" else REJECTED,
                "decided_at": iso(now or utcnow()),
                "decided_by": str(operator or "feishu")[:120],
                "reason": "已确认" if decision == "confirm" else "已拒绝",
            }
            if feishu is not None:
                fields["feishu"] = feishu
            record.update(fields)
            self._write(record)
            return record, None, 200

    def expire_all(self, now=None):
        changed = 0
        with self.lock:
            for path in self.state_dir.glob("fa_*.json"):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if record.get("status") == PENDING:
                    before = record["status"]
                    if self._expire(record, now=now).get("status") != before:
                        changed += 1
        return changed

    def record_alert(self, alert):
        with self.lock:
            with (self.state_dir / "alerts.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(alert, ensure_ascii=False) + "\n")
                fh.flush()

    @staticmethod
    def public_view(record):
        if not record:
            return None
        return {key: value for key, value in record.items()
                if key != "approval_token"}


class FeishuSender:
    def __init__(self, config: Config):
        self.config = config
        self._token = ""
        self._token_expires = 0.0

    def _post(self, url, payload, headers=None):
        request = urllib.request.Request(
            url, data=canonical(payload), method="POST",
            headers={"Content-Type": "application/json; charset=utf-8",
                     **(headers or {})})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8", "replace") or "{}")

    def _tenant_token(self):
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        result = self._post(
            self.config.feishu_base + "/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": self.config.feishu_app_id,
             "app_secret": self.config.feishu_app_secret})
        if result.get("code") != 0 or not result.get("tenant_access_token"):
            raise RuntimeError("tenant token request failed")
        self._token = result["tenant_access_token"]
        self._token_expires = time.time() + int(result.get("expire", 7200))
        return self._token

    @staticmethod
    def card_for(record):
        account = (record.get("account") or record.get("account_name")
                   or "未登记")
        platform = record.get("platform_name") or record.get("platform") or "未登记"
        env = record.get("env_label") or record.get("env_id") or "未登记"
        topics = " ".join(record.get("topics") or []) or "无"
        content = (
            f"**账号**：{account}\n"
            f"**环境 / 平台**：{env} / {platform}\n"
            f"**作品**：{record.get('title') or '未填写'}\n"
            f"**计划时间**：{record.get('schedule_at') or '未填写'}\n"
            f"**话题**：{topics}\n"
            f"**确认单**：{record.get('approval_id')}")
        return {
            "config": {"wide_screen_mode": True, "update_multi": True},
            "header": {"template": "blue",
                       "title": {"tag": "plain_text", "content": "发布确认"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md",
                 "content": "**在对话里回复「确认」即可发布，回复「驳回」则取消。**"}},
            ],
        }

    def send_card(self, record):
        card = self.card_for(record)
        if self.config.test_mode:
            out = (self.config.state_dir / "outbox"
                   / f"{record['approval_id']}-{secrets.token_hex(4)}.json")
            out.write_text(json.dumps({"test_mode": True, "card": card},
                                      ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
            return {"ok": True, "dry_run": True, "test_mode": True,
                    "outbox": str(out)}
        token = self._tenant_token()
        result = self._post(
            self.config.feishu_base + "/open-apis/im/v1/messages?receive_id_type="
            + self.config.feishu_receive_id_type,
            {"receive_id": self.config.feishu_receive_id,
             "msg_type": "interactive",
             "content": json.dumps(card, ensure_ascii=False)},
            headers={"Authorization": f"Bearer {token}"})
        if result.get("code") != 0:
            raise RuntimeError("card send failed")
        return {"ok": True, "test_mode": False, "dry_run": False,
                "message_id": (result.get("data") or {}).get("message_id")}

    def send_alert(self, title, message):
        text = f"需要到电脑前处理一次\n{title}\n{message}"
        if self.config.test_mode:
            out = (self.config.state_dir / "outbox"
                   / f"alert-{int(time.time() * 1000)}.json")
            out.write_text(json.dumps({"test_mode": True, "text": text},
                                      ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
            return {"ok": True, "dry_run": True, "test_mode": True,
                    "outbox": str(out)}
        token = self._tenant_token()
        result = self._post(
            self.config.feishu_base + "/open-apis/im/v1/messages?receive_id_type="
            + self.config.feishu_receive_id_type,
            {"receive_id": self.config.feishu_receive_id,
             "msg_type": "text",
             "content": json.dumps({"text": text}, ensure_ascii=False)},
            headers={"Authorization": f"Bearer {token}"})
        if result.get("code") != 0:
            raise RuntimeError("alert send failed")
        return {"ok": True, "test_mode": False, "dry_run": False,
                "message_id": (result.get("data") or {}).get("message_id")}


def make_handler(config: Config, store: Store, sender: FeishuSender):
    class Handler(BaseHTTPRequestHandler):
        server_version = "WinportApproval/1.0"

        def log_message(self, fmt, *args):
            print(f"{self.address_string()} {fmt % args}", flush=True)

        def _send(self, status, payload):
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except BrokenPipeError:
                pass

        def _body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if length <= 0 or length > MAX_BODY:
                return None
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None

        def _auth(self, expected):
            provided = self.headers.get("X-Approval-Token", "")
            return bool(expected) and hmac.compare_digest(provided, expected)

        def _send_approval(self, record, created=False, status=200):
            public = store.public_view(record)
            return self._send(status, {
                "ok": True,
                "created": created,
                "approval_id": record["approval_id"],
                "approval_token": record["approval_token"],
                "status": record.get("status"),
                "expires_at": record.get("expires_at"),
                "feishu": record.get("feishu"),
                "approval": public,
            })

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                return self._send(200, {
                    "ok": True,
                    "service": "winport-approval",
                    "time": iso(utcnow()),
                    "test_mode": config.test_mode,
                    "feishu_dry_run": config.test_mode,
                    "feishu_configured": bool(
                        config.feishu_app_id and config.feishu_app_secret
                        and config.feishu_receive_id),
                })
            match = re.fullmatch(r"/api/approvals/(fa_[0-9a-f]{24})", path)
            if match:
                record = store.get(match.group(1))
                if not record:
                    return self._send(404, {"ok": False, "error": "not found"})
                provided = self.headers.get("X-Approval-Token", "")
                if not (hmac.compare_digest(provided, record.get("approval_token", ""))
                        or self._auth(config.client_token)):
                    return self._send(403, {"ok": False, "error": "bad token"})
                return self._send(200, {"ok": True,
                                        "approval": store.public_view(record)})
            return self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/approvals":
                return self._create_approval()
            match = re.fullmatch(r"/api/approvals/(fa_[0-9a-f]{24})/decision", path)
            if match:
                return self._decision(match.group(1))
            if path == "/api/feishu/events":
                return self._feishu_event()
            if path == "/api/alerts":
                return self._alert()
            return self._send(404, {"ok": False, "error": "not found"})

        def _create_approval(self):
            if not self._auth(config.client_token):
                return self._send(403, {"ok": False, "error": "bad token"})
            body = self._body()
            if not isinstance(body, dict):
                return self._send(400, {"ok": False, "error": "bad json"})
            required = ("idempotency_key", "confirm_token", "env_id",
                        "platform", "title", "material_fingerprint",
                        "schedule_at")
            missing = [key for key in required if not body.get(key)]
            if missing:
                return self._send(400, {"ok": False,
                                        "error": "missing: " + ",".join(missing)})
            try:
                record, created = store.create(body)
            except ValueError as exc:
                return self._send(400, {"ok": False, "error": str(exc)})
            if record.get("status") in (CONFIRMED, REJECTED, TIMEOUT):
                return self._send_approval(record, created=False)
            if record.get("status") == PENDING and (record.get("feishu") or {}).get("ok"):
                return self._send_approval(record, created=False)
            record = store.prepare_send(record["approval_id"]) or record
            try:
                info = sender.send_card(record)
            except Exception:
                store.mark_send_failed(record["approval_id"])
                return self._send(502, {
                    "ok": False,
                    "error": "确认卡发送失败，未进入可确认状态",
                    "approval_id": record["approval_id"],
                })
            record = store.update(record["approval_id"], status=PENDING,
                                  reason=None, feishu=info) or record
            return self._send_approval(record, created=created,
                                       status=201 if created else 200)

        def _decision(self, approval_id):
            signature = (self.headers.get(CONTROL_PLANE_SIGNATURE_HEADER)
                         or "").strip()
            issued_at = (self.headers.get(CONTROL_PLANE_ISSUED_AT_HEADER)
                         or "").strip()
            control_plane = bool(signature or issued_at)
            if control_plane:
                try:
                    verify_control_plane_signature(
                        approval_id, signature, issued_at)
                except Exception:
                    return self._send(401, {
                        "ok": False,
                        "error": "invalid control-plane signature",
                    })
            if not self._auth(config.decision_token):
                return self._send(403, {"ok": False, "error": "bad token"})
            body = self._body()
            if not isinstance(body, dict):
                return self._send(400, {"ok": False, "error": "bad json"})
            decision = normalize_decision(body.get("decision"))
            if not decision:
                return self._send(400, {"ok": False,
                                        "error": "decision must be confirm or reject"})
            if control_plane and decision != "confirm":
                return self._send(401, {
                    "ok": False,
                    "error": "control-plane signature is confirm-only",
                })
            record, error, code = store.decide(
                approval_id, decision, str(body.get("operator") or "service"),
                feishu=({"ok": True, "dry_run": False,
                         "source": "control_plane"}
                        if control_plane else
                        {"ok": True, "dry_run": bool(config.test_mode),
                         "source": "local"}))
            if error:
                return self._send(code, {"ok": False, "error": error,
                                         "approval": store.public_view(record)})
            return self._send(200, {"ok": True,
                                    "approval": store.public_view(record)})

        def _feishu_event(self):
            if not config.verification_token:
                return self._send(503, {"ok": False, "error": "callback disabled"})
            body = self._body()
            if not isinstance(body, dict):
                return self._send(400, {"ok": False, "error": "bad json"})
            if body.get("encrypt"):
                return self._send(400, {
                    "ok": False,
                    "error": "encrypted callback is not enabled; disable Encrypt Key",
                })
            header = body.get("header") if isinstance(body.get("header"), dict) else {}
            token = body.get("token") or header.get("token") or ""
            if not hmac.compare_digest(str(token), config.verification_token):
                return self._send(403, {"ok": False, "error": "bad verification token"})
            if body.get("type") == "url_verification" or "challenge" in body:
                return self._send(200, {"challenge": body.get("challenge", "")})
            approval_id, decision, operator = extract_decision(body)
            if not approval_id or not decision:
                return self._send(400, {"ok": False, "error": "decision not found"})
            if config.allowed_open_ids and operator not in config.allowed_open_ids:
                return self._send(403, {"ok": False, "error": "operator not allowed"})
            record, error, code = store.decide(approval_id, decision, operator)
            if error:
                target = CONFIRMED if decision == "confirm" else REJECTED
                if record and record.get("status") == target:
                    return self._send(200, {"ok": True, "status": target,
                                            "already": True})
                return self._send(code, {"ok": False, "error": error})
            return self._send(200, {"ok": True, "status": record.get("status")})

        def _alert(self):
            if not self._auth(config.client_token):
                return self._send(403, {"ok": False, "error": "bad token"})
            body = self._body()
            if not isinstance(body, dict) or not body.get("message"):
                return self._send(400, {"ok": False, "error": "bad alert"})
            alert = {"kind": str(body.get("kind") or "manual")[:40],
                     "title": str(body.get("title") or "")[:120],
                     "message": str(body["message"])[:1500],
                     "created_at": iso(utcnow())}
            store.record_alert(alert)
            try:
                info = sender.send_alert(alert["title"], alert["message"])
            except Exception:
                return self._send(502, {"ok": False,
                                        "error": "通知发送失败"})
            return self._send(200, {"ok": True, "feishu": info})

    return Handler


def make_server(config: Config, *, sender=None):
    store = Store(config.state_dir, config.timeout_minutes)
    sender = sender or FeishuSender(config)
    handler = make_handler(config, store, sender)
    httpd = ThreadingHTTPServer((config.host, config.port), handler)
    httpd.store = store
    httpd.config = config
    httpd.sender = sender

    def sweep():
        while True:
            time.sleep(max(2, config.sweep_seconds))
            try:
                store.expire_all()
            except Exception:
                pass

    threading.Thread(target=sweep, daemon=True).start()
    return httpd


def main(argv=None):
    parser = argparse.ArgumentParser(description="Feishu publish-approval service")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--state-dir")
    parser.add_argument("--test-mode", action="store_true",
                        help="explicit local test mode; cards are written to outbox")
    args = parser.parse_args(argv)
    config = Config.from_env()
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.state_dir:
        config.state_dir = Path(args.state_dir)
    if args.test_mode:
        config.test_mode = True
    missing = config.missing_required()
    if missing:
        raise SystemExit("BLOCKED: missing " + ", ".join(missing))
    httpd = make_server(config)
    print(json.dumps({
        "service": "winport-approval",
        "listening": f"{config.host}:{config.port}",
        "state_dir": str(config.state_dir),
        "test_mode": config.test_mode,
    }, ensure_ascii=False), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
