"""Process identity judgement (Mac `ps -o comm` replacement).

The plan is explicit (section 4.2): judge by the executable path + the exact
`--user-data-dir=` argument; helper processes (crashpad_handler, GPU, utility,
renderer) do NOT count as "someone is using Chrome"; and cleanup must NEVER do
a machine-wide `taskkill /IM chrome.exe` (that would kill the customer's own
Chrome).
"""

from __future__ import annotations

import os
import ntpath
import sys
from pathlib import Path
import posixpath
import re
import subprocess

from .subprocess_text import hidden_window_options, text_mode_options

#: Names we treat as "a browser process" when scanning for a live
#: ``--user-data-dir=<our profile>``.  1.2.2 note: we only ever LAUNCH
#: chrome.exe; msedge.exe/chromium.exe stay listed so that a stray process
#: holding our profile directory is still detected (double-launch guard), not
#: so that we would ever start one.
BROWSER_EXE_NAMES = {"chrome.exe", "chromium.exe", "msedge.exe",
                     "chrome", "chromium", "playwright"}
# 1.2.26: destructive/reuse decisions accept Google Chrome only.  A process
# named chromium/edge is not proof that the customer's Chrome profile belongs
# to this tool.
CHROME_PROCESS_NAMES = {"chrome.exe"}
EXTERNAL_PROTOCOL_DIALOG_FEATURE = "ExternalProtocolDialog"
NOT_A_USER = ("crashpad_handler", "gpu-process", "utility", "--type=renderer",
              "--type=gpu", "helper")


def list_processes() -> list:
    """Return [{pid, name, cmdline}] best effort.

    Order: psutil (if installed) -> PowerShell CIM (Windows) -> /proc (Linux).
    """
    try:
        import psutil  # type: ignore
        out = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                # psutil already parsed the Windows command line.  Joining and
                # re-splitting it loses argument boundaries for paths with
                # spaces, which can turn ``C:/app/env personal`` into the
                # different profile ``C:/app/env``.
                cmdline = list(proc.info["cmdline"] or [])
                out.append({"pid": proc.info["pid"], "name": proc.info["name"] or "",
                            "cmdline": cmdline})
            except Exception:
                continue
        return out
    except ImportError:
        pass
    if os.name == "nt":
        return _list_processes_helper() or _list_processes_powershell()
    return _list_processes_proc()


_HELPER_CODE = (
    "import json,psutil;"
    "print(json.dumps([{'pid': item.info['pid'],"
    "'name': item.info['name'] or '',"
    "'cmdline': list(item.info['cmdline'] or [])}"
    " for item in psutil.process_iter(['pid', 'name', 'cmdline'])]))"
)


def _helper_python() -> str:
    """Locate an interpreter that has psutil installed.

    The bundled ``runtime`` python ships without third-party packages, so the
    agent process can lack psutil while the bootstrap venv next to the data
    directory has it.  Starting powershell.exe instead is what trips 360's
    "PowerShell command execution" protection on customer machines.
    """
    candidates = []
    argv = list(sys.argv or [])
    if "--data" in argv:
        index = argv.index("--data")
        if index + 1 < len(argv):
            candidates.append(Path(argv[index + 1]) / ".venv" / "Scripts" / "python.exe")
    for name in ("CLI_PY", "WINPORT_PYTHON"):
        value = os.environ.get(name)
        if value:
            candidates.append(Path(value))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "HuolongAgent" / "publish-worker"
                          / ".venv" / "Scripts" / "python.exe")
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return ""


def _list_processes_helper() -> list:
    helper = _helper_python()
    if not helper:
        return []
    command = [helper, "-c", _HELPER_CODE]
    try:
        out = subprocess.run(command, capture_output=True, timeout=30,
                             **hidden_window_options(command),
                             **text_mode_options())
    except (OSError, subprocess.SubprocessError):
        return []
    import json
    try:
        payload = json.loads(out.stdout or "[]")
    except ValueError:
        return []
    if not isinstance(payload, list):
        return []
    return [{"pid": item.get("pid"), "name": item.get("name") or "",
             "cmdline": item.get("cmdline") or ""} for item in payload
            if isinstance(item, dict)]


def _list_processes_powershell() -> list:
    command = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
               "Get-CimInstance Win32_Process | "
               "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"]
    try:
        out = subprocess.run(command, capture_output=True, timeout=30,
                             **hidden_window_options(command),
                             **text_mode_options())
    except (OSError, subprocess.SubprocessError):
        return []
    import json
    try:
        payload = json.loads(out.stdout or "[]")
    except ValueError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    result = []
    for item in payload:
        result.append({"pid": item.get("ProcessId"),
                       "name": item.get("Name") or "",
                       "cmdline": item.get("CommandLine") or ""})
    return result


def _list_processes_proc() -> list:
    result = []
    proc_root = "/proc"
    if not os.path.isdir(proc_root):
        return result
    for entry in os.listdir(proc_root):
        if not entry.isdigit():
            continue
        try:
            with open(f"{proc_root}/{entry}/cmdline", "rb") as fh:
                raw = fh.read()
            with open(f"{proc_root}/{entry}/comm", encoding="utf-8",
                      errors="replace") as fh:
                name = fh.read().strip()
        except OSError:
            continue
        result.append({"pid": int(entry), "name": name,
                       "cmdline": [part.decode("utf-8", "replace")
                                   for part in raw.split(b"\x00") if part]})
    return result


