from __future__ import annotations

import multiprocessing
import os
import subprocess
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


os.environ.setdefault(
    "XG_FACTORY_SESSION_SECRET", "test-session-secret-must-be-at-least-32-bytes"
)

from app.state_store import StateStore
from app.media_runtime import _single_thread_command, media_slot
from app.worker import DurableWorker


def _claim_attempt_in_process(
    db_path: str,
    owner: str,
    ready_queue,
    start_event,
    result_queue,
) -> None:
    """Spawn-safe worker used to exercise SQLite claiming across OS processes."""
    try:
        store = StateStore(db_path)
        ready_queue.put((owner, os.getpid()))
        if not start_event.wait(10):
            result_queue.put((owner, None, os.getpid(), "start timeout"))
            return
        attempt = store.claim_attempt(owner, 120)
        result_queue.put(
            (owner, attempt["id"] if attempt else None, os.getpid(), None)
        )
    except BaseException as exc:
        result_queue.put((owner, None, os.getpid(), repr(exc)))


def _run_ffmpeg_in_shared_slot(
    lock_dir: str,
    worker_no: int,
    ready_queue,
    start_event,
    event_queue,
    result_queue,
    active,
    max_active,
    counter_lock,
) -> None:
    """Run a real ffmpeg process while holding one cross-process media slot."""
    ready_queue.put((worker_no, os.getpid()))
    if not start_event.wait(10):
        result_queue.put((worker_no, os.getpid(), "start timeout"))
        return
    error = None
    try:
        with media_slot(Path(lock_dir), slots=2):
            with counter_lock:
                active.value += 1
                max_active.value = max(max_active.value, active.value)
            acquired_at = time.monotonic()
            event_queue.put(("acquired", worker_no, acquired_at, os.getpid()))

            # Keep both initial slots occupied before either command can finish.
            deadline = time.monotonic() + 5
            while active.value < 2 and time.monotonic() < deadline:
                time.sleep(0.01)

            try:
                subprocess.run(
                    _single_thread_command([
                        "ffmpeg", "-v", "error", "-re", "-f", "lavfi",
                        "-i", "color=c=black:s=16x16:r=10:d=0.6",
                        "-f", "null", "-",
                    ]),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                )
            finally:
                with counter_lock:
                    active.value -= 1
                event_queue.put(
                    ("released", worker_no, time.monotonic(), os.getpid())
                )
    except BaseException as exc:
        error = repr(exc)
    finally:
        result_queue.put((worker_no, os.getpid(), error))


class MultiInstanceStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="factory-concurrency-")
        self.root = Path(self.temp.name)
        self.db = self.root / "platform.sqlite3"
        self.store = StateStore(self.db)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_project(self, project_id: str) -> None:
        self.store.create_project(
            project_id,
            project_id,
            self.root / "projects" / project_id,
            {
                "name": project_id,
                "stores": [{"store_id": "store_main", "display_name": project_id}],
                "offers": [],
                "industry_path": "catering/hotpot",
            },
            {"show_process": "full"},
        )

    def test_independent_instances_claim_each_attempt_once(self) -> None:
        expected = set()
        for index in range(20):
            project_id = f"prj_{index:02d}"
            self.create_project(project_id)
            expected.add(
                self.store.enqueue_node(
                    project_id,
                    "BUSINESS_DIAGNOSIS",
                    f"cyc_{project_id}",
                    f"piece_{project_id}",
                    {"source": "concurrency-test"},
                )
            )

        def drain(owner: str) -> list[str]:
            local = StateStore(self.db)
            claimed: list[str] = []
            while True:
                attempt = local.claim_attempt(owner, 120)
                if attempt is None:
                    return claimed
                claimed.append(attempt["id"])
                self.assertTrue(
                    local.finish_attempt(
                        attempt["id"], True, lease_owner=owner,
                        usage={"test": True},
                    )
                )

        with ThreadPoolExecutor(max_workers=4) as pool:
            batches = list(pool.map(drain, [f"owner-{index}" for index in range(4)]))

        actual = [attempt_id for batch in batches for attempt_id in batch]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(set(actual)))

    def test_four_processes_claim_without_duplicate_attempts(self) -> None:
        expected: set[str] = set()
        for index in range(4):
            project_id = f"prj_process_{index}"
            self.create_project(project_id)
            expected.add(
                self.store.enqueue_node(
                    project_id,
                    "BUSINESS_DIAGNOSIS",
                    f"cyc_{project_id}",
                    f"piece_{project_id}",
                    {"source": "multiprocessing-claim-test"},
                )
            )

        context = multiprocessing.get_context("spawn")
        ready_queue = context.Queue()
        result_queue = context.Queue()
        start_event = context.Event()
        processes = [
            context.Process(
                target=_claim_attempt_in_process,
                args=(
                    str(self.db),
                    f"process-owner-{index}",
                    ready_queue,
                    start_event,
                    result_queue,
                ),
            )
            for index in range(4)
        ]

        try:
            for process in processes:
                process.start()
            ready = [ready_queue.get(timeout=15) for _ in processes]
            self.assertEqual(len({pid for _, pid in ready}), 4)
            start_event.set()
            results = [result_queue.get(timeout=15) for _ in processes]
        finally:
            start_event.set()
            for process in processes:
                process.join(timeout=10)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)

        self.assertEqual([process.exitcode for process in processes], [0] * 4)
        self.assertEqual([error for *_, error in results], [None] * 4)
        claimed = [attempt_id for _, attempt_id, _, _ in results]
        self.assertEqual(set(claimed), expected)
        self.assertEqual(len(claimed), len(set(claimed)))

    def test_concurrent_audit_writes_keep_one_hash_chain(self) -> None:
        project_id = "prj_audit"
        self.create_project(project_id)

        def append_batch(worker_no: int) -> None:
            local = StateStore(self.db)
            for event_no in range(10):
                local.audit(
                    project_id,
                    f"worker-{worker_no}",
                    "system",
                    "concurrency_test",
                    str(event_no),
                    {"worker": worker_no, "event": event_no},
                )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(append_batch, range(8)))

        self.assertTrue(self.store.verify_audit(project_id))
        self.assertEqual(len(self.store.audit_events(project_id)), 81)
        ledger = self.root / "projects" / project_id / "event_ledger.jsonl"
        self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 81)

    def test_stale_lease_owner_cannot_finish_reclaimed_attempt(self) -> None:
        project_id = "prj_lease"
        self.create_project(project_id)
        attempt_id = self.store.enqueue_node(
            project_id,
            "BUSINESS_DIAGNOSIS",
            f"cyc_{project_id}",
            f"piece_{project_id}",
            {"source": "lease-test"},
        )
        first = self.store.claim_attempt("owner-old", 30)
        self.assertEqual(first["id"], attempt_id)
        with self.store._connect() as conn:
            conn.execute(
                "UPDATE run_attempts SET lease_expires_at='2000-01-01T00:00:00.000000Z' WHERE id=?",
                (attempt_id,),
            )
        self.assertEqual(self.store.reconcile_attempts(), 1)
        second = self.store.claim_attempt("owner-new", 30)
        self.assertEqual(second["id"], attempt_id)
        self.assertFalse(
            self.store.finish_attempt(attempt_id, True, lease_owner="owner-old")
        )
        self.assertTrue(
            self.store.finish_attempt(attempt_id, True, lease_owner="owner-new")
        )

    def test_sqlite_connections_share_wal_and_required_pragmas(self) -> None:
        relative_alias = self.root / "nested" / ".." / "platform.sqlite3"
        alias = StateStore(relative_alias)
        self.assertEqual(alias.db_path, self.store.db_path)
        with alias._connect() as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
            self.assertEqual(conn.execute("PRAGMA synchronous").fetchone()[0], 1)

    def test_rate_limit_is_shared_by_independent_instances(self) -> None:
        stores = [self.store, StateStore(self.db)]

        def consume(index: int) -> bool:
            return stores[index % 2].consume_rate_limit(
                "login:shared-client", 5, 60, now=1000.0
            )

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(consume, range(20)))
        self.assertEqual(sum(results), 5)

    def test_remote_polling_does_not_block_main_worker_loop(self) -> None:
        started = threading.Event()
        release = threading.Event()

        class EmptyStore:
            def reconcile_attempts(self):
                return 0

            def claim_attempt(self, *_):
                return None

        worker = DurableWorker(EmptyStore(), object(), poll_seconds=0.01)

        def blocking_poll() -> None:
            started.set()
            release.wait(2)

        worker.set_remote_poller(blocking_poll)
        worker.start()
        try:
            self.assertTrue(started.wait(1))
            before = time.monotonic()
            self.assertFalse(worker.run_once())
            self.assertLess(time.monotonic() - before, 0.2)
        finally:
            release.set()
            worker.stop()

    def test_ffmpeg_command_is_limited_to_one_thread(self) -> None:
        command = _single_thread_command(["ffmpeg", "-y", "-i", "in.mp4", "out.mp4"])
        self.assertEqual(command[-7:-1], [
            "-threads", "1", "-filter_threads", "1", "-filter_complex_threads", "1"
        ])

    def test_three_ffmpeg_processes_share_only_two_slots(self) -> None:
        context = multiprocessing.get_context("spawn")
        ready_queue = context.Queue()
        event_queue = context.Queue()
        result_queue = context.Queue()
        start_event = context.Event()
        active = context.Value("i", 0, lock=False)
        max_active = context.Value("i", 0, lock=False)
        counter_lock = context.Lock()
        processes = [
            context.Process(
                target=_run_ffmpeg_in_shared_slot,
                args=(
                    str(self.store.lock_dir),
                    index,
                    ready_queue,
                    start_event,
                    event_queue,
                    result_queue,
                    active,
                    max_active,
                    counter_lock,
                ),
            )
            for index in range(3)
        ]

        try:
            for process in processes:
                process.start()
            ready = [ready_queue.get(timeout=15) for _ in processes]
            self.assertEqual(len({pid for _, pid in ready}), 3)
            start_event.set()
            events = [event_queue.get(timeout=20) for _ in range(6)]
            results = [result_queue.get(timeout=20) for _ in processes]
        finally:
            start_event.set()
            for process in processes:
                process.join(timeout=10)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)

        self.assertEqual([process.exitcode for process in processes], [0] * 3)
        self.assertEqual([error for _, _, error in results], [None] * 3)
        self.assertEqual(max_active.value, 2)
        acquired = sorted(
            (event for event in events if event[0] == "acquired"),
            key=lambda event: event[2],
        )
        released = sorted(
            (event for event in events if event[0] == "released"),
            key=lambda event: event[2],
        )
        self.assertEqual(len(acquired), 3)
        self.assertEqual(len(released), 3)
        self.assertEqual(
            sum(event[2] < released[0][2] for event in acquired),
            2,
            "the third ffmpeg task must wait until an initial slot is released",
        )


if __name__ == "__main__":
    unittest.main()

# EXECUTOR: codex
