"""settings.json / accounts.json loading with sane defaults.

Hardcoded ~/publish-worker paths (Mac plan section 10.2) are replaced by the
Layout object; settings only carry customer-visible preferences.
"""

from __future__ import annotations

import copy

from .errors import ConfigError
from .jsonio import read_json

DEFAULT_SETTINGS = {
    "remote_channel": {"enabled": True},
    "vendor": None,                       # filled from version.py when absent
    "customer_id": "",
    "timezone": "Asia/Shanghai",
    "schedule": {
        "min_lead_minutes": 130,          # Mac parity, do not change
        "max_horizon_days": 14,           # Mac parity, do not change
        "avoid_minute_marks": [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55],
        "gap_min": 5,
        "gap_max": 8,
        # 1.2.20: customer-adjustable publish cadence controls.
        "windows": [
            ["07:00", "09:30"],
            ["11:00", "13:30"],
            ["17:00", "19:30"],
            ["20:00", "22:30"]
        ],
        "window_entries": [
            {"id": "morning", "start": "07:00", "end": "09:30", "enabled": True},
            {"id": "noon", "start": "11:00", "end": "13:30", "enabled": True},
            {"id": "evening", "start": "17:00", "end": "19:30", "enabled": True},
            {"id": "night", "start": "20:00", "end": "22:30", "enabled": True}
        ],
        "max_per_day_per_account": 0,
        "cross_account_gap_minutes": [5, 8],
        "backoff": {
            "initial_minutes": 30,
            "multiplier": 2.0,
            "max_minutes": 360
        },
    },
    "downlink": {
        "poll_interval_seconds": 300,     # launchd StartInterval=300 parity
        "max_concurrency": 2,
        "retry_backoff_seconds": [5, 15, 45, 135],
        "manifest_url_ttl_seconds": 600,  # <= 10 min
        "media_url_ttl_seconds": 3600,    # <= 60 min
        "bandwidth_limit_kbps": 0,        # 0 = unlimited
    },
    "retention_days": 14,
    "disk_watermark_gb": 5,
    "sms_wait_seconds": 180,
    "verification_detect_seconds": 30,
    "qr_wait_seconds": 300,
    "alerts": {"tray": True, "upload_summary": True},
    # 1.2.13: publishing waits for a Feishu confirmation.  The customer machine
    # carries only a low-privilege install token; the vendor Feishu app secret
    # lives on the approval service, never in this file or this package.
    "feishu_approval": {
        "enabled": True,
        "endpoint": "",
        "client_token": "",
        "timeout_minutes": 30,
        "poll_interval_seconds": 15,
    },
    # In-place incremental updates.  An empty manifest_url means "disabled"
    # even when enabled is true, so an unconfigured install never polls.
    "updates": {
        "enabled": True,
        "manifest_url": "",
        "check_interval_seconds": 3600,
        "initial_delay_seconds": 180,
        "request_timeout_seconds": 30,
        "download_retries": 4,
        "failed_retry_seconds": 21600,
        "health_timeout_seconds": 60,
        "tunnel_timeout_seconds": 30,
        "allow_insecure_http": False,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(path):
    raw = read_json(path, default=None)
    if raw is None:
        return copy.deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        raise ConfigError(f"settings.json must be an object: {path}")
    return _deep_merge(DEFAULT_SETTINGS, raw)
