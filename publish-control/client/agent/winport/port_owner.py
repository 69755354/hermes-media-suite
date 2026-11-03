"""Prove that a PID really is this program before terminating it.

The port owner must be a Python process running ``-m winport`` with the exact
data directory of this installation. An image name alone is never enough.
"""

from __future__ import annotations

import os


def _norm(value) -> str:
    return os.path.normcase(os.path.normpath(str(value)))


def process_cmdline(pid):
    """Return argv for ``pid`` through psutil, or None when it is unavailable."""
    try:
        import psutil  # type: ignore
    except Exception:
        return None
    try:
        argv = psutil.Process(int(pid)).cmdline()
    except Exception:
        return None
    if not argv:
        return None
    return [str(part) for part in argv]


def ownership_from_argv(argv, data_dir):
    """Return ``(owned, reason)`` for an already-read command line."""
    if not argv:
        return False, "cmdline unavailable"
    command = " ".join(str(part) for part in argv)
    if "winport" not in command.lower():
        return False, "not a winport process"
    if _norm(data_dir) not in _norm(command):
        return False, "different data directory"
    return True, "winport owns this data directory"


def ownership(pid, data_dir):
    return ownership_from_argv(process_cmdline(pid), data_dir)


def is_winport_owner(pid, data_dir) -> bool:
    return ownership(pid, data_dir)[0]
