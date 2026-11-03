"""Manifest (batch-<id>.json) parsing and the generation-side validation rules.

Rules are copied verbatim from source/mac-reference/downlink-and-folder-binding-plan.md
section 1.2 / 1.3.  Nothing here is invented: where the source does not define a
value (e.g. the exact 13 export column names) the code stays data-driven and the
item is listed in VERIFY.md as real-machine-only.
"""

from __future__ import annotations

import re
import unicodedata

from .errors import ConfigError
from .hashing import is_hex

SCHEMA_VERSION = "1.0"
VIDEO_EXTS = (".mp4", ".mov", ".m4v")
MAX_FOLDER_KEY_LEN = 64

_FOLDER_KEY_OK = re.compile(r"^[\w\-\u4e00-\u9fff]+$", re.UNICODE)
_FILE_NAME_OK = re.compile(r"^(\d{2})_(.+)\.(mp4|mov|m4v)$", re.IGNORECASE)


def normalize_folder_key(name: str) -> str:
    """NFC + strip, exactly as the binding algorithm step 1 requires."""
    return unicodedata.normalize("NFC", str(name)).strip()


def folder_key_allowed(key: str):
    """Return (ok, reason).  Client folders are compared with this normaliser."""
    if not key:
        return False, "empty"
    if len(key) > MAX_FOLDER_KEY_LEN:
        return False, f"too_long>{MAX_FOLDER_KEY_LEN}"
    if key != key.strip():
        return False, "leading_or_trailing_space"
    if any(c.isspace() for c in key):
        return False, "contains_space"
    if not _FOLDER_KEY_OK.match(key):
        return False, "forbidden_char"
    return True, "ok"


def _iter_pieces(manifest):
    pieces = manifest.get("pieces") or []
    if not isinstance(pieces, list):
        raise ConfigError("manifest.pieces must be a list")
    return pieces


def derive_folder_key(batch: dict) -> str:
    """<batch_id>_<account_nickname>_<task_type> (downlink plan section 3.1)."""
    return normalize_folder_key(
        f"{batch.get('batch_id','')}_{batch.get('account_nickname','')}_"
        f"{batch.get('task_type','')}")


def validate_manifest(manifest: dict, *, seen_folder_keys=None):
    """Return a list of human-readable error strings; [] means valid.

    seen_folder_keys: folder_keys already used by other batches of the same
    customer prefix, for the global uniqueness rule (rule 2).
    """
    errors = []
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(manifest.get("manifest_seq"), int):
        errors.append("manifest_seq must be an integer")

    batch = manifest.get("batch")
    if not isinstance(batch, dict):
        return errors + ["batch missing"]

    batch_id = batch.get("batch_id")
    if not batch_id:
        errors.append("batch.batch_id missing")

    pieces = _iter_pieces(manifest)
    piece_count = batch.get("piece_count")
    if piece_count != len(pieces):
        errors.append(f"piece_count {piece_count} != len(pieces) {len(pieces)}")

    key = batch.get("folder_key")
    if not key:
        errors.append("batch.folder_key missing")
    else:
        if normalize_folder_key(key) != key:
            errors.append("folder_key is not NFC/stripped")
        ok, reason = folder_key_allowed(key)
        if not ok:
            errors.append(f"folder_key rejected: {reason}")
        if seen_folder_keys and key in seen_folder_keys:
            errors.append(f"folder_key not unique: {key}")
        expected = derive_folder_key(batch)
        if key != expected:
            errors.append(f"folder_key '{key}' != derived '{expected}'")

    file_names = set()
    piece_nos = set()
    for idx, piece in enumerate(pieces):
        where = f"pieces[{idx}]"
        if not isinstance(piece, dict):
            errors.append(f"{where} is not an object")
            continue
        fname = piece.get("file_name", "")
        m = _FILE_NAME_OK.match(fname)
        if not m:
            errors.append(f"{where}.file_name not <NN>_<name>.<ext>: {fname!r}")
        else:
            if int(m.group(1)) != piece.get("piece_no"):
                errors.append(f"{where}.file_name NN != piece_no")
        if fname in file_names:
            errors.append(f"{where}.file_name duplicated: {fname}")
        file_names.add(fname)
        if piece.get("piece_no") in piece_nos:
            errors.append(f"{where}.piece_no duplicated: {piece.get('piece_no')}")
        piece_nos.add(piece.get("piece_no"))

        if not is_hex(piece.get("md5", ""), 32):
            errors.append(f"{where}.md5 not 32 lowercase hex")
        if not is_hex(piece.get("sha256", ""), 64):
            errors.append(f"{where}.sha256 not 64 lowercase hex")
        if not piece.get("media_key"):
            errors.append(f"{where}.media_key missing")
        if not isinstance(piece.get("title"), str) or not piece.get("title"):
            errors.append(f"{where}.title missing")
        if len(piece.get("title", "")) > 200:
            errors.append(f"{where}.title > 200 chars")
        if len(piece.get("copy_body", "")) > 4000:
            errors.append(f"{where}.copy_body > 4000 chars")
    return errors


def manifest_summary(manifest: dict) -> dict:
    batch = manifest.get("batch", {})
    return {
        "batch_id": batch.get("batch_id"),
        "folder_key": batch.get("folder_key"),
        "account_id": batch.get("account_id"),
        "account_nickname": batch.get("account_nickname"),
        "task_type": batch.get("task_type"),
        "piece_count": batch.get("piece_count"),
        "paused": bool(batch.get("paused", False)),
        "expires_at": batch.get("expires_at"),
        "manifest_seq": manifest.get("manifest_seq"),
    }
