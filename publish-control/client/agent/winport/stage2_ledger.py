"""Publish idempotency ledger: run/stage2-ledger.json (Mac parity).

States: RESERVED (pre-submit only) / SUBMIT_INTENT (durable intent) / CONSUMED /
UNKNOWN (result not known -> look up the platform before retrying).
Idempotency key = account + content_hash + schedule_at (publish-ops-rules 3).
"""

from __future__ import annotations

import copy
import json
import shutil
import time
from pathlib import Path

from .errors import GateRed
from .hashing import sha256_bytes
from .jsonio import read_json, write_json
from .lock import FileLock

RESERVED = "RESERVED"
CONSUMED = "CONSUMED"
UNKNOWN = "UNKNOWN"
SUBMIT_INTENT = "SUBMIT_INTENT"

LEDGER_VERSION = 1


def content_hash(account_id: str, title: str, copy_body: str, file_sha256: str) -> str:
    payload = "\x1f".join([account_id or "", title or "", copy_body or "",
                           file_sha256 or ""])
    return sha256_bytes(payload.encode("utf-8"))


def idempotency_key(account_id: str, content_hash_value: str, schedule_at: str) -> str:
    return f"{account_id}|{content_hash_value}|{schedule_at}"


class Stage2Ledger:
    """Publish idempotency ledger, guarded by a cross-process file lock.

    Concurrency matters here: two clicks / two threads / two processes must never
    both see "key NEW" and both submit.  Every mutation re-reads the file INSIDE
    the lock, so the check-and-set is atomic across threads and processes.
    """

    def __init__(self, path, *, lock_timeout=15.0):
        self.path = Path(path)
        self.lock_timeout = lock_timeout
        self._lock = FileLock(self.path.with_name(self.path.name + ".lock"))
        self._reload()

    def _reload(self):
        self.data = read_json(self.path, default=None)
        if self.data is None and not self.path.exists():
            self.data = {"version": LEDGER_VERSION, "entries": {}}
        if not isinstance(self.data, dict) or not isinstance(self.data.get("entries"), dict):
            raise GateRed("publish ledger damaged; restore/reconcile before publishing")
        if any(not isinstance(e, dict) or e.get("state") not in
               (RESERVED, SUBMIT_INTENT, CONSUMED, UNKNOWN)
               for e in self.data["entries"].values()):
            raise GateRed("publish ledger contains invalid state; refusing to publish")

    class _Guard:
        def __init__(self, ledger):
            self.ledger = ledger

        def __enter__(self):
            if not self.ledger._lock.acquire(timeout=self.ledger.lock_timeout):
                raise GateRed("stage2 ledger is locked by another publisher; "
                              "refusing to publish concurrently")
            try:
                self.ledger._reload()
                return self.ledger
            except BaseException:
                self.ledger._lock.release()
                raise

        def __exit__(self, *exc):
            self.ledger._lock.release()
            return False

    def locked(self):
        """Context manager: acquire the lock and re-read the ledger."""
        return self._Guard(self)

    def state(self, key: str):
        self._reload()
        entry = self.data["entries"].get(key)
        return entry.get("state") if entry else None

    def reserve(self, key: str, **meta) -> str:
        """Reserve the key atomically.  Returns 'NEW' if this call created the
        reservation, otherwise the existing state (caller must NOT republish)."""
        with self.locked():
            existing = self.data["entries"].get(key)
            if existing:
                return existing.get("state", UNKNOWN)
            for entry in self.data["entries"].values():
                # A page-confirmed publish without a consumable receipt stays
                # SUBMIT_INTENT so the same key can never replay.  It has a
                # known successful outcome, though, so it must not block a
                # different scheduled publish on the same account forever.
                confirmed = entry.get("publish_confirmed") is True
                if (meta.get("account_id")
                        and entry.get("account_id") == meta["account_id"]
                        and not confirmed
                        and (entry["state"] in (SUBMIT_INTENT, UNKNOWN) or
                             (entry["state"] == RESERVED
                              and entry.get("reservation_schema") != 2))):
                    return entry["state"]
                # Receipt IDs are globally single-use. Same account+media cannot
                # be replayed in a later scheduling window after an uncertain click.
                if any(meta.get(k) and meta[k] == entry.get(k)
                       for k in ("receipt_id", "approval_id", "replay_identity")):
                    return entry["state"]
            self.data["entries"][key] = {
                "state": RESERVED,
                "reservation_schema": 2,
                "reserved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                **meta,
            }
            self.save()
            return "NEW"

    def reserve_republish(self, key: str, *, original_key: str,
                          base_identity: str, **meta) -> str:
        """Reserve one explicitly confirmed republish key.

        A republish may only follow a CONSUMED publish in the same material
        chain.  RESERVED / SUBMIT_INTENT / UNKNOWN attempts are never bypassed:
        they must be reconciled first, otherwise a lost result could be
        published twice.  This check and the reservation happen under the same
        file lock so two concurrent confirmations cannot both pass.
        """
        with self.locked():
            original = self.data["entries"].get(original_key)
            # Never let an explicit republish slip past an account-wide
            # uncertain attempt (the same check normal reserve() performs).
            for entry in self.data["entries"].values():
                if (meta.get("account_id")
                        and entry.get("account_id") == meta["account_id"]
                        and entry.get("publish_confirmed") is not True
                        and (entry.get("state") in (SUBMIT_INTENT, UNKNOWN)
                             or (entry.get("state") == RESERVED
                                 and entry.get("reservation_schema") != 2))):
                    return entry.get("state", UNKNOWN)
            chain = []
            for entry in self.data["entries"].values():
                identity = str(entry.get("replay_identity") or "")
                if identity == base_identity or identity.startswith(
                        base_identity + "|republish:"):
                    chain.append(entry)
            # The same material may have been consumed in a different schedule
            # window; the normal reserve() then reports CONSUMED through the
            # replay identity.  Accept that case only when every matching entry
            # is CONSUMED, so an in-flight / unknown attempt still blocks.
            consumed = bool(original and original.get("state") == CONSUMED)
            consumed = consumed or any(
                entry.get("state") == CONSUMED for entry in chain)
            if not consumed:
                if original is not None:
                    return original.get("state", UNKNOWN)
                return "NOT_CONSUMED"
            for entry in chain:
                if entry.get("state") != CONSUMED:
                    return entry.get("state", UNKNOWN)
            if original is not None and original.get("state") != CONSUMED:
                return original.get("state", UNKNOWN)
            existing = self.data["entries"].get(key)
            if existing:
                return existing.get("state", UNKNOWN)
            for entry in self.data["entries"].values():
                if any(meta.get(k) and meta[k] == entry.get(k)
                       for k in ("receipt_id", "approval_id")):
                    return entry.get("state", UNKNOWN)
            self.data["entries"][key] = {
                "state": RESERVED,
                "reservation_schema": 2,
                "reserved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                **meta,
            }
            self.save()
            return "NEW"

    def mark_submit_intent(self, key: str, *, attempt_id=None) -> None:
        """Durable write BEFORE mouse-down; never recyclable after this point."""
        with self.locked():
            entry = self.data["entries"].get(key)
            if not entry or entry.get("state") != RESERVED:
                raise GateRed("reservation changed before submit")
            entry.update(state=SUBMIT_INTENT, attempt_id=attempt_id,
                         submit_intent_at=time.time())
            self.save()

    def mark_publish_confirmed(self, key: str, *, signal: str, work_id=None,
                               attempt_id=None) -> None:
        """Record a page-confirmed publish that has no consumable receipt.

        The entry deliberately stays ``SUBMIT_INTENT``: without a validated
        create_v2 receipt it is not a ``CONSUMED`` row, so the exact key remains
        blocked.  The confirmation flag only stops this known-success row from
        being treated as an account-wide uncertain attempt by later
        reservations.  A work ID found in the page URL is recorded as
        evidence, never as a receipt or a fake CONSUMED ID.
        """
        signal = str(signal or "").strip()
        allowed = {"success_toast", "manage_url", "create_v2_status_ok"}
        with self.locked():
            entry = self.data["entries"].get(key)
            if not entry or entry.get("state") != SUBMIT_INTENT:
                raise GateRed("publish confirmation requires SUBMIT_INTENT")
            if signal not in allowed:
                raise GateRed("publish confirmation requires a success signal")
            if attempt_id and entry.get("attempt_id") and attempt_id != entry["attempt_id"]:
                raise GateRed("publish confirmation attempt mismatch")
            if work_id is not None:
                from .publish_guard import is_ascii_mid
                if not isinstance(work_id, str) or not is_ascii_mid(work_id):
                    raise GateRed("invalid page work ID")
            entry.update(publish_confirmed=True,
                         publish_confirmed_signal=signal,
                         publish_confirmed_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            if work_id is None:
                entry["publish_confirmed_without_id"] = True
                entry.pop("publish_confirmed_work_id", None)
            else:
                entry["publish_confirmed_work_id"] = work_id
                entry.pop("publish_confirmed_without_id", None)
            self.save()

    def bind_submission(self, key: str, creation_id: str, video_id: str) -> None:
        """Persist the actual create_v2 request pair, including pending/UNKNOWN attempts."""
        with self.locked():
            entry = self.data["entries"].get(key)
            if not entry or entry.get("state") != SUBMIT_INTENT:
                raise GateRed("submission binding requires SUBMIT_INTENT")
            if any(not isinstance(v, str) or not v or v != v.strip() for v in (creation_id, video_id)):
                raise GateRed("invalid submission identity")
            if entry.get("creation_id") and (entry["creation_id"], entry.get("video_id")) != (creation_id, video_id):
                raise GateRed("submission identity changed")
            if any(k != key and e.get("creation_id") == creation_id for k, e in self.data["entries"].items()):
                raise GateRed("creation_id already bound to another attempt")
            entry.update(creation_id=creation_id, video_id=video_id)
            self.save()

    def consume(self, key: str, platform_work_id: str, *, before_consume=None, **meta) -> None:
        with self.locked():
            from .publish_guard import is_ascii_mid
            entry = self.data["entries"].get(key)
            if not entry or entry.get("state") != SUBMIT_INTENT:
                raise GateRed("consume requires SUBMIT_INTENT")
            if not isinstance(platform_work_id, str) or not is_ascii_mid(platform_work_id) or platform_work_id != platform_work_id.strip():
                raise GateRed("invalid platform work ID")
            if any(other_key != key and other.get("platform_work_id") == platform_work_id
                   for other_key, other in self.data["entries"].items()):
                raise GateRed("platform work ID already used")
            if callable(before_consume): before_consume()
            evidence = meta.get("publish_evidence")
            proof = evidence.get("receipt") if isinstance(evidence, dict) else None
            if not isinstance(proof, dict):
                raise GateRed("consume requires this attempt's create_v2 receipt")
            from .platform_receipt import parse_work_id
            common = (
                type(proof.get("status")) is int and proof["status"] == 200 and
                parse_work_id({"status_code": proof.get("status_code"), "item_id": proof.get("item_id")}) == platform_work_id and
                proof.get("work_id") == platform_work_id and proof.get("result") == "SUCCESS" and
                entry.get("attempt_id") and proof.get("attempt_id") == entry["attempt_id"] and
                entry.get("creation_id") and entry.get("video_id") and
                (proof.get("creation_id"), proof.get("video_id")) ==
                (entry["creation_id"], entry["video_id"]))
            explicit = proof.get("source") == "playwright_response"
            page_receipt = (
                proof.get("source") == "platform_page" and
                proof.get("new_after_submit") is True and
                proof.get("fingerprint") == entry.get("content_hash"))
            if page_receipt:
                try:
                    observed_at = float(proof.get("observed_at"))
                    submitted_at = float(entry.get("submit_intent_at"))
                    page_receipt = observed_at >= submitted_at
                except (TypeError, ValueError):
                    page_receipt = False
            if not common or not (explicit or page_receipt):
                raise GateRed("receipt differs from durable submission binding")
            if any(k in meta for k in ("state", "platform_work_id", "consumed_at", "attempt_id", "creation_id", "video_id")):
                raise GateRed("protected ledger fields")
            entry.update(state=CONSUMED,
                         platform_work_id=platform_work_id,
                         consumed_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                         **meta)
            self.save()

    def mark_unknown(self, key: str, reason: str) -> None:
        with self.locked():
            entry = self.data["entries"].setdefault(key, {"state": RESERVED})
            entry.update(state=UNKNOWN, reason=reason,
                         marked_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            self.save()

    def recycle_zombie(self, key: str, reason="manual recycle") -> bool:
        """RESERVED -> deleted, but only after backing up the ledger file.
        CONSUMED / UNKNOWN can never be recycled (Mac parity)."""
        with self.locked():
            entry = self.data["entries"].get(key)
            if not entry or entry.get("state") != RESERVED or entry.get("reservation_schema") != 2:
                return False
            self.backup(reason)
            del self.data["entries"][key]
            self.save()
            return True

    def backup(self, reason: str) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dst = self.path.with_name(self.path.name + f".bak-{stamp}")
        if self.path.exists():
            shutil.copy2(self.path, dst)
        return dst

    def save(self) -> None:
        write_json(self.path, self.data)

    def snapshot(self) -> dict:
        return copy.deepcopy(self.data)

    def refresh(self) -> dict:
        """Re-read the file from disk (after another process wrote it)."""
        self._reload()
        return self.data
