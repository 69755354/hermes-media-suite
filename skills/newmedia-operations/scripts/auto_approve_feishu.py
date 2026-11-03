#!/usr/bin/env python3
"""Auto-approve pending Feishu pairing requests every 2 minutes.
Paired with cron: keeps new-user notification working while users get auto-approved.
"""
import json, os, time
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
PAIRING_DIRS = [
    HERMES_HOME / "pairing",
    HERMES_HOME / "profiles" / "customer" / "pairing",
]

approved_any = False
for pairing_dir in PAIRING_DIRS:
    pending_path = pairing_dir / "feishu-pending.json"
    approved_path = pairing_dir / "feishu-approved.json"
    if not pending_path.exists():
        continue
    try:
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        continue
    if not pending:
        continue
    approved = {}
    if approved_path.exists():
        try:
            approved = json.loads(approved_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            approved = {}
    for entry_id, info in pending.items():
        user_id = info.get("user_id", "")
        user_name = info.get("user_name", "")
        if user_id and user_id not in approved:
            approved[user_id] = {"user_name": user_name, "approved_at": time.time()}
            approved_any = True
    approved_path.write_text(json.dumps(approved, indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(approved_path, 0o600)
    pending_path.write_text("{}\n", encoding="utf-8")
    os.chmod(pending_path, 0o600)

print(f"{'Approved new users.' if approved_any else 'No pending users.'}")
