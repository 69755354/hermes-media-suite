"""Thin ctypes wrappers around the Win32 calls the agent needs.

Everything degrades to a documented no-op with a reason on non-Windows so the
static self-test can import and exercise the surrounding logic.
"""

from __future__ import annotations

import os

IS_WINDOWS = os.name == "nt"

# SetThreadExecutionState flags
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

SW_RESTORE = 9


def _user32():
    import ctypes
    return ctypes.windll.user32


def _kernel32():
    import ctypes
    return ctypes.windll.kernel32


def set_thread_execution_state(flags: int):
    """Return the previous state value, or None if unsupported here."""
    if not IS_WINDOWS:
        return None
    try:
        return _kernel32().SetThreadExecutionState(flags)
    except Exception:
        return None


def find_window(title_part: str):
    if not IS_WINDOWS:
        return None
    try:
        return _user32().FindWindowW(None, title_part)
    except Exception:
        return None


def show_window(hwnd, command=SW_RESTORE) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        return bool(_user32().ShowWindow(hwnd, command))
    except Exception:
        return False


def allow_set_foreground_window(pid: int) -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(_user32().AllowSetForegroundWindow(pid))
    except Exception:
        return False


def set_foreground_window(hwnd) -> bool:
    """SetForegroundWindow can be refused by the OS when the caller is not the
    foreground process; callers must treat False as 'use the flash fallback'."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        return bool(_user32().SetForegroundWindow(hwnd))
    except Exception:
        return False


def flash_window(hwnd, count=5) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False

    import ctypes

    class FLASHWINFO:
        def __init__(self):
            self.cbSize = ctypes.sizeof(self)
            self.hwnd = hwnd
            self.dwFlags = 3  # FLASHW_ALL
            self.uCount = count
            self.dwTimeout = 0

    try:
        info = FLASHWINFO()
        return bool(_user32().FlashWindowEx(ctypes.byref(info)))
    except Exception:
        return False
