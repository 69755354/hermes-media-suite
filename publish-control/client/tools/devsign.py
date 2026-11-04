"""DEV/TEST-ONLY signing helpers.  NOT part of the customer runtime.

1.2.5 (GPT review 1.2.4 items 3 / 19): the agent runtime (``agent/winport/``)
must not ship a licence / approval *issuer*.  Any code that can MINT a signed
licence or an approval receipt is a test / control-plane concern, so it lives
here under ``tools/`` (never imported by the agent) and signs with an explicit
private seed that never ships.

The customer package keeps only the VERIFIER: the 32-byte vendor public key in
``config/vendor_pubkey.hex``.  There is no private key of any kind in the
package (the production signing key lives on the control plane).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

from winport import ed25519_pure


# --------------------------------------------------------------------------- #
# Ed25519 SIGNING primitives -- test / control-plane side ONLY.
#
# 1.2.5 (GPT review item 14): these USED to live in the customer runtime module
# ``agent/winport/ed25519_pure.py``.  The runtime must be a PURE verifier, so the
# minting half (publickey / sign) moved here.  The curve math they reuse is the
# shared, dependency-free arithmetic in ed25519_pure (also used by verify()).
# --------------------------------------------------------------------------- #
def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _encodepoint(point) -> bytes:
    x, y = point
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))


def publickey(seed: bytes) -> bytes:
    """DEV/TEST ONLY.  Derive the Ed25519 public key for a private seed."""
    h = _sha512(seed)
    a = 2 ** 254 + sum(2 ** i * ((h[i // 8] >> (i % 8)) & 1) for i in range(3, 254))
    return _encodepoint(ed25519_pure._scalarmult(ed25519_pure.B, a))


def sign(message: bytes, seed: bytes, public: bytes) -> bytes:
    """DEV/TEST ONLY.  Ed25519-sign ``message`` with a throwaway private seed."""
    h = _sha512(seed)
    a = 2 ** 254 + sum(2 ** i * ((h[i // 8] >> (i % 8)) & 1) for i in range(3, 254))
    r = ed25519_pure._hint(h[32:64] + message) % ed25519_pure.Q
    R = ed25519_pure._scalarmult(ed25519_pure.B, r)
    S = (r + ed25519_pure._hint(_encodepoint(R) + public + message) * a) \
        % ed25519_pure.Q
    return _encodepoint(R) + S.to_bytes(32, "little")


def mint_dev_license(private_seed: bytes, **fields) -> dict:
    """DEV/TEST ONLY.  Build an Ed25519-signed licence with a test seed."""
    body = {
        "customer_id": fields.get("customer_id", "dev-000"),
        "machine_id": fields["machine_id"],
        "accounts": fields.get("accounts", []),
        "plan": fields.get("plan", "by_account"),
        "quota": fields.get("quota", {"publish_per_month": 100, "accounts": 1}),
        "seats": fields.get("seats", 4),
        "features": fields.get("features", ["fill", "collect", "report",
                                            "downlink"]),
        "issued_at": fields.get("issued_at",
                                time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                              time.gmtime())),
        "expires_at": fields["expires_at"],
        "grace_days": fields.get("grace_days", 14),
    }
    public = publickey(private_seed)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    body["signature"] = sign(payload, private_seed, public).hex()
    return body


def issue_receipt_for_test(private_seed: bytes, plan: dict, *,
                           operation_mode="approved_publish",
                           receipt_id="RCP-0001", approver_id="newme-owner",
                           ttl_minutes=30, now=None) -> dict:
    """DEV/TEST + control-plane side only.  The agent has no call site for this;
    production receipts are minted by the control plane (Ed25519, same trust
    root as licences) and arrive via the Feishu button / panel.
    """
    now = now or datetime.now(timezone.utc)
    receipt = {
        "receipt_id": receipt_id,
        "approver_id": approver_id,
        "approver_role": "account_owner",
        "plan_id": plan["plan_id"],
        "operation_mode": operation_mode,
        "content_hash": (plan.get("compliance") or {}).get("content_hash"),
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
    }
    body = {k: v for k, v in receipt.items() if k != "signature"}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    public = publickey(private_seed)
    receipt["signature"] = sign(canonical, private_seed, public).hex()
    return receipt
