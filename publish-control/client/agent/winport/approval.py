"""ApprovalReceipt verification (Ed25519, signed by the CONTROL PLANE).

Hard rules (downlink plan section 2.5 / approval-issuance.md):

  * the agent NEVER signs a receipt itself  --  there is no signing call site in
    the customer runtime, and no private key of any kind ships in the package;
  * the ONLY trust root is the fixed vendor public key that ships in
    ``config/vendor_pubkey.hex`` (the same key that verifies licences).  A
    caller-supplied key / trust root is REFUSED, and an empty key is refused --
    1.2.4 shipped an HMAC path that accepted ``b""`` and a customer-chosen key,
    so a freshly minted empty-key receipt verified.  That path is gone;
  * a receipt may only change plan_id / operation_mode, and the derived
    content_hash must still equal the plan's compliance.content_hash.

Any receipt that fails verification is BLOCKED, never "best effort".
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from . import ed25519_pure
from .errors import GateRed

ASCII_SAFE = re.compile(r"^[A-Za-z0-9._:\-]{1,64}$")
REPUBLISH_NONCE_RE = re.compile(r"^[0-9a-f]{16,64}$")

ALLOWED_MODES = ("fill", "approved_publish")

#: fixed, non-overridable location of the trust root inside the program tree.
TRUST_ROOT_RELATIVE = "config/vendor_pubkey.hex"


def _canonical(receipt: dict) -> bytes:
    body = {k: v for k, v in receipt.items() if k != "signature"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _trust_root_ok(public_key) -> str | None:
    """Return a block reason when the trust root is unusable, else None."""
    if public_key is None:
        return "approval trust root missing"
    if not isinstance(public_key, (bytes, bytearray)):
        return "approval trust root is not bytes"
    if len(bytes(public_key)) != 32:
        return (f"approval trust root must be the 32-byte vendor public key, "
                f"got {len(bytes(public_key))} bytes")
    ok, reason = ed25519_pure.public_key_valid(bytes(public_key))
    return None if ok else f"approval trust root invalid: {reason}"


def verify_receipt(receipt: dict, plan: dict, public_key, *,
                   now=None, operation_mode=None,
                   allow_republish: bool = False) -> dict:
    """Return {'ok', 'reason'}. Never raises for a bad receipt; it blocks.

    ``public_key`` is the FIXED vendor trust root (32-byte Ed25519 public key).
    An empty / missing / caller-chosen key is a block, not a bypass.
    """
    now = now or datetime.now(timezone.utc)
    if not isinstance(receipt, dict):
        return {"ok": False, "reason": "receipt missing"}
    trust_reason = _trust_root_ok(public_key)
    if trust_reason is not None:
        return {"ok": False, "reason": trust_reason}

    for field in ("receipt_id", "approver_id", "plan_id", "operation_mode",
                  "content_hash", "issued_at", "expires_at", "signature"):
        if not receipt.get(field):
            return {"ok": False, "reason": f"receipt.{field} missing"}
    for field in ("receipt_id", "approver_id"):
        if not ASCII_SAFE.match(str(receipt[field])):
            return {"ok": False, "reason": f"receipt.{field} not ASCII-safe"}

    if receipt["operation_mode"] not in ALLOWED_MODES:
        return {"ok": False, "reason": f"bad operation_mode {receipt['operation_mode']}"}

    # A republish receipt is deliberately a separate, signed claim.  Normal
    # publishing must never accept it, and an explicit republish must not be
    # possible with an ordinary receipt.  The claim is covered by the Ed25519
    # signature because it lives inside the canonical receipt body.
    republish = receipt.get("republish")
    if republish is not None:
        if not allow_republish:
            return {"ok": False,
                    "reason": "republish receipt is not valid for a normal publish"}
        if not isinstance(republish, dict):
            return {"ok": False, "reason": "receipt.republish must be an object"}
        nonce = str(republish.get("nonce") or "")
        if not REPUBLISH_NONCE_RE.match(nonce):
            return {"ok": False, "reason": "receipt.republish.nonce invalid"}
        if str(republish.get("confirmed_at") or "").strip() == "":
            return {"ok": False, "reason": "receipt.republish.confirmed_at missing"}
    elif allow_republish:
        return {"ok": False, "reason": "explicit republish requires a republish claim"}

    if operation_mode and receipt["operation_mode"] != operation_mode:
        return {"ok": False, "reason": "receipt operation does not authorize this action"}
    expected_hash = (plan.get("compliance") or {}).get("content_hash")
    if "piece" in plan:
        from .idempotency import material_fingerprint
        computed = material_fingerprint(plan["piece"], account_id=plan.get("account_id", ""))
        if expected_hash != computed:
            return {"ok": False, "reason": "plan content changed; regenerate preview and approval"}
    if not expected_hash:
        return {"ok": False, "reason": "plan.compliance.content_hash missing"}
    if receipt["content_hash"] != expected_hash:
        return {"ok": False,
                "reason": "content_hash mismatch (receipt may only change "
                          "plan_id/operation_mode)"}
    if receipt["plan_id"] != plan.get("plan_id"):
        return {"ok": False, "reason": "receipt.plan_id != plan.plan_id"}

    try:
        expires = datetime.fromisoformat(receipt["expires_at"].replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return {"ok": False, "reason": "receipt.expires_at not ISO-8601"}
    try:
        issued = datetime.fromisoformat(receipt["issued_at"].replace("Z", "+00:00"))
        if issued.tzinfo is None:
            issued = issued.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return {"ok": False, "reason": "receipt.issued_at not ISO-8601"}
    if not issued <= now < expires:
        return {"ok": False, "reason": "APPROVAL_EXPIRED"}

    try:
        provided = bytes.fromhex(receipt["signature"])
    except (ValueError, TypeError):
        return {"ok": False, "reason": "receipt.signature not hex"}
    if not ed25519_pure.verify(provided, _canonical(receipt), bytes(public_key)):
        return {"ok": False, "reason": "APPROVAL_SIGNATURE"}
    return {"ok": True, "reason": "ok", "operation_mode": receipt["operation_mode"]}


def require_receipt(receipt, plan, public_key, *, now=None, operation_mode=None,
                    allow_republish: bool = False) -> dict:
    result = verify_receipt(receipt, plan, public_key, now=now,
                            operation_mode=operation_mode,
                            allow_republish=allow_republish)
    if not result["ok"]:
        raise GateRed(f"approval rejected: {result['reason']}")
    return result
