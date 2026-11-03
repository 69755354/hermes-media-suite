#!/usr/bin/env python3
# > 执行者：codex
"""一键跑火锅店 P1 闭环；默认真调本机推理与 ffmpeg。

`--fast` 仅用于代码回归，推理输出会明确使用确定性测试适配器；正式验收不要传。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]
sys.path.insert(0, str(APP_ROOT))


def fast_reasoner(prompt: str, output: Path, timeout: int) -> str:
    del timeout
    if "只输出 JSON" in prompt:
        text = json.dumps(
            {
                "candidates": [
                    {"id": "v1", "angle": "工艺", "script": "这口锅底每天认真准备，先看真实炒制过程，再看双人套餐里的菜品。两个人下班后来，按门店当天实际供应点单。镜头只使用已授权的锅底、菜品与服务过程素材，价格和有效期都以已经核验的信息为准。"},
                    {"id": "v2", "angle": "套餐", "script": "两个人吃火锅，点什么总要纠结。把锅底、荤菜和素菜按真实套餐摆出来，先看清分量，再决定是否到店。双人堂食套餐已经登记，具体菜品、价格、有效期和当天供应，都按门店已经核验的信息为准。"},
                    {"id": "v3", "angle": "场景", "script": "下班后想找个地方慢慢吃顿火锅，先看看门店真实环境，再看看锅底和菜品。主推套餐适合两人堂食，门头、菜单和服务过程都用已授权实拍素材呈现，预约、排队和当天供应以门店公开信息为准。"},
                ],
                "titles": ["这口锅底怎么做", "两个人怎么点", "下班后吃火锅"],
                "topics": ["锅底", "套餐", "到店"],
                "source_mapping": [{"source": "冻结门店事实", "usage": "文案事实"}],
            },
            ensure_ascii=False,
        )
    else:
        text = (
            "> 执行者：codex\n\n# 整体打法\n\n平台组合：短视频同城。\n\n内容配比：工艺、套餐、真实场景。\n\n"
            "阶段节奏：先验证再放大。\n\n投流策略：先核验承接数据。\n\n变现方式：到店获客。\n\n风险边界：不编造数据，不承诺效果。\n\n"
            + "所有动作以门店事实、授权素材和已核验来源为边界。" * 12
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return text


def payload() -> dict:
    booking = {"channel": "phone", "public_value": "028-88888888", "is_public": True}
    evidence = [
        {"asset_id": "asset_menu", "evidence_type": "menu_photo", "store_id": "store_main", "rights_confirmed": True},
        {"asset_id": "asset_price", "evidence_type": "price_board_photo", "store_id": "store_main", "rights_confirmed": True},
        {"asset_id": "asset_storefront", "evidence_type": "storefront_photo", "store_id": "store_main", "rights_confirmed": True},
        {"asset_id": "asset_dish", "evidence_type": "dish_photo", "store_id": "store_main", "rights_confirmed": True},
        {"asset_id": "asset_service", "evidence_type": "service_process_photo", "store_id": "store_main", "rights_confirmed": True},
    ]
    return {
        "industry_path": "catering/hotpot",
        "cuisine_categories": ["川味牛油火锅"],
        "signature_dishes": [{"name": "手工牛油锅底", "category": "锅底", "store_ids": ["store_main"], "evidence_asset_ids": ["asset_dish"]}],
        "average_spend_fen": 10000,
        "average_spend_unknown": False,
        "package_details": [{"name": "双人套餐", "item_lines": [{"item_name": "双人堂食套餐", "quantity": 1, "unit": "份"}], "amount_fen": 19900, "store_ids": ["store_main"], "evidence_asset_ids": ["asset_menu", "asset_price"]}],
        "service_modes": ["dine_in"],
        "business_exceptions": [{"kind": "other", "description": "节假日营业时间以门店公告为准"}],
        "booking_queue_methods": [booking],
        "allergen_declarations": [{"name": "other", "status": "unknown", "affected_items": [], "note": "到店前请询问服务人员"}],
        "sells_alcohol": False,
        "stores": [{"store_id": "store_main", "legal_name": "成都老灶餐饮有限公司", "display_name": "老灶火锅", "address": "成都市示例路 88 号", "city": "成都", "public_booking_methods": [booking], "evidence_asset_ids": ["asset_storefront"]}],
        "offers": [{"offer_id": "offer_main", "name": "双人套餐", "specification": "双人堂食，菜品以门店实际供应为准", "amount_fen": 19900, "valid_from": "2026-08-16T00:00:00+08:00", "valid_to": "2026-12-31T23:59:59+08:00", "store_ids": ["store_main"], "inventory_rule": {"mode": "unlimited", "quantity": None}, "evidence_asset_ids": ["asset_menu", "asset_price"]}],
        "evidence_assets": evidence,
        "offer_intent": {"mode": "selected", "offer_ids": ["offer_main"]},
        "selling_points": ["牛油锅底自己炒"],
        "contacts": {"internal": {"name": "项目联系人", "channel": "028-88888888"}, "public": [booking]},
        "prefs": {"show_process": "full"},
        "authorizations": [
            {"type": "material_rights", "purpose": "本项目内容制作", "platforms": ["抖音"], "valid_from": "2026-08-16T00:00:00+08:00", "valid_to": "2027-08-16T23:59:59+08:00"},
            {"type": "business_qualification", "purpose": "门店经营事实核验", "platforms": ["抖音"], "valid_from": "2026-08-16T00:00:00+08:00", "valid_to": "2027-08-16T23:59:59+08:00"},
        ],
        "piece_format": "VIDEO_SHORT",
        "platform": "抖音",
    }


def expect(response, status: int = 200):
    if response.status_code != status:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="使用确定性测试推理；不算 live reason 验收")
    parser.add_argument("--runtime-dir", type=Path)
    args = parser.parse_args()
    runtime = (args.runtime_dir or APP_ROOT / "runtime" / f"acceptance-{int(time.time())}").resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    os.environ["XG_FACTORY_OPS_PASSWORD"] = "accept-ops-password"
    os.environ["XG_FACTORY_SESSION_SECRET"] = "acceptance-session-secret-must-be-at-least-32-bytes"
    os.environ["XG_FACTORY_DB"] = str(runtime / "import.sqlite3")
    os.environ["XG_FACTORY_PROJECTS_DIR"] = str(runtime / "import-projects")

    from fastapi.testclient import TestClient
    from app.main import create_app
    from tests.test_p1_platform import FakeBillingClient, hotpot_payload

    billing = FakeBillingClient({101: "5000.00"})
    app = create_app(runtime / "platform.sqlite3", runtime / "projects", reasoner=fast_reasoner if args.fast else None, start_worker=False, billing_client=billing)
    client = TestClient(app)
    client_login = expect(client.post("/api/v1/billing/access", json={"customer_id": "101"}))
    client_csrf = client_login["csrf"]
    ops_login = expect(client.post("/api/v1/auth/login", json={"account": "审核员", "password": "accept-ops-password", "role": "ops"}))
    ops_csrf = ops_login["csrf"]
    created = expect(client.post("/api/v1/projects", json=hotpot_payload(), headers={"X-CSRF-Token": client_csrf, "Idempotency-Key": "accept-create-0001"}), 201)
    project_id = created["project_id"]
    demo_project_dir = runtime / "projects" / project_id
    (demo_project_dir / "DEMO_SCRIPT.md").write_text(
        "# 火锅店 P1 演示\n\n"
        "1. 提交行业表单、结构化套餐、门店与授权。\n"
        "2. 上传授权素材并完成项目授权审核。\n"
        "3. 人工导入三条已核验洞察。\n"
        "4. 逐步推进免费任务与人工门，完成内容方案确认。\n"
        "5. 在付费边界停住，随后仅使用授权素材执行免费合成。\n"
        "6. 完成成片确认、交付审核、ZIP 下载和复盘提醒检查。\n",
        encoding="utf-8",
    )

    with tempfile.TemporaryDirectory(prefix="p1-assets-") as temporary:
        temporary_path = Path(temporary)
        source_video = temporary_path / "authorized-source.mp4"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0xB72A20:s=360x640:r=25:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source_video)], capture_output=True, text=True, check=True)
        uploads: list[tuple[str, bytes, str, str | None, str | None]] = [(source_video.name, source_video.read_bytes(), "video/mp4", None, None)]
        evidence_types = ("menu_photo", "price_board_photo", "storefront_photo", "dish_photo", "service_process_photo")
        planned_ids = ("asset_menu", "asset_price", "asset_storefront", "asset_dish", "asset_service")
        for index, (name, evidence_type, planned_id) in enumerate(zip(("菜单实拍", "价目实拍", "门头实拍", "菜品实拍", "服务过程实拍"), evidence_types, planned_ids), 1):
            buffer = io.BytesIO()
            Image.new("RGB", (640, 480), (120 + index * 10, 45, 35)).save(buffer, "JPEG")
            uploads.append((f"{name}.jpg", buffer.getvalue(), "image/jpeg", planned_id, evidence_type))
        asset_ids = []
        for index, (name, data, mime, planned_id, evidence_type) in enumerate(uploads):
            form_data = {"store_id": "store_main"}
            if planned_id:
                form_data.update({"planned_asset_id": planned_id, "evidence_type": evidence_type})
            response = client.post(
                f"/api/v1/projects/{project_id}/assets",
                files={"file": (name, data, mime)},
                data=form_data,
                headers={"X-CSRF-Token": client_csrf, "Idempotency-Key": f"accept-asset-{index:04d}"},
            )
            asset_ids.append(expect(response, 201)["asset_id"])

    def approve_current(gate_id: str) -> None:
        checked = expect(client.post(f"/internal/v1/projects/{project_id}/gates/{gate_id}/check", headers={"X-CSRF-Token": ops_csrf}))
        if checked["rc"] == 0:
            return
        if checked["rc"] != 3 or not checked.get("check_token"):
            raise RuntimeError(f"{gate_id} check 未进入可审核状态：{checked}")
        pending = expect(client.get("/internal/v1/reviews/pending"))["items"]
        item = next(row for row in pending if row["project_id"] == project_id and row["gate_id"] == gate_id)
        approved = expect(client.post(
            f"/internal/v1/projects/{project_id}/gates/{gate_id}/approve",
            json={"check_token": checked["check_token"], "evidence_artifact_id": item["evidence_artifact_id"]},
            headers={"X-CSRF-Token": ops_csrf},
        ))
        if approved["rc"] != 0:
            raise RuntimeError(f"{gate_id} approve 失败：{approved}")

    approve_current("G_PROJECT_AUTHORIZED")
    insights = [
        {"title": "本地生活商家经营入口", "source_url": "https://life.douyin.com/", "source_name": "抖音来客公开页面", "finding": "短视频本地生活内容应围绕真实门店与实际服务场景组织，具体效果仍需发布后验证", "verified_at": "2026-08-16T00:00:00Z"},
        {"title": "推荐菜资料字段要求", "source_url": "https://kf.dianping.com/csCenter/app/questions/7706", "source_name": "大众点评商户通帮助中心", "finding": "推荐菜资料需要菜名、价格、图片和图文介绍，内容生产应与已核验菜单和菜品实拍一致", "verified_at": "2026-08-16T00:00:00Z"},
        {"title": "餐饮经营信息公示要求", "source_url": "https://rules-center.meituan.com/m/detail/guize/395005?activeRule=1", "source_name": "美团规则中心", "finding": "门店展示信息应真实、准确、完整、及时，门面照片、经营地址与资质信息需要保持一致", "verified_at": "2026-08-16T00:00:00Z"},
    ]
    expect(client.post(f"/internal/v1/projects/{project_id}/insights/import", json={"items": insights}, headers={"X-CSRF-Token": ops_csrf}))

    for _ in range(80):
        state = expect(client.post(f"/internal/v1/projects/{project_id}/advance", headers={"X-CSRF-Token": ops_csrf}))["status"]
        if state == "QUEUED":
            if not app.state.worker.run_once():
                raise RuntimeError("任务已入队但 worker 未领取")
        elif state == "INTERNAL_REVIEW":
            pending = expect(client.get("/internal/v1/reviews/pending"))["items"]
            row = next(item for item in pending if item["project_id"] == project_id)
            approve_current(row["gate_id"])
        elif state == "WAITING_C1":
            confirmation = next(row for row in expect(client.get(f"/api/v1/projects/{project_id}/confirmations"))["items"] if row["confirm_id"] == "C1")
            expect(client.post(f"/api/v1/projects/{project_id}/confirmations/C1", json={"decision": "ok", "revision": confirmation["revision"]}, headers={"X-CSRF-Token": client_csrf, "Idempotency-Key": "accept-c1-0000001"}))
        elif state == "WAITING_BOSS_APPROVAL":
            break
        elif state in {"RUNNING", "WAITING_INSIGHT_IMPORT"}:
            continue
        else:
            raise RuntimeError(f"付费边界前出现意外状态：{state}")
    else:
        raise RuntimeError("未在 80 步内到达付费边界")

    paid = expect(client.post(f"/internal/v1/projects/{project_id}/paid-steps/video-generate/authorize", json={"request_hash": "formal-request"}, headers={"X-CSRF-Token": ops_csrf}))
    if paid["status"] != "WAITING_BOSS_APPROVAL" or paid["conditions"]["paid_api_enabled"]:
        raise RuntimeError("付费边界未保持关闭")
    expect(client.post(f"/internal/v1/projects/{project_id}/media/compose", json={"asset_id": asset_ids[0]}, headers={"X-CSRF-Token": ops_csrf}))
    approve_current("G_TECHNICAL_QC_PASS")
    state = expect(client.post(f"/internal/v1/projects/{project_id}/advance", headers={"X-CSRF-Token": ops_csrf}))["status"]
    if state != "WAITING_C2":
        raise RuntimeError(f"技术质检后未进入 C2：{state}")
    c2 = next(row for row in expect(client.get(f"/api/v1/projects/{project_id}/confirmations"))["items"] if row["confirm_id"] == "C2")
    expect(client.post(f"/api/v1/projects/{project_id}/confirmations/C2", json={"decision": "ok", "revision": c2["revision"]}, headers={"X-CSRF-Token": client_csrf, "Idempotency-Key": "accept-c2-0000001"}))

    for _ in range(20):
        state = expect(client.post(f"/internal/v1/projects/{project_id}/advance", headers={"X-CSRF-Token": ops_csrf}))["status"]
        if state == "QUEUED":
            app.state.worker.run_once()
        elif state == "INTERNAL_REVIEW":
            approve_current("G_DELIVERY_READY")
        elif state == "DELIVERED":
            break
        elif state in {"RUNNING", "PHASE1_COMPLETE"}:
            continue
        else:
            raise RuntimeError(f"交付阶段出现意外状态：{state}")

    delivery = expect(client.get(f"/api/v1/projects/{project_id}/delivery"))
    downloaded = client.get(f"/api/v1/projects/{project_id}/delivery/{delivery['items'][0]['download_token']}")
    if downloaded.status_code != 200 or not downloaded.content.startswith(b"PK"):
        raise RuntimeError("交付 ZIP 下载失败")
    reminders = expect(client.get(f"/api/v1/projects/{project_id}/review-reminders"))["items"]
    if [row["at"] for row in reminders] != ["T+1 天", "T+3 天", "T+7 天"]:
        raise RuntimeError("复盘提醒不完整")
    audit = expect(client.get(f"/internal/v1/projects/{project_id}/audit"))
    if not audit["hash_chain_ok"]:
        raise RuntimeError("审计链校验失败")
    print(json.dumps({"ok": True, "mode": "fast" if args.fast else "live", "project_id": project_id, "runtime": str(runtime), "zip_bytes": len(downloaded.content), "audit_events": len(audit["items"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
