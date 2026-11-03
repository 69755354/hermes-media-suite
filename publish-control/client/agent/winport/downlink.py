"""Automatic fetch: LIST -> CHECK -> DIFF -> FETCH -> VERIFY -> BIND -> READY.

Implements downlink plan sections 2.1-2.4 and 3.x.  Not carried over on
purpose: any form of guessed binding.  A folder name that does not match the
whitelist exactly stops at "pending confirmation" and never publishes.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from . import folder_bind
from .errors import ConfigError
from .hashing import md5_file, sha256_file
from .httpfetch import (FetchError, RangeNotHonored, RateLimiter, open_stream,
                        read_all, url_identity)
from .jsonio import read_json, write_json
from .ledger import DownlinkLedger
from .manifest import manifest_summary, validate_manifest


def _default_free_bytes(path) -> int | None:
    import shutil
    try:
        return shutil.disk_usage(str(path)).free
    except OSError:
        return None


class FileSystemSource:
    """Local 'bucket' used by the offline demo/self-test and by air-gapped
    delivery.  Same object-key shape as the real bucket."""

    def __init__(self, root):
        self.root = Path(root)

    def manifest_url(self, customer_id: str) -> str:
        if not customer_id:
            # local fixture convenience: a single customer prefix is unambiguous
            candidates = sorted((self.root / "customers").glob("*/manifests/latest.json"))
            if len(candidates) != 1:
                raise FetchError(
                    "customer_id required (found %d local customer prefixes)"
                    % len(candidates))
            return candidates[0].as_uri()
        return (self.root / "customers" / customer_id / "manifests"
                / "latest.json").as_uri()

    def object_url(self, object_key: str) -> str:
        return (self.root / object_key).as_uri()


class PresignedHttpSource:
    """Real bucket: customer-scoped, read-only, short-lived presigned URLs.

    token_endpoint is provided by the control plane and returns:
      {"manifest_url": ..., "objects": {"<key>": "<presigned url>"},
       "expires_in": 600}
    The agent holds only the machine-bound licence + a short-lived read-only
    token -- never a bucket AccessKey/Secret (hard constraint).
    """

    def __init__(self, token_endpoint: str, license_obj: dict, customer_id: str):
        self.token_endpoint = token_endpoint
        self.license_obj = license_obj
        self.customer_id = customer_id
        self._cache = {}
        self._cache_expiry = 0.0

    def _refresh(self, object_key=None):
        now = time.time()
        if object_key and object_key in self._cache and now < self._cache_expiry:
            return self._cache[object_key]
        body = read_all(self.token_endpoint)
        import json
        payload = json.loads(body.decode("utf-8"))
        self._cache = payload.get("objects", {})
        self._cache["__manifest__"] = payload.get("manifest_url")
        self._cache_expiry = now + float(payload.get("expires_in", 300)) - 30
        return self._cache.get(object_key)

    def manifest_url(self, customer_id: str) -> str:
        return self._refresh("__manifest__")

    def object_url(self, object_key: str) -> str:
        url = self._refresh(object_key)
        if not url:
            raise FetchError(f"no presigned url for {object_key}")
        return url


class Downlink:
    def __init__(self, layout, source, settings, *, machine_id=None,
                 customer_id=None, logger=None, free_bytes=None):
        self.layout = layout
        self.source = source
        self.settings = settings
        #: disk-space gate (settings.disk_watermark_gb): never start a download
        #: that cannot finish.  ``free_bytes`` is injectable so the static host
        #: can prove the gate without filling a real disk.
        self._free_bytes = free_bytes or _default_free_bytes
        self.disk_watermark_bytes = int(
            float(settings.get("disk_watermark_gb", 5)) * (1024 ** 3))
        self.ledger = DownlinkLedger(layout.downlink_ledger,
                                     machine_id=machine_id,
                                     customer_id=customer_id)
        self.customer_id = customer_id
        self.logger = logger
        self.limiter = RateLimiter(
            (settings.get("downlink") or {}).get("bandwidth_limit_kbps", 0))
        self.seq_file = layout.run / "downlink-seq.json"
        #: last storage-related failure (disk full / permission); surfaced in the
        #: round summary as a plain-language, recoverable message.
        self.last_storage_error = None

    # -- helpers ---------------------------------------------------------
    def _local_seq(self) -> int:
        return int((read_json(self.seq_file, default={}) or {}).get("manifest_seq", 0))

    def _set_local_seq(self, seq: int) -> None:
        write_json(self.seq_file, {"manifest_seq": seq})

    def _write_folder_state(self, folder: Path, state: dict) -> None:
        write_json(folder / ".folder.json", state)

    # -- one round -------------------------------------------------------
    def run_once(self, *, bind_only=False) -> dict:
        """Returns a round summary.  Never raises for a transport failure: the
        next heartbeat (5 minutes, launchd StartInterval=300 parity) retries."""
        result = {"listed": False, "manifest_seq": None, "downloaded": 0,
                  "skipped": 0, "failed": 0, "folders": [], "errors": []}
        free = self._free_bytes(self.layout.data)
        if free is not None and free < self.disk_watermark_bytes:
            reason = (f"磁盘可用空间不足：仅 {free / 1e9:.2f} GB，"
                      f"低于阈值 {self.disk_watermark_bytes / 1e9:.2f} GB；"
                      "本轮取件已停止，未写入任何文件（清出空间后自动重试）")
            self.ledger.log("ALERT", reason="disk_low", free_bytes=free,
                            watermark_bytes=self.disk_watermark_bytes)
            result["errors"].append(reason)
            result["disk_low"] = True
            return result
        try:
            raw = read_all(self.source.manifest_url(self.customer_id))
        except (FetchError, TypeError) as exc:
            self.ledger.log("ALERT", reason=f"latest.json unreachable: {exc}")
            result["errors"].append(str(exc))
            return result

        import json
        manifest = json.loads(raw.decode("utf-8"))
        seq = int(manifest.get("manifest_seq", 0))
        result["listed"] = True
        result["manifest_seq"] = seq
        self.ledger.log("LIST", manifest_seq=seq,
                        url_host=url_identity(
                            self.source.manifest_url(self.customer_id))["host"])

        if seq <= self._local_seq():
            self.ledger.log("CHECK", skipped=True, reason="seq_not_newer",
                            manifest_seq=seq)
            return result

        errors = validate_manifest(manifest)
        if errors:
            self.ledger.log("ALERT", reason="manifest invalid",
                            errors=errors)
            result["errors"].extend(errors)
            return result

        if manifest["batch"].get("paused") or manifest.get("paused"):
            # Kill switch: stop fetching this batch, do NOT delete local data.
            self.ledger.log("CHECK", paused=True,
                            batch_id=manifest["batch"].get("batch_id"))
            return result

        batch = manifest["batch"]
        folder = self.layout.inbox / batch["batch_id"] / batch["folder_key"]
        folder.mkdir(parents=True, exist_ok=True)

        # DIFF + FETCH + VERIFY
        for piece in manifest["pieces"]:
            target = folder / piece["file_name"]
            if self._piece_ok(target, piece):
                self.ledger.log("SKIP", batch_id=batch["batch_id"],
                                piece_id=piece["piece_id"], bytes=piece["media_bytes"])
                result["skipped"] += 1
                continue
            ok = self._fetch_piece(manifest, batch, piece, target)
            if ok:
                result["downloaded"] += 1
            else:
                result["failed"] += 1
                if self.last_storage_error:      # disk full / permission
                    result["errors"].append(self.last_storage_error)
                    result["storage_error"] = True
                    break

        bind = folder_bind.bind_folder(manifest, folder, self.layout,
                                       verify=True)
        result["folders"].append(bind)
        for row in bind.get("files", []):
            self.ledger.log(row["action"], batch_id=batch["batch_id"],
                            piece_id=row.get("piece_id"),
                            result=row.get("result"),
                            md5=row.get("md5"), sha256=row.get("sha256"))
        self.ledger.log("BIND_OK" if bind["status"] == folder_bind.READY
                        else "BIND_PENDING",
                        batch_id=batch["batch_id"], folder_key=batch["folder_key"],
                        status=bind["status"])
        if bind["status"] == folder_bind.READY:
            self.ledger.log("READY", batch_id=batch["batch_id"])
            self._set_local_seq(seq)
        else:
            self.ledger.log("INCOMPLETE", batch_id=batch["batch_id"],
                            status=bind["status"])
        self._write_folder_state(folder, {
            **bind, "batch_id": batch["batch_id"],
            "folder_key": batch["folder_key"],
            "manifest": manifest_summary(manifest),
        })
        return result

    def _piece_ok(self, target: Path, piece: dict) -> bool:
        if not target.exists() or target.stat().st_size != piece.get("media_bytes", -1):
            return False
        if md5_file(target) != piece.get("md5"):
            return False
        return sha256_file(target) == piece.get("sha256")

    def _fetch_piece(self, manifest, batch, piece, target: Path) -> bool:
        backoff = (self.settings.get("downlink") or {}).get(
            "retry_backoff_seconds", [5, 15, 45, 135])
        part = target.with_name(target.name + ".part")
        state_path = target.with_name(target.name + ".part.json")
        expected = piece.get("media_bytes")
        state = read_json(state_path, default={}) or {}
        # 1.2.5: reconcile the recorded offset with the ACTUAL part size before
        # trusting it (GPT review 1.2.4 item 11).  A missing part, a part shorter
        # than the sidecar claims, or a part that already reached/overshot the
        # expected size all mean "start over" rather than "append onto garbage".
        bytes_done = 0
        if part.exists():
            actual = part.stat().st_size
            recorded = int(state.get("bytes_done", actual))
            if expected is not None and actual >= expected:
                part.unlink(missing_ok=True)
                state_path.unlink(missing_ok=True)
            elif actual != recorded:
                bytes_done = actual
                write_json(state_path, {"bytes_done": bytes_done,
                                        "total_bytes": expected,
                                        "reconciled": True})
            else:
                bytes_done = actual
        elif state_path.exists():
            state_path.unlink(missing_ok=True)

        attempt = 0
        while attempt < len(backoff) + 1:
            attempt += 1
            try:
                url = self.source.object_url(piece["media_key"])
                total, chunks = open_stream(url, offset=bytes_done)
                mode = "ab" if bytes_done else "wb"
                with part.open(mode) as fh:
                    for block in chunks:
                        fh.write(block)
                        bytes_done += len(block)
                        self.limiter.account(len(block))
                        write_json(state_path, {
                            "bytes_done": bytes_done,
                            "total_bytes": expected,
                            "url_host": url_identity(url)["host"]})
                action = "RESUME" if attempt > 1 and mode == "ab" else "DOWNLOAD"
                self.ledger.log(action, batch_id=batch["batch_id"],
                                piece_id=piece["piece_id"],
                                url_host=url_identity(url)["host"],
                                bytes=expected, bytes_done=bytes_done,
                                attempt=attempt, result="OK")
            except RangeNotHonored as exc:
                # The server answered a ranged request with the whole file: throw
                # the partial away so we never append a full-file response onto it.
                self.ledger.log("RESET", batch_id=batch["batch_id"],
                                piece_id=piece["piece_id"], result="RANGE_IGNORED",
                                reason=str(exc), attempt=attempt)
                part.unlink(missing_ok=True)
                state_path.unlink(missing_ok=True)
                bytes_done = 0
                if attempt <= len(backoff):
                    time.sleep(backoff[min(attempt - 1, len(backoff) - 1)])
                continue
            except OSError as exc:
                # Disk full / permission / device error mid-download: keep the
                # already-verified files, record a recoverable Chinese state, and
                # stop hammering the disk (GPT review 1.2.4 item 12).
                self.ledger.log("VERIFY_FAIL", batch_id=batch["batch_id"],
                                piece_id=piece["piece_id"],
                                result="STORAGE_ERROR", reason=str(exc),
                                attempt=attempt)
                self.last_storage_error = (
                    f"下载写入失败（磁盘空间不足或没有权限）：{exc}。"
                    f"已下载并校验通过的文件不受影响；请清理磁盘后重试。")
                return False
            except FetchError as exc:
                self.ledger.log("VERIFY_FAIL", batch_id=batch["batch_id"],
                                piece_id=piece["piece_id"], result="FETCH_ERROR",
                                reason=str(exc), attempt=attempt)
                if exc.status == 403:
                    bytes_done = part.stat().st_size if part.exists() else 0
                if attempt <= len(backoff):
                    time.sleep(backoff[min(attempt - 1, len(backoff) - 1)])
                continue

            if self._verify_and_commit(part, target, state_path, piece,
                                       batch, attempt):
                return True
            # a failed verify deletes the part + sidecar, so the NEXT attempt must
            # restart from zero (the recorded bytes_done no longer matches).
            bytes_done = 0
            if attempt <= len(backoff):
                time.sleep(backoff[min(attempt - 1, len(backoff) - 1)])
        return False

    def _verify_and_commit(self, part, target, state_path, piece, batch,
                           attempt) -> bool:
        size = part.stat().st_size if part.exists() else 0
        if size != piece.get("media_bytes"):
            self.ledger.log("VERIFY_FAIL", batch_id=batch["batch_id"],
                            piece_id=piece["piece_id"], result="SIZE_MISMATCH",
                            got=size, expected=piece.get("media_bytes"),
                            attempt=attempt)
            return False
        got_md5 = md5_file(part)
        got_sha = sha256_file(part)
        if got_md5 != piece["md5"] or got_sha != piece["sha256"]:
            self.ledger.log("VERIFY_FAIL", batch_id=batch["batch_id"],
                            piece_id=piece["piece_id"], result="HASH_MISMATCH",
                            md5=got_md5, sha256=got_sha, attempt=attempt)
            part.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
            return False
        os.replace(part, target)
        state_path.unlink(missing_ok=True)
        self.ledger.log("VERIFY_OK", batch_id=batch["batch_id"],
                        piece_id=piece["piece_id"], md5=got_md5, sha256=got_sha)
        return True
