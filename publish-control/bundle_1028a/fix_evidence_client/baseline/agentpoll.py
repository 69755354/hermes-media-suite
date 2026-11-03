"""Client-side control-plane poller for the multitenant publish worker.

Run on each customer machine (normally as a daemon thread next to the local
panel, or as a scheduled task)::

    CUSTOMER_ID=c_123 CUSTOMER_TOKEN=... CONTROL_URL=https://control.example \
      python -m agent.winport.agentpoll

Every ``AGENT_POLL_INTERVAL`` seconds (default 20) it calls
``POST /api/agent/poll`` with ``Authorization: Bearer <customer token>``.
A command is executed only when its kind is in :data:`ALLOWED_KINDS`; the
result is posted back to ``POST /api/command`` (falling back to
``/api/agent/result`` for older control planes).

The poller is intentionally standard-library only.  It never shells out with
an arbitrary payload: the command kind maps to a fixed CLI subcommand and only
a small allow-list of structured fields is turned into arguments.  A
``payload.args`` list is rejected outright, and every path field is checked
against the customer data root before it reaches the worker CLI.

Idempotency: the last terminal result for every ``command_id`` is persisted in
``<customer>/run/agentpoll-state.json``.  If the control plane redelivers a
command after a restart, the stored result is replayed and the command is not
executed a second time.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .customer_paths import (
    DEFAULT_CUSTOMER_ID,
    CustomerLayout,
    customer_root,
    default_data_root,
    normalize_customer_id,
)
from .secure_io import assert_no_reparse_chain, is_within
from .subprocess_text import hidden_window_options

DEFAULT_CONTROL_URL = "http://127.0.0.1:8899"
DEFAULT_POLL_INTERVAL = 20.0
DEFAULT_MAX_BACKOFF = 300.0
DEFAULT_COMMAND_TIMEOUT = 300.0
STATE_VERSION = 1

#: The command kinds the control plane / poller are allowed to execute.
#: ``schedule`` is intentionally absent: this build does not ship bot_ops.py,
#: so accepting it used to degrade into an empty publish-enqueue invocation.
ALLOWED_KINDS = ("publish", "collect", "report", "status")

#: Kind -> worker CLI subcommand.
COMMAND_SUBCOMMANDS = {
    "publish": "publish",
    "collect": "collect-all",
    "report": "report",
    "status": "state",
}

LOG = logging.getLogger("winport.agentpoll")


class AgentPollError(RuntimeError):
    """Base error for the poller."""


class AuthError(AgentPollError):
    """The control plane rejected the customer token."""


class ControlPlaneError(AgentPollError):
    """The control plane was unreachable or returned an invalid response."""


class UnsupportedCommand(AgentPollError):
    """The command kind is not on the client-side whitelist."""

    def __init__(self, kind, detail=""):
        message = f"unsupported command kind: {kind!r}"
        if detail:
            message += f" ({detail})"
        super().__init__(message)
        self.kind = kind
        self.detail = detail


def normalize_kind(kind) -> str:
    return str(kind or "").strip().lower()


def is_allowed(kind) -> bool:
    return normalize_kind(kind) in ALLOWED_KINDS


_LOOPBACK_HOSTS = frozenset(("localhost",))


def _is_loopback_host(host) -> bool:
    value = str(host or "").strip().strip("[]").lower()
    if value in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def validate_control_url(value) -> str:
    """Allow HTTPS anywhere, plain HTTP only on loopback.

    A Bearer token is sent on every poll.  Plain HTTP to a remote host would
    expose it to any network observer, so that combination is rejected before
    the first request is made.
    """
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("control_url is required")
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("control_url must use https:// (or http:// on loopback)")
    if parts.username or parts.password:
        raise ValueError("control_url must not contain credentials")
    if not parts.hostname:
        raise ValueError("control_url has no host")
    if parts.fragment:
        raise ValueError("control_url must not contain a fragment")
    if parts.query:
        raise ValueError("control_url must not contain a query string")
    if scheme == "http" and not _is_loopback_host(parts.hostname):
        raise ValueError(
            "http control_url is only allowed for loopback; use https://")
    return raw.rstrip("/")


def _env_bool(value) -> bool:
    return str(value or "").strip().lower() not in ("", "0", "false", "no", "off")


def next_backoff(current, interval=DEFAULT_POLL_INTERVAL,
                 max_backoff=DEFAULT_MAX_BACKOFF) -> float:
    """Exponential backoff helper used by the poll loop (never below 1s)."""
    return min(max(float(current) * 2, float(interval), 1.0), float(max_backoff))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class AgentConfig:
    """Runtime configuration for one customer machine.

    ``data_root`` is the base publish-worker data root.  The effective
    customer directory is exposed as :attr:`layout` / :attr:`customer_root`.
    """

    def __init__(
        self,
        customer_id=DEFAULT_CUSTOMER_ID,
        token="",
        control_url=DEFAULT_CONTROL_URL,
        data_root=None,
        poll_interval=DEFAULT_POLL_INTERVAL,
        max_backoff=DEFAULT_MAX_BACKOFF,
        command_timeout=DEFAULT_COMMAND_TIMEOUT,
        cli_python=None,
        cli_root=None,
        program_dir=None,
        state_file=None,
        status_file=None,
        interval=None,
        timeout=None,
        system_root=None,
        single_root=False,
        **kwargs,
    ):
        self.customer_id = normalize_customer_id(customer_id)
        self.token = str(token or "")
        self.control_url = validate_control_url(
            control_url or DEFAULT_CONTROL_URL)
        self.base_data_root = Path(data_root).expanduser() if data_root else default_data_root()
        self.poll_interval = float(
            interval if interval is not None else poll_interval
        )
        self.max_backoff = float(max_backoff)
        self.command_timeout = float(
            timeout if timeout is not None else command_timeout
        )
        self.cli_python = str(cli_python or os.environ.get("CLI_PY") or sys.executable)
        self.cli_root = str(cli_root) if cli_root else None
        self.program_dir = str(program_dir) if program_dir else self.cli_root
        self.state_file = Path(state_file) if state_file else None
        self._status_file = Path(status_file) if status_file else None
        self.single_root = bool(single_root)
        # ``single_root`` is for a dedicated customer machine: the historical
        # publish-worker root stays the data area (so inbox/config/profiles do
        # not move), while CUSTOMER_ID still selects the control-plane queue.
        # Omit it when several customers share one machine; then data is
        # namespaced under customers/<customer_id>/.
        self.layout = CustomerLayout(
            self.base_data_root, self.customer_id,
            scoped=not bool(single_root), system_root=system_root)
        if kwargs.get("ensure"):
            self.layout.ensure()

    @property
    def data_root(self) -> Path:
        return self.layout.root

    @property
    def customer_root(self) -> Path:
        return self.layout.root

    @classmethod
    def from_env(cls, env=None, require_explicit_control_url=False,
                 **overrides):
        env = os.environ if env is None else env
        customer_id = (
            env.get("CUSTOMER_ID")
            or env.get("WINPORT_CUSTOMER_ID")
            or env.get("AGENT_CUSTOMER_ID")
            or DEFAULT_CUSTOMER_ID
        )
        token = (
            env.get("CUSTOMER_TOKEN")
            or env.get("AGENT_TOKEN")
            or env.get("WINPORT_CUSTOMER_TOKEN")
            or ""
        )
        data_root = env.get("WINPORT_DATA") or env.get("WORKER_DATA_ROOT")
        configured_url = env.get("CONTROL_URL")
        if require_explicit_control_url:
            if not configured_url:
                raise ValueError(
                    "CONTROL_URL is required for automatic agentpoll startup")
            if urlsplit(configured_url).scheme.lower() != "https":
                raise ValueError(
                    "automatic agentpoll startup requires an https CONTROL_URL")
        kwargs = dict(
            customer_id=customer_id,
            token=token,
            control_url=configured_url or DEFAULT_CONTROL_URL,
            data_root=data_root,
            poll_interval=env.get("AGENT_POLL_INTERVAL") or DEFAULT_POLL_INTERVAL,
            max_backoff=env.get("AGENT_MAX_BACKOFF") or DEFAULT_MAX_BACKOFF,
            command_timeout=env.get("AGENT_COMMAND_TIMEOUT") or DEFAULT_COMMAND_TIMEOUT,
            cli_python=env.get("CLI_PY") or env.get("WINPORT_PYTHON"),
            cli_root=env.get("CLI_ROOT"),
            program_dir=env.get("WINPORT_PROGRAM") or env.get("CLI_ROOT"),
            state_file=env.get("AGENT_STATE_FILE"),
            status_file=env.get("AGENT_STATUS_FILE"),
            system_root=env.get("WINPORT_SYSTEM"),
            single_root=_env_bool(env.get("WINPORT_CUSTOMER_ROOT")
                                  or env.get("AGENT_SINGLE_ROOT")),
        )
        kwargs.update(overrides)
        return cls(**kwargs)

    def to_dict(self) -> dict:
        return {
            "customer_id": self.customer_id,
            "control_url": self.control_url,
            "data_root": str(self.data_root),
            "system_root": str(self.layout.system),
            "single_root": self.single_root,
            "poll_interval": self.poll_interval,
            "max_backoff": self.max_backoff,
            "command_timeout": self.command_timeout,
            "cli_python": self.cli_python,
            "cli_root": self.cli_root,
            "has_token": bool(self.token),
            "status_file": str(self.status_path),
        }

    @property
    def status_path(self) -> Path:
        return self._status_file or (self.layout.run / "agentpoll-status.json")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _headers(config) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if config.token:
        # Bearer is the documented form; the legacy header is also accepted by
        # the control plane and by older builds.
        headers["Authorization"] = "Bearer " + config.token
        headers["X-Agent-Token"] = config.token
    return headers


def _http_json(config, method, path, payload=None, timeout=None):
    """Small urllib wrapper. Returns (status, decoded_json)."""
    url = config.control_url.rstrip("/") + path
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=_headers(config), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout or 15) as response:
            raw = response.read().decode("utf-8", "replace")
            try:
                return response.status, json.loads(raw or "{}")
            except ValueError:
                return response.status, {"raw": raw}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw or "{}")
        except ValueError:
            body = {"raw": raw}
        if exc.code in (401, 403):
            raise AuthError(body.get("error") or "control plane rejected token") from exc
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ControlPlaneError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Poll / result protocol
# ---------------------------------------------------------------------------

def poll_once(config, channel=None, include_unaddressed=False):
    """Ask the control plane for one command, optionally scoped to a channel.

    ``channel`` makes one machine able to run several accounts in parallel:
    each worker only claims its own channel's commands.  Only the default
    worker passes ``include_unaddressed`` so legacy commands without a channel
    are still delivered exactly once.

    Returns the command dict, or ``None`` when the queue is empty.
    """
    request = {"customer_id": config.customer_id}
    if channel:
        request["channel"] = str(channel)
        if include_unaddressed:
            request["include_unaddressed"] = True
    status, body = _http_json(
        config,
        "POST",
        "/api/agent/poll",
        request,
        timeout=15,
    )
    if status >= 400:
        raise ControlPlaneError(body.get("error") or f"poll failed ({status})")
    command = body.get("command")
    if not command:
        return None
    if not isinstance(command, dict):
        raise ControlPlaneError("invalid command in poll response")
    command_id = command.get("command_id") or command.get("id")
    if command_id:
        command["command_id"] = str(command_id)
        command["id"] = str(command_id)
    return command


def post_result(config, command, result):
    """Post a terminal result. Returns the control-plane response body."""
    command_id = command.get("command_id") or command.get("id")
    status = "done" if result.get("ok") else "failed"
    body = {
        "customer_id": config.customer_id,
        "command_id": command_id,
        "id": command_id,
        "kind": normalize_kind(command.get("kind")),
        "status": status,
        "result": result,
    }
    try:
        code, response = _http_json(config, "POST", "/api/command", body, timeout=20)
        if code in (404, 405):
            code, response = _http_json(config, "POST", "/api/agent/result", body, timeout=20)
    except ControlPlaneError:
        raise
    if code >= 400:
        raise ControlPlaneError(response.get("error") or f"result post failed ({code})")
    return response


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------

def _layout(config) -> CustomerLayout:
    return config.layout


def _is_inside(path, root) -> bool:
    return is_within(path, root)


def _tenant_path(config, value, *, suffix=None, must_exist=False,
                 roots=None):
    """Resolve and confine one control-plane supplied path.

    Every path that reaches the worker CLI goes through this check.  A path
    that is relative, outside the tenant root, or of an unexpected type is a
    hard command failure rather than a silently accepted argument.
    """
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("path is required")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("path must be absolute")
    config.layout.validate()
    allowed = tuple(roots or (config.layout.root,))
    if not any(_is_inside(path, root) for root in allowed):
        raise ValueError("path is outside the customer data area")
    for root in allowed:
        if _is_inside(path, root):
            assert_no_reparse_chain(path, root=root)
    resolved = Path(os.path.abspath(os.fspath(path))).resolve(strict=False)
    if suffix and resolved.suffix.lower() != suffix:
        raise ValueError("unexpected file type")
    if must_exist and not resolved.exists():
        raise ValueError("path does not exist")
    return resolved


def _payload_flag(value) -> bool:
    """Accept only an explicit confirmation flag, never a truthy string."""
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def build_argv(config, kind, payload):
    """Translate a whitelisted command into a fixed worker CLI invocation."""
    kind = normalize_kind(kind)
    if kind not in ALLOWED_KINDS:
        detail = ("schedule commands are not shipped in this build"
                  if kind == "schedule" else "")
        raise UnsupportedCommand(kind, detail)
    payload = payload if isinstance(payload, dict) else {}
    if "args" in payload:
        raise UnsupportedCommand(
            kind, "payload.args is not permitted")
    data = str(_layout(config).root)
    program = str(config.program_dir) if config.program_dir else None

    def finish(argv, with_program=True):
        if program and with_program:
            argv.extend(["--program", program])
        return argv

    if kind == "status":
        return finish([config.cli_python, "-m", "agent.winport.cli", "state", "--data", data])

    if kind == "collect":
        argv = [config.cli_python, "-m", "agent.winport.cli", "collect-all", "--data", data]
        if payload.get("day"):
            argv += ["--day", str(payload["day"])]
        if payload.get("collect_only"):
            argv.append("--collect-only")
        if payload.get("report_only"):
            argv.append("--report-only")
        if payload.get("out"):
            argv += ["--out", str(_tenant_path(config, payload["out"]))]
        return finish(argv)

    if kind == "report":
        argv = [config.cli_python, "-m", "agent.winport.cli", "report", "--data", data]
        if payload.get("day"):
            argv += ["--day", str(payload["day"])]
        if payload.get("collection_json"):
            argv += ["--collection-json", str(_tenant_path(
                config, payload["collection_json"], must_exist=True))]
        return finish(argv)

    if kind == "publish":
        op = str(payload.get("op") or payload.get("action") or "").strip().lower()
        if op == "confirm":
            argv = [config.cli_python, "-m", "agent.winport.cli", "publish",
                    "--data", data, "--mode", "approved_publish"]
            for key, flag, suffix in (
                    ("plan", "--plan", ".json"),
                    ("preview", "--preview", ".json"),
                    ("receipt", "--receipt", ".json")):
                if payload.get(key):
                    argv += [flag, str(_tenant_path(
                        config, payload[key], suffix=suffix,
                        must_exist=True))]
            if payload.get("confirm_token"):
                argv += ["--confirm-token", str(payload["confirm_token"])]
            if payload.get("license"):
                argv += ["--license", str(_tenant_path(
                    config, payload["license"], suffix=".json",
                    must_exist=True, roots=(_layout(config).system,)))]
            if _payload_flag(payload.get("allow_submit")):
                argv.append("--allow-submit")
            if _payload_flag(payload.get("canary_armed")):
                argv.append("--canary-armed")
            if payload.get("republish_confirmed"):
                argv.append("--republish-confirmed")
            return finish(argv)
        argv = [config.cli_python, "-m", "agent.winport.cli", "publish", "--data", data]
        for key, flag, suffix in (
                ("plan", "--plan", ".json"),
                ("preview", "--preview", ".json"),
                ("receipt", "--receipt", ".json")):
            if payload.get(key):
                argv += [flag, str(_tenant_path(
                    config, payload[key], suffix=suffix, must_exist=True))]
        for key, flag in (
                ("mode", "--mode"),
                ("confirm_token", "--confirm-token"),
                ("approval_id", "--approval-id")):
            if payload.get(key):
                argv += [flag, str(payload[key])]
        if payload.get("license"):
            argv += ["--license", str(_tenant_path(
                config, payload["license"], suffix=".json",
                must_exist=True, roots=(_layout(config).system,)))]
        if _payload_flag(payload.get("allow_submit")):
            argv.append("--allow-submit")
        return finish(argv)

    raise UnsupportedCommand(kind)


def _parse_worker_output(stdout):
    """Return the last JSON object printed by the worker, if any."""
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _worker_env(config) -> dict:
    env = os.environ.copy()
    layout = _layout(config)
    env["WINPORT_DATA"] = str(layout.root)
    env["WINPORT_SYSTEM"] = str(layout.system)
    env["CUSTOMER_ID"] = config.customer_id
    if config.token:
        env["CUSTOMER_TOKEN"] = config.token
    if config.program_dir:
        env["WINPORT_PROGRAM"] = str(config.program_dir)
    return env


def execute_command(config, command, runner=None):
    """Execute one command locally. ``runner`` is injectable for tests."""
    kind = normalize_kind(command.get("kind"))
    if kind not in ALLOWED_KINDS:
        detail = ("schedule commands are not shipped in this build"
                  if kind == "schedule" else "")
        raise UnsupportedCommand(kind, detail)
    payload = command.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    if "args" in payload:
        raise UnsupportedCommand(kind, "payload.args is not permitted")

    op = str(payload.get("op") or payload.get("action") or "").strip().lower()
    if kind == "publish" and op in ("prepare", "create", "confirm"):
        # The bot's raw "publish" message is queued as op=create.  Older
        # control-plane rows may still carry op=prepare; both mean the same
        # fixed prepare operation (scan inbox + dry-run preview).
        op = "prepare" if op in ("prepare", "create") else "confirm"
        layout = _layout(config)
        try:
            layout.ensure()
        except OSError as exc:
            return {
                "ok": False,
                "status": "failed",
                "error": f"cannot create customer data area: {exc}",
                "kind": kind,
                "command_id": command.get("command_id") or command.get("id"),
            }
        from . import remote_ops
        command_id = command.get("command_id") or command.get("id")
        if op == "prepare":
            result = remote_ops.prepare(config, payload, command_id=command_id)
        else:
            result = remote_ops.confirm(config, payload, command_id=command_id,
                                        runner=runner)
        result.setdefault("command_id", command_id)
        result.setdefault("kind", kind)
        result.setdefault("status", "done" if result.get("ok") else "failed")
        return result

    argv = build_argv(config, kind, payload)
    layout = _layout(config)
    try:
        layout.ensure()
    except OSError as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": f"cannot create customer data area: {exc}",
            "kind": kind,
            "command_id": command.get("command_id") or command.get("id"),
            "argv": argv,
        }

    timeout = payload.get("timeout", config.command_timeout)
    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        timeout = config.command_timeout
    timeout = max(1.0, min(timeout, 3600.0))

    runner = runner or subprocess.run
    try:
        proc = runner(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_worker_env(config),
            cwd=config.cli_root or None,
            shell=False,
            **hidden_window_options(argv),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": f"command timed out after {timeout:g}s",
            "kind": kind,
            "command_id": command.get("command_id") or command.get("id"),
            "argv": argv,
            "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "") if isinstance(exc.stderr, str) else "",
        }
    except Exception as exc:  # noqa: BLE001 - reported, never crashes the loop
        return {
            "ok": False,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "kind": kind,
            "command_id": command.get("command_id") or command.get("id"),
            "argv": argv,
        }

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    exit_code = proc.returncode
    parsed = _parse_worker_output(stdout)
    ok = (
        exit_code == 0
        and parsed.get("ok", True) is not False
        and not parsed.get("error")
    )
    return {
        "ok": ok,
        "status": "done" if ok else "failed",
        "kind": kind,
        "command_id": command.get("command_id") or command.get("id"),
        "exit_code": exit_code,
        "stdout": stdout[-20000:],
        "stderr": stderr[-20000:],
        "result": parsed,
        "argv": argv,
    }


# ---------------------------------------------------------------------------
# Durable idempotency state
# ---------------------------------------------------------------------------

class CommandState:
    """Atomic JSON state keyed by command_id (one file per customer)."""

    def __init__(self, path, lock=None):
        self.path = Path(path)
        # One lock per state FILE, not per instance: two channel workers hold
        # their own CommandState objects but must serialise on the same file.
        self._lock = lock or threading.RLock()

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            if isinstance(data, dict) and isinstance(data.get("commands"), dict):
                return data
        except (OSError, ValueError):
            pass
        return {"version": STATE_VERSION, "commands": {}}

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, command_id):
        with self._lock:
            return self._read()["commands"].get(str(command_id))

    def mark_running(self, command_id, kind):
        with self._lock:
            data = self._read()
            data["commands"][str(command_id)] = {
                "status": "running",
                "kind": kind,
                "updated": time.time(),
                "posted": False,
            }
            self._write(data)

    def mark_result(self, command_id, result):
        with self._lock:
            data = self._read()
            entry = data["commands"].get(str(command_id), {})
            entry.update(
                {
                    "status": result.get("status") or ("done" if result.get("ok") else "failed"),
                    "result": result,
                    "updated": time.time(),
                    "posted": False,
                }
            )
            data["commands"][str(command_id)] = entry
            self._write(data)

    def mark_posted(self, command_id):
        with self._lock:
            data = self._read()
            entry = data["commands"].get(str(command_id))
            if entry is not None:
                entry["posted"] = True
                entry["posted_at"] = time.time()
                self._write(data)

    def pending(self):
        with self._lock:
            return [
                (cid, entry)
                for cid, entry in self._read()["commands"].items()
                if entry.get("result") and not entry.get("posted")
            ]


_STATE_LOCKS: dict[str, threading.RLock] = {}
_STATE_LOCKS_GUARD = threading.Lock()


def _state_for(config) -> CommandState:
    path = config.state_file or (_layout(config).run / "agentpoll-state.json")
    key = str(path)
    with _STATE_LOCKS_GUARD:
        lock = _STATE_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _STATE_LOCKS[key] = lock
    return CommandState(path, lock=lock)


def _write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)


def write_status(config, **fields):
    """Write the observability marker used by startup/supervision.

    The poller itself updates this file on every poll and every error.  The
    startup chain also uses it to record a disabled or failed poller, so a
    silent non-running poller is visible in ``run/agentpoll-status.json``.
    """
    data = {
        "version": STATE_VERSION,
        "customer_id": config.customer_id,
        "control_url": config.control_url,
        "updated": time.time(),
    }
    data.update(fields)
    try:
        _write_json_atomic(config.status_path, data)
        return True
    except OSError:
        return False


def process_command(config, command, runner=None):
    """Idempotently execute one command and persist its result.

    A command that already has a terminal result is *not* executed again; the
    stored result is returned with ``replayed=True``.
    """
    command_id = str(command.get("command_id") or command.get("id") or "").strip()
    if not command_id:
        return {
            "ok": False,
            "status": "failed",
            "error": "command_id missing",
            "kind": normalize_kind(command.get("kind")),
        }
    kind = normalize_kind(command.get("kind"))
    state = _state_for(config)

    prior = state.get(command_id)
    if prior and prior.get("status") in ("done", "failed", "cancelled"):
        result = dict(prior.get("result") or {})
        result["replayed"] = True
        result["command_id"] = command_id
        return result
    if prior and prior.get("status") == "running":
        # Another process/thread claimed it. Never execute twice.
        return {
            "ok": False,
            "status": "running",
            "error": "command already running",
            "kind": kind,
            "command_id": command_id,
            "replayed": True,
        }

    state.mark_running(command_id, kind)
    try:
        if kind not in ALLOWED_KINDS:
            raise UnsupportedCommand(kind)
        result = execute_command(config, command, runner=runner)
    except UnsupportedCommand as exc:
        result = {
            "ok": False,
            "status": "failed",
            "error": "unsupported_command",
            "detail": str(exc),
            "kind": kind,
            "command_id": command_id,
        }
    except Exception as exc:  # noqa: BLE001
        result = {
            "ok": False,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "kind": kind,
            "command_id": command_id,
        }
    result.setdefault("command_id", command_id)
    result.setdefault("kind", kind)
    state.mark_result(command_id, result)
    return result


# ---------------------------------------------------------------------------
# Long-running loop
# ---------------------------------------------------------------------------

class AgentPoller:
    """Poll loop with network backoff; safe to run in a daemon thread."""

    def __init__(self, config, stop_event=None, runner=None, logger=None,
                 sleep=None):
        self.config = config
        self.stop_event = stop_event or threading.Event()
        self.runner = runner
        self.log = logger or LOG
        self.sleep = sleep or time.sleep
        self._custom_sleep = sleep is not None
        self.thread = None
        self._status_lock = threading.Lock()
        self._status_data = {
            "state": "starting",
            "consecutive_failures": 0,
            "last_error": None,
        }

    def stop(self):
        self._status(state="stopping")
        self.stop_event.set()

    def status(self):
        with self._status_lock:
            return dict(self._status_data)

    def _status(self, **fields):
        with self._status_lock:
            self._status_data.update(fields)
            self._status_data["updated"] = time.time()
            data = dict(self._status_data)
        data.update({
            "version": STATE_VERSION,
            "customer_id": self.config.customer_id,
            "control_url": self.config.control_url,
            "pid": os.getpid(),
            "thread": threading.current_thread().name,
        })
        try:
            _write_json_atomic(self.config.status_path, data)
        except OSError as exc:
            self.log.warning("could not write agentpoll status: %s", exc)

    def _note_error(self, state, exc):
        with self._status_lock:
            failures = int(self._status_data.get("consecutive_failures") or 0) + 1
        self._status(
            state=state,
            last_error=f"{type(exc).__name__}: {exc}",
            last_error_at=time.time(),
            consecutive_failures=failures,
        )

    def _flush_pending(self):
        state = _state_for(self.config)
        for command_id, entry in state.pending():
            command = {
                "command_id": command_id,
                "kind": entry.get("kind"),
            }
            try:
                post_result(self.config, command, entry.get("result") or {})
                state.mark_posted(command_id)
            except ControlPlaneError as exc:
                self.log.warning("pending result %s not posted yet: %s", command_id, exc)
                return

    def run_once(self):
        """One poll/execute/post cycle. Returns the command result or None."""
        self._flush_pending()
        try:
            command = poll_once(self.config)
        except Exception as exc:  # noqa: BLE001 - record before re-raising
            self._note_error("poll_error", exc)
            raise
        if not command:
            self._status(state="idle", last_poll_at=time.time(),
                         last_error=None, consecutive_failures=0)
            return None
        command_id = command.get("command_id") or command.get("id")
        kind = normalize_kind(command.get("kind"))
        self.log.info("command %s received: %s", command_id, kind)
        self._status(state="executing", last_poll_at=time.time(),
                     last_command_id=command_id,
                     last_command_kind=kind,
                     last_error=None, consecutive_failures=0)
        result = process_command(self.config, command, runner=self.runner)
        if result.get("status") == "running" and result.get("replayed"):
            # Another worker owns this command; never overwrite its running
            # state with a synthetic failure.
            return result
        state = _state_for(self.config)
        try:
            post_result(self.config, command, result)
            state.mark_posted(command_id)
            self._status(state="idle", last_result_at=time.time(),
                         last_result_status=result.get("status"))
        except ControlPlaneError as exc:
            self.log.warning("result %s kept for retry: %s", command_id, exc)
            self._note_error("result_post_error", exc)
        return result

    def _worker_channels(self):
        """Enabled Douyin channels on this machine; one worker each."""
        try:
            from .platforms import load_registry
            _envs, channels = load_registry(_layout(self.config))
        except Exception as exc:  # noqa: BLE001 - never block the poller
            self.log.warning("channel registry unavailable: %s", exc)
            return []
        out = []
        for channel in channels:
            if not getattr(channel, "enabled", True):
                continue
            platform = str(getattr(channel, "platform", "") or "")
            if platform and platform != "douyin":
                # Only Douyin has a real publish driver; other platforms would
                # poll forever for commands they can never execute.
                continue
            channel_id = str(getattr(channel, "channel_id", "") or "")
            if channel_id:
                out.append(channel_id)
        return out

    def run(self):
        """Run one worker per publish channel when several are configured."""
        channels = self._worker_channels()
        if len(channels) <= 1:
            return self._run_single()
        layout = _layout(self.config)
        self._status(state="starting", channels=channels)
        try:
            layout.ensure()
        except OSError as exc:
            self.log.error("cannot create customer data area %s: %s",
                           layout.root, exc)
        self.log.info(
            "agent poller started customer=%s control=%s channels=%s",
            self.config.customer_id, self.config.control_url,
            ",".join(channels))
        workers = []
        for index, channel in enumerate(channels):
            thread = threading.Thread(
                target=self._channel_loop, args=(channel, index == 0),
                name="winport-agentpoll-" + channel.replace(":", "-"),
                daemon=True)
            thread.start()
            workers.append(thread)
        try:
            while not self.stop_event.is_set():
                if not any(thread.is_alive() for thread in workers):
                    self.log.error("all channel workers exited; stopping")
                    break
                self._wait(2.0)
        finally:
            self._status(state="stopped", stopped_at=time.time())

    def _channel_loop(self, channel, is_default):
        """Poll and execute the commands belonging to one channel."""
        delay = max(1.0, self.config.poll_interval)
        while not self.stop_event.is_set():
            try:
                self._flush_pending()
                command = poll_once(self.config, channel=channel,
                                    include_unaddressed=is_default)
            except AuthError as exc:
                self.log.error("authentication failed (%s): %s", channel, exc)
                self._note_error("auth_error", exc)
                self._wait(delay)
                delay = next_backoff(delay, self.config.poll_interval,
                                     self.config.max_backoff)
                continue
            except Exception as exc:  # noqa: BLE001
                self.log.warning("poll failed (%s): %s; retry in %.0fs",
                                 channel, exc, delay)
                self._note_error("poll_error", exc)
                self._wait(delay)
                delay = next_backoff(delay, self.config.poll_interval,
                                     self.config.max_backoff)
                continue
            delay = max(1.0, self.config.poll_interval)
            self._status(state="polling", channel=channel,
                         last_poll_at=time.time(), last_error=None,
                         consecutive_failures=0)
            if not command:
                self._wait(self.config.poll_interval)
                continue
            command_id = command.get("command_id") or command.get("id")
            kind = normalize_kind(command.get("kind"))
            self.log.info("command %s received on %s: %s",
                          command_id, channel, kind)
            self._status(state="executing", channel=channel,
                         last_command_id=command_id, last_command_kind=kind)
            try:
                result = process_command(self.config, command,
                                         runner=self.runner)
                if result.get("status") == "running" and result.get("replayed"):
                    continue
                state = _state_for(self.config)
                try:
                    post_result(self.config, command, result)
                    state.mark_posted(command_id)
                    self._status(state="polling", channel=channel,
                                 last_result_at=time.time(),
                                 last_result_status=result.get("status"))
                except ControlPlaneError as exc:
                    self.log.warning("result %s kept for retry: %s",
                                     command_id, exc)
                    self._note_error("result_post_error", exc)
            except UnsupportedCommand as exc:
                self.log.warning("ignored unsupported command: %s", exc)
                self._status(state="unsupported_command", channel=channel,
                             last_error=str(exc))
            except Exception as exc:  # noqa: BLE001
                self.log.exception("command processing failed: %s", exc)
                self._note_error("command_error", exc)

    def _run_single(self):
        self._status(state="starting")
        layout = _layout(self.config)
        try:
            layout.ensure()
        except OSError as exc:
            self.log.error("cannot create customer data area %s: %s", layout.root, exc)
            self._status(state="startup_error",
                         last_error=f"{type(exc).__name__}: {exc}")
        delay = max(1.0, self.config.poll_interval)
        self.log.info(
            "agent poller started customer=%s control=%s interval=%ss",
            self.config.customer_id,
            self.config.control_url,
            self.config.poll_interval,
        )
        try:
            while not self.stop_event.is_set():
                try:
                    self._flush_pending()
                    command = poll_once(self.config)
                except AuthError as exc:
                    self.log.error("authentication failed: %s", exc)
                    self._note_error("auth_error", exc)
                    self._wait(delay)
                    delay = next_backoff(delay, self.config.poll_interval,
                                         self.config.max_backoff)
                    continue
                except (ControlPlaneError, Exception) as exc:  # noqa: BLE001
                    self.log.warning("poll failed: %s; retry in %.0fs", exc, delay)
                    self._note_error("poll_error", exc)
                    self._wait(delay)
                    delay = next_backoff(delay, self.config.poll_interval,
                                         self.config.max_backoff)
                    continue

                delay = max(1.0, self.config.poll_interval)
                self._status(state="polling", last_poll_at=time.time(),
                             last_error=None, consecutive_failures=0)
                if command:
                    command_id = command.get("command_id") or command.get("id")
                    kind = normalize_kind(command.get("kind"))
                    self.log.info("command %s received: %s", command_id, kind)
                    self._status(state="executing", last_command_id=command_id,
                                 last_command_kind=kind)
                    try:
                        result = process_command(self.config, command,
                                                 runner=self.runner)
                        if result.get("status") == "running" and result.get("replayed"):
                            continue
                        state = _state_for(self.config)
                        try:
                            post_result(self.config, command, result)
                            state.mark_posted(command_id)
                            self._status(
                                state="polling",
                                last_result_at=time.time(),
                                last_result_status=result.get("status"),
                            )
                        except ControlPlaneError as exc:
                            self.log.warning(
                                "result %s kept for retry: %s",
                                command_id, exc,
                            )
                            self._note_error("result_post_error", exc)
                    except UnsupportedCommand as exc:
                        self.log.warning("ignored unsupported command: %s", exc)
                        self._status(state="unsupported_command",
                                     last_error=str(exc))
                    except Exception as exc:  # noqa: BLE001
                        self.log.exception("command processing failed: %s", exc)
                        self._note_error("command_error", exc)
                    continue
                self._wait(self.config.poll_interval)
        finally:
            self._status(state="stopped", stopped_at=time.time())

    def _wait(self, seconds):
        # Event.wait makes shutdown immediate; tests can inject a no-op sleep.
        if self._custom_sleep:
            self.sleep(seconds)
        elif hasattr(self.stop_event, "wait"):
            self.stop_event.wait(seconds)
        else:
            self.sleep(seconds)

    def start(self):
        if self.thread and self.thread.is_alive():
            return self.thread
        self.thread = threading.Thread(target=self._run_guarded,
                                       name="winport-agentpoll", daemon=True)
        self.thread.start()
        return self.thread

    def _run_guarded(self):
        try:
            self.run()
        except Exception as exc:  # noqa: BLE001 - must leave a visible marker
            self.log.exception("agent poller stopped unexpectedly: %s", exc)
            self._status(state="fatal", fatal=True,
                         last_error=f"{type(exc).__name__}: {exc}",
                         last_error_at=time.time())


def start_background(config=None, **kwargs):
    """Convenience entry point for ``main.py``/panel startup."""
    poller = AgentPoller(
        config or AgentConfig.from_env(require_explicit_control_url=True),
        **kwargs)
    poller.start()
    return poller


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _configure_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="WinPort multitenant control-plane poller")
    parser.add_argument("--customer-id", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--control-url", default=None)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--interval", type=float, default=None)
    parser.add_argument("--once", action="store_true", help="poll one cycle and exit")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)
    overrides = {}
    if args.customer_id:
        overrides["customer_id"] = args.customer_id
    if args.token:
        overrides["token"] = args.token
    if args.control_url:
        overrides["control_url"] = args.control_url
    if args.data_root:
        overrides["data_root"] = args.data_root
    if args.interval is not None:
        overrides["poll_interval"] = args.interval
    try:
        config = AgentConfig.from_env(**overrides)
    except ValueError as exc:
        parser.error(str(exc))
    if not config.token:
        parser.error("CUSTOMER_TOKEN (or --token) is required")
    if args.once:
        result = AgentPoller(config).run_once()
        print(json.dumps(result or {"command": None}, ensure_ascii=False, indent=2))
        return 0
    AgentPoller(config)._run_guarded()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# Compatibility aliases
# ---------------------------------------------------------------------------

ALLOWED_COMMANDS = ALLOWED_KINDS
WHITELIST = ALLOWED_KINDS
POLL_INTERVAL = DEFAULT_POLL_INTERVAL
AGENT_POLL_INTERVAL = DEFAULT_POLL_INTERVAL
poll = poll_once
execute = execute_command
report_result = post_result
