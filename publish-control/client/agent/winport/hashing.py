"""Hash helpers.  Manifest carries BOTH md5 and sha256; sha256 is authoritative
(matches the Mac executor's verify_local_files), md5 is the requested
interoperability value (downlink plan sections 1.2 and 8.1 #7)."""

from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK = 1 << 20


def md5_file(path) -> str:
    return _hash_file(path, hashlib.md5())


def sha256_file(path) -> str:
    return _hash_file(path, hashlib.sha256())


def _hash_file(path, h):
    with Path(path).open("rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_hex(value: str, length: int) -> bool:
    if not isinstance(value, str) or len(value) != length:
        return False
    return all(c in "0123456789abcdef" for c in value)


#: Match a CPython bytecode cache path and recover the source it belongs to.
#: ``agent/winport/__pycache__/cli.cpython-311.pyc`` -> ``agent/winport/cli.py``
import re as _re

_PYC = _re.compile(r"^(?P<dir>.*?)/__pycache__/(?P<stem>.+?)\."
                   r"cpython-\d+\.(?:pyc|pyo)$")


def cache_source_rel(rel: str, known) -> str | None:
    """Return the manifest source path a bytecode cache belongs to, or None.

    1.2.5 (GPT review item 5): a stray ``.pyc`` with NO matching source is a
    tamper vector and must be reported; a normal ``__pycache__`` entry whose
    ``.py`` IS in the manifest is just a runtime cache and is ignored.
    """
    m = _PYC.match(rel)
    if not m:
        return None
    source = f"{m.group('dir')}/{m.group('stem')}.py".lstrip("/")
    return source if source in known else None
