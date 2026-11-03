"""Folder name == task binding key.  Whitelist EXACT match, never a guess.

downlink plan sections 3.1-3.3.  Statuses: READY / UNKNOWN_FOLDER /
AMBIGUOUS_FOLDER / COUNT_MISMATCH / FILE_PIECE_AMBIGUOUS / INCOMPLETE.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from .hashing import md5_file, sha256_file
from .manifest import VIDEO_EXTS, normalize_folder_key

READY = "READY"
UNKNOWN_FOLDER = "UNKNOWN_FOLDER"
AMBIGUOUS_FOLDER = "AMBIGUOUS_FOLDER"
COUNT_MISMATCH = "COUNT_MISMATCH"
FILE_PIECE_AMBIGUOUS = "FILE_PIECE_AMBIGUOUS"
BAD_FILE = "BAD_FILE"
INCOMPLETE = "INCOMPLETE"


def list_videos(folder: Path) -> list:
    out = []
    for path in sorted(folder.iterdir()):
        if path.name.startswith("."):
            continue
        if path.suffix.lower() in VIDEO_EXTS and path.is_file():
            out.append(path)
    return out


def match_folder(folder_name: str, whitelist):
    """Step 1-3 of the algorithm.  Returns (status, folder_key_or_None)."""
    key = normalize_folder_key(folder_name)
    hits = [w for w in whitelist if w == key]
    if len(hits) == 1:
        return "MATCH", hits[0]
    if not hits:
        return UNKNOWN_FOLDER, None
    return AMBIGUOUS_FOLDER, None


def match_file_to_piece(path: Path, pieces):
    """R1 -> R2 -> R3 -> ambiguous.  Returns (piece_or_None, reason)."""
    stem = path.stem
    prefix = stem.split("_", 1)[0].split("-", 1)[0]
    if prefix.isdigit():
        no = int(prefix)
        hits = [p for p in pieces if p.get("piece_no") == no]
        if len(hits) == 1:
            return hits[0], "R1"
    hits = [p for p in pieces if stem in (p.get("name"), Path(p.get("file_name", "")).stem)]
    if len(hits) == 1:
        return hits[0], "R2"
    if len(pieces) == 1:
        return pieces[0], "R3"
    return None, "R4"


def bind_folder(manifest, folder: Path, layout, *, verify=True) -> dict:
    batch = manifest["batch"]
    pieces = manifest["pieces"]
    expected_key = batch["folder_key"]
    status = READY
    files_report = []

    actual_name = unicodedata.normalize("NFC", folder.name)
    if actual_name != expected_key:
        status = UNKNOWN_FOLDER
        return {"folder": str(folder), "folder_name": folder.name,
                "status": status, "expected_folder_key": expected_key,
                "files": []}

    videos = list_videos(folder)
    if len(videos) != batch.get("piece_count"):
        status = COUNT_MISMATCH

    assigned = {}
    for path in videos:
        piece, reason = match_file_to_piece(path, pieces)
        if piece is None:
            status = FILE_PIECE_AMBIGUOUS
            files_report.append({"file": path.name, "action": "BIND_PENDING",
                                 "result": "FILE_PIECE_AMBIGUOUS"})
            continue
        if piece["piece_id"] in assigned.values():
            status = FILE_PIECE_AMBIGUOUS
            files_report.append({"file": path.name, "action": "BIND_PENDING",
                                 "result": "DUPLICATE_PIECE",
                                 "piece_id": piece["piece_id"]})
            continue
        assigned[path.name] = piece["piece_id"]
        row = {"file": path.name, "piece_id": piece["piece_id"], "rule": reason}
        if verify:
            ok, detail = verify_file(path, piece)
            row.update(detail)
            if not ok:
                row["action"] = "VERIFY_FAIL"
                row["result"] = "BAD_FILE"
                status = BAD_FILE
                files_report.append(row)
                continue
        row["action"] = "BIND_OK"
        row["result"] = "OK"
        files_report.append(row)

    if status == READY and len(files_report) != batch.get("piece_count"):
        status = INCOMPLETE
    return {"folder": str(folder), "folder_name": folder.name, "status": status,
            "expected_folder_key": expected_key,
            "piece_count": batch.get("piece_count"),
            "videos_found": len(videos), "files": files_report}


def verify_file(path: Path, piece: dict):
    size = path.stat().st_size
    if size != piece.get("media_bytes"):
        return False, {"result": "SIZE_MISMATCH", "got": size,
                       "expected": piece.get("media_bytes")}
    got_md5 = md5_file(path)
    got_sha = sha256_file(path)
    ok = got_md5 == piece.get("md5") and got_sha == piece.get("sha256")
    return ok, {"md5": got_md5, "sha256": got_sha}


def white_list(manifests):
    """Active folder_key whitelist for one customer prefix."""
    return {m["batch"]["folder_key"] for m in manifests
            if m and m.get("batch", {}).get("folder_key")
            and not m["batch"].get("paused")}
