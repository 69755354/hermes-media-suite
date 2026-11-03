from __future__ import annotations
# > 执行者：codex

import json
import io
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from PIL import Image


os.environ.setdefault("XG_FACTORY_OPS_PASSWORD", "ops-test-password")
os.environ.setdefault("XG_FACTORY_SESSION_SECRET", "test-session-secret-must-be-at-least-32-bytes")
os.environ.setdefault("XG_FACTORY_DB", "/tmp/p1-test-import.sqlite3")
os.environ.setdefault("XG_FACTORY_PROJECTS_DIR", "/tmp/p1-test-import-projects")

from app.main import create_app
from app.billing import BillingError


class FakeBillingClient:
    def __init__(self, balances: dict[int, str] | None = None) -> None:
        source = balances or {101: "5000.00", 202: "5000.00", 303: "0.00"}
        self.customers = {
            customer_id: {"customer_id": customer_id, "account_id": customer_id + 1000, "balance": value}
            for customer_id, value in source.items()
        }
        self.tasks: dict[int, dict] = {}
        self.idempotency: dict[str, int] = {}
        self.deliveries: dict[int, dict] = {}
        self.next_task_id = 1
        self.next_delivery_id = 1

    def balance(self, customer_id: int) -> dict:
        if customer_id not in self.customers:
            raise BillingError("not found", status_code=404, detail="customer/account not found")
        return dict(self.customers[customer_id])

    def balance_with_alerts(self, customer_id: int) -> dict:
        result = self.balance(customer_id)
        result["low_balance"] = {"warning": False, "ratio": "0.30"}
        result["alerts"] = []
        return result

    def create_video_task(self, account_id: int, idempotency_key: str) -> dict:
        if idempotency_key in self.idempotency:
            return self.task(self.idempotency[idempotency_key])
        customer = next((row for row in self.customers.values() if row["account_id"] == account_id), None)
        if customer is None:
            raise BillingError("not found", status_code=404)
        if __import__("decimal").Decimal(customer["balance"]) - __import__("decimal").Decimal("750") < -100:
            raise BillingError("insufficient", status_code=409, detail="insufficient available balance")
        task_id = self.next_task_id
        self.next_task_id += 1
        self.idempotency[idempotency_key] = task_id
        self.tasks[task_id] = {
            "id": task_id,
            "account_id": account_id,
            "customer_id": customer["customer_id"],
            "task_type": "video",
            "status": "reserved",
            "estimated": "750.00",
            "settlement": None,
        }
        return self.task(task_id)

    def task(self, task_id: int) -> dict:
        if task_id not in self.tasks:
            raise BillingError("not found", status_code=404)
        return dict(self.tasks[task_id])

    def settle(self, task_id: int) -> dict:
        task = self.tasks[task_id]
        if task["status"] == "settled":
            return self.task(task_id)
        customer = self.customers[task["customer_id"]]
        value = __import__("decimal").Decimal(customer["balance"]) - __import__("decimal").Decimal("750")
        if value < -100:
            raise BillingError("insufficient", status_code=409, detail="overdraft limit is -100.00 points")
        customer["balance"] = f"{value:.2f}"
        task["status"] = "settled"
        task["settlement"] = {"transaction_id": task_id + 10000, "actual": "-750.00"}
        return self.task(task_id)

    def cancel(self, task_id: int, reason: str) -> dict:
        del reason
        self.tasks[task_id]["status"] = "cancelled"
        return self.task(task_id)

    def prepare_delivery(self, task_id: int) -> dict:
        if self.tasks[task_id]["status"] != "settled":
            raise BillingError("not settled", status_code=409, detail="task must be settled before delivery")
        delivery_id = self.next_delivery_id
        self.next_delivery_id += 1
        token = f"delivery-token-{delivery_id}"
        self.deliveries[delivery_id] = {"task_id": task_id, "token": token, "used": False}
        return {"delivery_id": delivery_id, "token": token, "storage_key": f"test/{task_id}"}

    def confirm_delivery(self, delivery_id: int, token: str) -> dict:
        row = self.deliveries[delivery_id]
        if row["token"] != token or row["used"]:
            raise BillingError("invalid delivery", status_code=409)
        row["used"] = True
        return {"ok": True}


