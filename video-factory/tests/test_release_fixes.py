from __future__ import annotations

import ast
import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx


os.environ.setdefault(
    "XG_FACTORY_SESSION_SECRET", "test-session-secret-must-be-at-least-32-bytes"
)

from app import config
from app.billing import BillingClient
from app.main import create_app
from app.state_store import StateStore


class ReleaseFixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="factory-release-fixes-")
        self.root = Path(self.temp.name)
        self.store = StateStore(self.root / "platform.sqlite3")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_project(self, project_id: str = "prj_release") -> None:
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

    def test_async_ops_handlers_offload_blocking_work(self) -> None:
        tree = ast.parse(inspect.getsource(create_app))
        handlers = {
            node.name: ast.get_source_segment(inspect.getsource(create_app), node) or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }
        directly_offloaded = {
            "login",
            "internal_approve",
            "run_node",
            "rollback",
            "internal_confirm",
            "import_insights",
            "compose_media",
            "paid_authorize",
            "internal_update_order",
        }
        for name in directly_offloaded:
            self.assertIn("anyio.to_thread.run_sync", handlers[name], name)
        self.assertIn("await run_node", handlers["retry_node"])

    def test_billing_default_timeout_applies_to_login_and_api_requests(self) -> None:
        observed: list[dict[str, float]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            observed.append(request.extensions["timeout"])
            if request.url.path == "/auth/admin-login":
                return httpx.Response(200, json={"token": "fresh-token"})
            return httpx.Response(
                200, json={"customer_id": 7, "account_id": 8, "balance": "100"}
            )

        client = BillingClient(
            "http://billing.test",
            admin_password="password",
            transport=httpx.MockTransport(handler),
        )
        try:
            client.balance(7)
        finally:
            client.close()

        self.assertEqual(len(observed), 2)
        for timeout in observed:
            self.assertEqual(
                timeout,
                {"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0},
            )

    def test_lock_dir_rejects_blank_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "lock_dir 不能为空"):
            StateStore(self.root / "blank.sqlite3", lock_dir="   ")

    def test_named_locks_use_one_bounded_inode(self) -> None:
        for index in range(500):
            with self.store.interprocess_lock(f"request:{index}") as acquired:
                self.assertTrue(acquired)
        self.assertEqual(
            [path.name for path in self.store.lock_dir.glob("*.lock")],
            ["state-store.lock"],
        )

    def test_audit_default_does_not_fsync_jsonl(self) -> None:
        self.create_project()
        with patch("app.state_store.os.fsync") as fsync:
            self.store.audit(
                "prj_release", "operator", "internal_ops", "checked", "target", {}
            )
        fsync.assert_not_called()

    def test_audit_jsonl_is_written_only_after_database_commit(self) -> None:
        self.create_project()

        def fail_after_observing_commit(_ledger: Path, event: dict[str, object]) -> None:
            with self.store._connect() as conn:
                row = conn.execute(
                    "SELECT action FROM audit_events WHERE project_id=? AND hash=?",
                    ("prj_release", event["hash"]),
                ).fetchone()
            self.assertIsNotNone(row)
            raise OSError("simulated JSONL failure")

        with patch.object(
            self.store, "_append_audit_ledger", side_effect=fail_after_observing_commit
        ):
            with self.assertRaisesRegex(OSError, "simulated JSONL failure"):
                self.store.audit(
                    "prj_release",
                    "operator",
                    "internal_ops",
                    "committed_first",
                    "target",
                    {},
                )

        self.assertTrue(
            any(
                event["action"] == "committed_first"
                for event in self.store.audit_events("prj_release")
            )
        )

    def test_production_concurrency_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XG_FACTORY_WORKER_LEASE_SECONDS", None)
            os.environ.pop("XG_FACTORY_REQUEST_THREADS", None)
            os.environ.pop("XG_FACTORY_BILLING_TIMEOUT", None)
            self.assertEqual(config.worker_lease_seconds(), 600)
            self.assertEqual(config.request_threads(), 24)
            self.assertEqual(config.billing_timeout_seconds(), 10.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# EXECUTOR: codex