def is_pid_alive(pid) -> bool:
    """Cross-platform liveness check that is SAFE on Windows.

    ``os.kill(pid, 0)`` is Unix-only in meaning; on Windows CPython maps every
    non-console signal to TerminateProcess, so using it as a health check kills
    the target.  This helper uses psutil when present, otherwise the Win32
    OpenProcess/GetExitCodeProcess pair, and only falls back to ``kill(pid, 0)``
    on POSIX.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore
        try:
            return bool(psutil.pid_exists(pid)) and                 psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
        except Exception:
            pass
    except ImportError:
        pass
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                          wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                                ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (SystemError, OSError):
        return False
    except Exception:
        return False


def is_user_process(proc: dict) -> bool:
    raw = proc.get("cmdline") or ""
    cmdline = " ".join(str(part) for part in raw).lower() \
        if isinstance(raw, (list, tuple)) else str(raw).lower()
    return not any(marker in cmdline for marker in NOT_A_USER)


def split_windows_command_line(command_line) -> list[str]:
    """Split a Windows command line into argv using CommandLineToArgvW rules.

    ``cmdline`` may already be a list.  The parser keeps argument boundaries
    inside quotes (including quoted paths with spaces) and applies the Windows
    backslash-before-quote rules.  It deliberately does not use substring
    matching: ``env_1`` and ``env_10`` are different arguments.
    """
    if isinstance(command_line, (list, tuple)):
        return [str(part) for part in command_line]
    text = str(command_line or "")
    args = []
    i = 0
    while i < len(text):
        while i < len(text) and text[i] in " \t":
            i += 1
        if i >= len(text):
            break
        current = []
        quoted = False
        while i < len(text):
            if text[i] in " \t" and not quoted:
                break
            slashes = 0
            while i < len(text) and text[i] == "\\":
                slashes += 1
                i += 1
            if i < len(text) and text[i] == '"':
                current.extend("\\" * (slashes // 2))
                if slashes % 2:
                    current.append('"')
                elif quoted and i + 1 < len(text) and text[i+1] == '"':
                    current.append('"')
                    i += 1
                else:
                    quoted = not quoted
                i += 1
            else:
                current.extend("\\" * slashes)
                if i < len(text) and (quoted or text[i] not in " \t"):
                    current.append(text[i])
                    i += 1
                else:
                    break
        if quoted:
            return []  # uncertainty must not reach process cleanup
        args.append("".join(current))
    return args


def normalize_path(path) -> str:
    """Canonical comparison form for a Windows/Unix profile or executable path."""
    value = str(path or "").strip().strip('"').replace("\\", "/")
    if not value:
        return ""
    if re.match(r"^[A-Za-z]:/", value):
        value = ntpath.normpath(value).replace("\\", "/")
    else:
        value = posixpath.normpath(value)
    return value.rstrip("/").lower()


def _option_values(argv: list[str], option: str) -> list[str]:
    prefix = option + "="
    return [part[len(prefix):] for part in argv
            if part.lower().startswith(prefix.lower())]


def process_argv(proc: dict) -> list[str]:
    return split_windows_command_line(proc.get("cmdline") or "")


def has_disable_feature(argv: list[str], feature: str) -> bool:
    """True only when an explicit ``--disable-features`` list contains feature."""
    values = _option_values(argv, "--disable-features")
    if len(values) != 1:
        return False
    features = {v.strip() for v in values[0].split(",")}
    enabled = _option_values(argv, "--enable-features")
    if any(feature in {v.strip() for v in item.split(",")} for item in enabled):
        return False
    return bool(feature) and feature in features


def listening_pids(port, *, netstat=None) -> set[int]:
    """Return PIDs that are actually listening on ``port`` on Windows.

    The process command line can *claim* a remote-debugging port without owning
    it (for example after a crash, port reuse, or a hand-edited marker).  The
    destructive cleanup path therefore checks the OS socket table as well as
    argv.  Non-Windows builds return an empty set: they never call taskkill.
    """
    try:
        port = int(port)
    except (TypeError, ValueError):
        return set()
    if port <= 0 or os.name != "nt":
        return set()
    try:
        command = ["netstat", "-ano"]
        result = (netstat or subprocess.run)(
            command, capture_output=True, timeout=15,
            **hidden_window_options(command), **text_mode_options())
    except (OSError, subprocess.SubprocessError):
        return set()
    owners: set[int] = set()
    for line in str(getattr(result, "stdout", "") or "").splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        if "LISTEN" not in parts[3].upper():
            continue
        local_address = parts[1]
        try:
            local_port = int(local_address.rsplit(":", 1)[1])
            pid = int(parts[4])
        except (IndexError, TypeError, ValueError):
            continue
        if local_port == port and pid > 0:
            owners.add(pid)
    return owners


def profile_processes(profile_dir, processes=None, *, expected_exe=None,
                      expected_port=None) -> list:
    """Processes whose parsed argv names this exact profile and port.

    Only a real Chrome executable is eligible.  The ``--user-data-dir`` value
    must equal the whole normalized path; same-prefix directories (env_1 vs
    env_10), quoted paths, non-browser processes and helper subprocesses are
    rejected.  When ``expected_port`` is supplied, the process must also own
    that exact remote-debugging port.
    """
    target = normalize_path(profile_dir)
    if not target:
        return []
    expected_exe_norm = normalize_path(expected_exe) if expected_exe else None
    processes = processes if processes is not None else list_processes()
    hits = []
    for proc in processes:
        argv = process_argv(proc)
        if not argv:
            continue
        reported_name = posixpath.basename(
            str(proc.get("name") or "").replace("\\", "/")).lower()
        if reported_name and reported_name not in CHROME_PROCESS_NAMES:
            continue
        exe = argv[0].strip().strip('"')
        exe_name = posixpath.basename(exe.replace("\\", "/")).lower()
        if exe_name not in CHROME_PROCESS_NAMES:
            continue
        if expected_exe_norm and normalize_path(exe) != expected_exe_norm:
            continue
        if not is_user_process({"cmdline": " ".join(argv)}):
            continue
        profiles = _option_values(argv, "--user-data-dir")
        if len(profiles) != 1 or normalize_path(profiles[0]) != target:
            continue
        if expected_port is not None:
            ports = _option_values(argv, "--remote-debugging-port")
            if len(ports) != 1:
                continue
            try:
                if int(ports[0]) != int(expected_port):
                    continue
            except (TypeError, ValueError):
                continue
        hits.append(proc)
    return hits


def is_profile_in_use(profile_dir, processes=None) -> bool:
    return bool(profile_processes(profile_dir, processes))


def verify_launch_argv(pid, profile_dir, *, expected_exe, expected_port=None,
                       processes=None, require_dialog_guard=True) -> dict:
    """Verify the spawned PID still names the exact Chrome/profile/port argv."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return {"verified": False, "reason": "PID_INVALID"}
    if pid <= 0:
        return {"verified": False, "reason": "PID_INVALID"}
    snapshot = processes if processes is not None else list_processes()
    same_pid = [proc for proc in snapshot if str(proc.get("pid")) == str(pid)]
    if len(same_pid) != 1:
        return {"verified": False, "reason": "PID_NOT_UNIQUE_OR_GONE",
                "matches": len(same_pid)}
    matches = profile_processes(profile_dir, same_pid, expected_exe=expected_exe,
                                expected_port=expected_port)
    if len(matches) != 1:
        return {"verified": False, "reason": "ARGV_IDENTITY_MISMATCH",
                "matches": len(matches), "pid": pid}
    argv = process_argv(matches[0])
    if require_dialog_guard and not has_disable_feature(
            argv, EXTERNAL_PROTOCOL_DIALOG_FEATURE):
        return {"verified": False, "reason": "DIALOG_GUARD_ARGV_MISSING",
                "pid": pid, "argv": argv}
    return {"verified": True, "reason": "ARGV_MATCH", "pid": pid,
            "argv": argv, "profile": normalize_path(profile_dir),
            "exe": normalize_path(argv[0]) if argv else "",
            "port": int(expected_port) if expected_port is not None else None}


