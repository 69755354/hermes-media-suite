"""Downlink ledger: run/downlink-ledger.jsonl (append-only, one event per line).

Separate from the publish idempotency ledger by design (downlink plan section 2.6):
downlink-ledger records FETCHING, stage2-ledger records PUBLISHING.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from .jsonio import append_jsonl

ACTIONS = {
    "LIST", "CHECK", "DIFF", "SKIP", "DOWNLOAD", "RESUME", "RESET",
    "VERIFY_FAIL",
    "VERIFY_OK", "BIND_OK", "BIND_PENDING", "READY", "INCOMPLETE",
    "APPROVE_ASK", "APPROVE_GOT", "CLEANUP", "ALERT",
}

MAX_BYTES = 20 << 20


class DownlinkLedger:
    def __init__(self, path, machine_id=None, operator="客户本机",
                 customer_id=None):
        self.path = Path(path)
        self.machine_id = machine_id
        self.operator = operator
        self.customer_id = customer_id

    def _rotate_if_needed(self) -> None:
        try:
            if self.path.exists() and self.path.stat().st_size > MAX_BYTES:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                self.path.rename(self.path.with_name(
                    self.path.name + f".{stamp}"))
        except OSError:
            pass

    def log(self, action: str, **fields) -> dict:
        if action not in ACTIONS:
            raise ValueError(f"unknown downlink action: {action}")
        self._rotate_if_needed()
        record = {
            "ts": fields.pop("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z")),
            "machine_id": self.machine_id,
            "operator": self.operator,
            "customer_id": self.customer_id,
            "action": action,
        }
        record.update(fields)
        append_jsonl(self.path, record)
        return record