def deterministic_reasoner(prompt: str, output: Path, timeout: int) -> str:
    del timeout
    if "只输出 JSON" in prompt:
        result = {
            "candidates": [
                {"id": "v1", "angle": "工艺", "script": "这口锅底每天认真准备，先看真实炒制过程，再看双人套餐里的菜品。两个人下班后来，按门店当天实际供应点单。镜头只使用已授权的锅底、菜品与服务过程素材，价格和有效期都以已经核验的信息为准。"},
                {"id": "v2", "angle": "套餐", "script": "两个人吃火锅，点什么总要纠结。把锅底、荤菜和素菜按真实套餐摆出来，先看清分量，再决定是否到店。双人堂食套餐已经登记，具体菜品、价格、有效期和当天供应，都按门店已经核验的信息为准。"},
                {"id": "v3", "angle": "场景", "script": "下班后想找个地方慢慢吃顿火锅，先看看门店真实环境，再看看锅底和菜品。主推套餐适合两人堂食，门头、菜单和服务过程都用已授权实拍素材呈现，预约、排队和当天供应以门店公开信息为准。"},
            ],
            "titles": ["这口锅底怎么做", "两个人怎么点", "下班后吃火锅"],
            "topics": ["锅底", "套餐", "到店"],
            "source_mapping": [{"source": "门店冻结事实", "usage": "文案事实"}],
        }
        text = json.dumps(result, ensure_ascii=False)
    else:
        text = (
            "> 执行者：codex\n\n# 整体打法\n\n平台组合：短视频同城。\n\n内容配比：工艺、套餐、真实场景。\n\n"
            "阶段节奏：先验证再放大。\n\n投流策略：先核验承接数据。\n\n变现方式：到店获客。\n\n风险边界：不编造数据，不承诺效果。\n\n"
            + "所有动作以门店事实、授权素材和已核验来源为边界。" * 12
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return text


def hotpot_payload() -> dict:
    evidence = [
        {"asset_id": "asset_menu", "evidence_type": "menu_photo", "store_id": "store_main", "rights_confirmed": True},
        {"asset_id": "asset_price", "evidence_type": "price_board_photo", "store_id": "store_main", "rights_confirmed": True},
        {"asset_id": "asset_storefront", "evidence_type": "storefront_photo", "store_id": "store_main", "rights_confirmed": True},
        {"asset_id": "asset_dish", "evidence_type": "dish_photo", "store_id": "store_main", "rights_confirmed": True},
        {"asset_id": "asset_service", "evidence_type": "service_process_photo", "store_id": "store_main", "rights_confirmed": True},
    ]
    return {
        "content_type": "store_visit",
        "industry_path": "catering/hotpot",
        "business_name": "老灶火锅",
        "address": "成都市锦江区示例路 88 号",
        "contact": "028-88888888",
        "signature_item": "手工牛油锅底",
        "selling_points": ["牛油锅底自己炒"],
        "average_spend_fen": 10000,
        "offer": {"name": "双人套餐", "specification": "双人堂食套餐", "amount_fen": 19900},
        "evidence_assets": evidence,
        "content_authorization": {"accepted": True, "portrait_confirmed": False},
        "prefs": {"show_process": "full"},
        "piece_format": "VIDEO_SHORT",
        "platform": "抖音",
    }


def minimal_hotpot_payload() -> dict:
    payload = hotpot_payload()
    payload["evidence_assets"] = [
        {"asset_id": "asset_storefront_1", "evidence_type": "storefront_photo", "store_id": "store_main", "rights_confirmed": True},
        {"asset_id": "asset_product_1", "evidence_type": "product_photo", "store_id": "store_main", "rights_confirmed": True},
    ]
    payload.pop("prefs")
    payload.pop("piece_format")
    payload.pop("platform")
    return payload


def drama_payload() -> dict:
    return {
        "content_type": "drama",
        "industry_path": "catering/hotpot",
        "business_name": "山岚生活馆",
        "address": "杭州市西湖区示例路 18 号",
        "contact": "13800000001",
        "selling_points": ["真实店员故事", "店内场景可拍"],
        "drama_direction": "dual",
        "character_count": 2,
        "evidence_assets": [
            {"asset_id": "asset_drama_scene_1", "evidence_type": "drama_scene_reference", "store_id": "store_main", "rights_confirmed": True}
        ],
        "content_authorization": {"accepted": True, "portrait_confirmed": False},
    }


def oral_payload() -> dict:
    return {
        "content_type": "oral",
        "industry_path": "catering/hotpot",
        "business_name": "山岚生活馆",
        "address": "杭州市西湖区示例路 18 号",
        "contact": "13800000001",
        "selling_points": ["店主亲自讲解"],
        "oral_content_direction": "店主讲创业故事",
        "reference_style": "真诚自然",
        "evidence_assets": [
            {"asset_id": "asset_presenter_1", "evidence_type": "presenter_portrait", "store_id": "store_main", "rights_confirmed": True}
        ],
        "content_authorization": {"accepted": True, "portrait_confirmed": True},
    }


class P1PlatformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="p1-platform-")
        root = Path(self.tmp.name)
        self.billing = FakeBillingClient()
        self.app = create_app(root / "platform.sqlite3", root / "projects", reasoner=deterministic_reasoner, start_worker=False, billing_client=self.billing)
        self.client = TestClient(self.app)
        response = self.client.post("/api/v1/billing/access", json={"customer_id": "101"})
        self.assertEqual(response.status_code, 200, response.text)
        self.client_csrf = response.json()["csrf"]
        response = self.client.post("/api/v1/auth/login", json={"account": "审核员", "password": "ops-test-password", "role": "ops"})
        self.assertEqual(response.status_code, 200, response.text)
        self.ops_csrf = response.json()["csrf"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def create_project(self) -> str:
        response = self.client.post(
            "/api/v1/projects",
            json=hotpot_payload(),
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "create-project-0001"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["project_id"]

    def upload_required_evidence(self, project_id: str) -> None:
        planned = [
            ("asset_menu", "menu_photo"),
            ("asset_price", "price_board_photo"),
            ("asset_storefront", "storefront_photo"),
            ("asset_dish", "dish_photo"),
            ("asset_service", "service_process_photo"),
        ]
        for index, (asset_id, evidence_type) in enumerate(planned):
            buffer = io.BytesIO()
            Image.new("RGB", (32, 32), (40 * index, 80, 120)).save(buffer, format="JPEG")
            response = self.client.post(
                f"/api/v1/projects/{project_id}/assets",
                files={"file": (f"{asset_id}.jpg", buffer.getvalue(), "image/jpeg")},
                data={"store_id": "store_main", "planned_asset_id": asset_id, "evidence_type": evidence_type},
                headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": f"upload-{asset_id}"},
            )
            self.assertEqual(response.status_code, 201, response.text)

    def test_factory_form_loads_without_due_diligence_fields(self) -> None:
        response = self.client.get("/projects/new")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("我同意你们拍摄", response.text)
        self.assertIn("不收集营业执照", response.text)
        self.assertLess(response.text.index("name=\"content_type\""), response.text.index("name=\"industry_path\""))
        self.assertIn("你想做探店视频、剧情类还是口播视频？", response.text)
        self.assertIn("探店视频", response.text)
        self.assertIn("剧情视频", response.text)
        self.assertIn("口播视频", response.text)
        self.assertNotIn("你是实体店还是自媒体", response.text)
        for removed in ('name="qualification"', 'name="sells_alcohol"', 'name="allergen"', 'name="business_exception"'):
            self.assertNotIn(removed, response.text)

    def test_all_enabled_industries_use_ten_or_fewer_required_groups(self) -> None:
        workflow_root = Path(
            os.environ.get(
                "XG_FACTORY_WORKFLOW_ROOT",
                str(next((p for p in Path(__file__).resolve().parents if (p / "wiki" / "spec" / "INDUSTRY_FORM_SCHEMA.yaml").is_file()), Path(__file__).resolve().parents[3])),
            )
        ).resolve()
        schema_path = workflow_root / "wiki" / "spec" / "INDUSTRY_FORM_SCHEMA.yaml"
        contract = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        self.assertLessEqual(len(contract["submission_schema"]["required"]), 10)
        profiles = contract["form_profiles"]
        for parent in contract["industry_taxonomy"]:
            for child in parent.get("children", []):
                if not child.get("enabled"):
                    continue
                profile = profiles[child["form_profile"]]
                self.assertLessEqual(profile["required_field_count"], 10)

    def test_minimal_core_payload_is_accepted(self) -> None:
        response = self.client.post(
            "/api/v1/projects",
            json=minimal_hotpot_payload(),
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "minimal-core-payload"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        project = self.app.state.store.get_project(response.json()["project_id"])
        self.assertEqual(project["name"], "老灶火锅")
        brief = json.loads((Path(project["project_dir"]) / "BRIEF.json").read_text(encoding="utf-8"))
        self.assertNotIn("legal_name", brief["stores"][0])
        self.assertNotIn("sells_alcohol", brief)
        self.assertNotIn("allergen_declarations", brief)

    def test_removed_due_diligence_fields_are_rejected(self) -> None:
        payload = minimal_hotpot_payload()
        payload["sells_alcohol"] = False
        response = self.client.post(
            "/api/v1/projects",
            json=payload,
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "reject-legacy-fields"},
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_content_type_branch_constraints(self) -> None:
        missing_type = minimal_hotpot_payload()
        missing_type.pop("content_type")
        response = self.client.post(
            "/api/v1/projects", json=missing_type,
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "missing-content-type"},
        )
        self.assertEqual(response.status_code, 400, response.text)

        store_missing_product = minimal_hotpot_payload()
        store_missing_product["evidence_assets"] = [store_missing_product["evidence_assets"][0]]
        response = self.client.post(
            "/api/v1/projects", json=store_missing_product,
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "store-missing-product"},
        )
        self.assertEqual(response.status_code, 400, response.text)

        drama_mismatch = drama_payload()
        drama_mismatch["character_count"] = 1
        response = self.client.post(
            "/api/v1/projects", json=drama_mismatch,
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "drama-count-mismatch"},
        )
        self.assertEqual(response.status_code, 400, response.text)

        oral_missing_presenter = oral_payload()
        oral_missing_presenter["evidence_assets"] = []
        response = self.client.post(
            "/api/v1/projects", json=oral_missing_presenter,
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "oral-missing-presenter"},
        )
        self.assertEqual(response.status_code, 400, response.text)

        oral_with_price = oral_payload()
        oral_with_price["average_spend_fen"] = 8800
        response = self.client.post(
            "/api/v1/projects", json=oral_with_price,
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "oral-rejects-price"},
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_project_contract_one_piece_idempotency_and_client_views(self) -> None:
        project_id = self.create_project()
        repeated = self.client.post(
            "/api/v1/projects",
            json=hotpot_payload(),
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "create-project-0001"},
        )
        self.assertEqual(repeated.status_code, 201)
        self.assertEqual(repeated.json()["project_id"], project_id)
        with sqlite3.connect(self.app.state.store.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM pieces WHERE project_id=?", (project_id,)).fetchone()[0], 1)
        views = self.client.get(f"/api/v1/projects/{project_id}/artifacts")
        self.assertEqual(views.status_code, 200)
        self.assertGreaterEqual(len(views.json()["items"]), 2)
        for item in views.json()["items"]:
            detail = self.client.get(f"/api/v1/projects/{project_id}/artifacts/{item['client_view_id']}")
            self.assertEqual(detail.status_code, 200)
            body = detail.text.lower()
            for forbidden in ("/home/ubuntu", "codex", "claude", "deepseek", "执行者", "节点1"):
                self.assertNotIn(forbidden, body)
        hidden_mode = self.client.patch(
            f"/api/v1/projects/{project_id}/preferences",
            json={"show_process": "result_only"},
            headers={"X-CSRF-Token": self.client_csrf},
        )
        self.assertEqual(hidden_mode.status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/projects/{project_id}/artifacts").json()["items"], [])
        self.assertEqual(self.client.get(f"/api/v1/projects/{project_id}/artifacts/D_START_EXECUTION_GUIDE").status_code, 404)

    def test_cross_client_project_is_hidden_as_404(self) -> None:
        project_id = self.create_project()
        other = TestClient(self.app)
        login = other.post("/api/v1/billing/access", json={"customer_id": "202"})
        self.assertEqual(login.status_code, 200)
        hidden = other.get(f"/api/v1/projects/{project_id}/progress")
        self.assertEqual(hidden.status_code, 404)
        listed = other.get("/api/v1/projects")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["items"], [])
        self.assertEqual(other.get("/internal/v1/reviews/pending").status_code, 404)
        self.assertEqual(other.get(f"/api/v1/projects/{project_id}/delivery/not-a-valid-token").status_code, 404)

    def test_gate_token_is_required_and_stale_manifest_is_rejected(self) -> None:
        project_id = self.create_project()
        self.upload_required_evidence(project_id)
        no_token = self.client.post(
            f"/internal/v1/projects/{project_id}/gates/G_PROJECT_AUTHORIZED/approve",
            json={"evidence_artifact_id": "A_PROJECT_CHARTER"},
            headers={"X-CSRF-Token": self.ops_csrf},
        )
        self.assertEqual(no_token.status_code, 400)
        checked = self.client.post(
            f"/internal/v1/projects/{project_id}/gates/G_PROJECT_AUTHORIZED/check",
            headers={"X-CSRF-Token": self.ops_csrf},
        )
        self.assertEqual(checked.status_code, 200, checked.text)
        self.assertEqual(checked.json()["rc"], 3, checked.text)
        project = self.app.state.store.get_project(project_id)
        charter = Path(self.app.state.store.artifact(project_id, "A_PROJECT_CHARTER")["path"])
        charter.write_text(charter.read_text(encoding="utf-8") + "\n审批后变更", encoding="utf-8")
        stale = self.client.post(
            f"/internal/v1/projects/{project_id}/gates/G_PROJECT_AUTHORIZED/approve",
            json={"check_token": checked.json()["check_token"], "evidence_artifact_id": "A_PROJECT_CHARTER"},
            headers={"X-CSRF-Token": self.ops_csrf},
        )
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(stale.json()["rc"], 2, stale.text)

    def test_confirm_protocol_has_three_distinct_decisions_and_no_skip(self) -> None:
        project_id = self.create_project()
        project = self.app.state.store.get_project(project_id)
        self.app.state.store.create_confirmation(project_id, "C1", project["piece"]["id"], None, target_artifact_ids=["A_STORE_FACTS"])
        pause = self.client.post(
            f"/api/v1/projects/{project_id}/confirmations/C1",
            json={"decision": "pause", "revision": 1},
            headers={"X-CSRF-Token": self.client_csrf, "Idempotency-Key": "confirm-pause-0001"},
        )
        self.assertEqual(pause.status_code, 200, pause.text)
        state_path = Path(project["project_dir"]) / "CONFIRM.json"
        if state_path.exists():
            self.assertFalse(json.loads(state_path.read_text(encoding="utf-8")).get("skip_mode", False))
        order = self.app.state.store.order(project_id)
        self.assertEqual(order["revise_used"], 0)

    def test_cancelled_attempt_is_terminal_and_reconcile_is_durable(self) -> None:
        project_id = self.create_project()
        project = self.app.state.store.get_project(project_id)
        store = self.app.state.store
        store.set_node(project_id, "BUSINESS_DIAGNOSIS", project["cycle"]["id"], project["piece"]["id"], "RUNNING")
        store.set_node(project_id, "BUSINESS_DIAGNOSIS", project["cycle"]["id"], project["piece"]["id"], "CANCELLED_BY_CLIENT")
        store.set_node(project_id, "BUSINESS_DIAGNOSIS", project["cycle"]["id"], project["piece"]["id"], "SIGNED_OFF")
        row = next(item for item in store.node_runs(project_id) if item["node_id"] == "BUSINESS_DIAGNOSIS")
        self.assertEqual(row["status"], "CANCELLED_BY_CLIENT")
        self.assertEqual(store.reconcile_attempts(), 0)

    def test_ffmpeg_compose_is_formal_and_mock_cannot_export(self) -> None:
        project_id = self.create_project()
        project = self.app.state.store.get_project(project_id)
        source = Path(project["project_dir"]) / "assets" / "source.mp4"
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=360x640:r=25:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], capture_output=True, text=True, check=True)
        digest = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
        asset_id = self.app.state.store.add_asset(project_id, "source.mp4", source.name, "video/mp4", source.stat().st_size, digest, "store_main")
        self.app.state.store.verify_authorizations(project_id, "审核员")
        output = self.app.state.orchestrator.compose_media(project_id, asset_id)
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 1000)
        self.assertTrue((Path(project["project_dir"]) / "previews" / "C2_low.mp4").is_file())
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1", str(output)], capture_output=True, text=True, check=True)
        self.assertIn("duration=30", probe.stdout)
        mock = output.parent / "fixture_MOCK.mp4"
        mock.write_bytes(output.read_bytes())
        with self.assertRaises(ValueError):
            self.app.state.store.add_artifact(project_id, "A_VIDEO_MASTER", mock, "0" * 64, "D_CYCLE_MEDIA", project["cycle"]["id"], project["piece"]["id"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
