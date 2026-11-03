"""Idempotency key: 素材指纹 + 环境 + 时间窗 (source/design-refs-mainstream.md C).

Why this shape
--------------
主流发布工具踩过的坑是「重试 / 强杀重启 / 重复点击 → 同一条内容发了两遍」。
A key built from (account, content, exact schedule second) does NOT stop that:
a retry 3 seconds later, or a restart that re-reads the plan with a slightly
different timestamp, produces a *different* key and publishes again.

So the key here is deliberately coarse in exactly one dimension:

    键 = material_fingerprint(piece) + env_id + time_window(schedule_at)

  * ``material_fingerprint`` -- sha256 of the piece identity (title + copy +
    media sha256).  The same video/文案 always hashes the same, whatever the
    file name or upload path.
  * ``env_id`` -- the environment (one account system), so the same content may
    still be published once per environment (env_1 vs env_2 are different 号).
  * ``time_window`` -- ``schedule_at`` floored to a window (default 60 min).  Two
    retries that land in the same planned window collapse onto the SAME key and
    the second one is refused, instead of being published twice.

``stage2_ledger.Stage2Ledger`` still owns the atomic reserve/consume; this module
only decides *what* the key is.  The legacy ``stage2_ledger.idempotency_key``
(account|content|exact-time) is kept for Mac parity / old ledgers.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from .hashing import sha256_bytes
from .stage2_ledger import content_hash

#: default window: 60 minutes (schedule.pick_slots keeps >=35 min gaps, so two
#: intended pieces never share a window by accident).
DEFAULT_WINDOW_MINUTES = 60

SCHEMA = "idempotency/3.0"


def _parse_time(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def material_fingerprint(piece: dict, *, account_id: str = "") -> str:
    """素材指纹 = sha256(account + title + copy_body + media sha256).

    Reuses ``stage2_ledger.content_hash`` so the dry-run preview, the publish key
    and the approval receipt all speak about the exact same bytes.
    """
    piece = piece or {}
    payload = {"schema": "publish-content/3", "account_id": account_id or "",
               "title": piece.get("title") or "",
               "copy_body": piece.get("copy_body") or "",
               "sha256": piece.get("sha256") or piece.get("media_sha256"),
               "topics": piece.get("topics") or [],
               "cover_sha256": piece.get("cover_sha256") or {},
               "covers_requested": sorted(k for k, v in (piece.get("covers") or {}).items() if v),
               "platform_account_id": piece.get("platform_account_id") or "",
               "poi": piece.get("poi")}
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8"))


def time_window_bucket(schedule_at, *, window_minutes: int = DEFAULT_WINDOW_MINUTES) -> str:
    """Floor ``schedule_at`` to a fixed-size window -> a stable string.

    ``2026-10-16T14:37:00+08:00`` with 60-min windows -> ``20261016T1400``.
    """
    minutes = int(window_minutes)
    if minutes <= 0 or minutes > 24 * 60:
        raise ValueError("window_minutes must be within 1..1440")
    dt = _parse_time(schedule_at).astimezone(timezone.utc)
    floored = dt.replace(minute=(dt.minute // minutes) * minutes, second=0,
                         microsecond=0)
    return floored.strftime("%Y%m%dT%H%M") + f"/{minutes}m"


def publish_key(env_id: str, piece: dict, schedule_at, *,
                account_id: str = "", window_minutes: int = DEFAULT_WINDOW_MINUTES,
                material_fp: str | None = None) -> str:
    """The 1.2.0 publish idempotency key: 素材指纹 + 环境 + 时间窗."""
    if not env_id:
        raise ValueError("env_id is required: the key must be scoped to one environment")
    fp = material_fp or material_fingerprint(piece, account_id=account_id)
    window = time_window_bucket(schedule_at, window_minutes=window_minutes)
    return f"{env_id}|{fp}|{window}"


def key_fingerprint(key: str) -> str:
    """Short, safe handle for a key (audit logs / UI); never the raw key alone."""
    return sha256_bytes(str(key).encode("utf-8"))[:16]
