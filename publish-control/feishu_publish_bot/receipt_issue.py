"""Issue Ed25519-signed approval receipts for ``approved_publish``.

The receipt trust root is separate from the licence vendor key: the customer
runtime verifies receipts with ``config/receipt_pubkey.hex`` only.  The signing
seed never leaves the bot host.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED_PATH = Path(os.environ.get("RECEIPT_SEED_PATH") or Path.home() / ".hermes" / "keys" / "receipt_signing.hex")

#: mirrors agent/winport/approval.py:ASCII_SAFE
ASCII_SAFE = re.compile(r"^[A-Za-z0-9._:\-]{1,64}$")

#: The caller-facing name is ``publish``; the client's exact on-wire value is
#: ``approved_publish`` (agent/winport/publish_exec.py:MODE_APPROVED).  ``fill``
#: is kept for completeness but is never used for real submission here.
_OPERATION_MODES = {
    "publish": "approved_publish",
    "approved_publish": "approved_publish",
    "fill": "fill",
}

try:  # preferred signer
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    _CRYPTO = True
except Exception:  # pragma: no cover - exercised by the fallback test
    serialization = None
    Ed25519PrivateKey = None
    _CRYPTO = False

try:  # pure-Python fallback, copied from the customer runtime
    import ed25519_pure
except Exception:  # pragma: no cover - only if the copy is missing
    ed25519_pure = None


def _canonical(receipt: dict) -> bytes:
    """Byte-for-byte copy of agent/winport/approval.py::_canonical."""
    body = {k: v for k, v in receipt.items() if k != "signature"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _load_seed(path: Path | str | None = None) -> bytes:
    p = Path(path) if path is not None else Path(SEED_PATH)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise ValueError(f"receipt signing seed unreadable: {p}: {exc}") from exc
    try:
        text = raw.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise ValueError(f"receipt signing seed is not UTF-8: {p}") from exc
    if len(text) != 64:
        raise ValueError(f"receipt signing seed must be 64 hex chars, got {len(text)}: {p}")
    try:
        seed = bytes.fromhex(text)
    except ValueError as exc:
        raise ValueError(f"receipt signing seed is not hex: {p}") from exc
    if len(seed) != 32:
        raise ValueError(f"receipt signing seed must be 32 bytes, got {len(seed)}: {p}")
    return seed


def _encodepoint(point) -> bytes:
    x, y = point
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))


def _pure_publickey(seed: bytes) -> bytes:
    h = hashlib.sha512(seed).digest()
    a = 2 ** 254 + sum(2 ** i * ((h[i // 8] >> (i % 8)) & 1)
                       for i in range(3, 254))
    return _encodepoint(ed25519_pure._scalarmult(ed25519_pure.B, a))


def _pure_sign(message: bytes, seed: bytes, public: bytes) -> bytes:
    h = hashlib.sha512(seed).digest()
    a = 2 ** 254 + sum(2 ** i * ((h[i // 8] >> (i % 8)) & 1)
                       for i in range(3, 254))
    r = ed25519_pure._hint(h[32:64] + message) % ed25519_pure.Q
    R = ed25519_pure._scalarmult(ed25519_pure.B, r)
    S = (r + ed25519_pure._hint(_encodepoint(R) + public + message) * a) \
        % ed25519_pure.Q
    return _encodepoint(R) + S.to_bytes(32, "little")


def _sign(message: bytes, seed: bytes) -> bytes:
    if _CRYPTO:
        key = Ed25519PrivateKey.from_private_bytes(seed)
        return key.sign(message)
    if ed25519_pure is None:
        raise RuntimeError("no Ed25519 signer: cryptography missing and "
                           "ed25519_pure.py not found")
    public = _pure_publickey(seed)
    return _pure_sign(message, seed, public)


def sign_control_plane_decision(approval_id, issued_at=None):
    """Return ``(issued_at, signature_hex)`` for one decision header.

    The message is exactly ``"<approval_id>|confirm|<issued_at>"`` and is
    signed with the same receipt seed the customer verifies against
    ``config/receipt_pubkey.hex``.
    """
    approval_id = str(approval_id or "")
    if not re.fullmatch(r"fa_[0-9a-f]{24}", approval_id):
        raise ValueError("approval_id must match fa_[0-9a-f]{24}")
    issued = str(issued_at or datetime.now(timezone.utc).isoformat())
    message = f"{approval_id}|confirm|{issued}".encode("utf-8")
    return issued, _sign(message, _load_seed()).hex()


def issue_receipt(plan: dict, approver_id: str,
                  operation_mode: str = "publish",
                  ttl_minutes: int = 30,
                  republish: bool = False,
                  device_id: str | None = None,
                  binding_epoch: int | None = None) -> dict:
    """Return one signed receipt for the plan's current content hash.

    ``operation_mode="publish"`` is normalised to the client's exact value
    ``approved_publish``; the returned dict contains that on-wire value.
    Missing plan fields, a bad approver id, a bad TTL or an unreadable seed
    raise instead of minting a receipt the client would silently reject.
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be a dict")
    plan_id = plan.get("plan_id")
    content_hash = (plan.get("compliance") or {}).get("content_hash")
    if not plan_id:
        raise ValueError("plan.plan_id missing")
    if not content_hash:
        raise ValueError("plan.compliance.content_hash missing")

    approver_id = str(approver_id or "")
    if not ASCII_SAFE.match(approver_id):
        raise ValueError("approver_id must be 1-64 ASCII-safe characters")

    mode = _OPERATION_MODES.get(str(operation_mode))
    if mode is None:
        raise ValueError(f"unsupported operation_mode: {operation_mode}")

    try:
        ttl = float(ttl_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError("ttl_minutes must be a positive number") from exc
    if ttl <= 0:
        raise ValueError("ttl_minutes must be a positive number")

    now = datetime.now(timezone.utc)
    receipt = {
        "receipt_id": "RCP-" + now.strftime("%Y%m%dT%H%M%SZ") + "-"
                      + secrets.token_hex(4),
        "approver_id": approver_id,
        "plan_id": plan_id,
        "operation_mode": mode,
        "content_hash": content_hash,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
    }
    if republish:
        receipt["republish"] = {
            "confirmed_at": now.isoformat(),
            "nonce": secrets.token_hex(16),
            "reason": "customer_confirmed",
        }
    # Device identity is part of the signed body, so a ledger/receipt can be
    # attributed to exactly one machine.  It is omitted for legacy customers
    # whose old agent has no device identity to present.
    if device_id is not None:
        device_id = str(device_id or "")
        if not ASCII_SAFE.match(device_id):
            raise ValueError("device_id must be 1-64 ASCII-safe characters")
        receipt["device_id"] = device_id
    if binding_epoch is not None:
        if type(binding_epoch) is not int or binding_epoch < 0:
            raise ValueError("binding_epoch must be a non-negative integer")
        receipt["device_binding_epoch"] = binding_epoch
    receipt["signature"] = _sign(_canonical(receipt), _load_seed()).hex()
    return receipt
