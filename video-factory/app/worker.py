"""SQLite lease 驱动、可多进程并行的 durable worker。"""
# > 执行者：codex

from __future__ import annotations

import threading
import time
import uuid
from typing import Callable

from .orchestrator import Orchestrator
from .state_store import StateStore


class DurableWorker:
    def __init__(
        self,
        store: StateStore,
        orchestrator: Orchestrator,
        poll_seconds: float = 0.5,
        *,
        lease_seconds: int = 120,
        reconcile_seconds: int = 30,
    ):
        self.store = store
        self.orchestrator = orchestrator
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = max(5.0, lease_seconds / 3)
        self.reconcile_seconds = reconcile_seconds
        self.owner = "worker_" + uuid.uuid4().hex[:12]
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._remote_poller: Callable[[], None] | None = None
        self._remote_wake = threading.Event()
        self._remote_thread: threading.Thread | None = None
        self._last_reconcile = 0.0

    def set_remote_poller(self, poller: Callable[[], None]) -> None:
        self._remote_poller = poller
        if self._thread and self._thread.is_alive():
            self._start_remote_thread()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.store.reconcile_attempts()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self.owner, daemon=True)
        self._thread.start()
        self._start_remote_thread()

    def _start_remote_thread(self) -> None:
        if self._remote_poller is None:
            return
        if self._remote_thread and self._remote_thread.is_alive():
            return
        self._remote_thread = threading.Thread(
            target=self._run_remote_polling,
            name=f"{self.owner}_remote_poll",
            daemon=True,
        )
        self._remote_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._remote_wake.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._remote_thread:
            self._remote_thread.join(timeout=5)

    def wake(self) -> None:
        self._wake.set()

    def wake_remote(self) -> None:
        """非阻塞唤醒远程轮询线程；HTTP 请求不执行实际轮询。"""
        self._remote_wake.set()

    def run_once(self) -> bool:
        now = time.monotonic()
        if now - self._last_reconcile >= self.reconcile_seconds:
            self._last_reconcile = now
            self.store.reconcile_attempts()
        attempt = self.store.claim_attempt(self.owner, self.lease_seconds)
        if not attempt:
            return False
        attempt["lease_owner"] = self.owner
        if not self.store.heartbeat_attempt(
            attempt["id"], self.owner, self.lease_seconds
        ):
            return False
        finished = threading.Event()

        def heartbeat() -> None:
            while not finished.wait(self.heartbeat_seconds):
                try:
                    if not self.store.heartbeat_attempt(
                        attempt["id"], self.owner, self.lease_seconds
                    ):
                        return
                except Exception:
                    # 短暂写锁竞争由下一轮续租恢复；租约到期后状态层会拒绝旧 owner 收尾。
                    continue

        heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"{self.owner}_heartbeat",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            self.orchestrator.execute_attempt(attempt)
        except Exception:
            # 状态已经由编排器写入；worker 继续处理下一项。
            pass
        finally:
            finished.set()
            heartbeat_thread.join(timeout=1)
        return True

    def _run_remote_polling(self) -> None:
        while not self._stop.is_set():
            poller = self._remote_poller
            if poller is not None:
                try:
                    poller()
                except Exception:
                    # 状态端抖动不得终止本地任务 worker；下轮继续轮询。
                    pass
            self._remote_wake.wait(5)
            self._remote_wake.clear()

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self.run_once():
                self._wake.wait(self.poll_seconds)
                self._wake.clear()
