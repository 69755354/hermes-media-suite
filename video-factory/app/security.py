"""无外部依赖的登录会话与 CSRF 保护。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


SESSION_TTL_SECONDS = 12 * 60 * 60


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def derive_secret(password: str) -> bytes:
    """从仅存在于环境变量的密码派生会话签名密钥。"""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), b"xingguang-video-factory-session-v1", 200_000
    )


def password_matches(submitted: str, expected: str) -> bool:
    return hmac.compare_digest(submitted.encode("utf-8"), expected.encode("utf-8"))


def create_session(secret: bytes, now: int | None = None, claims: dict[str, Any] | None = None) -> str:
    issued = int(now if now is not None else time.time())
    payload = {
        "iat": issued,
        "exp": issued + SESSION_TTL_SECONDS,
        "nonce": secrets.token_urlsafe(18),
    }
    if claims:
        payload.update(claims)
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64encode(raw)
    signature = _b64encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def parse_session(token: str | None, secret: bytes, now: int | None = None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    try:
        body, supplied = token.split(".", 1)
        expected = _b64encode(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied, expected):
            return None
        payload = json.loads(_b64decode(body))
        current = int(now if now is not None else time.time())
        if not isinstance(payload, dict) or current >= int(payload["exp"]):
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def csrf_token(session: dict[str, Any], secret: bytes) -> str:
    nonce = str(session["nonce"])
    return _b64encode(hmac.new(secret, f"csrf:{nonce}".encode("utf-8"), hashlib.sha256).digest())


def csrf_matches(supplied: str, session: dict[str, Any], secret: bytes) -> bool:
    return bool(supplied) and hmac.compare_digest(supplied, csrf_token(session, secret))
