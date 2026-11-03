"""Desktop drop folder for publish materials.

Customers do not look inside %LOCALAPPDATA%.  Every launch (and the installer)
therefore keeps a real folder on the desktop named after this module's
``MATERIALS_DIR_NAME`` and makes the media resolver look there as well.

The folder is a plain directory.  It is deliberately *not* junctioned into the
inbox: a second path to the same file makes publish_exec see two candidates and
refuse to publish.  The resolver simply searches both roots instead.
"""

from __future__ import annotations

import os
from pathlib import Path

MATERIALS_DIR_NAME = "\u53d1\u5e03\u7d20\u6750"
README_NAME = "\u5148\u770b\u8fd9\u91cc.txt"
README_TEXT = (
    "\u628a\u8981\u53d1\u5e03\u7684\u89c6\u9891\uff08mp4\uff09\u76f4\u63a5\u62f7"
    "\u8fdb\u8fd9\u4e2a\u6587\u4ef6\u5939\u3002\n"
    "\u6587\u4ef6\u540d\u4e0d\u8981\u6539\uff0c\u4e5f\u4e0d\u8981\u518d\u5957"
    "\u4e00\u5c42\u6587\u4ef6\u5939\u3002\n\n"
    "\u653e\u8fdb\u6765\u4ee5\u540e\u8ddf\u6211\u4eec\u8bf4\u4e00\u58f0"
    "\uff08\u6216\u6309\u6211\u4eec\u53d1\u7684\u4efb\u52a1\u786e\u8ba4"
    "\uff09\uff0c\u52a9\u624b\u5c31\u4f1a\u7528\u8fd9\u53f0\u7535\u8111"
    "\u5df2\u767b\u5f55\u7684\u8d26\u53f7\u628a\u5b83\u53d1\u51fa\u53bb\u3002\n"
)


def desktop_dir() -> Path | None:
    """Resolve the real desktop, following OneDrive redirection."""
    if os.name == "nt":
        try:
            import winreg  # type: ignore

            key = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                   r"\User Shell Folders")
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                value, _ = winreg.QueryValueEx(handle, "Desktop")
            expanded = os.path.expandvars(str(value))
            if expanded:
                return Path(expanded)
        except Exception:
            pass
        base = os.environ.get("USERPROFILE") or str(Path.home())
        return Path(base) / "Desktop"
    base = os.environ.get("XDG_DESKTOP_DIR") or str(Path.home() / "Desktop")
    return Path(base)


def materials_dir() -> Path | None:
    desktop = desktop_dir()
    if desktop is None:
        return None
    return desktop / MATERIALS_DIR_NAME


def _write_readme(folder: Path) -> None:
    target = folder / README_NAME
    try:
        if target.exists() and target.read_text(encoding="utf-8-sig") == README_TEXT:
            return
        target.write_text(README_TEXT, encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        try:
            target.write_text(README_TEXT, encoding="utf-8-sig")
        except OSError:
            pass


def _prune_legacy_link(inbox: Path, folder: Path, log=None) -> None:
    """Remove the 1.2.142 junction that made every desktop file appear twice."""
    link = inbox / MATERIALS_DIR_NAME
    try:
        if not os.path.lexists(str(link)):
            return
        if os.path.normcase(os.path.realpath(str(link))) != os.path.normcase(
                os.path.realpath(str(folder))):
            return
        attributes = getattr(os.lstat(str(link)), "st_file_attributes", 0)
        if not attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
            return
        os.rmdir(str(link))
        if log:
            log("removed legacy desktop materials junction")
    except OSError as exc:
        if log:
            log("legacy materials junction kept: %s" % exc)


def ensure(data_dir, log=None) -> Path | None:
    """Create the desktop drop folder and wire it to the media resolver."""
    folder = materials_dir()
    if folder is None:
        return None
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if log:
            log("desktop materials folder unavailable: %s" % exc)
        return None
    _write_readme(folder)
    if data_dir is not None:
        try:
            inbox = Path(data_dir) / "inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            _prune_legacy_link(inbox, folder, log)
        except OSError:
            pass
    return folder


def media_roots(layout) -> list:
    """Every directory the media resolver may search for a dropped file.

    Roots are de-duplicated by real path: an older build may have left a
    junction inside the inbox, which would otherwise make the same file show
    up twice and trip the "duplicate file name" guard in publish_exec.
    """
    candidates = []
    try:
        candidates.append(Path(layout.inbox))
    except Exception:
        pass
    folder = materials_dir()
    if folder is not None and folder.is_dir():
        candidates.append(folder)
    roots = []
    seen = set()
    for root in candidates:
        try:
            key = os.path.normcase(os.path.realpath(str(root)))
        except Exception:
            key = os.path.normcase(str(root))
        if key in seen:
            continue
        seen.add(key)
        roots.append(root)
    return roots
