from __future__ import annotations
# > 执行者：codex

import hashlib
import os
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("XG_FACTORY_OPS_PASSWORD", "ops-test-password")
os.environ.setdefault("XG_FACTORY_SESSION_SECRET", "test-session-secret-must-be-at-least-32-bytes")

from app.billing import BillingClient
from app.main import create_app
from tests.test_p1_platform import FakeBillingClient, deterministic_reasoner, hotpot_payload


class BillingAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="billing-alignment-")
        root = Path(self.tmp.name)
        self.billing = FakeBillingClient({101: "5000.00", 303: "0.00", 404: "600.00", 505: "700.00"})
        self.app = create_app(
            root / "platform.sqlite3",
            root / "projects",
            reasoner=deterministic_reasoner,
            start_worker=False,
            billing_client=self.billing,
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def enter(self, customer_id: int) -> dict:
        response = self.client.post("/api/v1/billing/access", json={"customer_id": str(customer_id)})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def create_project(self, csrf: str, key: str = "billing-create-project") -> str:
        response = self.client.post(
            "/api/v1/projects",
            json=hotpot_payload(),
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["estimated_points"], "750.00")
        return response.json()["project_id"]

    def test_zero_or_unknown_customer_cannot_enter(self) -> None:
        zero = self.client.post("/api/v1/billing/access", json={"customer_id": "303"})
        self.assertEqual(zero.status_code, 403, zero.text)
        self.assertIn("积分余额为0", zero.json()["message"])
        unknown = self.client.post("/api/v1/billing/access", json={"customer_id": "999"})
        self.assertEqual(unknown.status_code, 403, unknown.text)

    def test_billing_low_balance_warning_is_shown_below_initial_thirty_percent(self) -> None:
        original = self.billing.balance_with_alerts
        self.billing.balance_with_alerts = lambda customer_id: {
            **self.billing.balance(customer_id),
            "low_balance": {"warning": True, "ratio": "0.30"},
            "alerts": [{"type": "low_balance"}],
        }
        try:
            self.enter(101)
            page = self.client.get("/projects")
            self.assertEqual(page.status_code, 200, page.text)
            self.assertIn("积分已低于初始额度的 30%", page.text)
        finally:
            self.billing.balance_with_alerts = original

    def test_balance_plus_overdraft_limit_is_checked_before_task(self) -> None:
        csrf = self.enter(404)["csrf"]
        blocked = self.client.post(
            "/api/v1/projects",
            json=hotpot_payload(),
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": "billing-insufficient"},
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertEqual(self.billing.tasks, {})

        second = TestClient(self.app)
        allowed_access = second.post("/api/v1/billing/access", json={"customer_id": "505"})
        self.assertEqual(allowed_access.status_code, 200, allowed_access.text)
        allowed = second.post(
            "/api/v1/projects",
            json=hotpot_payload(),
            headers={"X-CSRF-Token": allowed_access.json()["csrf"], "Idempotency-Key": "billing-overdraft-allowed"},
        )
        self.assertEqual(allowed.status_code, 201, allowed.text)

    def test_generation_success_settles_and_deducts_once(self) -> None:
        access = self.enter(101)
        project_id = self.create_project(access["csrf"])
        project = self.app.state.store.get_project(project_id)
        source = Path(project["project_dir"]) / "assets" / "billing-source.mp4"
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=360x640:r=25:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
            capture_output=True,
            text=True,
            check=True,
        )
        asset_id = self.app.state.store.add_asset(
            project_id,
            source.name,
            source.name,
            "video/mp4",
            source.stat().st_size,
            hashlib.sha256(source.read_bytes()).hexdigest(),
            "store_main",
        )
        self.app.state.store.verify_authorizations(project_id, "审核员")
        ops = self.client.post(
            "/api/v1/auth/login",
            json={"account": "审核员", "password": "ops-test-password", "role": "ops"},
        ).json()
        generated = self.client.post(
            f"/internal/v1/projects/{project_id}/media/compose",
            json={"asset_id": asset_id},
            headers={"X-CSRF-Token": ops["csrf"]},
        )
        self.assertEqual(generated.status_code, 200, generated.text)
        self.assertEqual(generated.json()["billing_status"], "settled")
        self.assertEqual(self.billing.balance(101)["balance"], "4250.00")
        self.assertEqual(self.app.state.store.project_billing(project_id)["status"], "settled")

    def test_delivery_is_blocked_until_settled_then_consumes_remote_gate(self) -> None:
        access = self.enter(101)
        project_id = self.create_project(access["csrf"], "billing-delivery-project")
        project = self.app.state.store.get_project(project_id)
        target = Path(project["project_dir"]) / "delivery" / f"{project_id}_交付资料包.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PK\x03\x04billing-delivery-test")
        self.app.state.store.add_internal_review(
            project_id,
            "G_DELIVERY_READY",
            "ALLOWED",
            "审核员",
            str(target),
            "ALLOWED",
            piece_id=project["piece"]["id"],
        )
        blocked = self.client.get(f"/api/v1/projects/{project_id}/delivery")
        self.assertEqual(blocked.status_code, 409, blocked.text)

        row = self.app.state.store.project_billing(project_id)
        self.billing.settle(row["billing_task_id"])
        ready = self.client.get(f"/api/v1/projects/{project_id}/delivery")
        self.assertEqual(ready.status_code, 200, ready.text)
        downloaded = self.client.get(ready.json()["items"][0]["download_url"])
        self.assertEqual(downloaded.status_code, 200, downloaded.text)
        updated = self.app.state.store.project_billing(project_id)
        self.assertEqual(updated["status"], "delivered")
        self.assertTrue(self.billing.deliveries[updated["delivery_id"]]["used"])

    def test_billing_client_repeated_settle_skips_second_post(self) -> None:
        calls: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.method == "GET":
                return httpx.Response(200, json={
                    "id": 7, "status": "reserved", "estimated": "750.00"
                })
            return httpx.Response(200, json={
                "id": 7,
                "status": "settled",
                "estimated": "750.00",
                "settlement": {"actual": "-750.00"},
            })

        client = BillingClient(
            "http://billing.test",
            auth_token="test-token",
            transport=httpx.MockTransport(handler),
        )
        try:
            first = client.settle(7)
            second = client.settle(7)
        finally:
            client.close()
        self.assertEqual(first, second)
        self.assertEqual(calls, [
            ("GET", "/tasks/7"),
            ("POST", "/tasks/7/settle"),
        ])

    def test_twenty_concurrent_settles_charge_once(self) -> None:
        state = {
            "status": "reserved",
            "balance": Decimal("5000.00"),
        }
        ledger: list[dict[str, object]] = []
        calls: list[tuple[str, str]] = []
        server_lock = threading.Lock()

        def task_payload() -> dict[str, object]:
            settlement = ledger[0] if ledger else None
            return {
                "id": 77,
                "status": state["status"],
                "estimated": "750.00",
                "settlement": settlement,
            }

        def handler(request: httpx.Request) -> httpx.Response:
            with server_lock:
                calls.append((request.method, request.url.path))
                if request.method == "GET":
                    return httpx.Response(200, json=task_payload())
                if state["status"] != "settled":
                    state["balance"] -= Decimal("750.00")
                    state["status"] = "settled"
                    ledger.append({
                        "transaction_id": 10077,
                        "task_id": 77,
                        "actual": "-750.00",
                    })
                return httpx.Response(200, json=task_payload())

        client = BillingClient(
            "http://billing.test",
            auth_token="test-token",
            transport=httpx.MockTransport(handler),
        )
        barrier = threading.Barrier(20)

        def settle_once(_: int) -> dict[str, object]:
            barrier.wait(timeout=5)
            return client.settle(77)

        try:
            with ThreadPoolExecutor(max_workers=20) as pool:
                results = list(pool.map(settle_once, range(20)))
        finally:
            client.close()

        self.assertEqual(len(results), 20)
        self.assertTrue(all(result["status"] == "settled" for result in results))
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["task_id"], 77)
        self.assertEqual(state["balance"], Decimal("4250.00"))
        self.assertEqual(calls.count(("POST", "/tasks/77/settle")), 1)
        self.assertEqual(calls.count(("GET", "/tasks/77")), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# EXECUTOR: codex
