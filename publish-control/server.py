"""Multitenant control plane: customer registry / command queue / results.

Single file, standard library only:

    CONTROL_DB=/path/control.db CONTROL_PORT=8899 \
      CONTROL_ADMIN_TOKEN=... CONTROL_INBOUND_TOKEN=... python3 server.py

Design
------
* ``customers`` keeps the legacy ``chat_id`` column and the newer
  ``feishu_chat_id`` column; old databases are migrated and backfilled.
* ``command_id`` is the idempotency key.  Repeating the same command_id
  inserts once; polling claims a command atomically with ``BEGIN IMMEDIATE``
  so only one customer machine receives it.
* Results land in ``commands.result``.  A repeated callback never overwrites
  the first terminal result.
* Customer agents authenticate with ``Authorization: Bearer <token>`` (new)
  or ``X-Agent-Token: <token>`` (legacy).
* Every management endpoint (customers, commands, tokens, receipts) requires
  ``CONTROL_ADMIN_TOKEN``.  Inbound webhooks require ``CONTROL_INBOUND_TOKEN``
  (or the admin token when that variable is not set).  If no admin token is
  configured the management API fails closed with HTTP 503.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

DB = os.environ.get(
    "CONTROL_DB",
    "/home/ubuntu/workflow/projects/publish_control/control.db",
)

#: Management routes require this shared secret.  It is intentionally
#: mandatory: if it is not configured the management API fails closed instead
#: of exposing every customer's queue and token.
ADMIN_TOKEN_ENV = "CONTROL_ADMIN_TOKEN"
#: Optional separate secret for Feishu/inbound webhooks.  When absent the
#: admin token is accepted so existing single-operator deployments can migrate
#: without weakening the management API.
INBOUND_TOKEN_ENV = "CONTROL_INBOUND_TOKEN"

#: Command kinds allowed on both the server and the customer machine.
ALLOWED_KINDS = ("publish", "collect", "report", "status")
#: /update/<file> streams in chunks of this size (bytes).
UPDATE_CHUNK_BYTES = 1 << 20

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_RESERVED_NAMES = frozenset(
    ("con", "prn", "aux", "nul", "clock$")
    + tuple("com%d" % i for i in range(1, 10))
    + tuple("lpt%d" % i for i in range(1, 10))
)


class InvalidCustomerId(ValueError):
    """The customer id is not a safe, canonical Windows path component."""


def admin_token() -> str:
    return os.environ.get(ADMIN_TOKEN_ENV, "").strip()


def inbound_token() -> str:
    return os.environ.get(INBOUND_TOKEN_ENV, "").strip()


def token_equal(expected, supplied) -> bool:
    """Constant-time comparison that is safe for arbitrary header bytes."""
    try:
        return hmac.compare_digest(str(expected).encode("utf-8"),
                                   str(supplied).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError):
        return False


def normalize_customer_id(value) -> str:
    """Canonicalise a customer id exactly like the Windows client does."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = text.lower()
    if not _ID_RE.match(text):
        raise InvalidCustomerId(f"invalid customer_id: {value!r}")
    if text.endswith("."):
        raise InvalidCustomerId(
            f"invalid customer_id (trailing dot): {value!r}")
    if text.split(".", 1)[0] in _RESERVED_NAMES:
        raise InvalidCustomerId(
            f"invalid customer_id (reserved Windows name): {value!r}")
    return text

#: A running command becomes visible again after this lease, so a customer
#: machine that crashed mid-command can retry. The client's command_id state
#: prevents a second execution when the first result was already persisted.
COMMAND_LEASE_SECONDS = float(os.environ.get("COMMAND_LEASE_SECONDS", "300"))

_TERMINAL_STATUSES = ("done", "failed", "cancelled", "error")
_init_lock = threading.Lock()
_initialized = set()


def _db_path() -> str:
    return os.path.abspath(DB)


