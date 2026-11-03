"""Cross-platform single-instance / single-browser lock.

This is the single biggest code change of the port (plan section 0 item 4 and
section 4.2): macOS uses fcntl.flock, which does not exist on Windows.  Windows
uses msvcrt.locking on an exclusive file handle; POSIX keeps the historical
flock behaviour so the Mac semantics (LOCK_EX|LOCK_NB) are preserved.

Two layers, same as the Mac side:
  * agent.lock        -> only one main process
  * one-browser.lock  -> only one browser per profile
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path


class FileLock:
    """A non-blocking advisory file lock bound to a lock file path.

    Usage:
        lock = FileLock(path)
        if not lock.acquire():
            ... someone else holds it ...
        ...
        lock.release()

    Works as a context manager as well.  The lock is released automatically by
    the OS when the process dies, so a crashed instance never wedges the lock.
    """

    def __init__(self, path, *, poll: float = 0.0):
        self.path = Path(path)
        self.poll = poll
        self._fh = None
        self._locked = False

    # -- internal --------------------------------------------------------
    def _try_lock(self) -> bool:
        if os.name == "nt":
            import msvcrt
            self._fh.seek(0)
            try:
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        else:
            import fcntl
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                return False

    def _unlock(self) -> None:
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass

    # -- public ----------------------------------------------------------
    def acquire(self, timeout: float = 0.0) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a+b")
        # Ensure the file has at least one byte so Windows byte-range locking
        # has something to lock.
        self._fh.seek(0, os.SEEK_END)
        if self._fh.tell() == 0:
            self._fh.write(b"0")
            self._fh.flush()
        deadline = time.monotonic() + max(timeout, 0.0)
        while True:
            if self._try_lock():
                self._locked = True
                self._write_owner()
                return True
            if time.monotonic() >= deadline:
                self.release()
                return False
            time.sleep(random.uniform(0.1, 0.3))

    def _write_owner(self) -> None:
        """Best-effort owner stamp for diagnostics (not used for judgement)."""
        try:
            self._fh.seek(0)
            self._fh.truncate()
            stamp = f'{{"pid": {os.getpid()}}}\n'
            self._fh.write(stamp.encode("utf-8"))
            self._fh.flush()
        except OSError:
            pass

    @property
    def locked(self) -> bool:
        return self._locked

    def release(self) -> None:
        if self._fh is None:
            return
        if self._locked:
            self._unlock()
            self._locked = False
        try:
            self._fh.close()
        finally:
            self._fh = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"lock already held: {self.path}")
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def lock_is_held(path) -> bool:
    """Return True if some other process currently holds the lock."""
    probe = FileLock(path)
    if probe.acquire():
        probe.release()
        return False
    return True
