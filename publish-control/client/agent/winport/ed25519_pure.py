"""Pure-Python Ed25519 (RFC 8032) — VERIFY ONLY.

Why this exists: the wheel set on the customer machine ships the `cryptography`
package, but the Linux static self-test here has no third-party modules at all.
A dependency-free verifier lets the licence check be exercised end to end in CI
and on the dev machine, with identical semantics.

This is the compact reference construction (Edwards curve over 2^255-19,
SHA-512, canonical little-endian encoding).  It is used for VERIFYING the
vendor licence / approval receipt only.

1.2.5 (GPT review 1.2.5 item 14): the customer runtime module must be a PURE
verifier.  The signing primitives (``publickey`` / ``sign`` / ``_encodepoint``)
no longer live here -- they moved to ``tools/devsign.py``, which is the
test/control-plane side and never ships a private key.  The production signing
key never leaves the control plane.
"""

from __future__ import annotations

import hashlib

P = 2 ** 255 - 19
Q = 2 ** 252 + 27742317777372353535851937790883648493


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


_D = (-121665 * _inv(121666)) % P
_I = pow(2, (P - 1) // 4, P)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = (x * _I) % P
    if x % 2 != 0:
        x = P - x
    return x


_By = (4 * _inv(5)) % P
_Bx = _xrecover(_By)
B = (_Bx, _By)


def _edwards(p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    k = _D * x1 * x2 * y1 * y2
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + k)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - k)
    return (x3 % P, y3 % P)


def _scalarmult(point, e: int):
    if e == 0:
        return (0, 1)
    half = _scalarmult(point, e // 2)
    doubled = _edwards(half, half)
    if e & 1:
        doubled = _edwards(doubled, point)
    return doubled


def _decodepoint(data: bytes):
    if len(data) != 32:
        raise ValueError("point must be 32 bytes")
    y = int.from_bytes(data, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if (x & 1) != (data[31] >> 7):
        x = P - x
    point = (x, y)
    if not _isoncurve(point):
        raise ValueError("decoding point that is not on curve")
    return point


def _isoncurve(point) -> bool:
    x, y = point
    return (-x * x + y * y - 1 - _D * x * x * y * y) % P == 0


def _hint(data: bytes) -> int:
    return int.from_bytes(_sha512(data), "little")


def verify(signature: bytes, message: bytes, public: bytes) -> bool:
    if len(signature) != 64 or len(public) != 32:
        return False
    try:
        R = _decodepoint(signature[:32])
        A = _decodepoint(public)
    except ValueError:
        return False
    S = int.from_bytes(signature[32:], "little")
    if S >= Q:
        return False
    h = _hint(signature[:32] + public + message)
    return _scalarmult(B, S) == _edwards(R, _scalarmult(A, h))


IDENTITY = (0, 1)


def is_identity(point) -> bool:
    return point == IDENTITY


def is_on_curve(point) -> bool:
    return _isoncurve(point)


def is_low_order(point) -> bool:
    """True for the small-order points (8*P == identity) that break binding."""
    return is_identity(_scalarmult(point, 8))


def public_key_valid(public: bytes) -> tuple:
    """(ok, reason) -- a shape/curve sanity check, NOT a signature check.

    Used to prove the shipped ``config/vendor_pubkey.hex`` really is a usable
    Ed25519 public key before anyone blames the licence file.
    """
    if not isinstance(public, (bytes, bytearray)):
        return False, "public key is not bytes"
    if len(public) != 32:
        return False, f"public key must be 32 bytes, got {len(public)}"
    try:
        point = _decodepoint(bytes(public))
    except ValueError as exc:
        return False, f"public key is not a valid curve point: {exc}"
    if is_identity(point):
        return False, "public key is the identity point"
    if is_low_order(point):
        return False, "public key has small order (clone risk)"
    return True, "on curve, not identity, not small order"
