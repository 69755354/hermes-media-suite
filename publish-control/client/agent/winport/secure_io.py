"""Link-safe file access for customer-controlled inputs.

Path checks alone do not close a scan/read race: an inbox file can be
replaced by a symbolic link, junction, or another reparse point between the
scan and the hash or upload.  Every security-sensitive read in the publish
path goes through this module instead.

The final path component is opened without following a reparse point.  On
POSIX this uses ``O_NOFOLLOW``; on Windows it uses
``FILE_FLAG_OPEN_REPARSE_POINT`` and checks the opened handle's attributes.
An opened handle is then used for both hashing and copying, so the bytes that
were hashed are the bytes that are written to the private staging file.
"""
from __future__ import annotations

import errno
import hashlib
import os
import stat
from pathlib import Path

CHUNK = 1 << 20
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _absolute(path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _reparse_from_stat(st) -> bool:
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0)
                & FILE_ATTRIBUTE_REPARSE_POINT)


def is_reparse_point(path) -> bool:
    """Return True when the path itself is a link or reparse point."""
    try:
        return _reparse_from_stat(os.lstat(os.fspath(path)))
    except OSError:
        return False


def is_within(path, root) -> bool:
    """Lexical containment check that never follows a link."""
    path_abs = os.path.normcase(str(_absolute(path)))
    root_abs = os.path.normcase(str(_absolute(root)))
    try:
        return os.path.commonpath((path_abs, root_abs)) == root_abs
    except ValueError:
        return False


def assert_no_reparse_chain(path, *, root=None) -> Path:
    """Reject a reparse point at ``path`` or between it and ``root``.

    ``root`` is the trusted directory and is included in the check.  When it
    is omitted only the final path component is checked; callers that walk
    outside a known customer root must pass that root explicitly.
    """
    path_abs = _absolute(path)
    root_abs = _absolute(root) if root is not None else None
    if root_abs is not None and not is_within(path_abs, root_abs):
        raise OSError(errno.EACCES, "path is outside the trusted root",
                      str(path_abs))

    cursor = path_abs
    while True:
        if is_reparse_point(cursor):
            raise OSError(errno.ELOOP,
                          "symbolic link or reparse point is not allowed",
                          str(cursor))
        if root_abs is None or os.path.normcase(str(cursor)) == os.path.normcase(str(root_abs)):
            break
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    return path_abs


def _open_posix(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return os.open(str(path), flags)


def _open_windows(path: Path) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    generic_read = 0x80000000
    share_all = 0x00000007
    open_existing = 3
    open_reparse_point = 0x00200000
    backup_semantics = 0x02000000
    handle = create_file(
        str(path), generic_read, share_all, None, open_existing,
        open_reparse_point | backup_semantics, None)
    invalid = ctypes.c_void_p(-1).value
    if handle is None or int(handle) == invalid:
        raise OSError(ctypes.get_last_error(), "cannot open file", str(path))
    try:
        return msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close_handle(handle)
        raise


def secure_open(path, *, root=None):
    """Open a regular file for reading without following a link/reparse point."""
    path_abs = assert_no_reparse_chain(path, root=root)
    if os.name == "nt":
        fd = _open_windows(path_abs)
    else:
        fd = _open_posix(path_abs)
    try:
        st = os.fstat(fd)
        if _reparse_from_stat(st):
            raise OSError(errno.ELOOP,
                          "opened handle is a symbolic link or reparse point",
                          str(path_abs))
        if not stat.S_ISREG(st.st_mode):
            raise OSError(errno.EINVAL, "regular file required", str(path_abs))
        return os.fdopen(fd, "rb", closefd=True)
    except BaseException:
        os.close(fd)
        raise


def secure_stat(path, *, root=None):
    """Return ``fstat`` data from a no-follow opened handle."""
    with secure_open(path, root=root) as handle:
        return os.fstat(handle.fileno())


def sha256_file(path, *, root=None) -> str:
    """Hash the bytes read through a no-follow handle."""
    digest = hashlib.sha256()
    with secure_open(path, root=root) as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def copy_hashed_file(source, destination, *, root=None, expected_sha256=None):
    """Copy one regular file through a single handle and return (sha, size).

    The source handle is opened without following links.  The destination is
    created exclusively, so an existing link cannot redirect the write.  When
    ``expected_sha256`` is supplied, a mismatch removes the partial output and
    raises ``ValueError``.
    """
    destination = _absolute(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    flags |= getattr(os, "O_NOFOLLOW", 0)

    digest = hashlib.sha256()
    size = 0
    with secure_open(source, root=root) as src:
        dst_fd = os.open(str(destination), flags, 0o600)
        try:
            dst = os.fdopen(dst_fd, "wb", closefd=True)
        except BaseException:
            os.close(dst_fd)
            try:
                destination.unlink()
            except OSError:
                pass
            raise
        try:
            with dst:
                while True:
                    block = src.read(CHUNK)
                    if not block:
                        break
                    digest.update(block)
                    size += len(block)
                    dst.write(block)
                dst.flush()
                os.fsync(dst.fileno())
        except BaseException:
            try:
                destination.unlink()
            except OSError:
                pass
            raise

    actual = digest.hexdigest()
    if expected_sha256 is not None and actual != str(expected_sha256).lower():
        try:
            destination.unlink()
        except OSError:
            pass
        raise ValueError("source changed after it was inspected")
    return actual, size
