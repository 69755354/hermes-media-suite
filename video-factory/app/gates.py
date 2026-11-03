"""存量门禁安全适配层：补足 check→token→approve、身份、证据路径和授权链断言。"""
# > 执行者：codex
from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import re
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import config
from .compliance import load_rules, scan_text
from .state_store import StateStore, canonical_json


REPO_ROOT = config.REPO_ROOT
WORKFLOW_GATE = REPO_ROOT / "scripts" / "workflow_gate.py"
CONFIRM_GATE = REPO_ROOT / "scripts" / "confirm_gate.py"
TICKET = REPO_ROOT / "scripts" / "workflow_ticket.py"
TOKEN_TTL_SECONDS = 300

BRANCH_CONTRACT = {
    "MEDIA_PRODUCTION": {
        "VIDEO_SHORT": {
            "requires": ["A_ASSET_MANIFEST", "A_PROMPT_PACKAGE", "A_PROMPT_QC", "A_RENDER_BUDGET_APPROVAL"],
            "produces": ["A_TECH_QC", "A_ACTUAL_COST", "A_COST_LEDGER", "A_VIDEO_MASTER", "A_COVER", "A_SUBTITLES"],
        },
        "IMAGE_POST": {
            "requires": ["A_ASSET_MANIFEST", "A_PROMPT_PACKAGE", "A_PROMPT_QC", "A_RENDER_BUDGET_APPROVAL"],
            "produces": ["A_TECH_QC", "A_ACTUAL_COST", "A_COST_LEDGER", "A_IMAGE_SET", "A_COVER"],
        },
    },
    "DELIVERY_PACKAGE": {
        "VIDEO_SHORT": {
            "requires": ["A_GROWTH_PLAYBOOK", "A_CONTENT_CALENDAR", "A_OFFER_PATH", "A_TRACKING_SPEC", "A_TECH_QC", "A_VIDEO_MASTER"],
            "produces": ["A_FINAL_REVIEW", "A_MEDIA_DELIVERY", "A_PUBLISH_PACKAGE", "A_PUBLISH_GUIDE", "A_RESPONSE_PLAYBOOK", "A_TRACE_CODE_SET", "A_DELIVERY_RECORD"],
        },
        "IMAGE_POST": {
            "requires": ["A_GROWTH_PLAYBOOK", "A_CONTENT_CALENDAR", "A_OFFER_PATH", "A_TRACKING_SPEC", "A_TECH_QC", "A_IMAGE_SET"],
            "produces": ["A_FINAL_REVIEW", "A_MEDIA_DELIVERY", "A_PUBLISH_PACKAGE", "A_PUBLISH_GUIDE", "A_RESPONSE_PLAYBOOK", "A_TRACE_CODE_SET", "A_DELIVERY_RECORD"],
        },
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def project_lock(project_dir: Path) -> Iterator[None]:
    project_dir.mkdir(parents=True, exist_ok=True)
    lock_path = project_dir / ".platform.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run_semantic_gate(project_dir: Path, gate_id: str) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", str(WORKFLOW_GATE), "check", str(project_dir.resolve()), gate_id],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return result.returncode, (result.stdout or result.stderr).strip()


def _legacy_approve(project_dir: Path, gate_id: str, by: str, evidence: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", str(WORKFLOW_GATE), "approve", str(project_dir.resolve()), gate_id, "--by", by, "--evidence", str(evidence.resolve())],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return result.returncode, (result.stdout or result.stderr).strip()


def confirm_point(project_dir: Path, point: str, quote: str = "可以") -> tuple[int, str]:
    if point not in {"node4_copy", "node8_image", "node12_render"}:
        return 2, "确认点无效"
    if quote != "可以":
        return 2, "确认适配器只接受规范枚举"
    state_path = project_dir / "CONFIRM.json"
    if state_path.exists() and json.loads(state_path.read_text(encoding="utf-8")).get("skip_mode") is True:
        return 2, "确认状态受到污染"
    result = subprocess.run(
        ["python3", str(CONFIRM_GATE), "confirm", str(project_dir.resolve()), point, "可以"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if state_path.exists() and json.loads(state_path.read_text(encoding="utf-8")).get("skip_mode") is True:
        return 2, "确认状态受到污染"
    return result.returncode, (result.stdout or result.stderr).strip()


def check_confirm_point(project_dir: Path, point: str) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", str(CONFIRM_GATE), "check", str(project_dir.resolve()), point],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode, (result.stdout or result.stderr).strip()


def ticket_status(project_dir: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["python3", str(TICKET), "status", "--project", str(project_dir.resolve())],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.returncode, (result.stdout or result.stderr).strip()


def _node_for_gate(registry: dict[str, Any], gate_id: str) -> tuple[str, dict[str, Any]]:
    for node_id, node in registry["nodes"].items():
        if node["exit_gate"] == gate_id:
            return node_id, node
    raise KeyError(gate_id)


def _artifact_sets(registry: dict[str, Any], node_id: str, node: dict[str, Any], piece_format: str) -> tuple[list[str], list[str]]:
    branch = BRANCH_CONTRACT.get(node_id, {}).get(piece_format)
    if branch:
        return branch["requires"], branch["produces"]
    return list(node.get("requires", [])), list(node.get("produces", []))


def _project_authorization_context(store: StateStore, project_id: str) -> tuple[list[str], dict[str, Any]]:
    project = store.get_project(project_id)
    brief = json.loads((Path(project["project_dir"]) / "BRIEF.json").read_text(encoding="utf-8"))
    planned = {row["asset_id"]: row for row in brief.get("evidence_assets", [])}
    bindings = {row["planned_asset_id"]: row for row in store.evidence_bindings(project_id)}
    assets = {row["id"]: row for row in store.assets(project_id)}
    content_type = brief.get("content_type")
    planned_types = {row.get("evidence_type") for row in planned.values()}
    problems: list[str] = []
    if content_type == "store_visit" and not (
        "storefront_photo" in planned_types
        and bool({"product_photo", "menu_photo", "dish_photo"} & planned_types)
    ):
        problems.append("required_evidence_types")
    if content_type == "oral" and "presenter_portrait" not in planned_types:
        problems.append("required_evidence_types")
    if set(planned) != set(bindings):
        problems.append("evidence_upload_binding")
    for planned_id, binding in bindings.items():
        asset = assets.get(binding["asset_id"])
        if not asset or planned_id not in planned or binding["evidence_type"] != planned[planned_id]["evidence_type"]:
            problems.append("evidence_asset_integrity")
            break
    auth = store.authorizations(project_id)
    if not {"material_rights", "business_qualification"}.issubset({row["type"] for row in auth}):
        problems.append("authorization_entities")
    context = {
        "evidence": [
            {
                "planned_asset_id": key,
                "evidence_type": row["evidence_type"],
                "asset_id": row["asset_id"],
                "sha256": assets.get(row["asset_id"], {}).get("sha256"),
                "bytes": assets.get(row["asset_id"], {}).get("bytes"),
            }
            for key, row in sorted(bindings.items())
        ],
        "authorization_ids": sorted(row["id"] for row in auth),
    }
    return sorted(set(problems)), context


def build_gate_manifest(store: StateStore, project_id: str, registry: dict[str, Any], gate_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    if not project:
        raise KeyError(project_id)
    node_id, node = _node_for_gate(registry, gate_id)
    requires, produces = _artifact_sets(registry, node_id, node, project["piece"]["format"])
    current: dict[str, dict[str, Any]] = {}
    for row in store.artifacts(project_id):
        path = Path(row["path"])
        if not path.is_file():
            continue
        current[row["artifact_id"]] = {"sha256": sha256_file(path), "bytes": path.stat().st_size, "mock": row["mock"]}
    missing_requires = [item for item in requires if item not in current or current[item]["bytes"] <= 0]
    missing_produces = [item for item in produces if item not in current or current[item]["bytes"] <= 0]
    manifest = {
        "gate_id": gate_id,
        "node_id": node_id,
        "piece_id": project["piece"]["id"],
        "requires": {item: current[item] for item in requires if item in current},
        "produces": {item: current[item] for item in produces if item in current},
        "missing_requires": missing_requires,
        "missing_produces": missing_produces,
        "upstream_gate_states": {
            row["point_or_gate"]: row["decision"]
            for row in store.reviews(project_id)
            if row["created_at"]
        },
    }
    if gate_id == "G_PROJECT_AUTHORIZED":
        problems, context = _project_authorization_context(store, project_id)
        manifest["platform_assertions"] = {"problems": problems, "context": context}
    return manifest


def _copy_hard_gate(store: StateStore, project_id: str) -> tuple[bool, str]:
    copy_ids = ["A_COPY_FINAL", "A_PLATFORM_COPY_PACK", "A_COPY_VERSION_1", "A_COPY_VERSION_2", "A_COPY_VERSION_3"]
    rows = [store.artifact(project_id, artifact_id, formal_only=True) for artifact_id in copy_ids]
    rows = [row for row in rows if row]
    project = store.get_project(project_id)
    voice = Path(project["project_dir"]) / "节点5_口播稿.md"
    scanned = 0
    rules = load_rules(config.CONFIG_DIR / "compliance_rules.yaml")
    findings: list[str] = []
    for row in rows:
        path = Path(row["path"])
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        scanned += 1
        result = scan_text(path.read_text(encoding="utf-8"), "餐饮/火锅", rules)
        findings.extend(f"{row['artifact_id']}:{item['term']}" for item in result["findings"] if item["level"] == "block")
    if voice.is_file():
        scanned += 1
        result = scan_text(voice.read_text(encoding="utf-8"), "餐饮/火锅", rules)
        findings.extend(f"口播稿:{item['term']}" for item in result["findings"] if item["level"] == "block")
    if scanned == 0:
        return False, "BLOCKED:G_COPY_READY:已扫 0 个文件"
    if findings:
        return False, f"BLOCKED:G_COPY_READY:已扫 {scanned} 个文件；命中 " + "、".join(findings)
    review = store.artifact(project_id, "A_COPY_REVIEW", formal_only=True)
    review_text = Path(review["path"]).read_text(encoding="utf-8") if review else ""
    if not all(term in review_text for term in ("事实", "合规", "授权", "可执行")):
        return False, f"BLOCKED:G_COPY_READY:已扫 {scanned} 个文件；四硬门结论不完整"
    facts = store.facts_revision(project_id)
    if not facts or not facts["frozen_at"]:
        return False, f"BLOCKED:G_COPY_READY:已扫 {scanned} 个文件；门店事实尚未冻结"
    return True, f"COPY_HARD_GATES_ALLOWED:已扫 {scanned} 个文件；事实/合规/授权/可执行已分别检查"


def _encode_token(secret: bytes, manifest: dict[str, Any]) -> str:
    payload = {"manifest_hash": hashlib.sha256(canonical_json(manifest).encode()).hexdigest(), "issued_at": int(time.time())}
    body = base64.urlsafe_b64encode(canonical_json(payload).encode()).decode().rstrip("=")
    signature = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def check_gate_atomic(
    store: StateStore,
    project_id: str,
    registry: dict[str, Any],
    gate_id: str,
    secret: bytes,
) -> dict[str, Any]:
    project = store.get_project(project_id)
    if not project:
        raise KeyError(project_id)
    project_dir = Path(project["project_dir"])
    with project_lock(project_dir):
        manifest = build_gate_manifest(store, project_id, registry, gate_id)
        platform_problems = manifest.get("platform_assertions", {}).get("problems", [])
        if manifest["missing_requires"] or manifest["missing_produces"] or platform_problems:
            output = "BLOCKED:审批依据不完整"
            rc = 2
        else:
            if gate_id == "G_COPY_READY":
                hard_ok, hard_output = _copy_hard_gate(store, project_id)
                if not hard_ok:
                    rc, output = 2, hard_output
                else:
                    rc, legacy_output = run_semantic_gate(project_dir, gate_id)
                    output = hard_output + "\n" + legacy_output
            else:
                rc, output = run_semantic_gate(project_dir, gate_id)
            if rc == 2 and manifest["node_id"] in BRANCH_CONTRACT:
                piece_format = store.get_project(project_id)["piece"]["format"]
                forbidden = {
                    "VIDEO_SHORT": {"A_IMAGE_SET", "A_ARTICLE_LAYOUT"},
                    "IMAGE_POST": {"A_VIDEO_MASTER", "A_SUBTITLES", "A_ARTICLE_LAYOUT"},
                }[piece_format]
                blocking_lines = []
                for line in output.splitlines():
                    if "BLOCKED" not in line or "门禁检查未通过" in line or any(item in line for item in forbidden):
                        continue
                    upstream = re.search(r"上游门\s+(G_[A-Z0-9_]+)", line)
                    if upstream and store.gate_allowed(project_id, upstream.group(1)):
                        # 旧文件状态不知道平台分支审批；SQLite 中的同项目正式审批
                        # 是平台真相源，且已受 token+manifest 约束。
                        continue
                    blocking_lines.append(line)
                if not blocking_lines:
                    output = output + f"\nMANUAL_REVIEW_REQUIRED:{gate_id}:branch_quality_review"
                    rc = 3
        token = None
        if rc == 3:
            token = _encode_token(secret, manifest)
            store.save_gate_check(project_id, gate_id, token, manifest, rc, output, TOKEN_TTL_SECONDS)
        elif rc == 0 and not store.gate_allowed(project_id, gate_id):
            store.add_internal_review(
                project_id, gate_id, "ALLOWED", "system", "", output,
                piece_id=manifest["piece_id"], manifest=manifest,
            )
        store.audit(project_id, "operator", "internal_ops", "gate_check", gate_id, {"rc": rc, "output": output, "basis": manifest})
        return {"rc": rc, "output": output, "check_token": token, "basis": manifest}


def assert_delivery_chain(store: StateStore, project_id: str) -> list[str]:
    failures: list[str] = []
    if not store.gate_allowed(project_id, "G_PROJECT_AUTHORIZED"):
        failures.append("project_authorization")
    for artifact_id in ("A_AUTHORIZATION_REGISTER", "A_RIGHTS_REGISTER"):
        artifact = store.artifact(project_id, artifact_id, formal_only=True)
        if not artifact or artifact["bytes"] <= 0:
            failures.append(artifact_id)
    auth_rows = store.authorizations(project_id)
    if not auth_rows or any(row["status"] != "verified" or row["revoked_at"] for row in auth_rows):
        failures.append("authorization_entities")
    confirmations = store.confirmations(project_id)
    c2 = next((row for row in confirmations if row["confirm_id"] == "C2"), None)
    if not c2 or c2["status"] != "ok":
        failures.append("C2")
    if any(item["mock"] for item in store.artifacts(project_id)):
        failures.append("mock_artifact")
    return failures


def approve_gate_atomic(
    store: StateStore,
    project_id: str,
    registry: dict[str, Any],
    gate_id: str,
    token: str,
    evidence_artifact_id: str,
    reviewer: str,
) -> dict[str, Any]:
    project = store.get_project(project_id)
    if not project:
        raise KeyError(project_id)
    project_dir = Path(project["project_dir"]).resolve()
    with project_lock(project_dir):
        checked = store.consume_gate_check(project_id, gate_id, token)
        if not checked:
            return {"rc": 2, "output": "BLOCKED:check_token 无效、过期或已使用", "check_token": None}
        current = build_gate_manifest(store, project_id, registry, gate_id)
        if current != checked["manifest"]:
            return {"rc": 2, "output": "BLOCKED:审批依据已变化，请重新检查", "check_token": None}
        if gate_id == "G_DELIVERY_READY":
            failures = assert_delivery_chain(store, project_id)
            if failures:
                store.audit(project_id, reviewer, "internal_ops", "gate_approve_blocked", gate_id, {"blocked_by": failures})
                return {"rc": 2, "output": "BLOCKED:交付前置断言未通过", "check_token": None, "blocked_by": failures}
        evidence = store.artifact(project_id, evidence_artifact_id, formal_only=True)
        if not evidence:
            return {"rc": 2, "output": "BLOCKED:审核证据不是本项目登记产物", "check_token": None}
        evidence_path = Path(evidence["path"]).resolve()
        if project_dir not in evidence_path.parents:
            return {"rc": 2, "output": "BLOCKED:审核证据路径越界", "check_token": None}
        # 冻结旧脚本在媒体节点仍把视频/图文两条互斥分支一起做哈希，
        # check 已由平台按 piece.format 收敛过；approve 必须沿用同一份已签名
        # manifest，不能为了迎合旧脚本伪造另一分支产物。
        if current["node_id"] in BRANCH_CONTRACT:
            rc = 0
            output = f"ALLOWED:{gate_id}:platform_branch_contract:{project['piece']['format']}"
        else:
            rc, output = _legacy_approve(project_dir, gate_id, reviewer, evidence_path)
        decision = "ALLOWED" if rc == 0 else "BLOCKED"
        store.add_internal_review(
            project_id,
            gate_id,
            decision,
            reviewer,
            evidence_artifact_id,
            output,
            piece_id=project["piece"]["id"],
            evidence_artifact_id=evidence_artifact_id,
            check_token=token,
            manifest=current,
        )
        if rc == 0 and gate_id == "G_PROJECT_AUTHORIZED":
            store.verify_authorizations(project_id, reviewer)
        return {"rc": rc, "output": output, "check_token": None, "basis": current}
