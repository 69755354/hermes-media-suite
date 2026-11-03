"""Startup lock + foreground feedback (Windows plan section 4.2).

Two layers, same as Mac:
  run/agent.lock        -> only one main process
  run/one-browser.lock  -> only one browser per profile

If the lock is held we do NOT exit silently: the existing window is brought
forward (Mac parity: osascript activate), so "I clicked and nothing happened"
never occurs.
"""

from __future__ import annotations

from . import focus
from .lock import FileLock, lock_is_held


class InstanceGuard:
    def __init__(self, layout, logger=None):
        self.layout = layout
        self.logger = logger
        self._lock = FileLock(layout.agent_lock)

    def already_running(self) -> bool:
        return lock_is_held(self.layout.agent_lock)

    def acquire(self, timeout=0.0) -> bool:
        return self._lock.acquire(timeout=timeout)

    def release(self) -> None:
        self._lock.release()

    def start_or_focus(self) -> dict:
        """Returns {'started': bool, 'focused': bool, 'reason': str}."""
        if self._lock.acquire():
            return {"started": True, "focused": False, "reason": "lock acquired"}
        result = focus.focus_existing()
        if self.logger:
            self.logger.info("instance already running; focus=%s", result)
        return {"started": False, "focused": result.get("focused", False),
                "reason": result.get("reason", "already running")}


class EnvironmentLease:
    """Single-instance lease for one ENVIRONMENT (source/env-design.md rule 1).

    Same advisory-file-lock mechanics as the agent / browser locks, but keyed by
    ``run/envs/<env_id>.lease`` so two environments never block each other while
    one environment can never start a second instance.
    """

    def __init__(self, layout, env_id, logger=None):
        self.layout = layout
        self.env_id = env_id
        self.logger = logger
        path = layout.env_lease_dir / f"{env_id}.lease"
        self._lock = FileLock(path)

    @property
    def path(self):
        return self._lock.path

    def held(self) -> bool:
        return lock_is_held(self._lock.path)

    def acquire(self, timeout=0.0) -> bool:
        return self._lock.acquire(timeout=timeout)

    def release(self) -> None:
        self._lock.release()


class BrowserLease:
    """Single-browser lock for one profile (Mac parity: run/one-browser.lock)."""

    def __init__(self, layout, profile_dir, logger=None):
        self.layout = layout
        self.profile_dir = profile_dir
        self.logger = logger
        self._lock = FileLock(layout.one_browser_lock)

    def acquire(self) -> bool:
        from . import proc
        if proc.is_profile_in_use(self.profile_dir):
            return False
        return self._lock.acquire()

    def release(self) -> None:
        self._lock.release()
