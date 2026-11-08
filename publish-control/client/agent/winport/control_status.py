"""Customer-visible status of the Feishu/control-plane connection.

The file ALWAYS lives in the shared worker data root
(``<data>/control-status.json``), never below a historical
``<data>/customers/<id>`` tenant root.  The poller runs with a tenant root for
its own state, but both it and the panel must read the same status file.  It
never contains a customer/device token.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

STATES = ("connected", "pending", "missing", "error", "disabled")
MAX_REASON = 300


def _data_dir(layout) -> Path:
    """Resolve the SHARED worker data root from Layout or CustomerLayout.

    ``Layout`` exposes ``data``; ``CustomerLayout`` keeps the shared root in
    ``base`` while its ``root`` is the per-customer tenant.  Preferring ``base``
    over ``root`` is what keeps the poller and panel on one file.
    """
    data = getattr(layout, "data", None)
    if data is None:
        data = getattr(layout, "base", None)
    if data is None:
        data = getattr(layout, "root", None)
    if data is None:
        raise AttributeError("layout has no data root")
    return Path(data)


def status_path(layout) -> Path:
    return _data_dir(layout) / "control-status.json"


def _clean_reason(reason) -> str:
    if reason is None:
        return ""
    text = str(reason).replace("\r", " ").replace("\n", " ").strip()
    return text[:MAX_REASON]


def write_status(layout, state, reason="", *, customer_id="", device_id="",
                 updated=None) -> Path:
    """Atomically write the status file with mode 0600 and no secrets."""
    if state not in STATES:
        raise ValueError(f"invalid control status: {state!r}")
    target = status_path(layout)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "reason": _clean_reason(reason),
        "updated": float(updated if updated is not None else time.time()),
        "customer_id": str(customer_id or ""),
        "device_id": str(device_id or ""),
    }
    fd, name = tempfile.mkstemp(prefix=".control-status-", suffix=".json",
                                dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(payload, out, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(name, 0o600)
        os.replace(name, target)
        os.chmod(target, 0o600)
    finally:
        Path(name).unlink(missing_ok=True)
    return target


def read_status(layout):
    """Return a normalised status dict, or ``None`` when absent/unreadable."""
    try:
        data = json.loads(status_path(layout).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("state") not in STATES:
        return None
    return {
        "state": data["state"],
        "reason": _clean_reason(data.get("reason")),
        "updated": data.get("updated"),
        "customer_id": str(data.get("customer_id") or ""),
        "device_id": str(data.get("device_id") or ""),
    }
