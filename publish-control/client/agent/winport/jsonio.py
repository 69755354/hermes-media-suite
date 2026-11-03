"""UTF-8 JSON helpers with atomic writes.

UTF-8 is forced everywhere (PYTHONUTF8=1 in the launcher is the belt; these
helpers are the braces).  Never rely on the console code page (GBK).

Reads use ``utf-8-sig`` (source/brief-encoding-20261016.md): the config files we
seed are UTF-8 WITH BOM so Chinese Windows tools (Notepad, PowerShell 5.1) read
them correctly, and a customer who re-saves one in Notepad may add or drop the
BOM -- ``utf-8-sig`` strips a BOM when present and behaves like ``utf-8`` when
it is not, so the same file loads either way.  Writes stay BOM-less ``utf-8``
(our own output is read back by the agent, never by a legacy Windows parser).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .errors import StorageNotWritable


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def write_json(path, obj, *, indent=2):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=indent)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def write_text_atomic(path, text, *, encoding="utf-8", newline=None):
    """Write text via a same-directory temp file + fsync + atomic replace.

    1.2.5 (GPT review 1.2.4 item 12): a report / CSV written with a plain
    ``open(..., "w")`` is TRUNCATED the instant it is opened, so a crash or a
    full disk leaves a half-written file and destroys the previous good one.
    Here a failure leaves the old file untouched and cleans up the temp file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-",
                               suffix=path.suffix or ".txt")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def append_jsonl(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 1.2.5 (GPT review item 12): repair a broken TAIL *before* appending.  The
    # old code only inserted a newline, so an interrupted previous write left a
    # half-line in the MIDDLE of the file after the next append -- and then a
    # read raised (read_jsonl only tolerated a corrupt LAST line).  Now the
    # partial tail is quarantined and removed first, so a new record always
    # starts on a clean boundary.
    # 1.2.5 round-2 (GPT review item 12): if the tail CANNOT be repaired we must
    # NOT append -- otherwise the new record is glued onto the bad tail and is
    # then silently dropped on read.  Fail loudly instead.
    if not _repair_partial_tail(path):
        raise StorageNotWritable(
            f"JSONL 文件尾部损坏且无法修复，已拒绝追加（避免新记录被静默丢弃）：{path}")
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _repair_partial_tail(path: Path) -> bool:
    """Make ``path`` end on a record boundary (quarantine a partial tail).

    A complete record that merely lacks a trailing newline is kept (we just add
    the newline); only a tail that is NOT valid JSON on its own (a crash / power
    cut mid-write, possibly inside a multi-byte UTF-8 char) is quarantined to
    ``<name>.tail.bad`` and truncated away.

    Returns True when the file is (now) on a clean boundary, False when a
    partial tail exists but could not be removed (the caller must then refuse to
    append).
    """
    try:
        if not path.exists() or not path.stat().st_size:
            return True
        with path.open("rb") as fh:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) == b"\n":
                return True                  # already on a clean boundary
        raw = path.read_bytes()
        idx = raw.rfind(b"\n")
        tail = raw[idx + 1:]
        if not tail:
            return True
        try:
            json.loads(tail.decode("utf-8").strip())
        except (UnicodeDecodeError, ValueError):
            pass                             # corrupt/partial -> quarantine
        else:
            with path.open("ab") as fh:      # complete record, only missing LF
                fh.write(b"\n")
            return True
        try:
            path.with_name(path.name + ".tail.bad").write_bytes(tail + b"\n")
        except OSError:
            pass                             # quarantine is best-effort
        with path.open("r+b") as fh:
            fh.truncate(idx + 1)
        return True
    except OSError:
        return False


def read_jsonl(path, *, quarantine_tail=True):
    """Read JSONL, tolerating a half-written trailing line.

    1.2.5 (GPT review 1.2.4 item 12): a crash / power cut mid-append leaves an
    incomplete last record -- possibly cut inside a multi-byte UTF-8 character.
    That must not make the whole ledger unreadable, and it must not poison later
    appends.  So we work on BYTES: a corrupt / truncated TRAILING line is
    quarantined to ``<name>.tail.bad`` AND removed from the file (truncate), so
    the next append starts on a clean record boundary.  A corrupt MIDDLE line is
    real damage and is still raised, not hidden.
    """
    path = Path(path)
    if not path.exists():
        return []
    raw = path.read_bytes()
    segments = raw.split(b"\n")
    rows = []
    bad = []                                 # (is_last, seg)
    good_upto = 0
    offset = 0
    tail_cut = None
    last_index = len(segments) - 1
    for index, seg in enumerate(segments):
        is_last = index == last_index
        line_end = offset + len(seg) + (0 if is_last else 1)
        if seg.strip() == b"":
            offset = line_end
            good_upto = line_end
            continue
        ok = True
        try:
            text = seg.decode("utf-8")
        except UnicodeDecodeError:
            ok = False
        if ok:
            try:
                rows.append(json.loads(text.strip()))
            except json.JSONDecodeError:
                ok = False
        if ok:
            good_upto = line_end
        else:
            # 1.2.5 (GPT review item 12): a bad line anywhere is isolated and
            # skipped instead of aborting the whole read.  A bad TAIL is also
            # truncated away so the next append starts clean; a bad MIDDLE line
            # is real damage but is still quarantined, not hidden.
            bad.append((is_last, seg))
            if is_last:
                tail_cut = good_upto
        offset = line_end
    if bad:
        try:
            path.with_name(path.name + ".tail.bad").write_bytes(
                b"".join(seg + b"\n" for _last, seg in bad))
        except OSError:
            pass
    if tail_cut is not None and quarantine_tail:
        try:
            with path.open("r+b") as fh:
                fh.truncate(tail_cut)
        except OSError:
            pass
    return rows