def kill_profile_browsers(profile_dir, processes=None, *, expected_exe=None,
                          expected_port=None, netstat=None) -> list:
    """Terminate ONLY processes bound to this exact user-data-dir.

    Never uses taskkill /IM <name>.  Returns the pids we asked to stop.  On
    non-Windows this is a no-op (the static test never kills anything).
    """
    if not expected_exe or expected_port is None:
        # A kill without both identity fields is not provable; stop.
        return []
    hits = profile_processes(profile_dir, processes, expected_exe=expected_exe,
                             expected_port=expected_port)
    if os.name != "nt":
        return []
    killed = []
    port_owners = listening_pids(expected_port, netstat=netstat) \
        if expected_port is not None else None
    for proc in hits:
        try:
            # Re-read immediately before the kill: a stale PID may now belong
            # to an unrelated process.  It must match the same full identity.
            current = list_processes()
            pid = proc.get("pid")
            same_pid = [item for item in current
                        if str(item.get("pid")) == str(pid)]
            if len(same_pid) != 1:
                continue
            confirmed = profile_processes(
                profile_dir, same_pid, expected_exe=expected_exe,
                expected_port=expected_port)
            if len(confirmed) != 1:
                continue
            # The OS must also say this pid owns the listening socket.  A
            # command-line flag alone is not proof of ownership.
            if port_owners != {int(pid)}:
                continue
            if listening_pids(expected_port, netstat=netstat) != {int(pid)}:
                continue
            result = subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                                    capture_output=True, timeout=15,
                                    **hidden_window_options(
                                        ["taskkill", "/PID", str(pid), "/F"]),
                                    **text_mode_options())
            if result.returncode == 0:
                killed.append(pid)
        except (OSError, subprocess.SubprocessError):
            continue
    return killed
