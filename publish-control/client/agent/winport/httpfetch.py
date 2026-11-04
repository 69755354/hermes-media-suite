"""HTTP fetch with Range resume, retry/backoff and credential redaction.

Only read verbs are used.  Presigned URLs expire; a 403 mid-download means we
ask the source for a fresh URL and RESUME from bytes_done, never restart from
zero (downlink plan section 2.2 / 6.1).

file:// is supported so the whole pipeline can run offline in the static test.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CHUNK = 1 << 18
DEFAULT_BACKOFF = (5, 15, 45, 135)


class FetchError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class RangeNotHonored(FetchError):
    """The server did NOT honour our Range request (returned 200 / wrong
    Content-Range).  The caller must discard the partial file and restart at
    offset 0 -- appending a whole-file response onto a partial would corrupt it
    (GPT review 1.2.4 item 11)."""


def url_identity(url: str) -> dict:
    """Log-safe identity: scheme + host[:port] + path only.

    Never the query string (a presigned URL is a bearer credential) and never the
    userinfo -- ``https://user:pass@host/p`` must log as ``host``, not
    ``user:pass@host`` (GPT review 1.2.5 item 10).
    """
    parts = urllib.parse.urlsplit(url)
    try:
        host = parts.hostname or parts.netloc or "local"
        if parts.port:
            host = f"{host}:{parts.port}"
    except ValueError:
        host = "local"
    return {"scheme": parts.scheme, "host": host, "key": parts.path}


def _read_file(url: str, offset: int):
    parts = urllib.parse.urlsplit(url)
    raw = urllib.parse.unquote(parts.path)
    if parts.netloc and parts.netloc.lower() != "localhost":
        raw = f"//{parts.netloc}{raw}"
    # Windows: ``file:///C:/x`` arrives as ``/C:/x``.  Path() then treats it as a
    # relative path rooted at the current drive and file reads fail (or, worse,
    # resolve somewhere else).  url2pathname applies the platform's own rule.
    path = Path(urllib.request.url2pathname(raw))
    size = path.stat().st_size
    fh = path.open("rb")
    fh.seek(offset)

    def gen():
        try:
            while True:
                block = fh.read(CHUNK)
                if not block:
                    break
                yield block
        finally:
            fh.close()

    return size, gen()


def _parse_content_range(value: str):
    """Strictly parse 'bytes <start>-<end>/<total|*>'.

    Returns (start, end, total|None) or raises RangeNotHonored.  1.2.5 (GPT
    review item 11): the old parser only read the start, so a malformed value
    such as ``bananas 5-wrong/2`` was accepted.  Now the unit MUST be ``bytes``,
    start/end MUST be integers with ``start <= end``, a numeric total MUST be
    greater than ``end``, and ``*`` means unknown total.
    """
    def bad():
        return RangeNotHonored(
            f"malformed Content-Range {value!r}; restarting download")
    if not value:
        raise bad()
    parts = value.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bytes":
        raise bad()
    rng, sep, size = parts[1].partition("/")
    if not sep:
        raise bad()
    if "-" not in rng:
        raise bad()
    left, _, right = rng.partition("-")
    try:
        start, end = int(left.strip()), int(right.strip())
    except ValueError:
        raise bad()
    if start < 0 or end < start:
        raise bad()
    size = size.strip()
    if size == "*":
        total = None
    else:
        try:
            total = int(size)
        except ValueError:
            raise bad()
        if total <= end:
            raise bad()
    return start, end, total


def _read_http(url: str, offset: int, timeout: float):
    headers = {}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code} for {url_identity(url)['host']}",
                         status=exc.code)
    except urllib.error.URLError as exc:
        raise FetchError(f"network error: {exc.reason}")
    status = getattr(response, "status", None)
    length = response.headers.get("Content-Length")
    total = None
    if offset:
        # A resume MUST be answered with 206 + a Content-Range that starts at the
        # offset we asked for; anything else means the server ignored Range.
        content_range = response.headers.get("Content-Range")
        if status != 206:
            response.close()
            raise RangeNotHonored(
                f"server ignored Range (status={status}); restarting download",
                status=status)
        try:
            start, end, cr_total = _parse_content_range(content_range or "")
        except RangeNotHonored:
            response.close()
            raise
        if start != offset:
            response.close()
            raise RangeNotHonored(
                f"Content-Range {content_range!r} does not start at {offset}; "
                "restarting download", status=status)
        if length is not None and int(length) != (end - start + 1):
            response.close()
            raise RangeNotHonored(
                f"Content-Range {content_range!r} disagrees with "
                f"Content-Length {length}; restarting download", status=status)
        total = cr_total
        if total is None and length is not None:
            total = offset + int(length)
    elif length is not None:
        total = int(length)

    def gen():
        try:
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                yield block
        finally:
            response.close()

    return total, gen()


def open_stream(url: str, *, offset: int = 0, timeout: float = 60.0):
    """Return (total_bytes_or_None, chunk_iterator)."""
    if url.startswith("file:"):
        return _read_file(url, offset)
    return _read_http(url, offset, timeout)


def read_all(url: str, *, timeout: float = 60.0, retries: int = 3) -> bytes:
    last = None
    for attempt in range(1, retries + 1):
        try:
            _, chunks = open_stream(url, timeout=timeout)
            return b"".join(chunks)
        except FetchError as exc:
            last = exc
            if attempt < retries:
                time.sleep(DEFAULT_BACKOFF[min(attempt - 1,
                                               len(DEFAULT_BACKOFF) - 1)])
    raise last


class RateLimiter:
    """Cheap global bandwidth cap (Kbit/s, 0 = unlimited) for customer home links."""

    def __init__(self, kbps: float = 0):
        self.kbps = kbps
        self._started = time.monotonic()
        self._bytes = 0

    def account(self, nbytes: int) -> None:
        if not self.kbps:
            return
        self._bytes += nbytes
        expected = self._bytes / (self.kbps * 1000 / 8.0)
        elapsed = time.monotonic() - self._started
        if expected > elapsed:
            time.sleep(expected - elapsed)
