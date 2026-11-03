"""Bring an existing window to the front, or at least make it obvious.

Mac parity: osascript 'activate'.  Windows parity: ShowWindow + SetForegroundWindow,
with AllowSetForegroundWindow first; if the OS refuses (a known Windows
restriction), fall back to flashing the taskbar and a tray balloon so the click
is never silently swallowed (Mac背景 section 2.4)."""

from __future__ import annotations

from . import win32
from .version import APP_NAME_DISPLAY


def focus_existing(title_part: str = APP_NAME_DISPLAY, *, flash=True) -> dict:
    if not win32.IS_WINDOWS:
        return {"focused": False, "flashed": False,
                "reason": "non-windows: no-op (static test)"}
    hwnd = win32.find_window(title_part)
    if not hwnd:
        return {"focused": False, "flashed": False, "reason": "window not found"}
    win32.show_window(hwnd)
    focused = win32.set_foreground_window(hwnd)
    flashed = win32.flash_window(hwnd) if (flash and not focused) else False
    return {"focused": focused, "flashed": flashed,
            "reason": "ok" if focused else "SetForegroundWindow refused; flashed"}
