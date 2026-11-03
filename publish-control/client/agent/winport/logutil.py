"""UTF-8 logging plus a redaction filter.

Discipline copied from the Mac side (audit.py): cookies, tokens, presigned
signatures and QR paths must never reach a log file.  redact() is applied to
every message written through this module.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .jsonio import append_jsonl

# A presigned URL is a bearer credential: drop the query string AND any
# userinfo (1.2.5/GPT item 10: ``https://user:pass@host/path?token=...`` used to
# keep the username/password in the netloc).
_URL_CRED = re.compile(
    # 1.2.5 (GPT review item 10): a host with NO path (``https://host?cred=X``)
    # must be redacted too, so the path part is optional.
    r"(https?://[^/\s?#]+(?:/[^\s?#]*)?)\?[^\s#]*", re.IGNORECASE)
_URL_USERINFO = re.compile(r"(?i)\b(https?://)[^/@\s]+@")
# Secret headers carry the secret to the END OF THE LINE: a multi-pair Cookie
# ("a=1; b=2") must be redacted whole, not just the first pair.
_SECRET_HEADER = re.compile(
    r"(?i)\b(cookie|set-cookie|authorization|proxy-authorization)\b\s*[=:]\s*[^\r\n]+")
# JSON form: "token": "value" / "access_key": "value" (quotes around key/value).
_SECRET_JSON = re.compile(
    r"(?i)(\"(?:cookie|set-cookie|authorization|access_key|secret|token|"
    r"access_token|refresh_token|signature|sessionid|session_id|passwd|"
    r"password)\"\s*:\s*)"
    # 1.2.5 (GPT review item 10): a JSON value may contain ESCAPED quotes
    # (``{"token":"X\"Y"}``); ``[^"]*`` stopped at the first ``\"`` and leaked
    # the rest.  Match a whole escaped string here.
    r"(\"(?:[^\"\\]|\\.)*\"|[^,}\s]+)")
# Header-ish / query-ish key=value form.
_SECRET_KV = re.compile(
    r"(?i)\b(cookie|set-cookie|authorization|token|access_key|secret|"
    r"signature|sessionid|session_id|passwd|password)\b\s*[=:]\s*\S+")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")
_QR_PATH = re.compile(r"(?i)([A-Za-z]:\\[^\s]*qrlogin[^\s]*|/[^\s]*qrlogin[^\s]*)")


def redact(text: str) -> str:
    text = _URL_USERINFO.sub(r"\1", str(text))
    text = _URL_CRED.sub(r"\1?<redacted>", text)
    # Strip the bearer token BEFORE the generic key/value rule so the token
    # itself never leaks (the generic rule would stop at the first space).
    text = _BEARER.sub("Bearer <redacted>", text)
    text = _SECRET_HEADER.sub(lambda m: m.group(1) + ": <redacted>", text)
    text = _SECRET_JSON.sub(lambda m: m.group(1) + "\"<redacted>\"", text)
    text = _SECRET_KV.sub(lambda m: m.group(1) + "=<redacted>", text)
    text = _QR_PATH.sub("<redacted-qr-path>", text)
    return text


#: keys whose VALUE is a credential regardless of what it looks like.  1.2.5
#: (GPT review item 10): the string-level rules miss a nested
#: ``{"token": "X"}``; masking by KEY closes that.
SENSITIVE_KEYS = {
    "cookie", "set_cookie", "authorization", "proxy_authorization", "token",
    "access_token", "refresh_token", "id_token", "access_key", "accesskey",
    "secret", "secret_key", "secretkey", "client_secret", "signature",
    "sessionid", "session_id", "session", "passwd", "password", "pwd",
    "api_key", "apikey", "private_key", "auth",
}


def sensitive_key(key) -> bool:
    return str(key).strip().lower().replace("-", "_") in SENSITIVE_KEYS


def redact_obj(value, key=None):
    """Recursively redact dicts / lists.

    1.2.5 (GPT review items 10): (a) every string leaf is rewritten by
    ``redact``; (b) any value whose KEY is a credential name is masked whole, so
    ``{"token": "X"}`` or ``{"cookie": "a=X; b=Y"}`` nested anywhere can no
    longer survive just because the value does not match a regex.
    """
    if key is not None and sensitive_key(key):
        return "<redacted>"
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_obj(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_obj(v) for v in value]
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True


def get_logger(name: str = "winport", log_dir: Path | None = None,
               level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.addFilter(RedactingFilter())
    logger.addHandler(sh)
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_dir / "agent.out", maxBytes=5 << 20,
                                 backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.addFilter(RedactingFilter())
        logger.addHandler(fh)
    logger.propagate = False
    return logger


def audit(log_dir: Path, event: str, **fields) -> None:
    """Append a redacted audit line to logs/stage2-audit.jsonl (Mac parity).

    Every value (including nested lists/dicts) is redacted before it is written.
    1.2.5 (GPT review item 10): the top-level KEY is passed through too, so
    ``audit(..., token="X")`` is masked by key, not only by value pattern.
    """
    record = {"event": redact(event)}
    for k, v in fields.items():
        record[k] = redact_obj(v, k)
    append_jsonl(Path(log_dir) / "stage2-audit.jsonl", record)
