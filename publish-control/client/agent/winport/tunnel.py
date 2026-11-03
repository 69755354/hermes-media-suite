"""Reverse SSH tunnel supervisor (macOS LaunchAgent parity).

Mac fact being ported (Mac background section 2.6): the tunnel flapped because
several autostart entries competed for the SAME remote port while
ExitOnForwardFailure=yes was set.  Rule enforced here: ONE remote port has
exactly ONE holder, and that is guarded by a local lock file so a second
autostart cannot join in.

The tunnel is an OPERATIONS convenience only.  Media delivery never depends on
it (downlink plan section 0.1).
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .lock import FileLock
from .subprocess_text import hidden_window_options, text_mode_options

DEFAULT_REMOTE_PORT = 46223
DEFAULT_LOCAL_PORT = 8000


def default_ssh_path() -> str:
    if os.name == "nt":
        return r"C:\Windows\System32\OpenSSH\ssh.exe"
    return "ssh"


def build_ssh_command(remote_host, remote_port=DEFAULT_REMOTE_PORT, *,
                      local_host="127.0.0.1", local_port=DEFAULT_LOCAL_PORT,
                      user=None, key_path=None, ssh_path=None,
                      exit_on_forward_failure=True) -> list:
    target = f"{user}@{remote_host}" if user else remote_host
    command = [ssh_path or default_ssh_path(),
               "-N",
               "-o", "ServerAliveInterval=30",
               "-o", "ServerAliveCountMax=3",
               "-o", f"ExitOnForwardFailure={'yes' if exit_on_forward_failure else 'no'}",
               "-R", f"{remote_port}:{local_host}:{local_port}"]
    if key_path:
        command += ["-i", str(key_path)]
    command.append(target)
    return command


def parse_netstat_listeners(text: str, port: int) -> list:
    """Extract pids listening on a port from `netstat -ano` output.

    Used to prove "only one holder for this remote port" on the real machine.
    """
    pids = []
    needle = f":{port}"
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].upper().startswith("TCP") \
                and needle in parts[1] and parts[3].upper() == "LISTENING":
            pids.append(parts[4] if len(parts) > 4 else parts[-1])
    return pids


def check_single_holder(port: int, runner=None) -> dict:
    if os.name != "nt":
        return {"checked": False, "reason": "non-windows: no-op (static test)"}
    command = ["netstat", "-ano"]
    runner = runner or (lambda: subprocess.run(
        command, capture_output=True, timeout=20,
        **hidden_window_options(command), **text_mode_options()).stdout)
    pids = parse_netstat_listeners(runner(), port)
    return {"checked": True, "port": port, "holder_pids": pids,
            "single_holder": len(pids) <= 1}


class TunnelSupervisor:
    """Holds the one-holder lock and reconnects with backoff on drop."""

    def __init__(self, layout, command, logger=None, backoff=(5, 15, 45, 135)):
        self.layout = layout
        self.command = command
        self.logger = logger
        self.backoff = backoff
        self.lock = FileLock(layout.run / "tunnel.lock")
        self._proc = None
        self.stopped = False

    def _log(self, message):
        if self.logger:
            self.logger.info("tunnel: %s", message)

    def run_forever(self, *, max_attempts=None):
        if not self.lock.acquire():
            self._log("another tunnel holder is already running; refusing to "
                      "join (one remote port = one holder)")
            return 3
        attempts = 0
        try:
            while not self.stopped:
                attempts += 1
                try:
                    self._proc = subprocess.Popen(
                        self.command,
                        **hidden_window_options(self.command, popen=True))
                    self._proc.wait()
                except (OSError, subprocess.SubprocessError) as exc:
                    self._log(f"spawn failed: {exc}")
                if max_attempts is not None and attempts >= max_attempts:
                    return 0
                delay = self.backoff[min(attempts - 1, len(self.backoff) - 1)]
                self._log(f"disconnected; reconnecting in {delay}s")
                time.sleep(delay)
        finally:
            self.lock.release()
        return 0

    def stop(self):
        self.stopped = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
