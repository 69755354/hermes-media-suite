#!/usr/bin/env python3
"""Read-only validator and explicit additive migration for multi-device.

The default mode never writes. ``--apply`` is an operator-only action and is
intended for an approved database copy or maintenance window; this repository's
test evidence runs it only against temporary databases.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "migrations/20261028_multidevice.sql"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

REQUIRED = {
    "customers": {
        "active_device_id", "binding_epoch", "dispatch_paused",
        "device_binding_enabled",
    },
    "commands": {"device_id", "binding_epoch"},
    "remote_ops": {"device_id", "binding_epoch"},
    "customer_devices": {
        "device_id", "customer_id", "token_hash", "status",
        "binding_epoch", "last_seen",
    },
}

ADDED = {
    "customer_devices": {
        "label", "machine_code", "created", "updated", "token_issued_at",
        "activated_at", "isolated_at", "retired_at", "notes",
    },
    "commands": {"material_sha256"},
}


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _base_schema(conn):
    for table, columns in REQUIRED.items():
        missing = columns - _columns(conn, table)
        if missing:
            raise ValueError(
                f"base schema missing in {table}: {', '.join(sorted(missing))}")


def validate(conn):
    _base_schema(conn)
    for table, columns in ADDED.items():
        missing = columns - _columns(conn, table)
        if missing:
            raise ValueError(
                f"multi-device schema missing in {table}: "
                + ", ".join(sorted(missing)))

    if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='device_material_claims'").fetchone():
        raise ValueError("device_material_claims missing")
    if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='device_events'").fetchone():
        raise ValueError("device_events missing")
    if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' "
            "AND name='one_active_customer_device'").fetchone():
        raise ValueError("single-active device index still present")

    seen_hashes = set()
    seen_machine = set()
    for row in conn.execute(
            "SELECT device_id, customer_id, token_hash, status, binding_epoch, "
            "machine_code FROM customer_devices"):
        device_id, customer_id, token_hash, status, epoch, machine_code = row
        if not device_id or not customer_id:
            raise ValueError("device/customer id required")
        if not isinstance(token_hash, str) or not HEX64.fullmatch(token_hash):
            raise ValueError(f"invalid token hash for {device_id}")
        if token_hash in seen_hashes:
            raise ValueError(f"duplicate token hash for {device_id}")
        seen_hashes.add(token_hash)
        if status not in ("active", "isolated", "retired"):
            raise ValueError(f"invalid device status for {device_id}")
        if type(epoch) is not int or epoch < 0:
            raise ValueError(f"invalid binding epoch for {device_id}")
        key = (customer_id, machine_code or "")
        if machine_code:
            if key in seen_machine:
                raise ValueError(f"duplicate machine code for {customer_id}")
            seen_machine.add(key)

    for customer_id, active_device_id in conn.execute(
            "SELECT customer_id, active_device_id FROM customers "
            "WHERE active_device_id IS NOT NULL AND active_device_id != ''"):
        row = conn.execute(
            "SELECT status FROM customer_devices "
            "WHERE device_id=? AND customer_id=?",
            (active_device_id, customer_id)).fetchone()
        if row is None:
            raise ValueError(f"default device missing for {customer_id}")
        if row[0] != "active":
            raise ValueError(f"default device is not active for {customer_id}")

    for (customer_id, paused, enabled) in conn.execute(
            "SELECT customer_id, dispatch_paused, device_binding_enabled "
            "FROM customers"):
        if paused not in (0, 1) or enabled not in (0, 1):
            raise ValueError(f"invalid customer flags for {customer_id}")

    for table in ("commands", "remote_ops"):
        for (row_id, customer_id, device_id) in conn.execute(
                f"SELECT id, customer_id, device_id FROM {table} "
                "WHERE device_id IS NOT NULL"):
            if not conn.execute(
                    "SELECT 1 FROM customer_devices "
                    "WHERE device_id=? AND customer_id=?",
                    (device_id, customer_id)).fetchone():
                raise ValueError(
                    f"{table} row {row_id} references foreign device")

    for row in conn.execute(
            "SELECT customer_id, material_sha256, device_id, status "
            "FROM device_material_claims"):
        customer_id, sha, device_id, status = row
        if not HEX64.fullmatch(sha or ""):
            raise ValueError("invalid material hash in claims")
        if status not in ("claimed", "published", "released"):
            raise ValueError("invalid material claim status")
        if not conn.execute(
                "SELECT 1 FROM customer_devices "
                "WHERE device_id=? AND customer_id=?",
                (device_id, customer_id)).fetchone():
            raise ValueError("material claim references foreign device")

    if conn.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("foreign key conflicts")
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("integrity check failed")
    return True


def _split_statements(text):
    return [part.strip() for part in text.split(";") if part.strip()]


def migrate(conn):
    _base_schema(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in _split_statements(SQL_PATH.read_text(encoding="utf-8")):
            if statement.startswith("--"):
                statement = "\n".join(
                    line for line in statement.splitlines()
                    if not line.lstrip().startswith("--")
                ).strip()
            if not statement:
                continue
            match = re.search(
                r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)\s+(\w+)",
                statement, re.I)
            if match:
                table, column, declared = match.groups()
                existing = {
                    row[1]: row[2] for row in conn.execute(
                        f"PRAGMA table_info({table})")
                }
                if column in existing:
                    if existing[column].upper() != declared.upper():
                        raise ValueError(
                            f"conflicting column {table}.{column}")
                    continue
            conn.execute(statement)
        validate(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    mode = "rw" if args.apply else "ro"
    conn = sqlite3.connect(
        args.database.resolve().as_uri() + f"?mode={mode}", uri=True)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        if args.apply:
            migrate(conn)
        else:
            validate(conn)
        print(json.dumps(
            {"ok": True, "mode": "apply" if args.apply else "read-only"}))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
