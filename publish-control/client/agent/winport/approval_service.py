"""Supervise the local Feishu approval service.

The approval service is a loopback-only helper shipped under
``vendor/approval_server``.  It used to be started by hand, which meant a
customer machine could come back after a reboot with the agent running but
without the service that answers approval queries.  ``ensure_running`` is the
single entry point used by the agent: it probes ``/health`` first and only
spawns a process when the service is actually down.

The service is deliberately started in ``APPROVAL_TEST_MODE=1``: it must not
send Feishu cards itself.  The bot on the control plane sends the card and the
customer machine only records the local decision.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .lock import FileLock

APPROVAL_HOST = "127.0.0.1"
APPROVAL_PORT = 8795
HEALTH_URL = f"http://{APPROVAL_HOST}:{APPROVAL_PORT}/health"
APPROVAL_SERVICE_NAME = "winport-approval"


def _hidden_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def approval_dir(layout) -> Path:
    return Path(layout.data) / "approval"


def decision_token_path(layout) -> Path:
    return approval_dir(layout) / "decision_token"


def service_log_path(layout) -> Path:
    return Path(layout.logs) / "approval-svc.log"


def load_or_create_decision_token(layout) -> str:
    """Return the persisted local decision token, creating it once."""
    path = decision_token_path(layout)
    try:
        token = path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        token = ""
    if token:
        return token

    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        existing = path.read_text(encoding="utf-8-sig").strip()
        if existing:
            return existing
        # A previous start died between create and write.  Replace the empty
        # file atomically instead of leaving a token-less service behind.
        tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        try:
            tmp.write_text(token + "\n", encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
        return token
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(token + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


def service_env(layout, settings, decision_token: str) -> dict:
    """Environment for the child service.  Secrets never go into logs."""
    settings = settings or {}
    feishu = settings.get("feishu_approval") or {}
    env = os.environ.copy()
    env.update({
        "APPROVAL_TEST_MODE": "1",
        "APPROVAL_HOST": APPROVAL_HOST,
        "APPROVAL_PORT": str(APPROVAL_PORT),
        "APPROVAL_CLIENT_TOKEN": str(feishu.get("client_token") or ""),
        "APPROVAL_DECISION_TOKEN": str(decision_token),
        "APPROVAL_STATE_DIR": str(approval_dir(layout) / "state"),
        "APPROVAL_TIMEOUT_MINUTES": "30",
    })
    return env


def health_ok(url: str = HEALTH_URL, timeout: float = 0.8) -> bool:
    """True only when the expected approval service answers ``/health``."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if getattr(response, "status", None) != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
        return (isinstance(payload, dict)
                and payload.get("service") == APPROVAL_SERVICE_NAME)
    except (OSError, ValueError, urllib.error.URLError):
        return False


def ensure_running(layout, settings, *, logger=None, health=None, popen=None,
                   wait_seconds: float = 8.0,
                   poll_interval: float = 0.25) -> dict:
    """Start the approval service if it is not already healthy.

    The function is intentionally fail-open for the agent: every failure is
    logged and returned as a small verdict, never raised.  A missing service
    only means approvals cannot be confirmed; it must not stop publishing
    collection or the control panel.
    """
    if logger is None:
        try:
            from .logutil import get_logger
            logger = get_logger("winport.approval_service", layout.logs)
        except Exception:
            logger = None
    probe = health or health_ok
    spawn = popen or subprocess.Popen

    lock = None
    acquired = False
    try:
        lock = FileLock(approval_dir(layout) / "approval-service.lock")
        acquired = lock.acquire(timeout=max(0.0, wait_seconds))
        if not acquired:
            if logger:
                logger.info("approval service start skipped: lock busy")
            return {"started": False, "reason": "busy"}
        if probe():
            return {"started": False, "reason": "already_running"}

        approval_dir(layout).mkdir(parents=True, exist_ok=True)
        Path(layout.logs).mkdir(parents=True, exist_ok=True)
        decision_token = load_or_create_decision_token(layout)
        server_dir = Path(layout.program) / "vendor" / "approval_server"
        server = server_dir / "server.py"
        env = service_env(layout, settings, decision_token)
        argv = [sys.executable, str(server)]
        log_path = service_log_path(layout)
        with log_path.open("ab") as log:
            spawn(argv, cwd=str(server_dir), env=env,
                  stdin=subprocess.DEVNULL, stdout=log,
                  stderr=subprocess.STDOUT, close_fds=True,
                  **_hidden_kwargs())
        if logger:
            logger.info("approval service spawned: %s", server)

        deadline = time.monotonic() + max(0.0, wait_seconds)
        while time.monotonic() < deadline:
            if probe():
                if logger:
                    logger.info("approval service is healthy")
                return {"started": True}
            time.sleep(max(0.01, poll_interval))
        if logger:
            logger.info("approval service did not become healthy within %.1fs",
                        wait_seconds)
        return {"started": False, "reason": "timeout"}
    except Exception as exc:
        if logger:
            logger.error("approval service start failed: %s: %s",
                         type(exc).__name__, exc)
        return {"started": False, "reason": "error"}
    finally:
        if acquired and lock is not None:
            lock.release()