def conn():
    """Return a connection; schema is created/migrated on first use."""
    path = _db_path()
    if path not in _initialized:
        init()
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _table_columns(c, table: str) -> set:
    try:
        return {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
    except sqlite3.DatabaseError:
        return set()


def init():
    """Create tables and migrate an existing single-customer database.

    Safe to call repeatedly and from multiple threads.
    """
    path = _db_path()
    with _init_lock:
        parent = os.path.dirname(os.path.abspath(DB))
        if parent:
            os.makedirs(parent, exist_ok=True)
        c = sqlite3.connect(DB, timeout=10)
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS customers(
                  customer_id TEXT PRIMARY KEY,
                  name TEXT,
                  chat_id TEXT,
                  feishu_chat_id TEXT,
                  machine_code TEXT,
                  token TEXT,
                  created REAL,
                  updated REAL
                );
                CREATE TABLE IF NOT EXISTS chat_bindings(
                  chat_id TEXT PRIMARY KEY,
                  customer_id TEXT NOT NULL,
                  created REAL
                );
                CREATE TABLE IF NOT EXISTS commands(
                  id TEXT PRIMARY KEY,
                  command_id TEXT,
                  customer_id TEXT NOT NULL,
                  kind TEXT,
                  payload TEXT,
                  status TEXT,
                  result TEXT,
                  error TEXT,
                  created REAL,
                  updated REAL,
                  delivered REAL,
                  started REAL,
                  finished REAL
                );
                CREATE TABLE IF NOT EXISTS remote_ops(
                  id TEXT PRIMARY KEY,
                  customer_id TEXT NOT NULL,
                  op TEXT,
                  body TEXT,
                  status TEXT,
                  result TEXT,
                  created REAL,
                  updated REAL
                );
                """
            )

            # --- customers migration -------------------------------------
            customers_cols = _table_columns(c, "customers")
            for name, decl in (
                ("feishu_chat_id", "TEXT"),
                ("updated", "REAL"),
            ):
                if name not in customers_cols:
                    c.execute(f"ALTER TABLE customers ADD COLUMN {name} {decl}")
            # Old databases only had chat_id; backfill both lookup paths.
            c.execute(
                "UPDATE customers SET feishu_chat_id = chat_id "
                "WHERE (feishu_chat_id IS NULL OR feishu_chat_id = '') "
                "AND chat_id IS NOT NULL AND chat_id != ''"
            )
            c.execute(
                "UPDATE customers SET chat_id = feishu_chat_id "
                "WHERE (chat_id IS NULL OR chat_id = '') "
                "AND feishu_chat_id IS NOT NULL AND feishu_chat_id != ''"
            )
            c.execute("UPDATE customers SET updated = created WHERE updated IS NULL")

            # --- customer id canonicalisation ---------------------------
            # Win32 treats C1/c1 and "c."/"c" as the same path.  Canonicalise
            # the database before adding the case-insensitive unique index so
            # two aliases can never address the same tenant directory.
            rows = c.execute("SELECT customer_id FROM customers").fetchall()
            mapping = {}
            canonical = set()
            for row in rows:
                old = str(row[0] or "")
                new = normalize_customer_id(old)
                if not new:
                    raise RuntimeError("empty customer_id in customers table")
                if new in canonical:
                    raise RuntimeError(
                        "customer_id collision after normalisation: %r" % new)
                canonical.add(new)
                if new != old:
                    mapping[old] = new
            for old, new in mapping.items():
                c.execute("UPDATE customers SET customer_id=? WHERE customer_id=?",
                          (new, old))
                c.execute("UPDATE commands SET customer_id=? WHERE customer_id=?",
                          (new, old))
            # Orphaned commands (their customer row was removed earlier) must
            # resolve to the same canonical id as a future customer row.
            command_ids = [row[0] for row in c.execute(
                "SELECT DISTINCT customer_id FROM commands").fetchall()]
            for old in command_ids:
                new = normalize_customer_id(old)
                if new != old:
                    c.execute(
                        "UPDATE commands SET customer_id=? WHERE customer_id=?",
                        (new, old))
            try:
                c.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_id_nocase "
                    "ON customers(customer_id COLLATE NOCASE)")
            except sqlite3.IntegrityError as exc:
                raise RuntimeError(
                    "customer_id aliases differ only by case; clean the "
                    "customers table before starting") from exc

            c.execute("CREATE INDEX IF NOT EXISTS idx_customers_chat ON customers(feishu_chat_id)")
            try:
                c.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_chat_unique "
                    "ON customers(COALESCE(NULLIF(feishu_chat_id,''), chat_id)) "
                    "WHERE COALESCE(NULLIF(feishu_chat_id,''), chat_id) IS NOT NULL"
                )
            except sqlite3.IntegrityError:
                # Existing databases may already contain a duplicate binding;
                # leave them readable and let the application return a clear
                # 409 on the next write.
                pass

            # --- commands migration --------------------------------------
            command_cols = _table_columns(c, "commands")
            for name, decl in (
                ("command_id", "TEXT"),
                ("error", "TEXT"),
                ("started", "REAL"),
                ("finished", "REAL"),
                ("channel_id", "TEXT"),
            ):
                if name not in command_cols:
                    c.execute(f"ALTER TABLE commands ADD COLUMN {name} {decl}")
            c.execute("UPDATE commands SET command_id = id WHERE command_id IS NULL OR command_id = ''")
            try:
                c.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_commands_command_id "
                    "ON commands(command_id)"
                )
            except sqlite3.IntegrityError:
                # Extremely old databases may contain duplicate ids; leave the
                # data untouched and fall back to the primary-key lookup.
                pass
            c.execute("CREATE INDEX IF NOT EXISTS idx_commands_customer ON commands(customer_id, status, created)")
            c.commit()
            _initialized.add(path)
        finally:
            c.close()



DEVICE_ONLINE_SECONDS = float(os.environ.get("DEVICE_ONLINE_SECONDS", "120"))


class DeviceBindingError(ValueError):
    """The caller is not a live device of this customer."""


class NoAvailableDevice(DeviceBindingError):
    """The customer has no active device that can accept this task."""


class MaterialDeviceConflict(DeviceBindingError):
    """One material is already owned by another device of the same customer."""


def _has_table(c, name):
    return bool(c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone())


def _require_multidevice_schema(c):
    """Fail closed instead of half-operating on a pre-migration database."""
    required_columns = {
        "customer_devices": {"label", "machine_code", "created", "updated"},
        "commands": {"material_sha256"},
    }
    missing = []
    for table, columns in required_columns.items():
        have = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
        missing.extend(f"{table}.{name}" for name in sorted(columns - have))
    for table in ("device_material_claims", "device_events"):
        if not _has_table(c, table):
            missing.append(table)
    if missing:
        raise DeviceBindingError(
            "multi-device migration required before use: " + ", ".join(missing))


def _binding(c, customer_id):
    row = c.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
    return dict(row) if row else {}


def _device_online(row, now=None):
    try:
        seen = float(row["last_seen"] or 0)
    except (KeyError, TypeError, ValueError):
        return False
    return seen > 0 and (time.time() if now is None else now) - seen <= DEVICE_ONLINE_SECONDS


def _device_dict(row, now=None):
    if row is None:
        return {}
    data = dict(row)
    data["online"] = _device_online(row, now=now)
    return data


def _resolve_device(c, customer_id, device_id=None, *, require_online=False):
    """Return an active device row, preferring the customer's online default.

    The customer-level ``active_device_id`` is a default, not an exclusive
    lock.  Any active device may own its own tasks, materials and ledger.
    """
    requested = str(device_id or "").strip()
    now = time.time()
    if requested:
        row = c.execute(
            "SELECT * FROM customer_devices WHERE device_id=? AND customer_id=? "
            "AND status='active'", (requested, customer_id)).fetchone()
        if row is None:
            raise DeviceBindingError("requested device is not active for this customer")
        if require_online and not _device_online(row, now=now):
            raise NoAvailableDevice("requested device is offline")
        return row

    customer = _binding(c, customer_id)
    preferred = str(customer.get("active_device_id") or "").strip()
    rows = c.execute(
        "SELECT * FROM customer_devices WHERE customer_id=? AND status='active' "
        "ORDER BY COALESCE(last_seen, 0) DESC, created, device_id",
        (customer_id,)).fetchall()
    if not rows:
        if customer.get("device_binding_enabled"):
            raise NoAvailableDevice("no active device is available")
        return None
    if require_online:
        online = [row for row in rows if _device_online(row, now=now)]
        if not online:
            raise NoAvailableDevice("no online device is available")
        rows = online
    for row in rows:
        if row["device_id"] == preferred:
            return row
    return rows[0]


def _device_guard(c, customer_id, device_id=None, binding_epoch=None,
                  device_token=None, claiming=False):
    b = _binding(c, customer_id)
    if claiming and b.get("dispatch_paused"):
        raise DeviceBindingError("dispatch paused")
    if not b.get("device_binding_enabled"):
        # Registration staging: a device may prove its own identity before
        # enforcement is switched on.  Omitting device_id keeps the legacy
        # customer-token path working; supplying one must be fully valid.
        if not device_id:
            return b
        if type(binding_epoch) is not int or binding_epoch < 0:
            raise DeviceBindingError("device or epoch rejected")
        row = c.execute(
            "SELECT * FROM customer_devices WHERE device_id=? AND customer_id=?",
            (device_id, customer_id)).fetchone()
        digest = hashlib.sha256(str(device_token or "").encode()).hexdigest()
        if (not row or row["status"] != "active"
                or row["binding_epoch"] != binding_epoch
                or not device_token
                or not token_equal(row["token_hash"], digest)):
            raise DeviceBindingError("device credentials rejected")
        seen = time.time()
        c.execute(
            "UPDATE customer_devices SET last_seen=?, updated=? WHERE device_id=?",
            (seen, seen, device_id))
        binding = dict(b)
        binding.update(device_id=device_id, binding_epoch=binding_epoch,
                       device_binding_epoch=binding_epoch, device=dict(row))
        return binding
    if not device_id or type(binding_epoch) is not int or binding_epoch < 0:
        raise DeviceBindingError("device or epoch rejected")
    row = c.execute("SELECT * FROM customer_devices WHERE device_id=? AND customer_id=?",
                    (device_id, customer_id)).fetchone()
    digest = hashlib.sha256(str(device_token or "").encode()).hexdigest()
    if (not row or row["status"] != "active" or row["binding_epoch"] != binding_epoch
            or not device_token or not token_equal(row["token_hash"], digest)):
        raise DeviceBindingError("device credentials rejected")
    seen = time.time()
    c.execute("UPDATE customer_devices SET last_seen=?, updated=? WHERE device_id=?",
              (seen, seen, device_id))
    binding = dict(b)
    binding.update(device_id=device_id, binding_epoch=binding_epoch,
                   device_binding_epoch=binding_epoch, device=dict(row))
    return binding


def _target_guard(row, binding):
    if binding.get("device_binding_enabled") and (
            row["device_id"] != binding.get("device_id") or
            row["binding_epoch"] != binding.get("device_binding_epoch")):
        raise DeviceBindingError(
            "task belongs to another device or an old epoch; reconcile manually")


def _stamp_target(c, table, task_id, customer_id, expected=None, device_id=None):
    b = _binding(c, customer_id)
    if b.get("dispatch_paused"):
        raise DeviceBindingError("dispatch paused")
    expected = expected if isinstance(expected, dict) else {}
    requested = str(device_id or expected.get("expected_device_id") or "").strip()
    # Explicit targeting is honoured during staged rollout too.  Only a
    # completely untargeted legacy write may remain unaddressed.
    if not b.get("device_binding_enabled") and not requested:
        return None
    row = _resolve_device(c, customer_id, requested or None)
    if expected:
        if expected.get("expected_device_id") not in (None, row["device_id"]):
            raise DeviceBindingError("dispatch binding changed; rebuild and reconfirm")
        if (expected.get("expected_binding_epoch") is not None and
                (type(expected.get("expected_binding_epoch")) is not int or
                 expected.get("expected_binding_epoch") != row["binding_epoch"])):
            raise DeviceBindingError("dispatch binding changed; rebuild and reconfirm")
    c.execute(f"UPDATE {table} SET device_id=?, binding_epoch=? WHERE id=?",
              (row["device_id"], row["binding_epoch"], task_id))
    return row


def _poll_device_clause(c, customer_id, binding):
    """Scope a poll to one device, or to legacy unaddressed rows only.

    During staged rollout a single registered machine may still claim legacy
    untargeted work, because there is no second machine to confuse it with.
    With two or more active devices, device-identified polls are strict.
    """
    target = str(binding.get("device_id") or "").strip()
    if not target:
        return " AND device_id IS NULL", ()
    if not binding.get("device_binding_enabled"):
        active = c.execute(
            "SELECT COUNT(*) FROM customer_devices "
            "WHERE customer_id=? AND status='active'",
            (customer_id,)).fetchone()[0]
        if active <= 1:
            return " AND (device_id=? OR device_id IS NULL)", (target,)
    return " AND device_id=?", (target,)


def _device_event(c, customer_id, device_id, event, detail=None):
    c.execute(
        "INSERT INTO device_events(id,customer_id,device_id,event,detail,created) "
        "VALUES(?,?,?,?,?,?)",
        (uuid.uuid4().hex, customer_id, device_id, event,
         json.dumps(detail or {}, ensure_ascii=False), time.time()))


def _public_device(row):
    data = _device_dict(row)
    data.pop("token_hash", None)
    return data


def list_devices(customer_id: str):
    customer_id = normalize_customer_id(customer_id)
    c = conn()
    try:
        _require_multidevice_schema(c)
        rows = c.execute(
            "SELECT * FROM customer_devices WHERE customer_id=? "
            "ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'isolated' THEN 1 "
            "ELSE 2 END, COALESCE(last_seen,0) DESC, created, device_id",
            (customer_id,)).fetchall()
        customer = _binding(c, customer_id)
        return {
            "customer_id": customer_id,
            "active_device_id": customer.get("active_device_id"),
            "device_binding_enabled": bool(
                customer.get("device_binding_enabled")),
            "devices": [_public_device(row) for row in rows],
        }
    finally:
        c.close()


def select_device(customer_id: str, device_id=None, require_online=True):
    customer_id = normalize_customer_id(customer_id)
    c = conn()
    try:
        _require_multidevice_schema(c)
        row = _resolve_device(
            c, customer_id, device_id, require_online=require_online)
        if row is None:
            raise NoAvailableDevice("no device is available")
        return _public_device(row)
    finally:
        c.close()


def add_device(customer_id: str, label=None, machine_code=None, token=None,
               enforce_binding=True):
    """Register one more machine under the same customer.

    The returned token is the machine's activation code and is shown once.
    Existing devices keep working; adding one never rotates their credentials.
    """
    customer_id = normalize_customer_id(customer_id)
    machine_code = str(machine_code or "").strip() or None
    label = str(label or "").strip() or None
    plain_token = str(token or "").strip() or ("dev_" + uuid.uuid4().hex)
    token_hash = hashlib.sha256(plain_token.encode("utf-8")).hexdigest()
    now = time.time()
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        _require_multidevice_schema(c)
        customer = c.execute(
            "SELECT * FROM customers WHERE customer_id=?",
            (customer_id,)).fetchone()
        if customer is None:
            raise UnknownCustomer(customer_id)
        if c.execute(
                "SELECT 1 FROM customer_devices WHERE token_hash=?",
                (token_hash,)).fetchone():
            raise DeviceBindingError("activation code is already in use")
        if machine_code and c.execute(
                "SELECT 1 FROM customer_devices WHERE customer_id=? "
                "AND machine_code=?", (customer_id, machine_code)).fetchone():
            raise DeviceBindingError("machine_code is already registered")
        device_id = "d_" + uuid.uuid4().hex[:20]
        epoch = int(customer["binding_epoch"] or 0)
        c.execute(
            "INSERT INTO customer_devices("
            "device_id,customer_id,token_hash,status,binding_epoch,last_seen,"
            "label,machine_code,created,updated,token_issued_at,activated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (device_id, customer_id, token_hash, "active", epoch, None,
             label, machine_code, now, now, now, now))
        default_device = customer["active_device_id"]
        if not default_device:
            default_device = device_id
        c.execute(
            "UPDATE customers SET active_device_id=?, device_binding_enabled=?, "
            "updated=? WHERE customer_id=?",
            (default_device, 1 if enforce_binding else
             customer["device_binding_enabled"], now, customer_id))
        _device_event(c, customer_id, device_id, "added",
                      {"label": label, "machine_code": machine_code,
                       "enforce_binding": bool(enforce_binding)})
        c.commit()
        row = c.execute(
            "SELECT * FROM customer_devices WHERE device_id=?",
            (device_id,)).fetchone()
        result = _public_device(row)
        result.update(ok=True, customer_id=customer_id, token=plain_token)
        return result
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def _choose_default_locked(c, customer_id, exclude=None):
    rows = c.execute(
        "SELECT * FROM customer_devices WHERE customer_id=? AND status='active' "
        "AND device_id!=? ORDER BY COALESCE(last_seen,0) DESC, created, device_id",
        (customer_id, exclude or "")).fetchall()
    return rows[0]["device_id"] if rows else None


def isolate_device(customer_id: str, device_id: str, *, retire=False):
    customer_id = normalize_customer_id(customer_id)
    device_id = str(device_id or "").strip()
    now = time.time()
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        _require_multidevice_schema(c)
        row = c.execute(
            "SELECT * FROM customer_devices WHERE device_id=? AND customer_id=?",
            (device_id, customer_id)).fetchone()
        if row is None:
            raise DeviceBindingError("unknown device")
        if row["status"] == "retired":
            raise DeviceBindingError("device is already retired")
        status = "retired" if retire else "isolated"
        c.execute(
            "UPDATE customer_devices SET status=?, updated=?, isolated_at=?, "
            "retired_at=CASE WHEN ?='retired' THEN ? ELSE retired_at END "
            "WHERE device_id=?",
            (status, now, now, status, now, device_id))
        customer = _binding(c, customer_id)
        if customer.get("active_device_id") == device_id:
            c.execute(
                "UPDATE customers SET active_device_id=?, updated=? "
                "WHERE customer_id=?",
                (_choose_default_locked(c, customer_id, exclude=device_id),
                 now, customer_id))
        # A revoked device must never lose an in-flight command silently.
        # Keep the facts, but make them visibly require reconciliation.
        c.execute(
            "UPDATE commands SET status='needs_reconcile', "
            "error=COALESCE(error, 'device isolated before completion'), updated=? "
            "WHERE customer_id=? AND device_id=? AND status IN ('queued','running')",
            (now, customer_id, device_id))
        c.execute(
            "UPDATE remote_ops SET status='needs_reconcile', updated=? "
            "WHERE customer_id=? AND device_id=? AND status IN ('queued','running')",
            (now, customer_id, device_id))
        _release_unpublished_claims(c, customer_id, device_id)
        _device_event(c, customer_id, device_id, status, {})
        c.commit()
        return list_devices(customer_id)
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def activate_device(customer_id: str, device_id: str, rotate_token=True):
    customer_id = normalize_customer_id(customer_id)
    device_id = str(device_id or "").strip()
    now = time.time()
    new_token = None
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        _require_multidevice_schema(c)
        row = c.execute(
            "SELECT * FROM customer_devices WHERE device_id=? AND customer_id=?",
            (device_id, customer_id)).fetchone()
        if row is None:
            raise DeviceBindingError("unknown device")
        if row["status"] == "active":
            return list_devices(customer_id)
        epoch = int(row["binding_epoch"] or 0) + 1
        if rotate_token:
            new_token = "dev_" + uuid.uuid4().hex
            token_hash = hashlib.sha256(new_token.encode("utf-8")).hexdigest()
        else:
            token_hash = row["token_hash"]
        c.execute(
            "UPDATE customer_devices SET status='active', binding_epoch=?, "
            "token_hash=?, updated=?, token_issued_at=?, activated_at=?, "
            "isolated_at=NULL, retired_at=NULL WHERE device_id=?",
            (epoch, token_hash, now, now, now, device_id))
        customer = _binding(c, customer_id)
        if not customer.get("active_device_id"):
            c.execute(
                "UPDATE customers SET active_device_id=?, updated=? "
                "WHERE customer_id=?", (device_id, now, customer_id))
        _device_event(c, customer_id, device_id, "activated",
                      {"binding_epoch": epoch, "token_rotated": bool(rotate_token)})
        c.commit()
        result = list_devices(customer_id)
        if new_token:
            result["token"] = new_token
        return result
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def set_default_device(customer_id: str, device_id: str):
    customer_id = normalize_customer_id(customer_id)
    device_id = str(device_id or "").strip()
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        _require_multidevice_schema(c)
        row = c.execute(
            "SELECT * FROM customer_devices WHERE device_id=? AND customer_id=? "
            "AND status='active'", (device_id, customer_id)).fetchone()
        if row is None:
            raise DeviceBindingError("default device must be active")
        c.execute(
            "UPDATE customers SET active_device_id=?, updated=? WHERE customer_id=?",
            (device_id, time.time(), customer_id))
        _device_event(c, customer_id, device_id, "default_selected", {})
        c.commit()
        return list_devices(customer_id)
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def enable_device_binding(customer_id: str):
    """Turn enforcement on after every machine has been registered/updated.

    This is deliberately separate from ``add_device`` for staged migration:
    register all devices with ``enforce_binding=False``, verify their tokens,
    then enable binding once.  Enabling does not rotate existing device tokens.
    """
    customer_id = normalize_customer_id(customer_id)
    now = time.time()
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        _require_multidevice_schema(c)
        customer = c.execute(
            "SELECT * FROM customers WHERE customer_id=?",
            (customer_id,)).fetchone()
        if customer is None:
            raise UnknownCustomer(customer_id)
        active = c.execute(
            "SELECT COUNT(*) FROM customer_devices "
            "WHERE customer_id=? AND status='active'",
            (customer_id,)).fetchone()[0]
        if active < 1:
            raise DeviceBindingError(
                "register at least one active device before enabling binding")
        c.execute(
            "UPDATE customers SET device_binding_enabled=1, updated=? "
            "WHERE customer_id=?", (now, customer_id))
        _device_event(c, customer_id, None, "binding_enabled",
                      {"active_devices": active})
        c.commit()
        return list_devices(customer_id)
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def switch_device(customer_id: str, old_device_id: str, new_device_id: str):
    """Isolate one old machine and make a new machine take over this customer.

    The ledger is not copied, rewritten or moved: both machines already belong
    to the same customer_id and the ledger remains keyed by that identity.
    """
    customer_id = normalize_customer_id(customer_id)
    old_device_id = str(old_device_id or "").strip()
    new_device_id = str(new_device_id or "").strip()
    if not old_device_id or not new_device_id or old_device_id == new_device_id:
        raise DeviceBindingError("switch requires two different devices")
    now = time.time()
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        _require_multidevice_schema(c)
        old = c.execute(
            "SELECT * FROM customer_devices WHERE device_id=? AND customer_id=?",
            (old_device_id, customer_id)).fetchone()
        new = c.execute(
            "SELECT * FROM customer_devices WHERE device_id=? AND customer_id=?",
            (new_device_id, customer_id)).fetchone()
        if old is None or new is None:
            raise DeviceBindingError("both devices must belong to the customer")
        if new["status"] != "active":
            raise DeviceBindingError("new device must be active before cutover")
        inflight = c.execute(
            "SELECT COUNT(*) FROM commands WHERE customer_id=? AND device_id=? "
            "AND status IN ('queued','running','needs_reconcile')",
            (customer_id, old_device_id)).fetchone()[0]
        inflight += c.execute(
            "SELECT COUNT(*) FROM remote_ops WHERE customer_id=? AND device_id=? "
            "AND status IN ('queued','running','needs_reconcile')",
            (customer_id, old_device_id)).fetchone()[0]
        if inflight:
            raise DeviceBindingError(
                "old device has unresolved tasks; reconcile before switch")
        c.execute(
            "UPDATE customer_devices SET status='isolated', updated=?, isolated_at=? "
            "WHERE device_id=?", (now, now, old_device_id))
        epoch = max(int(old["binding_epoch"] or 0), int(new["binding_epoch"] or 0)) + 1
        c.execute(
            "UPDATE customer_devices SET status='active', binding_epoch=?, "
            "updated=?, activated_at=? WHERE device_id=?",
            (epoch, now, now, new_device_id))
        c.execute(
            "UPDATE customers SET active_device_id=?, binding_epoch=?, "
            "device_binding_enabled=1, updated=? WHERE customer_id=?",
            (new_device_id, epoch, now, customer_id))
        _release_unpublished_claims(c, customer_id, old_device_id)
        _device_event(c, customer_id, old_device_id, "switched_out",
                      {"new_device_id": new_device_id})
        _device_event(c, customer_id, new_device_id, "switched_in",
                      {"old_device_id": old_device_id, "binding_epoch": epoch})
        c.commit()
        return list_devices(customer_id)
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def _material_hashes(payload):
    if not isinstance(payload, dict):
        return []
    values = []
    for key in ("material_sha256", "material_sha256s"):
        value = payload.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple)):
            values.extend(value)
    for value in payload.get("materials") or []:
        if isinstance(value, dict):
            values.append(value.get("sha256") or value.get("material_sha256"))
        elif isinstance(value, str):
            values.append(value)
    # Publish commands may carry only a prepared plan.  The material identity
    # is ``piece.sha256``; ``content_hash`` is a different fingerprint and must
    # not be treated as a material claim.
    def add_piece(container):
        if not isinstance(container, dict):
            return
        piece = container.get("piece")
        if isinstance(piece, dict):
            values.append(piece.get("sha256") or piece.get("material_sha256"))
        nested_plan = container.get("plan")
        if isinstance(nested_plan, dict):
            piece = nested_plan.get("piece")
            if isinstance(piece, dict):
                values.append(piece.get("sha256") or piece.get("material_sha256"))
        nested_plan_data = container.get("plan_data")
        if isinstance(nested_plan_data, dict):
            piece = nested_plan_data.get("piece")
            if isinstance(piece, dict):
                values.append(piece.get("sha256") or piece.get("material_sha256"))

    for key in ("piece", "plan", "plan_data", "item", "row"):
        add_piece(payload.get(key))
    result = []
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", text):
            raise DeviceBindingError("material_sha256 must be 64 lowercase hex characters")
        if text not in result:
            result.append(text)
    return result


def _claim_materials(c, customer_id, device, payload, command_id):
    if device is None:
        return []
    _require_multidevice_schema(c)
    hashes = _material_hashes(payload)
    material_ids = {}
    if isinstance(payload, dict):
        for value in payload.get("materials") or []:
            if isinstance(value, dict) and value.get("sha256"):
                material_ids[str(value["sha256"]).lower()] = value.get("material_id")
    now = time.time()
    for sha in hashes:
        row = c.execute(
            "SELECT * FROM device_material_claims "
            "WHERE customer_id=? AND material_sha256=?",
            (customer_id, sha)).fetchone()
        if row is not None and row["device_id"] != device["device_id"]:
            if row["status"] != "released":
                raise MaterialDeviceConflict(
                    "material already belongs to another device of this customer")
        if row is None:
            c.execute(
                "INSERT INTO device_material_claims("
                "customer_id,material_sha256,material_id,device_id,command_id,"
                "status,created,updated) VALUES(?,?,?,?,?,'claimed',?,?)",
                (customer_id, sha, material_ids.get(sha), device["device_id"],
                 command_id, now, now))
        elif row["status"] == "released":
            # The former owner never published it.  A replacement machine may
            # take the claim over; cross-device duplication is still blocked
            # once either device completes the publish.
            c.execute(
                "UPDATE device_material_claims SET device_id=?, command_id=?, "
                "material_id=COALESCE(?,material_id), status='claimed', updated=? "
                "WHERE customer_id=? AND material_sha256=?",
                (device["device_id"], command_id, material_ids.get(sha), now,
                 customer_id, sha))
        else:
            c.execute(
                "UPDATE device_material_claims SET command_id=?, "
                "material_id=COALESCE(material_id,?), updated=? "
                "WHERE customer_id=? AND material_sha256=?",
                (command_id, material_ids.get(sha), now, customer_id, sha))
    return hashes


def _release_unpublished_claims(c, customer_id, device_id):
    """Release claims that can no longer become a publish.

    A claim tied to queued/running/needs_reconcile/done work is never released:
    the outcome is unknown or already published.  Failed/cancelled work (or no
    command at all) is safe to hand to a replacement machine.
    """
    now = time.time()
    c.execute(
        "UPDATE device_material_claims SET status='released', updated=? "
        "WHERE customer_id=? AND device_id=? AND status='claimed' "
        "AND (command_id IS NULL OR NOT EXISTS ("
        " SELECT 1 FROM commands c WHERE c.id=device_material_claims.command_id "
        " AND c.status IN ('queued','running','needs_reconcile','done')))",
        (now, customer_id, device_id))


def _save_settings(c, customer_id, body):
    for key in ("default_title", "default_topics", "policy_version"):
        if key not in body:
            continue
        if key not in _table_columns(c, "customers"):
            raise DeviceBindingError("settings migration required")
        value = body[key]
        if key == "default_topics" and value is not None:
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise DeviceBindingError("default_topics must be a list or null")
            value = json.dumps(value, ensure_ascii=False)
        elif value is not None and not isinstance(value, str):
            raise DeviceBindingError("setting must be text or null")
        c.execute(f"UPDATE customers SET {key}=? WHERE customer_id=?", (value, customer_id))


def new_token() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Data helpers (usable directly from tests / small admin scripts)
# ---------------------------------------------------------------------------

def _chat_of(body: dict) -> str:
    value = body.get("feishu_chat_id")
    if value is None:
        value = body.get("chat_id")
    return str(value).strip() if value is not None else ""


def _customer_dict(row, include_token: bool = False) -> dict:
    if row is None:
        return {}
    data = {
        "customer_id": row["customer_id"],
        "name": row["name"],
        "chat_id": row["chat_id"],
        "feishu_chat_id": row["feishu_chat_id"] or row["chat_id"],
        "machine_code": row["machine_code"],
        "created": row["created"],
        "updated": row["updated"],
    }
    for key in ("default_title", "default_topics", "policy_version", "active_device_id",
                "binding_epoch", "dispatch_paused", "device_binding_enabled"):
        data[key] = row[key] if key in row.keys() else None
    if data["default_topics"] is not None:
        data["default_topics"] = json.loads(data["default_topics"])
    if include_token:
        data["token"] = row["token"]
    return data


def _command_dict(row) -> dict:
    if row is None:
        return {}
    payload = row["payload"]
    result = row["result"]
    try:
        payload = json.loads(payload or "{}")
    except (TypeError, ValueError):
        pass
    try:
        result = json.loads(result or "{}")
    except (TypeError, ValueError):
        pass
    return {
        "id": row["id"],
        "command_id": row["command_id"] or row["id"],
        "customer_id": row["customer_id"],
        "kind": row["kind"],
        "payload": payload,
        "status": row["status"],
        "result": result,
        "error": row["error"] if "error" in row.keys() else None,
        "created": row["created"],
        "updated": row["updated"],
        "delivered": row["delivered"] if "delivered" in row.keys() else None,
        "started": row["started"] if "started" in row.keys() else None,
        "finished": row["finished"] if "finished" in row.keys() else None,
        "device_id": row["device_id"] if "device_id" in row.keys() else None,
        "binding_epoch": row["binding_epoch"] if "binding_epoch" in row.keys() else None,
        "material_sha256": (row["material_sha256"]
                            if "material_sha256" in row.keys() else None),
        "channel_id": (row["channel_id"]
                       if "channel_id" in row.keys() else None),
    }


def _customer_response(customer: dict, **extra) -> dict:
    body = {"ok": True}
    body.update(customer)
    body["customer"] = customer
    body.update(extra)
    return body


def _command_response(command: dict, **extra) -> dict:
    body = {"ok": True, "command": command}
    if command:
        command_id = command.get("command_id") or command.get("id")
        body.update(
            {
                "id": command_id,
                "command_id": command_id,
                "kind": command.get("kind"),
                "status": command.get("status"),
                "payload": command.get("payload"),
            }
        )
    body.update(extra)
    return body


def get_customer(customer_id: str, include_token: bool = False):
    customer_id = normalize_customer_id(customer_id)
    c = conn()
    try:
        row = c.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
        return _customer_dict(row, include_token=include_token)
    finally:
        c.close()


def find_customer_by_chat(chat_id: str):
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        return {}
    c = conn()
    try:
        row = c.execute(
            "SELECT * FROM customers "
            "WHERE COALESCE(NULLIF(feishu_chat_id,''), chat_id)=? "
            "ORDER BY created LIMIT 1",
            (chat_id,),
        ).fetchone()
        if row is None:
            row = c.execute(
                "SELECT c.* FROM customers c JOIN chat_bindings b "
                "ON b.customer_id=c.customer_id WHERE b.chat_id=? LIMIT 1",
                (chat_id,),
            ).fetchone()
        return _customer_dict(row)
    finally:
        c.close()


def find_customer_by_token(token: str):
    token = str(token or "")
    if not token:
        return {}
    c = conn()
    try:
        row = c.execute("SELECT * FROM customers WHERE token=?", (token,)).fetchone()
        return _customer_dict(row)
    finally:
        c.close()


def _chat_conflict(chat_id: str, exclude_customer: str | None = None) -> str | None:
    if not chat_id:
        return None
    c = conn()
    try:
        row = c.execute(
            "SELECT customer_id FROM customers "
            "WHERE COALESCE(NULLIF(feishu_chat_id,''), chat_id)=? "
            "AND customer_id!=? LIMIT 1",
            (chat_id, exclude_customer or ""),
        ).fetchone()
        return row["customer_id"] if row else None
    finally:
        c.close()


def upsert_customer(body: dict):
    """Create or update a customer. Returns (customer, token, created)."""
    body = body or {}
    customer_id = normalize_customer_id(body.get("customer_id"))
    if not customer_id:
        customer_id = "c_" + uuid.uuid4().hex[:10]
    chat_id = _chat_of(body)
    now = time.time()

    conflict = _chat_conflict(chat_id, exclude_customer=customer_id)
    if conflict:
        raise ChatConflict(chat_id, conflict)

    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
        created = row is None
        if created:
            token = body.get("token") or new_token()
            c.execute(
                "INSERT INTO customers(customer_id,name,chat_id,feishu_chat_id,machine_code,token,created,updated) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    customer_id,
                    body.get("name"),
                    chat_id or None,
                    chat_id or None,
                    body.get("machine_code"),
                    token,
                    now,
                    now,
                ),
            )
        else:
            token = body.get("token") or row["token"] or new_token()
            if body.get("rotate_token") or body.get("rotate"):
                token = new_token()
            name = body.get("name", row["name"])
            machine_code = body.get("machine_code", row["machine_code"])
            # Keep the old binding unless a chat field is explicit; an empty
            # string explicitly unbinds it.
            if "feishu_chat_id" in body or "chat_id" in body:
                new_chat = chat_id
            else:
                new_chat = row["feishu_chat_id"] or row["chat_id"]
            c.execute(
                "UPDATE customers SET name=?, chat_id=?, feishu_chat_id=?, machine_code=?, "
                "token=?, updated=? WHERE customer_id=?",
                (name, new_chat or None, new_chat or None, machine_code, token, now, customer_id),
            )
        _save_settings(c, customer_id, body)
        c.commit()
        row = c.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
        return _customer_dict(row), token, created
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def update_customer(customer_id: str, body: dict):
    """PUT/PATCH /api/customers/<cid>."""
    body = body or {}
    customer_id = normalize_customer_id(customer_id)
    if not customer_id:
        return None
    chat_id = _chat_of(body)
    conflict = _chat_conflict(chat_id, exclude_customer=customer_id) if (
        "feishu_chat_id" in body or "chat_id" in body
    ) else None
    if conflict:
        raise ChatConflict(chat_id, conflict)

    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
        if row is None:
            return None
        fields, values = [], []
        for key in ("name", "machine_code"):
            if key in body:
                fields.append(f"{key}=?")
                values.append(body.get(key))
        if "feishu_chat_id" in body or "chat_id" in body:
            fields.extend(["chat_id=?", "feishu_chat_id=?"])
            values.extend([chat_id or None, chat_id or None])
        if body.get("rotate_token") or body.get("rotate"):
            fields.append("token=?")
            values.append(new_token())
        elif "token" in body and body.get("token"):
            fields.append("token=?")
            values.append(str(body["token"]))
        fields.append("updated=?")
        values.append(time.time())
        values.append(customer_id)
        c.execute(f"UPDATE customers SET {', '.join(fields)} WHERE customer_id=?", values)
        _save_settings(c, customer_id, body)
        c.commit()
        row = c.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
        return _customer_dict(row)
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def _payload_channel(payload) -> str:
    """Best-effort channel id carried by a command payload.

    A publish command may name its channel directly, or nest it inside the
    plan/row it is about.  Missing means "any channel" (legacy behaviour).
    """
    if not isinstance(payload, dict):
        return ""
    for key in ("channel_id", "channel"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("plan", "row", "item"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            value = nested.get("channel_id") or nested.get("channel")
            if isinstance(value, str) and value.strip():
                return value.strip()
    env_id = payload.get("env_id")
    platform = payload.get("platform")
    if isinstance(env_id, str) and env_id.strip():
        env_id = env_id.strip()
        if isinstance(platform, str) and platform.strip():
            return env_id + ":" + platform.strip()
        return env_id
    return ""


def enqueue_command(customer_id: str, kind: str, payload: dict | None = None,
                    command_id: str | None = None, device_id: str | None = None):
    """Insert one command; idempotent on command_id.

    Returns ``(command_dict, duplicate)``.
    """
    kind = str(kind or "").strip().lower()
    if kind not in ALLOWED_KINDS:
        raise UnsupportedKind(kind)
    customer_id = normalize_customer_id(customer_id)
    if not customer_id:
        raise UnknownCustomer("")
    command_id = str(command_id or "").strip() or uuid.uuid4().hex
    payload = payload if isinstance(payload, dict) else {}
    if device_id is None:
        device_id = payload.get("device_id") or payload.get("target_device_id")
    if payload.get('expected_customer_id') not in (None, customer_id):
        raise DeviceBindingError('customer binding changed')
    now = time.time()

    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        if not c.execute("SELECT 1 FROM customers WHERE customer_id=?", (customer_id,)).fetchone():
            raise UnknownCustomer(customer_id)
        row = c.execute(
            "SELECT * FROM commands WHERE command_id=? OR id=? LIMIT 1",
            (command_id, command_id),
        ).fetchone()
        if row is not None:
            c.commit()
            if row["customer_id"] != customer_id:
                raise CommandConflict(command_id, row["customer_id"], customer_id)
            if row["device_id"] and device_id and row["device_id"] != device_id:
                raise DeviceBindingError(
                    "command_id already belongs to another device")
            return _command_dict(row), True

        c.execute(
            "INSERT INTO commands(id,command_id,customer_id,kind,payload,status,result,created,updated,channel_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                command_id,
                command_id,
                customer_id,
                kind,
                json.dumps(payload, ensure_ascii=False),
                "queued",
                None,
                now,
                now,
                _payload_channel(payload) or None,
            ),
        )
        device = _stamp_target(
            c, "commands", command_id, customer_id,
            payload if kind == "publish" else None, device_id=device_id)
        material_hashes = _claim_materials(
            c, customer_id, device, payload, command_id) if kind == "publish" else []
        if material_hashes:
            c.execute(
                "UPDATE commands SET material_sha256=? WHERE id=?",
                (material_hashes[0], command_id))
        c.commit()
        row = c.execute("SELECT * FROM commands WHERE id=?", (command_id,)).fetchone()
        return _command_dict(row), False
    except sqlite3.IntegrityError:
        # Lost a race on the unique command_id: return the winner.
        try:
            c.rollback()
        except Exception:
            pass
        row = c.execute(
            "SELECT * FROM commands WHERE command_id=? OR id=? LIMIT 1",
            (command_id, command_id),
        ).fetchone()
        if row is None:
            raise
        return _command_dict(row), True
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def enqueue_remote(customer_id: str, op: str, body, device_id=None) -> str:
    """Queue one operator request for a customer machine (HTTPS pull model)."""
    customer_id = normalize_customer_id(customer_id)
    body = body if isinstance(body, dict) else {}
    if device_id is None:
        device_id = body.get("device_id") or body.get("target_device_id")
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT 1 FROM customers WHERE customer_id=?",
                        (customer_id,)).fetchone()
        if row is None:
            raise UnknownCustomer(customer_id)
        op_id = uuid.uuid4().hex
        now = time.time()
        c.execute(
            "INSERT INTO remote_ops(id, customer_id, op, body, status, created, updated)"
            " VALUES(?,?,?,?,?,?,?)",
            (op_id, customer_id, str(op or ""), json.dumps(body or {}),
             "queued", now, now))
        _stamp_target(c, "remote_ops", op_id, customer_id, device_id=device_id)
        c.commit()
        return op_id
    finally:
        c.close()


def poll_remote(customer_id: str, *, device_id=None, binding_epoch=None, device_token=None):
    """Atomically claim one queued operator request."""
    customer_id = normalize_customer_id(customer_id)
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        binding = _device_guard(c, customer_id, device_id, binding_epoch, device_token, claiming=True)
        device_clause, device_args = _poll_device_clause(c, customer_id, binding)
        row = c.execute(
            "SELECT * FROM remote_ops WHERE customer_id=? AND status='queued'"
            + device_clause +
            " ORDER BY created, rowid LIMIT 1",
            (customer_id,) + device_args).fetchone()
        if row is None:
            c.commit()
            return None
        _target_guard(row, binding)
        c.execute("UPDATE remote_ops SET status='running', updated=? WHERE id=?",
                  (time.time(), row["id"]))
        c.commit()
        try:
            payload = json.loads(row["body"] or "{}")
        except ValueError:
            payload = {}
        return {"id": row["id"], "op": row["op"], "body": payload, "device_id": row["device_id"] if "device_id" in row.keys() else None, "binding_epoch": row["binding_epoch"] if "binding_epoch" in row.keys() else None}
    finally:
        c.close()


def finish_remote(customer_id: str, op_id, ok, result, *, device_id=None, binding_epoch=None, device_token=None):
    customer_id = normalize_customer_id(customer_id)
    op_id = str(op_id or "").strip()
    if not op_id:
        return False, "id required"
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        binding = _device_guard(c, customer_id, device_id, binding_epoch, device_token)
        row = c.execute("SELECT * FROM remote_ops WHERE id=?",
                        (op_id,)).fetchone()
        if row is None:
            return False, "unknown op"
        if row["customer_id"] != customer_id:
            return False, "op belongs to another customer"
        _target_guard(row, binding)
        if row["status"] in ("done", "failed"):
            return True, "already terminal"
        c.execute(
            "UPDATE remote_ops SET status=?, result=?, updated=? WHERE id=?",
            ("done" if ok else "failed",
             json.dumps(result if result is not None else {}), time.time(), op_id))
        c.commit()
        return True, ""
    finally:
        c.close()


def _safe_to_redeliver(row) -> bool:
    """\u4e22\u4e86\u56de\u6267\u53ef\u4ee5\u91cd\u53d1\u7684\u547d\u4ee4\u3002

    prepare/create/materials \u53ea\u8bfb\u7d20\u6750\u5e76\u5199 plan/preview\uff0c\u91cd\u53d1\u662f\u5e42\u7b49\u7684\uff1b
    \u771f\u53d1\u5e03\uff08confirm\uff09\u4ecd\u4e0d\u91cd\u53d1\uff0c\u907f\u514d\u91cd\u590d\u63d0\u4ea4\u3002
    """
    try:
        payload = json.loads(row["payload"] or "{}")
    except Exception:
        return False
    if str(row["kind"] or "") != "publish":
        return True
    return str(payload.get("op") or "").lower() in (
        "create", "prepare", "materials", "status")


def poll_command(customer_id: str, channel: str | None = None,
                 include_unaddressed: bool = False, *, device_id=None, binding_epoch=None, device_token=None):
    """Atomically claim the oldest queued command for a customer.

    A command leaves ``queued`` exactly once, so two concurrent pollers cannot
    both receive it. Returns ``None`` when the queue is empty.

    ``channel`` scopes the claim to one publish channel so one machine can run
    two accounts in parallel.  ``include_unaddressed`` lets the default worker
    still pick up legacy commands that carry no channel at all; only the
    default worker may set it, otherwise two workers could run two unaddressed
    commands at once on different accounts.
    """
    customer_id = normalize_customer_id(customer_id)
    channel = str(channel or "").strip() or None
    # A publisher may address a command by env id ("env_1") while the client
    # polls with its full account channel ("env_1:douyin").  Match both: the
    # exact channel and its env prefix, otherwise such commands sit queued
    # forever and the bot never receives a prepare result.
    channel_base = channel.split(":", 1)[0] if channel else None
    if channel and include_unaddressed:
        channel_clause = " AND (channel_id=? OR channel_id=? OR channel_id IS NULL)"
        channel_args: tuple = (channel, channel_base)
    elif channel:
        channel_clause = " AND (channel_id=? OR channel_id=?)"
        channel_args = (channel, channel_base)
    else:
        channel_clause = ""
        channel_args = ()
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        binding = _device_guard(c, customer_id, device_id, binding_epoch, device_token, claiming=True)
        now = time.time()
        device_clause, device_args = _poll_device_clause(c, customer_id, binding)
        row = c.execute(
            "SELECT * FROM commands WHERE customer_id=? AND status='queued'"
            + channel_clause + device_clause +
            " ORDER BY created, rowid LIMIT 1",
            (customer_id,) + channel_args + device_args,
        ).fetchone()
        if row is None:
            # Lease expiry: re-deliver a stale running command. The client is
            # idempotent on command_id, so an already-finished command simply
            # replays its stored result.
            row = c.execute(
                "SELECT * FROM commands WHERE customer_id=? AND status='running'"
                + channel_clause +
                device_clause +
                " AND COALESCE(delivered, 0) < ? ORDER BY created, rowid LIMIT 1",
                (customer_id,) + channel_args + device_args +
                (now - COMMAND_LEASE_SECONDS,),
            ).fetchone()
            if row is None:
                c.commit()
                return None
            _target_guard(row, binding)
            if binding.get("device_binding_enabled") and not _safe_to_redeliver(row):
                c.execute("UPDATE commands SET status='needs_reconcile', updated=? WHERE id=?", (now, row["id"]))
                c.commit()
                return None
            c.execute(
                "UPDATE commands SET delivered=?, updated=? WHERE id=? AND status='running'",
                (now, now, row["id"]),
            )
            c.commit()
            row = c.execute("SELECT * FROM commands WHERE id=?", (row["id"],)).fetchone()
            result = _command_dict(row)
            result["command_id"] = result.get("command_id") or result["id"]
            result["id"] = result["command_id"]
            return result
        _target_guard(row, binding)
        cur = c.execute(
            "UPDATE commands SET status='running', delivered=?, started=?, updated=? "
            "WHERE id=? AND status='queued'",
            (now, now, now, row["id"]),
        )
        if cur.rowcount != 1:
            c.rollback()
            return None
        c.commit()
        row = c.execute("SELECT * FROM commands WHERE id=?", (row["id"],)).fetchone()
        result = _command_dict(row)
        # New clients use command_id; old clients read id.  Return both.
        result["command_id"] = result.get("command_id") or result["id"]
        result["id"] = result["command_id"]
        return result
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def get_command(command_id: str, customer_id: str | None = None):
    c = conn()
    try:
        sql = "SELECT * FROM commands WHERE command_id=? OR id=?"
        args = [command_id, command_id]
        if customer_id:
            customer_id = normalize_customer_id(customer_id)
            sql += " AND customer_id=?"
            args.append(customer_id)
        row = c.execute(sql + " LIMIT 1", args).fetchone()
        return _command_dict(row)
    finally:
        c.close()


def _published_evidence(payload_json, result):
    """Only a real publish may mark a material as published.

    prepare/create also ends as ``done`` but never publishes; the old code
    marked those claims published anyway (4 false rows found 2026-11-03).
    """
    try:
        payload = json.loads(payload_json or "{}")
    except Exception:
        payload = {}
    if str((payload or {}).get("op") or "").lower() != "confirm":
        return False
    if not isinstance(result, dict):
        return False
    if result.get("published") is True:
        return True
    return bool(result.get("platform_work_id") or result.get("work_id")
                or result.get("aweme_id"))


def record_result(customer_id: str, command_id: str, status: str = "done",
                  result: dict | None = None, *, device_id=None, binding_epoch=None, device_token=None):
    """Persist a terminal result. First terminal status wins (idempotent)."""
    customer_id = normalize_customer_id(customer_id)
    command_id = str(command_id or "").strip()
    if not customer_id:
        raise UnknownCustomer("")
    if not command_id:
        raise KeyError("command_id required")
    status = str(status or "done").strip().lower()
    if status in ("ok", "success", "completed"):
        status = "done"
    elif status in ("error", "exception"):
        status = "failed"
    if status not in ("done", "failed", "cancelled"):
        status = "failed"
    result = result if isinstance(result, dict) else {"value": result}
    now = time.time()

    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        binding = _device_guard(c, customer_id, device_id, binding_epoch, device_token)
        row = c.execute(
            "SELECT * FROM commands WHERE (command_id=? OR id=?) AND customer_id=? LIMIT 1",
            (command_id, command_id, customer_id),
        ).fetchone()
        if row is None:
            return None
        _target_guard(row, binding)
        if row["status"] in _TERMINAL_STATUSES:
            c.commit()
            return _command_dict(row), True
        error = result.get("error") if isinstance(result, dict) else None
        c.execute(
            "UPDATE commands SET status=?, result=?, error=?, finished=?, updated=? "
            "WHERE id=? AND customer_id=?",
            (
                status,
                json.dumps(result, ensure_ascii=False),
                str(error) if error else None,
                now,
                now,
                row["id"],
                customer_id,
            ),
        )
        if status == "done" and _published_evidence(row["payload"], result):
            c.execute(
                "UPDATE device_material_claims SET status='published', updated=? "
                "WHERE customer_id=? AND command_id=?",
                (now, customer_id, row["id"]))
        c.commit()
        row = c.execute("SELECT * FROM commands WHERE id=?", (row["id"],)).fetchone()
        return _command_dict(row), False
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise
    finally:
        c.close()


def list_commands(customer_id: str | None = None, limit: int = 50,
                  device_id: str | None = None):
    c = conn()
    try:
        if customer_id:
            customer_id = normalize_customer_id(customer_id)
            if device_id:
                rows = c.execute(
                    "SELECT * FROM commands WHERE customer_id=? AND device_id=? "
                    "ORDER BY created DESC LIMIT ?",
                    (customer_id, str(device_id), int(limit)),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM commands WHERE customer_id=? ORDER BY created DESC LIMIT ?",
                    (customer_id, int(limit)),
                ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM commands ORDER BY created DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [_command_dict(r) for r in rows]
    finally:
        c.close()


class ChatConflict(Exception):
    def __init__(self, chat_id, customer_id):
        super().__init__(f"chat_id {chat_id} already bound to {customer_id}")
        self.chat_id = chat_id
        self.customer_id = customer_id


class CommandConflict(Exception):
    def __init__(self, command_id, existing_customer, requested_customer):
        super().__init__(
            f"command_id {command_id} already belongs to {existing_customer}"
        )
        self.command_id = command_id
        self.existing_customer = existing_customer
        self.requested_customer = requested_customer


class UnsupportedKind(Exception):
    def __init__(self, kind):
        super().__init__(f"unsupported command kind: {kind}")
        self.kind = kind


class UnknownCustomer(Exception):
    def __init__(self, customer_id):
        super().__init__(f"unknown customer: {customer_id}")
        self.customer_id = customer_id


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

_INBOUND_PATHS = (
    "/api/inbound",
    "/api/message",
    "/api/messages",
    "/api/feishu",
    "/api/feishu/inbound",
    "/api/feishu/message",
)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PublishControl/2.0"

    def log_message(self, *args):
        pass

    # -- plumbing ---------------------------------------------------------
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_update_file(self, name):
        import re as _re
        name = str(name or "")
        if not _re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(json|zip)", name):
            return self._send(404, {"ok": False, "error": "not found"})
        root = os.environ.get("CONTROL_UPDATE_DIR") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "updates")
        full = os.path.join(root, name)
        if not os.path.isfile(full):
            return self._send(404, {"ok": False, "error": "not found"})
        # Stream in chunks: the full offline package is ~300 MB and a handful of
        # concurrent update checks must not each hold a copy in memory.
        try:
            fh = open(full, "rb")
            size = os.fstat(fh.fileno()).st_size
        except OSError:
            return self._send(500, {"ok": False, "error": "read failed"})
        with fh:
            self.send_response(200)
            self.send_header("Content-Type",
                             "application/json; charset=utf-8" if name.endswith(".json")
                             else "application/zip")
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    chunk = fh.read(UPDATE_CHUNK_BYTES)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    def _bearer(self):
        auth = (self.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return (
            (self.headers.get("X-Agent-Token") or "").strip()
            or (self.headers.get("X-Customer-Token") or "").strip()
        )

    def _auth(self, customer_id):
        token = self._bearer()
        if not token or not customer_id:
            return False
        c = conn()
        try:
            row = c.execute(
                "SELECT token FROM customers WHERE customer_id=?", (customer_id,)
            ).fetchone()
        finally:
            c.close()
        if row is None or not row["token"]:
            return False
        return token_equal(row["token"], token)

    def _admin_bearer(self):
        for header in ("X-Admin-Token", "X-Control-Token"):
            value = (self.headers.get(header) or "").strip()
            if value:
                return value
        return self._bearer()

    def _require_admin(self) -> bool:
        expected = admin_token()
        if not expected:
            self._send(503, {
                "ok": False,
                "error": "admin authentication is not configured",
                "code": "ADMIN_AUTH_UNCONFIGURED",
                "hint": "set " + ADMIN_TOKEN_ENV,
            })
            return False
        supplied = self._admin_bearer()
        if not supplied:
            self._send(401, {
                "ok": False,
                "error": "admin token required",
                "code": "ADMIN_TOKEN_REQUIRED",
            })
            return False
        if not token_equal(expected, supplied):
            self._send(403, {
                "ok": False,
                "error": "bad admin token",
                "code": "BAD_ADMIN_TOKEN",
            })
            return False
        return True

    def _require_inbound(self) -> bool:
        expected = inbound_token() or admin_token()
        if not expected:
            self._send(503, {
                "ok": False,
                "error": "inbound authentication is not configured",
                "code": "INBOUND_AUTH_UNCONFIGURED",
                "hint": "set " + INBOUND_TOKEN_ENV + " or " + ADMIN_TOKEN_ENV,
            })
            return False
        supplied = (self.headers.get("X-Inbound-Token") or "").strip()
        if not supplied:
            supplied = self._bearer()
        if not supplied:
            self._send(401, {
                "ok": False,
                "error": "inbound token required",
                "code": "INBOUND_TOKEN_REQUIRED",
            })
            return False
        if not token_equal(expected, supplied):
            self._send(403, {
                "ok": False,
                "error": "bad inbound token",
                "code": "BAD_INBOUND_TOKEN",
            })
            return False
        return True

    def _normalize_or_400(self, value):
        try:
            return normalize_customer_id(value)
        except InvalidCustomerId as exc:
            self._send(400, {
                "ok": False,
                "error": str(exc),
                "code": "INVALID_CUSTOMER_ID",
            })
            return None

    def _auth_or_find(self, body):
        """Return authenticated customer_id, or None after sending an error."""
        customer_id = str(body.get("customer_id") or "").strip()
        if customer_id:
            try:
                customer_id = normalize_customer_id(customer_id)
            except InvalidCustomerId as exc:
                self._send(400, {
                    "ok": False, "error": str(exc),
                    "code": "INVALID_CUSTOMER_ID"})
                return None
        if not customer_id:
            customer = find_customer_by_token(self._bearer())
            customer_id = customer.get("customer_id") or ""
        if not customer_id:
            self._send(400, {"ok": False, "error": "customer_id required"})
            return None
        c = conn()
        try:
            binding = _device_guard(c, customer_id, **self._device_args(body))
        finally:
            c.close()
        if (not binding.get("device_binding_enabled")
                and not binding.get("device_id")
                and not self._auth(customer_id)):
            self._send(403, {"ok": False, "error": "bad token", "code": "BAD_TOKEN"})
            return None
        return customer_id

    def _not_found(self):
        self._send(404, {"ok": False, "error": "not found"})

    @staticmethod
    def _kind_from_text(text: str):
        import re

        text = re.sub(r"\s+", "", str(text or ""))
        if not text:
            return None
        if text in ("6", "\u72b6\u6001", "status"):
            return "status"
        if text in ("5", "\u51fa\u8868", "\u62a5\u8868", "\u6570\u636e\u8868"):
            return "report"
        if text == "4" or text.startswith("\u53d6\u6570"):
            return "collect"
        if text in ("2", "3") or text.startswith(
                ("\u6539\u671f", "\u6682\u505c", "\u6392\u671f")):
            return "schedule"
        if text == "1" or text.startswith("\u53d1\u5e03") or text in (
                "\u786e\u8ba4", "\u786e\u8ba4\u53d1\u5e03"):
            return "publish"
        return None

    # -- GET --------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # ---- 更新分发（公开只读）-----------------------------------------
        # 清单由 Ed25519 厂商签名保护、补丁包由清单里的 sha256 绑定，所以
        # 公开可读不构成信任缺口；客户机 updater 只认签名，不认来源可信度。
        if path.startswith("/update/"):
            return self._send_update_file(path[len("/update/"):])

        if path == "/health":
            c = conn()
            try:
                customers = c.execute("SELECT COUNT(*) n FROM customers").fetchone()["n"]
                queued = c.execute(
                    "SELECT COUNT(*) n FROM commands WHERE status='queued'"
                ).fetchone()["n"]
            finally:
                c.close()
            return self._send(
                200, {"ok": True, "customers": customers, "queued": queued}
            )

        # Every remaining GET is a management read (customers, commands,
        # tokens, receipts).  Authenticate before any lookup.
        if not self._require_admin():
            return

        if path == "/api/customers":
            chat_id = (query.get("chat_id") or query.get("feishu_chat_id") or [""])[0].strip()
            if chat_id:
                customer = find_customer_by_chat(chat_id)
                if not customer:
                    return self._send(
                        404,
                        {
                            "ok": False,
                            "error": "unknown chat_id",
                            "code": "CHAT_NOT_FOUND",
                            "chat_id": chat_id,
                            "message": f"chat_id {chat_id} is not bound to any customer",
                        },
                    )
                return self._send(200, _customer_response(customer))
            c = conn()
            try:
                rows = [
                    _customer_dict(r)
                    for r in c.execute("SELECT * FROM customers ORDER BY created")
                ]
            finally:
                c.close()
            return self._send(200, {"ok": True, "customers": rows})

        if path.startswith("/api/customers/by-chat/"):
            chat_id = unquote(path[len("/api/customers/by-chat/"):]).strip()
            customer = find_customer_by_chat(chat_id)
            if not customer:
                return self._send(
                    404,
                    {
                        "ok": False,
                        "error": "unknown chat_id",
                        "code": "CHAT_NOT_FOUND",
                        "chat_id": chat_id,
                        "message": f"chat_id {chat_id} is not bound to any customer",
                    },
                )
            return self._send(200, _customer_response(customer))

        if path.startswith("/api/chat/"):
            chat_id = unquote(path[len("/api/chat/"):]).strip()
            customer = find_customer_by_chat(chat_id)
            if not customer:
                return self._send(
                    404,
                    {
                        "ok": False,
                        "error": "unknown chat_id",
                        "code": "CHAT_NOT_FOUND",
                        "chat_id": chat_id,
                        "message": f"chat_id {chat_id} is not bound to any customer",
                    },
                )
            return self._send(200, _customer_response(customer))

        if path == "/api/resolve":
            chat_id = (query.get("chat_id") or query.get("feishu_chat_id") or [""])[0].strip()
            customer = find_customer_by_chat(chat_id)
            if not customer:
                return self._send(
                    404,
                    {
                        "ok": False,
                        "error": "unknown chat_id",
                        "code": "CHAT_NOT_FOUND",
                        "chat_id": chat_id,
                        "message": f"chat_id {chat_id} is not bound to any customer",
                    },
                )
            return self._send(200, _customer_response(customer))

        device_match = re.fullmatch(
            r"/api/customers/([^/]+)/devices(?:/(select))?", path)
        if device_match:
            customer_id = self._normalize_or_400(
                unquote(device_match.group(1)))
            if customer_id is None:
                return
            customer = get_customer(customer_id)
            if not customer:
                return self._send(404, {
                    "ok": False, "error": "unknown customer",
                    "code": "CUSTOMER_NOT_FOUND", "customer_id": customer_id})
            try:
                if device_match.group(2) == "select":
                    requested = (query.get("device_id") or [""])[0].strip() or None
                    require_online = (query.get("require_online") or ["1"])[0].lower() not in (
                        "0", "false", "no")
                    device = select_device(
                        customer_id, requested, require_online=require_online)
                    return self._send(200, {
                        "ok": True, "customer_id": customer_id, "device": device})
                return self._send(200, {"ok": True, **list_devices(customer_id)})
            except NoAvailableDevice as exc:
                return self._send(409, {
                    "ok": False, "error": str(exc),
                    "code": "NO_AVAILABLE_DEVICE",
                    "customer_id": customer_id})
            except DeviceBindingError as exc:
                return self._send(409, {
                    "ok": False, "error": str(exc),
                    "code": "DEVICE_SCHEMA_REQUIRED",
                    "customer_id": customer_id})

        if path.startswith("/api/customers/"):
            customer_id = unquote(path[len("/api/customers/"):])
            customer_id = self._normalize_or_400(customer_id)
            if customer_id is None:
                return
            customer = get_customer(
                customer_id,
                include_token=(query.get("include_token") or ["0"])[0] in ("1", "true", "yes"),
            )
            if not customer:
                return self._send(
                    404,
                    {
                        "ok": False,
                        "error": "unknown customer",
                        "code": "CUSTOMER_NOT_FOUND",
                        "customer_id": customer_id,
                    },
                )
            return self._send(200, _customer_response(customer))

        if path.startswith("/api/command/") and path not in ("/api/command/list",):
            command_id = unquote(path[len("/api/command/"):])
            command = get_command(command_id)
            if not command:
                return self._send(404, {"ok": False, "error": "unknown command", "command_id": command_id})
            return self._send(200, _command_response(command))

        if path.startswith("/api/commands/") and path != "/api/commands/list":
            command_id = unquote(path[len("/api/commands/"):])
            command = get_command(command_id)
            if not command:
                return self._send(404, {"ok": False, "error": "unknown command", "command_id": command_id})
            return self._send(200, _command_response(command))

        if path in ("/api/command/list", "/api/commands", "/api/commands/list"):
            customer_id = (query.get("customer_id") or [""])[0].strip() or None
            device_id = (query.get("device_id") or [""])[0].strip() or None
            if customer_id:
                customer_id = self._normalize_or_400(customer_id)
                if customer_id is None:
                    return
            return self._send(
                200,
                {"ok": True, "commands": list_commands(
                    customer_id=customer_id, device_id=device_id)},
            )

        return self._not_found()

    # -- POST -------------------------------------------------------------
    def _device_args(self, body):
        return dict(device_id=body.get("device_id"), binding_epoch=body.get("binding_epoch"),
                    device_token=self._bearer())

    def do_POST(self):
        try:
            return self._post_dispatch()
        except MaterialDeviceConflict as exc:
            return self._send(409, {
                "ok": False, "code": "MATERIAL_DEVICE_CONFLICT",
                "error": str(exc)})
        except NoAvailableDevice as exc:
            return self._send(409, {
                "ok": False, "code": "NO_AVAILABLE_DEVICE",
                "error": str(exc)})
        except DeviceBindingError as exc:
            return self._send(409, {"ok": False, "code": "DEVICE_BINDING_REJECTED", "error": str(exc)})

    def _post_dispatch(self):
        path = urlparse(self.path).path
        body = self._body()

        # Customer-agent routes authenticate with the customer's own token.
        if path == "/api/agent/poll":
            customer_id = self._auth_or_find(body)
            if customer_id is None:
                return
            command = poll_command(
                customer_id,
                channel=body.get("channel") or body.get("channel_id"),
                include_unaddressed=bool(body.get("include_unaddressed")),
                **self._device_args(body),
            )
            return self._send(200, _command_response(command))

        if path in ("/api/agent/result", "/api/agent/report"):
            customer_id = self._auth_or_find(body)
            if customer_id is None:
                return
            return self._handle_result(customer_id, body)

        if path == "/api/agent/remote-poll":
            customer_id = self._auth_or_find(body)
            if customer_id is None:
                return
            return self._send(200, {"ok": True, "op": poll_remote(customer_id, **self._device_args(body))})

        if path == "/api/agent/remote-result":
            customer_id = self._auth_or_find(body)
            if customer_id is None:
                return
            ok, detail = finish_remote(customer_id, body.get("id"),
                                       bool(body.get("ok")), body.get("result"), **self._device_args(body))
            return self._send(200 if ok else 400,
                              {"ok": ok, "detail": detail})

        # Older clients post results to /api/command.  That path is customer-
        # authenticated; the same URL with a kind is an admin enqueue.
        if path == "/api/command" and (
            (body.get("command_id") or body.get("id")) and (
                "result" in body or ("status" in body and not body.get("kind"))
            )
        ):
            customer_id = self._auth_or_find(body)
            if customer_id is None:
                return
            return self._handle_result(customer_id, body)

        # Inbound webhooks use their own token; every other POST is a
        # management write and requires the admin token.
        if path in _INBOUND_PATHS:
            if not self._require_inbound():
                return
        else:
            if not self._require_admin():
                return

        if path in ("/api/customers", "/api/customers/"):
            try:
                customer, token, created = upsert_customer(body)
            except InvalidCustomerId as exc:
                return self._send(400, {
                    "ok": False, "error": str(exc),
                    "code": "INVALID_CUSTOMER_ID"})
            except ChatConflict as exc:
                return self._send(
                    409,
                    {
                        "ok": False,
                        "error": "chat_id already bound",
                        "code": "CHAT_ALREADY_BOUND",
                        "chat_id": exc.chat_id,
                        "customer_id": exc.customer_id,
                    },
                )
            return self._send(
                201 if created else 200,
                _customer_response(
                    customer,
                    created=created,
                    customer_id=customer["customer_id"],
                    token=token,
                ),
            )

        device_match = re.fullmatch(
            r"/api/customers/([^/]+)/devices(?:/(select|switch))?", path)
        if device_match:
            customer_id = self._normalize_or_400(
                unquote(device_match.group(1)))
            if customer_id is None:
                return
            action = device_match.group(2)
            try:
                if action == "select":
                    result = select_device(
                        customer_id,
                        body.get("device_id") or body.get("target_device_id"),
                        require_online=body.get("require_online", True) is not False)
                    return self._send(200, {
                        "ok": True, "customer_id": customer_id, "device": result})
                if action == "switch":
                    result = switch_device(
                        customer_id,
                        body.get("old_device_id") or body.get("from_device_id"),
                        body.get("new_device_id") or body.get("to_device_id"))
                    return self._send(200, {"ok": True, **result})
                result = add_device(
                    customer_id,
                    label=body.get("label") or body.get("name"),
                    machine_code=body.get("machine_code"),
                    token=body.get("activation_code") or body.get("token"),
                    enforce_binding=body.get("enforce_binding", True) is not False)
                return self._send(201, {"ok": True, **result})
            except UnknownCustomer:
                return self._send(404, {
                    "ok": False, "error": "unknown customer",
                    "code": "CUSTOMER_NOT_FOUND", "customer_id": customer_id})

        device_action = re.fullmatch(
            r"/api/customers/([^/]+)/devices/([^/]+)/(isolate|retire|activate|default)",
            path)
        if device_action:
            customer_id = self._normalize_or_400(
                unquote(device_action.group(1)))
            if customer_id is None:
                return
            device_id = unquote(device_action.group(2))
            action = device_action.group(3)
            if action == "isolate":
                result = isolate_device(customer_id, device_id)
            elif action == "retire":
                result = isolate_device(customer_id, device_id, retire=True)
            elif action == "activate":
                result = activate_device(
                    customer_id, device_id,
                    rotate_token=body.get("rotate_token", True) is not False)
            else:
                result = set_default_device(customer_id, device_id)
            payload = {"ok": True, **result}
            if result.get("token"):
                payload["token"] = result["token"]
            return self._send(200, payload)

        binding_match = re.fullmatch(
            r"/api/customers/([^/]+)/binding", path)
        if binding_match:
            customer_id = self._normalize_or_400(
                unquote(binding_match.group(1)))
            if customer_id is None:
                return
            if body.get("enabled", True) is not True:
                return self._send(400, {
                    "ok": False, "error": "binding can only be enabled",
                    "code": "BINDING_DISABLE_REFUSED"})
            try:
                result = enable_device_binding(customer_id)
            except UnknownCustomer:
                return self._send(404, {
                    "ok": False, "error": "unknown customer",
                    "code": "CUSTOMER_NOT_FOUND", "customer_id": customer_id})
            return self._send(200, {"ok": True, **result})

        if path.startswith("/api/customers/") and path.endswith("/command"):
            customer_id = unquote(path[len("/api/customers/"): -len("/command")])
            customer_id = self._normalize_or_400(customer_id)
            if customer_id is None:
                return
            try:
                command, duplicate = enqueue_command(
                    customer_id,
                    body.get("kind"),
                    body.get("payload"),
                    body.get("command_id") or body.get("id"),
                    device_id=body.get("device_id") or body.get("target_device_id"),
                )
            except UnknownCustomer:
                return self._send(404, {"ok": False, "error": "unknown customer", "customer_id": customer_id})
            except UnsupportedKind as exc:
                return self._send(400, {"ok": False, "error": "unsupported kind", "kind": exc.kind, "allowed": list(ALLOWED_KINDS)})
            return self._send(
                201 if not duplicate else 200,
                _command_response(command, duplicate=duplicate),
            )

        if path == "/api/remote/exec":
            customer_id = str(body.get("customer_id") or "").strip()
            if not customer_id and body.get("chat_id"):
                customer = find_customer_by_chat(body.get("chat_id"))
                if customer:
                    customer_id = customer["customer_id"]
            if not customer_id:
                return self._send(400, {"ok": False, "error": "customer_id required"})
            try:
                op_id = enqueue_remote(customer_id, body.get("op") or "ping",
                                       body.get("args") or body.get("body") or {},
                                       device_id=body.get("device_id") or body.get("target_device_id"))
            except UnknownCustomer:
                return self._send(404, {"ok": False, "error": "unknown customer"})
            return self._send(200, {"ok": True, "id": op_id})

        if path == "/api/command":
            customer_id = str(body.get("customer_id") or "").strip()
            if not customer_id and body.get("chat_id"):
                customer = find_customer_by_chat(body.get("chat_id"))
                if not customer:
                    return self._send(
                        404,
                        {
                            "ok": False,
                            "error": "unknown chat_id",
                            "code": "CHAT_NOT_FOUND",
                            "chat_id": body.get("chat_id"),
                            "message": "chat_id is not bound to any customer",
                        },
                    )
                customer_id = customer["customer_id"]
            if not customer_id:
                return self._send(400, {"ok": False, "error": "customer_id required"})
            try:
                command, duplicate = enqueue_command(
                    customer_id,
                    body.get("kind"),
                    body.get("payload"),
                    body.get("command_id") or body.get("id"),
                    device_id=body.get("device_id") or body.get("target_device_id"),
                )
            except UnknownCustomer:
                return self._send(404, {"ok": False, "error": "unknown customer", "customer_id": customer_id})
            except UnsupportedKind as exc:
                return self._send(400, {"ok": False, "error": "unsupported kind", "kind": exc.kind, "allowed": list(ALLOWED_KINDS)})
            except InvalidCustomerId as exc:
                return self._send(400, {"ok": False, "error": str(exc), "code": "INVALID_CUSTOMER_ID"})
            except CommandConflict as exc:
                return self._send(
                    409,
                    {
                        "ok": False,
                        "error": "command_id already used by another customer",
                        "code": "COMMAND_ID_CONFLICT",
                        "command_id": exc.command_id,
                        "customer_id": exc.existing_customer,
                    },
                )
            return self._send(
                201 if not duplicate else 200,
                _command_response(command, duplicate=duplicate),
            )

        if path in _INBOUND_PATHS:
            chat_id = str(body.get("chat_id") or body.get("feishu_chat_id") or "").strip()
            if not chat_id:
                return self._send(400, {"ok": False, "error": "chat_id required"})
            customer = find_customer_by_chat(chat_id)
            if not customer:
                return self._send(
                    404,
                    {
                        "ok": False,
                        "error": "unknown chat_id",
                        "code": "CHAT_NOT_FOUND",
                        "chat_id": chat_id,
                        "message": f"chat_id {chat_id} is not bound to any customer",
                        "hint": "bind it with PUT /api/customers/<customer_id>",
                    },
                )
            kind = body.get("kind") or self._kind_from_text(body.get("text"))
            if not kind:
                return self._send(
                    400,
                    {
                        "ok": False,
                        "error": "cannot determine command kind",
                        "code": "KIND_REQUIRED",
                        "allowed": list(ALLOWED_KINDS),
                    },
                )
            try:
                command, duplicate = enqueue_command(
                    customer["customer_id"],
                    kind,
                    body.get("payload"),
                    body.get("command_id") or body.get("id"),
                    device_id=body.get("device_id") or body.get("target_device_id"),
                )
            except UnsupportedKind as exc:
                return self._send(400, {"ok": False, "error": "unsupported kind", "kind": exc.kind, "allowed": list(ALLOWED_KINDS)})
            return self._send(
                201 if not duplicate else 200,
                _command_response(
                    command,
                    duplicate=duplicate,
                    customer_id=customer["customer_id"],
                ),
            )

        return self._not_found()

    def _handle_result(self, customer_id, body):
        command_id = body.get("command_id") or body.get("id")
        try:
            row = record_result(
                customer_id,
                command_id,
                body.get("status") or body.get("state") or "done",
                body.get("result"),
                **self._device_args(body),
            )
        except KeyError:
            return self._send(400, {"ok": False, "error": "command_id required"})
        if row is None:
            return self._send(
                404,
                {
                    "ok": False,
                    "error": "unknown command",
                    "code": "COMMAND_NOT_FOUND",
                    "command_id": command_id,
                    "customer_id": customer_id,
                },
            )
        command, duplicate = row
        return self._send(200, _command_response(command, duplicate=duplicate))

    # -- PUT / PATCH -------------------------------------------------------
    def do_PUT(self):
        self._update_customer()

    def do_PATCH(self):
        self._update_customer()

    def _update_customer(self):
        try:
            return self._update_customer_dispatch()
        except DeviceBindingError as exc:
            return self._send(409, {"ok": False, "code": "DEVICE_BINDING_REJECTED", "error": str(exc)})

    def _update_customer_dispatch(self):
        if not self._require_admin():
            return
        path = urlparse(self.path).path
        body = self._body()
        customer_id = ""
        if path.startswith("/api/customers/"):
            customer_id = unquote(path[len("/api/customers/"):])
        elif path in ("/api/customers", "/api/customers/"):
            customer_id = str(body.get("customer_id") or "").strip()
        if not customer_id:
            return self._send(400, {"ok": False, "error": "customer_id required"})
        customer_id = self._normalize_or_400(customer_id)
        if customer_id is None:
            return
        try:
            customer = update_customer(customer_id, body)
        except InvalidCustomerId as exc:
            return self._send(400, {
                "ok": False, "error": str(exc),
                "code": "INVALID_CUSTOMER_ID"})
        except ChatConflict as exc:
            return self._send(
                409,
                {
                    "ok": False,
                    "error": "chat_id already bound",
                    "code": "CHAT_ALREADY_BOUND",
                    "chat_id": exc.chat_id,
                    "customer_id": exc.customer_id,
                },
            )
        if customer is None:
            return self._send(
                404,
                {
                    "ok": False,
                    "error": "unknown customer",
                    "code": "CUSTOMER_NOT_FOUND",
                    "customer_id": customer_id,
                },
            )
        extra = {}
        if body.get("rotate_token") or body.get("rotate") or body.get("token"):
            full = get_customer(customer_id, include_token=True)
            extra["token"] = full.get("token")
        return self._send(200, _customer_response(customer, **extra))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PUT, PATCH, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()


def make_server(host=None, port=None):
    host = host or os.environ.get("CONTROL_HOST", "127.0.0.1")
    port = int(port if port is not None else os.environ.get("CONTROL_PORT", "8899"))
    init()
    srv = ThreadingHTTPServer((host, port), H)
    srv.daemon_threads = True
    return srv


def main():
    host = os.environ.get("CONTROL_HOST", "127.0.0.1")
    port = int(os.environ.get("CONTROL_PORT", "8899"))
    srv = make_server(host, port)
    print(f"control plane on {host}:{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Small compatibility aliases (used by admin scripts and unit tests)
# ---------------------------------------------------------------------------

ALLOWED_COMMANDS = ALLOWED_KINDS
COMMAND_WHITELIST = ALLOWED_KINDS


def create_customer(customer_id, name=None, feishu_chat_id=None, chat_id=None,
                    machine_code=None, token=None):
    body = {
        "customer_id": customer_id,
        "name": name,
        "machine_code": machine_code,
    }
    if feishu_chat_id is not None:
        body["feishu_chat_id"] = feishu_chat_id
    if chat_id is not None:
        body["chat_id"] = chat_id
    if token is not None:
        body["token"] = token
    customer, token_out, created = upsert_customer(body)
    return {"customer": customer, "token": token_out, "created": created}


get_customer_by_id = get_customer
get_customer_by_chat = find_customer_by_chat
complete_command = record_result
