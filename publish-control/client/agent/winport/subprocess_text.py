"""Decode child-process output with the host's local console code page.

Windows tools such as Chrome's installer, ``netstat`` and ``taskkill`` write
their redirected output in the active ANSI code page (GBK/cp936 on Chinese
Windows).  Python may still be running in UTF-8 mode because the launchers set
``PYTHONUTF8=1``, so an explicit UTF-8 pipe encoding raises UnicodeDecodeError
inside subprocess's reader thread.  Use ``mbcs`` on Windows because it always
maps to the active ANSI code page, even in UTF-8 mode.
"""

from __future__ import annotations

import locale
import ntpath
import os
import subprocess


_VISIBLE_BROWSER_EXES = frozenset({"chrome.exe", "msedge.exe"})


def _argv0(argv):
    if not argv:
        return ""
    first = argv if isinstance(argv, (str, bytes, os.PathLike)) else argv[0]
    try:
        value = os.fspath(first)
    except TypeError:
        value = str(first)
    if isinstance(value, bytes):
        value = os.fsdecode(value)
    return str(value).strip().strip('"')


def is_visible_browser(argv) -> bool:
    """True for a browser launch that must keep its normal visible window."""
    return ntpath.basename(_argv0(argv)).lower() in _VISIBLE_BROWSER_EXES


def _hidden_startupinfo():
    """STARTUPINFO that also hides the window when Windows Terminal is default.

    Win11 hands console children to Windows Terminal; CREATE_NO_WINDOW alone can
    still surface a terminal window, so request SW_HIDE explicitly as well.
    """
    try:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0  # SW_HIDE
        return info
    except Exception:
        return None


def hidden_window_options(argv, *, popen=False, creationflags=0) -> dict:
    """Subprocess keywords that keep a Windows child from opening a console."""
    options = {"creationflags": creationflags} if creationflags else {}
    if os.name != "nt" or is_visible_browser(argv):
        return options
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    options["creationflags"] = int(creationflags) | create_no_window
    info = _hidden_startupinfo()
    if info is not None:
        options["startupinfo"] = info
    if popen:
        options["stdin"] = subprocess.DEVNULL
    return options


def process_encoding() -> str:
    """Return the encoding used by local console tools."""
    if os.name == "nt":
        return "mbcs"
    return locale.getpreferredencoding(False) or "utf-8"


def text_mode_options() -> dict:
    """Return subprocess keywords for safely reading stdout/stderr as text."""
    return {"text": True, "encoding": process_encoding(), "errors": "replace"}


def decode_process_output(data, *, encoding=None) -> str:
    """Decode raw child-process output without raising on malformed bytes."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    raw = bytes(data)
    candidates = [encoding] if encoding else []
    candidates.extend((process_encoding(), "utf-8", "gbk", "mbcs"))
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return raw.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode(process_encoding(), errors="replace")
