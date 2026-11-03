#!/usr/bin/env python3
"""统一门禁入口（语义 ID 化）。

用法:
  workflow_gate.py check <项目目录> <gate_id> [--cycle ID] [--piece ID]
                           [--client CID] [--context-loaded 0|1]
  workflow_gate.py status <项目目录>
  workflow_gate.py approve <项目目录> <gate_id> --by <审批人> --evidence <路径>
"""
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

def _pick_path(*cands):
    """按受管候选路径解析：宿主 /home/ubuntu/workflow/wiki、沙箱里的 /home/ubuntu/wiki、脚本同级 ../wiki。

    候选表是硬编码的受管清单；规则表位置不接受环境变量覆盖，否则调用方可把
    闸门的单一事实源指向自造的宽松 YAML 绕过检查（与 skill_contract 同口径）。
    """
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return cands[-1]

_SD = os.path.dirname(os.path.abspath(__file__))
REGISTRY = _pick_path("/home/ubuntu/workflow/wiki/spec/WORKFLOW_REGISTRY.yaml",
                      "/home/ubuntu/wiki/spec/WORKFLOW_REGISTRY.yaml",
                      os.path.join(_SD, "..", "wiki", "spec", "WORKFLOW_REGISTRY.yaml"))
CREATIVE_ROUTE_TABLE = _pick_path("/home/ubuntu/workflow/wiki/spec/CREATIVE_ROUTE_TABLE.yaml",
                                  "/home/ubuntu/wiki/spec/CREATIVE_ROUTE_TABLE.yaml",
                                  os.path.join(_SD, "..", "wiki", "spec", "CREATIVE_ROUTE_TABLE.yaml"))
SCRIPTS = "/home/ubuntu/workflow/scripts"
MIN_MD_BYTES = 200
ALLOWED_STATUS = "ALLOWED"
SKIPPED_STATUS = "SKIPPED"
DEFAULT_ENTRY_TYPE = "FULL_SERVICE"
ENTRY_TYPES = {"FULL_SERVICE", "CLIENT_COPY", "TEST_RUN", "SINGLE_VIDEO"}
CREATIVE_START_GATE = "G_CREATIVE_READY"
TECHNICAL_GATE = "G_TECHNICAL_QC_PASS"
DELIVERY_GATE = "G_DELIVERY_READY"
ENTRY_COMPLIANCE_CHECKS = [("data_source_gate.py", "node4_body")]


def load_registry():
    import yaml
    with open(REGISTRY, encoding="utf-8") as f:
        return yaml.safe_load(f)


def state_path(proj):
    return os.path.join(proj, "workflow_state.json")


def default_state(proj):
    return {
        "project_id": os.path.basename(proj),
        "entry_type": DEFAULT_ENTRY_TYPE,
        "active_node_id": None,
        "artifacts": {},
        "gates": [],
    }


def normalize_gate_records(gates):
    """把旧版 gates 字典迁移为带实例维度的记录列表。"""
    if gates is None:
        return []
    if isinstance(gates, list):
        records = []
        for item in gates:
            if not isinstance(item, dict) or not item.get("gate_id"):
                raise ValueError("gates 列表中的每条记录必须包含 gate_id")
            record = dict(item)
            record.setdefault("cycle_id", None)
            record.setdefault("piece_id", None)
            records.append(record)
        return records
    if isinstance(gates, dict):
        records = []
        for gate_id, info in gates.items():
            record = dict(info) if isinstance(info, dict) else {"status": info}
            record.update({
                "gate_id": gate_id,
                "cycle_id": None,
                "piece_id": None,
                "legacy_scope": True,
            })
            records.append(record)
        return records
    raise ValueError("gates 必须是对象（旧格式）或记录列表（新格式）")


def normalize_state(proj, state):
    normalized = dict(state)
    normalized.setdefault("project_id", os.path.basename(proj))
    normalized.setdefault("entry_type", DEFAULT_ENTRY_TYPE)
    if normalized["entry_type"] not in ENTRY_TYPES:
        raise ValueError(
            f"entry_type 无效: {normalized['entry_type']}，允许值: {sorted(ENTRY_TYPES)}"
        )
    normalized.setdefault("active_node_id", None)
    normalized.setdefault("artifacts", {})
    normalized["gates"] = normalize_gate_records(normalized.get("gates"))
    return normalized


def load_state(proj):
    p = state_path(proj)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return normalize_state(proj, json.load(f))
    return default_state(proj)


def save_state(proj, state):
    with open(state_path(proj), "w", encoding="utf-8") as f:
        json.dump(normalize_state(proj, state), f, ensure_ascii=False, indent=2)


def gate_context(gate_id, cycle_id=None, piece_id=None):
    """项目授权永远是项目级，其余门按调用方给出的实例维度记录。"""
    if gate_id == "G_PROJECT_AUTHORIZED":
        return None, None
    return cycle_id, piece_id


def get_gate_record(state, gate_id, cycle_id=None, piece_id=None, allow_legacy=True):
    cycle_id, piece_id = gate_context(gate_id, cycle_id, piece_id)
    for record in state.get("gates", []):
        if (record.get("gate_id"), record.get("cycle_id"), record.get("piece_id")) == (
                gate_id, cycle_id, piece_id):
            return record
    if allow_legacy and (cycle_id is not None or piece_id is not None):
        for record in state.get("gates", []):
            if (record.get("gate_id") == gate_id and record.get("legacy_scope") is True and
                    record.get("cycle_id") is None and record.get("piece_id") is None):
                return record
    return None


def upsert_gate_record(state, record):
    key = (record["gate_id"], record.get("cycle_id"), record.get("piece_id"))
    records = state.setdefault("gates", [])
    for index, existing in enumerate(records):
        existing_key = (
            existing.get("gate_id"), existing.get("cycle_id"), existing.get("piece_id")
        )
        if existing_key == key:
            records[index] = record
            return
    records.append(record)


def state_artifact_path(proj, reg, artifact_id, state=None):
    """状态中的显式路径优先；未登记时回退注册表路径。"""
    state = state or load_state(proj)
    value = state.get("artifacts", {}).get(artifact_id)
    candidate = None
    if isinstance(value, str):
        candidate = value
    elif isinstance(value, dict):
        candidate = value.get("path")
    if candidate:
        return candidate if os.path.isabs(candidate) else os.path.join(proj, candidate)
    return artifact_path(proj, reg, artifact_id)


def sha256(path):
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


LEGACY_MAP = {
    # 会话级门，无项目级兼容适配器：身份必须由当前会话显式传入。
    "G_CLIENT_CONTEXT_LOADED": None,
    "G_PROJECT_AUTHORIZED": None,
    "G_BUSINESS_BASELINE_READY": None,
    "G_OFFER_VIABLE": None,
    # GROWTH_STRATEGY 的真实 exit gate；同时保留原策略评分适配。
    "G_STRATEGY_BY_CODEX": [("review_gate.py", "node3_strategy")],
    "G_INFRA_READY_FOR_PUBLISH": None,
    "G_CONTENT_PLAN_READY": None,
    "G_TOPIC_READY": [("review_gate.py", "node3_candidate"), ("review_gate.py", "node4_candidate")],
    "G_COPY_READY": [("review_gate.py", "node4_review"), ("review_gate.py", "node5_review"),
                     ("data_source_gate.py", "node4_body")],
    "G_CREATIVE_READY": None,
    "G_RENDER_READY": None,
    "G_TECHNICAL_QC_PASS": None,
    "G_DELIVERY_READY": [("review_gate.py", "node12_pre")],
    "G_PUBLISH_READY": None,
    "G_LEAD_CAPTURED": None,
    "G_CONVERSION_RECORDED": None,
    "G_RETENTION_LOOP_READY": None,
    "G_WEEKLY_REVIEW_READY": None,
    "G_CYCLE_CLOSED": None,
}

STRATEGY_ARTIFACTS = [
    "A_AUDIENCE_PROFILE", "A_LOCAL_COMPETITOR_SCAN", "A_CONTENT_BENCHMARKS",
    "A_GROWTH_PLAYBOOK", "A_FUNNEL_TARGETS", "A_RISK_PLAN",
    "A_TOPIC_CANDIDATES", "A_TOPIC_FINAL", "A_COPY_FINAL",
    "A_OFFER_PORTFOLIO", "A_UNIT_ECONOMICS", "A_OFFER_PATH",
]

NEGATIVE_LABEL_RE = re.compile(r"(专属负面|通用负面|负面约束|负面词|负面)\s*[：:]")
NEGATED_PREFIX_RE = re.compile(r"(禁止|避免|不要|别|不可|不得|不应|不能)\s*")
FAST_VOICE_RE = re.compile(
    r"语速\s*[：:]?\s*(?:快|略快|较快|偏快|加快|飞快)|"
    r"节奏\s*(?:明快|轻快|加快|快|急)|(?:稍|拉)快|快语速|急促|"
    r"speed\s*[=:]\s*(?:1\.[1-9]|[2-9](?:\.\d+)?)",
    re.I,
)
SILENT_SHOT_RE = re.compile(r"无台词|纯画面|画面展示|无对白|仅画面|静默镜")
# 2026-09-29 闸本体修复（§6.1-1）：标准 8 列分镜表的列名是「说话人|台词」，
# 不含「声音/语音/voice/audio」，旧 check_voice 因此在标准格式上恒 PASS。
# VOICE_COLUMN_RE 扩出声承载列；VOICE_HINT_CELL_RE 兜底扫非声音命名列里的声音指令。
VOICE_COLUMN_RE = re.compile(r"声音|语音|配音|voice|audio|说话人|台词|对白|旁白|口播", re.I)
VOICE_HINT_CELL_RE = re.compile(r"语速|配音|语气|音色|人声")
CHARACTER_REFERENCE_RE = re.compile(
    r"@图\s*1|character\s*(?:reference|sheet)|角色(?:参考|设定|形象|图)|"
    r"人物(?:参考|设定|形象|图)|仅作人物参考",
    re.I,
)
THREE_VIEW_RE = re.compile(r"三视图|three[\s_-]*view|character\s*(?:reference\s*)?sheet", re.I)
FRONT_VIEW_RE = re.compile(r"正面|front(?:al)?\s*view", re.I)
SIDE_VIEW_RE = re.compile(r"(?<!四分之三)侧面|profile\s*view|side\s*view", re.I)
EXTRA_VIEW_RE = re.compile(r"四分之三侧面|四分之三视角|3/4\s*view|背面|back\s*view", re.I)
CHINESE_LABEL_RE = re.compile(r"中文(?:标注|标签|标题|说明)|标注为中文|中文角度标注")
FACE_CLOSEUP_RE = re.compile(r"脸部|面部|五官", re.I)
CLOSEUP_RE = re.compile(r"特写|放大窗|细节窗|close[\s_-]*up|detail\s*(?:window|view)", re.I)


def artifact_path(proj, reg, artifact_id):
    spec = reg.get("artifacts", {}).get(artifact_id, {})
    rel = spec.get("path")
    return os.path.join(proj, rel) if rel else None


def node_for_gate(reg, gate_id):
    return next(((nid, node) for nid, node in reg["nodes"].items()
                 if node.get("exit_gate") == gate_id), (None, None))


def strip_negative_cells(text):
    """只删除负面标签及其后的同一子句，保留后续正向内容供检查。"""
    pattern = re.compile(
        r"(?:专属负面|通用负面|负面约束|负面词|负面)\s*[：:]\s*[^；。|\n]*(?:[；。]|(?=\||$))"
    )
    return pattern.sub("", text)


def reference_segment(text, image_number, all_segments=False):
    """返回 @图N 引用段；可遍历全文同编号的全部引用且不跨到下一引用。"""
    segments = [
        match.group("body")
        for match in re.finditer(rf"@图{image_number}(?P<body>.*?)(?=@图\d|$)", text, re.S)
    ]
    return segments if all_segments else (segments[0] if segments else "")


def reference_has_use(text, image_number, use_pattern, require_path=False):
    segments = reference_segment(text, image_number, all_segments=True)
    # 用途名可位于“仅用于/仅作”之前，但用途与路径必须在同一 @图N 段内取证。
    return any(
        re.search(r"仅(?:用于|作)", segment)
        and re.search(use_pattern, segment)
        and (not require_path or re.search(r"/[^`）)\s，,。；;]+", segment))
        for segment in segments
    )


def storyboard_rules(reg):
    node = reg.get("nodes", {}).get("CREATIVE_BLUEPRINT", {})
    return node.get("validation", {})



def project_duration_override(proj):
    """从项目状态读 PROJECT_CHARTER 声明的目标时长；未声明返回 None（不检查）。"""
    candidates = (
        "workflow_state.json",
        "project_charter.json",
        "PROJECT_CHARTER.md",
        os.path.join("artifacts", "project", "A_PROJECT_CHARTER.md"),
    )
    for cand in candidates:
        p = os.path.join(proj, cand)
        if not os.path.isfile(p):
            continue
        try:
            if cand.endswith(".json"):
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                for container in (data, data.get("charter", {}), data.get("project_charter", {})):
                    if not isinstance(container, dict):
                        continue
                    for key in ("target_total_duration_seconds", "target_duration_seconds", "duration_seconds"):
                        if container.get(key) is not None:
                            return container[key]
            else:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        m = re.search(
                            r"(?:target_total_duration_seconds|target_duration_seconds|目标时长)"
                            r"[\s|:=]*([0-9]+(?:\.[0-9]+)?)",
                            line,
                        )
                        if m:
                            return float(m.group(1))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def creative_preload_skills():
    """从创作路由单一事实源读取 CREATIVE_BLUEPRINT 的必读 skill。"""
    import yaml
    try:
        with open(CREATIVE_ROUTE_TABLE, encoding="utf-8") as handle:
            route_table = yaml.safe_load(handle) or {}
        route = route_table["routes"]["CREATIVE_BLUEPRINT"]
        skills = route.get("common", {}).get("skill", [])
        if not isinstance(skills, list) or not skills:
            raise ValueError("CREATIVE_BLUEPRINT.common.skill 为空")
        return [str(skill) for skill in skills]
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f"BLOCKED:G_CREATIVE_READY:创作路由表不可用（{exc}）")
        return None


def check_creative_preload(proj, entry_type=DEFAULT_ENTRY_TYPE):
    """2026-08-20 P1.3：G_CREATIVE_READY 预读检查——写分镜前必须先读创作方法论。
    FULL_SERVICE 强制；CLIENT_COPY/SINGLE_VIDEO 不要求补交导演预读记录。"""
    if entry_type in {"CLIENT_COPY", "SINGLE_VIDEO"}:
        return True
    cands = [
        os.path.join(proj, "_预读_CREATIVE_BLUEPRINT.md"),
        os.path.join(proj, "guard", "_预读_CREATIVE_BLUEPRINT.md"),
        os.path.join(proj, "节点5_预读_CREATIVE_BLUEPRINT.md"),
    ]
    pre = next((p for p in cands if os.path.isfile(p)), None)
    if pre is None:
        print("BLOCKED:G_CREATIVE_READY:缺少创作预读记录 _预读_CREATIVE_BLUEPRINT.md（写分镜前必须先读 director-thinking 方法论）")
        print("  请先 read_file 读 wiki/spec/CREATIVE_ROUTE_TABLE.yaml 对应 skill（director-thinking 等），再写预读记录文件。")
        return False
    try:
        with open(pre, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        content = ""
    required_skills = creative_preload_skills()
    if required_skills is None:
        return False
    missing = [
        skill for skill in required_skills
        if not re.search(rf"(?<![\w-]){re.escape(skill)}(?![\w-])", content)
    ]
    if missing:
        print(
            f"BLOCKED:G_CREATIVE_READY:预读记录 {os.path.basename(pre)} "
            f"缺少必读 skill：{','.join(missing)}"
        )
        return False
    return True


def check_prompt_scope(proj):
    """2026-08-20 P1.4：scope_guard——把闸的产物范围从「文件名含分镜」扩到
    「一切投喂模型的 prompt 文件」。验收用例：镜5执行脚本（手势缺失/缺声音字段/微动作0类别）必须 BLOCK。
    只扫描与创作 prompt 相关的文件，避免误伤知识库/接力文档。"""
    scope = []
    for root, _, files in os.walk(proj):
        for name in files:
            if not name.lower().endswith((".md", ".txt", ".py")):
                continue
            if not re.search(r"(prompt|提示词|分镜|执行脚本|shot|镜)", name, re.I):
                continue
            rel_path = os.path.relpath(os.path.join(root, name), proj)
            if re.search(
                    r"(接力|复盘|校验|知识库|index|大纲|简报|素材|进度|"
                    r"archive|归档|废弃|旧版|deprecated|(?:^|[._-])bak(?:[._-]|$)|"
                    r"(?:^|/)导演评审报告|^guard/director_review/|transcript)",
                    rel_path,
                    re.I):
                continue
            scope.append(os.path.join(root, name))
    if not scope:
        return True
    suggestions = []
    unreadable = []
    for p in scope:
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError as exc:
            unreadable.append(f"{os.path.basename(p)}: 无法读取（{exc}）")
            continue
        if not re.search(r"(手|指|掌|臂|腕|拳)", content):
            suggestions.append(f"{os.path.basename(p)}: 建议补充与台词绑定的手势/肢体动作")
        if not SILENT_SHOT_RE.search(content) and not re.search(
                r"(声音|语气|语调|旁白|口播|语速)", content):
            suggestions.append(f"{os.path.basename(p)}: 建议补充声音字段，或明确标注无对白/纯画面")
        if not re.search(r"(情绪|表情|动作|神态|微表情|肢体)", content):
            suggestions.append(f"{os.path.basename(p)}: 建议补充可见的表情、动作或神态")
    if unreadable:
        print("BLOCKED:G_CREATIVE_READY:创作 prompt 文件无法读取:")
        for item in unreadable:
            print(f"  - {item}")
        return False
    if suggestions:
        print("WARN:G_CREATIVE_READY:创作 prompt 改写建议:", file=sys.stderr)
        for item in suggestions:
            print(f"  - {item}", file=sys.stderr)
    return True


def creative_scope_config():
    """读取创作路由表中 scope_guard 的产物与文件名范围。"""
    import yaml
    try:
        with open(CREATIVE_ROUTE_TABLE, encoding="utf-8") as handle:
            route_table = yaml.safe_load(handle) or {}
        guard = route_table["routes"]["CREATIVE_BLUEPRINT"]["scope_guard"]
        artifact_ids = guard.get("applies_to_artifacts", [])
        patterns = guard.get("filename_patterns", [])
        exclude_path_prefixes = guard.get("exclude_path_prefixes", [])
        if (not isinstance(artifact_ids, list) or not isinstance(patterns, list)
                or not patterns or not isinstance(exclude_path_prefixes, list)):
            raise ValueError("scope_guard 配置无效")
        return (
            [str(value) for value in artifact_ids],
            [str(value) for value in patterns],
            [str(value) for value in exclude_path_prefixes],
        )
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f"BLOCKED:G_CREATIVE_READY:创作 scope_guard 路由不可用（{exc}）")
        return None


def locate_creative_prompt_files(proj, reg=None):
    """定位所有应进入意图闸的创作文件；路由表范围是单一事实源。"""
    scope = creative_scope_config()
    if scope is None:
        return None
    artifact_ids, patterns, exclude_path_prefixes = scope
    reg = reg or load_registry()
    matches = set()
    state = load_state(proj)

    for artifact_id in artifact_ids:
        path = state_artifact_path(proj, reg, artifact_id, state)
        if path and os.path.isfile(path):
            matches.add(os.path.realpath(path))

    excluded = re.compile(
        r"(接力|复盘|校验|知识库|index|大纲|简报|素材|进度|"
        r"archive|归档|废弃|旧版|deprecated|(?:^|[._-])bak(?:[._-]|$)|"
        r"^(?:briefs|tasks)/|(?:^|/)导演评审报告)",
        re.I,
    )
    normalized_prefixes = [
        prefix.replace("\\", "/").lstrip("./")
        for prefix in exclude_path_prefixes
        if prefix.replace("\\", "/").lstrip("./")
    ]
    for root, _, files in os.walk(proj):
        for name in files:
            path = os.path.join(root, name)
            rel_path = os.path.relpath(path, proj).replace(os.sep, "/")
            if excluded.search(rel_path):
                continue
            if any(
                    rel_path == prefix.rstrip("/") or rel_path.startswith(prefix)
                    for prefix in normalized_prefixes):
                continue
            folded_path = rel_path.casefold()
            route_match = any(
                fnmatch.fnmatchcase(folded_path, pattern.replace("\\", "/").casefold())
                or (
                    pattern.replace("\\", "/").startswith("**/")
                    and fnmatch.fnmatchcase(
                        folded_path, pattern.replace("\\", "/")[3:].casefold()
                    )
                )
                for pattern in patterns
            )
            storyboard_fallback = (
                name.lower().endswith((".md", ".txt"))
                and re.search(r"(storyboard|分镜)", name, re.I)
            )
            if route_match or storyboard_fallback:
                matches.add(os.path.realpath(path))
    return sorted(matches)



def check_director_intent(proj, reg=None):
    """2026-08-20 P2.2/P2.3：导演意图四维评审——LLM 当评委查非机械问题。
    action_tie/high 立即 BLOCK；其余维度保持 WARN。"""
    creative_files = locate_creative_prompt_files(proj, reg)
    if creative_files is None:
        return False
    if not creative_files:
        return True
    # 2026-08-21 广州机优化同步：全目录可能扫到历史版本，只评审最新 3 个（当前版本优先）。
    creative_files = sorted(
        creative_files,
        key=lambda path: os.path.getmtime(path),
        reverse=True,
    )[:3]
    report_dir = os.path.join(proj, "guard", "director_review")
    os.makedirs(report_dir, exist_ok=True)
    summary_report = os.path.join(proj, "导演评审报告.md")
    review_results = []
    action_tie_blocked = False
    for creative_file in creative_files:
        stem = os.path.splitext(os.path.basename(creative_file))[0]
        report = os.path.join(report_dir, f"导演评审报告_{stem}.md")
        try:
            rc = subprocess.run(
                [sys.executable, "/home/ubuntu/workflow/scripts/director_review_scorer.py",
                 creative_file, "--out", report],
                capture_output=True, text=True, timeout=180,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            review_results.append((creative_file, report, None, f"{type(exc).__name__}: {exc}"))
            print(
                f"WARN:G_CREATIVE_READY:意图闸运行异常（{os.path.basename(creative_file)}；"
                f"{type(exc).__name__}: {exc}），本次不拦截",
                file=sys.stderr,
            )
            continue
        out = (rc.stdout or "") + (rc.stderr or "")
        review_results.append((creative_file, report, rc.returncode, out))
        if rc.returncode == 4 or "INTENT_BLOCK:action_tie:high" in out:
            action_tie_blocked = True
            continue
        if rc.returncode == 2:
            print(
                "WARN:G_CREATIVE_READY:导演意图评审发现非 action_tie/high 问题"
                f"（{os.path.basename(creative_file)}，暂不拦截）:",
                file=sys.stderr,
            )
            for line in out.splitlines():
                if line.strip() and not line.startswith("意图闸") and not line.startswith("OUTPUT"):
                    print(f"  {line}", file=sys.stderr)
            continue
        if rc.returncode != 0:
            print(
                f"WARN:G_CREATIVE_READY:意图闸运行异常（{os.path.basename(creative_file)}；"
                f"rc={rc.returncode}），本次不拦截",
                file=sys.stderr,
            )
    with open(summary_report, "w", encoding="utf-8") as handle:
        handle.write("# 导演意图评审汇总\n\n")
        for creative_file, per_file_report, returncode, output in review_results:
            handle.write(f"## {os.path.relpath(creative_file, proj)}\n\n")
            handle.write(f"- 返回码: {returncode if returncode is not None else '运行异常'}\n")
            handle.write(f"- 独立报告: {os.path.relpath(per_file_report, proj)}\n\n")
            if os.path.isfile(per_file_report):
                with open(per_file_report, encoding="utf-8", errors="ignore") as source:
                    handle.write(source.read().strip() + "\n\n")
            elif output.strip():
                handle.write("```text\n" + output.strip() + "\n```\n\n")
    if action_tie_blocked:
        print("BLOCKED:G_CREATIVE_READY:动作-台词绑定存在 high 级问题（详见导演评审报告）")
        return False
    return True


def locate_storyboard(proj, reg=None):
    """注册表路径优先；否则扫描，且只接受唯一命中。"""
    reg = reg or load_registry()
    registered = artifact_path(proj, reg, "A_STORYBOARD")
    if registered and os.path.isfile(registered):
        return registered
    matches = []
    for root, _, files in os.walk(proj):
        for name in files:
            if name.endswith(".md") and re.search(r"(storyboard|分镜)", name, re.I):
                matches.append(os.path.join(root, name))
    if len(matches) > 1:
        print("BLOCKED:G_CREATIVE_READY:分镜文件多命中，须登记 A_STORYBOARD 或只保留唯一候选：")
        for path in sorted(matches):
            print(f"  - {path}")
        return None
    return matches[0] if matches else None


def locate_character_generation_records(proj, reg=None):
    """定位角色生图记录：优先 A_GENERATED_ASSETS，兼容旧节点8记录。"""
    reg = reg or load_registry()
    state = load_state(proj)
    registered = state_artifact_path(proj, reg, "A_GENERATED_ASSETS", state)
    if registered and os.path.isfile(registered):
        return [registered]

    candidates = []
    name_re = re.compile(
        r"A_GENERATED_ASSETS|(?:节点\s*8|node\s*8).*(?:生图|图像|记录)|"
        r"(?:角色|人物).*(?:生图|生成|提示词|记录)", re.I
    )
    for root, _, files in os.walk(proj):
        for name in files:
            if name_re.search(name) and name.lower().endswith((".md", ".txt", ".json", ".yaml", ".yml")):
                candidates.append(os.path.join(root, name))
    return sorted(set(candidates))


def character_reference_sections(content):
    """只取角色参考图段落，避免场景图/普通素材触发三视图检查。"""
    headings = list(re.finditer(r"^(?P<marks>#{1,6})\s+.*$", content, re.M))
    sections = []
    for index, heading in enumerate(headings):
        level = len(heading.group("marks"))
        end = len(content)
        for following in headings[index + 1:]:
            if len(following.group("marks")) <= level:
                end = following.start()
                break
        block = content[heading.start():end]
        if CHARACTER_REFERENCE_RE.search(block):
            sections.append(block)
    if sections:
        return sections
    return [content] if CHARACTER_REFERENCE_RE.search(content) else []


def has_three_view_elements(text):
    angles_ok = bool(
        THREE_VIEW_RE.search(text) or
        (FRONT_VIEW_RE.search(text) and SIDE_VIEW_RE.search(text) and EXTRA_VIEW_RE.search(text))
    )
    face_closeup_ok = bool(FACE_CLOSEUP_RE.search(text) and CLOSEUP_RE.search(text))
    return angles_ok and bool(CHINESE_LABEL_RE.search(text)) and face_closeup_ok


def check_three_view_structure(proj, reg=None):
    """角色参考图必须有三视图、中文标注和脸部特写；非角色素材不检查。"""
    reg = reg or load_registry()
    records = locate_character_generation_records(proj, reg)
    role_sections = []
    for path in records:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            role_sections.extend((path, section) for section in character_reference_sections(handle.read()))

    if not role_sections:
        prompt_path = state_artifact_path(proj, reg, "A_PROMPT_PACKAGE")
        character_expected = False
        if prompt_path and os.path.isfile(prompt_path):
            with open(prompt_path, encoding="utf-8", errors="ignore") as handle:
                character_expected = bool(CHARACTER_REFERENCE_RE.search(handle.read()))
        if character_expected:
            print("BLOCKED:G_RENDER_READY:已使用角色参考图/@图1，但未找到角色生图记录")
            return False
        return True

    invalid = [path for path, section in role_sections if not has_three_view_elements(section)]
    if invalid:
        names = "、".join(sorted({os.path.basename(path) for path in invalid}))
        print(
            "BLOCKED:G_RENDER_READY:角色参考图记录缺少三视图结构"
            "（需多角度/三视图、中文标注、脸部特写）：" + names
        )
        return False
    return True


def has_visible_content(path):
    """产物是否有可见正文：文件存在且去掉空白后仍有字符。"""
    if not path or not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8", errors="ignore") as handle:
        return bool(handle.read().strip())


def check_produced_by_codex(proj):
    """智力产物存在性 + 非空校验。

    2026-08-17 天行者定案删除产物首部的执行者标注后，原先的
    `执行者/produced_by/producer/author: codex|claude|cc` 首部正则已永久失效
    （标注不再写入，校验只会全量误杀）。本函数改为只验「文件存在 + 可见内容 > 0」；
    执行通道真实性（codex/claude/cc vs DS）由 wrapper 层负责，不在本脚本校验。
    """
    state = load_state(proj)
    artifacts = state.get("artifacts", {})
    if not artifacts:
        strategy_pattern = re.compile(r"(策略|分析|方案|洞察|拆解|复盘|评估|计划|打法|画像)", re.I)
        for root, _, files in os.walk(proj):
            for name in files:
                if not name.endswith(".md") or not strategy_pattern.search(name):
                    continue
                if not has_visible_content(os.path.join(root, name)):
                    print(f"BLOCKED: {name} 智力产物缺失或为空（须由 codex/claude 执行通道产出）")
                    return False
        return True
    for aid in STRATEGY_ARTIFACTS:
        if aid not in artifacts:
            continue
        value = artifacts[aid]
        path = value if isinstance(value, str) else value.get("path", "")
        if not has_visible_content(path):
            print(f"BLOCKED: {aid} 智力产物缺失或为空（须由 codex/claude 执行通道产出）")
            return False
    return True


def check_client_context_loaded(
        session_client_id=None, session_context_loaded=None):
    """会话级门：调用方必须已绑定 client_id 且已加载该客户 OVERVIEW。

    生产调用方从自己的会话对象取值后，通过参数传入。仅当两个参数都未传时，
    才允许 DEV_GATE_* 环境变量作为开发/单会话测试兼容路径，并明确告警。
    """
    cid = session_client_id or ""
    loaded = session_context_loaded is True
    if session_client_id is None and session_context_loaded is None:
        dev_cid = os.environ.get("DEV_GATE_BOUND_CLIENT_ID")
        dev_loaded = os.environ.get("DEV_GATE_CONTEXT_LOADED")
        if dev_cid is not None or dev_loaded is not None:
            print(
                "DEV_MODE:G_CLIENT_CONTEXT_LOADED:使用进程环境变量，仅限开发/单会话测试",
                file=sys.stderr,
            )
            cid = dev_cid or ""
            loaded = dev_loaded == "1"
    if not cid or not loaded:
        print(
            "BLOCKED:G_CLIENT_CONTEXT_LOADED:客户上下文未加载；需显式传入当前会话的 "
            "session_client_id/session_context_loaded（CLI: --client CID --context-loaded 1）"
        )
        return False
    return True


def parse_storyboard_rows(content):
    rows, header = [], None
    for line in content.splitlines():
        if not re.match(r"^\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if header is None and any(re.search(r"时长|duration", c, re.I) for c in cells):
            header = cells
            continue
        if cells:
            shot_id = re.fullmatch(r"(?:镜(?:头)?\s*|S)(\d+)", cells[0], re.I)
            if shot_id:
                rows.append((shot_id.group(1), cells, line))
    return header, rows


def parse_seedance_shots(content):
    """解析“镜头N”或“S01”标题下的 text prompt/四层 Seedance 分镜。"""
    shots = []
    headings = list(re.finditer(
        r"^##\s*(?:镜头\s*(?P<legacy>\d+)|S(?P<semantic>\d+))\s*[｜|](?P<title>.*?)\s*$",
        content, re.M))
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        section = content[match.end():end]
        duration_match = re.search(r"(?P<duration>\d+(?:\.\d+)?)\s*秒\s*$", match.group("title"))
        if not duration_match:
            duration_match = re.search(
                r"时码/时长.*?/\s*(?P<duration>\d+(?:\.\d+)?)\s*(?:秒|s)\b",
                section,
                re.I,
            )
        if not duration_match:
            range_match = re.search(
                r"(?P<start>\d+(?:\.\d+)?)\s*[—-]\s*(?P<end>\d+(?:\.\d+)?)",
                match.group("title") + "\n" + section,
            )
            duration = (
                float(range_match.group("end")) - float(range_match.group("start"))
                if range_match else None
            )
        else:
            duration = float(duration_match.group("duration"))
        prompt_match = re.search(r"```text\s*\n(.*?)\n```", section, re.S | re.I)
        four_layer = all(f"### {layer}" in section for layer in ("第一层", "第二层", "第三层", "第四层"))
        prompt = prompt_match.group(1) if prompt_match else (section.strip() if four_layer else "")
        if duration is not None and prompt:
            shots.append((match.group("legacy") or match.group("semantic"), duration, prompt))
    return shots


PART_CATEGORIES = {
    "眼眉": r"眼睑|眼神|瞳孔|眉心|眉头|眉毛|目光|视线|泪光|额头|眼睛",
    "嘴脸": r"嘴唇|嘴角|笑肌|鼻翼|鼻尖|脸颊",
    "呼吸喉颈": r"呼吸|吞咽|喉结|胸腔",
    "手": r"指尖|手指|食指|手腕|手掌",
    "肩颔": r"肩部|肩|下颔|下颌",
}
ACTION_RE = re.compile(r"抬升|抬起|轻收|下落|舒展|轻压|点头|收紧|上扬|落回|下移|回到|放松|直视|轻呼|指向|收回|阻挡|轻点")


def emotion_categories(text):
    """部位词必须与动作词在同一短句共现，裸部位不计数。"""
    found = set()
    for clause in re.split(r"[，,；;。]", text):
        if not ACTION_RE.search(clause):
            continue
        for category, pattern in PART_CATEGORIES.items():
            if re.search(pattern, clause):
                found.add(category)
    return found


def speech_errors(num, text):
    errors = []
    quoted = re.findall(r'"([^"\n]*)"', text)
    if not quoted:
        return [f"镜{num}: 缺少英文双引号包裹的台词"]
    for speech in quoted:
        count = len(re.sub(r"[\s，。！？、,.!?；;：:]", "", speech))
        if count < 2:
            errors.append(f"镜{num}: 台词为空或少于2字")
    return errors


def dialogue_exempt(text, is_talking_head=False):
    """明确标注的非口播纯画面镜可无台词。"""
    return not is_talking_head and bool(SILENT_SHOT_RE.search(text))


def check_storyboard(proj, reg=None):
    reg = reg or load_registry()
    sb_path = locate_storyboard(proj, reg)
    if not sb_path:
        print("BLOCKED:G_CREATIVE_READY:分镜脚本不存在或定位不唯一（A_STORYBOARD）")
        return False
    with open(sb_path, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    reference_bindings_ok = (
        reference_has_use(content, 1, r"人物|身份|东亚女性", require_path=True) and
        reference_has_use(content, 2, r"场景|咖啡馆|空间", require_path=True)
    )
    header, parsed_rows = parse_storyboard_rows(content)
    rows = parsed_rows if header and len(header) >= 8 else []
    seedance = [] if rows else parse_seedance_shots(content)
    if not rows and not seedance:
        print(f"BLOCKED:G_CREATIVE_READY:分镜脚本无法解析出8列表格或Seedance四层镜头（{os.path.basename(sb_path)}）")
        return False
    vague_words = ["开心地", "难过地", "愤怒地", "满意地", "惊讶地", "自然地", "很开心",
                   "显得很", "情绪：", "情绪:", "表情开心", "表情难过", "表情愤怒", "表情满意", "表情惊讶",
                   "笑一下"]
    bad = []
    total_duration = 0.0
    is_talking_head = bool(re.search(r"口播", content))
    rules = storyboard_rules(reg)
    max_shot = float(rules.get("max_shot_duration_seconds", 15))
    # 2026-09-29 闸本体修复（§6.1-2）：书面标准（AGENTS.md 第九节 / 快乐马 r2v 官方上限）
    # 是单段 3–15s、15 为硬上限；「口播单段 ≤10s」是闸自造的冲突口径，统一到 15。
    # 生产 registry 候选路径的 talking_head_max_shot_duration_seconds 同步 10->15（见 registry patch）。
    talking_head_max = float(rules.get("talking_head_max_shot_duration_seconds", 15))
    for num, cells, raw in rows:
        body = " | ".join(cells)
        positive = strip_negative_cells(raw)
        nonempty = len([c for c in cells if c.strip()])
        if nonempty < 8:
            bad.append(f"镜{num}: 表格非空列数不足8列（现有{nonempty}列）")
        duration_index = next((i for i, c in enumerate(header or []) if re.search(r"时长|duration", c, re.I)), None)
        duration_cell = cells[duration_index] if duration_index is not None and duration_index < len(cells) else ""
        durations = [float(v) for v in re.findall(r"(\d+(?:\.\d+)?)\s*(?:秒|s\b)", duration_cell, re.I)]
        if not durations:
            bad.append(f"镜{num}: 缺时长")
        else:
            total_duration += durations[0]
            limit = talking_head_max if is_talking_head or re.search(r"口播", body) else max_shot
            if max(durations) > limit:
                bad.append(f"镜{num}: 单镜时长{max(durations):g}s超过上限{limit}s")
        shot_is_talking_head = is_talking_head or bool(re.search(r"口播", body))
        dialogue_cells = [c for c in cells if re.search(r"台词|对白", c)]
        if dialogue_exempt(body, shot_is_talking_head):
            pass
        elif not dialogue_cells:
            bad.append(f"镜{num}: 缺台词")
        else:
            dialogue_text = " ".join(dialogue_cells)
            quoted = re.findall(r'"([^"]*)"', dialogue_text)
            residual = re.sub(r'"[^"]*"', "", dialogue_text)
            residual = re.sub(r"^(?:台词|对白)\s*[：:]?\s*", "", residual).strip()
            if not quoted or residual:
                bad.append(f"镜{num}: 台词必须完整使用英文双引号包裹")
            for speech in quoted:
                count = len(re.sub(r"[\s，。！？、,.!?；;：:]", "", speech))
                if count < 2:
                    bad.append(f"镜{num}: 台词为空或少于2字")
        if not re.search(r"(画面|动作|手势|景别|近景|中近景|特写|露出|人物|机位|平视)", body):
            bad.append(f"镜{num}: 缺画面/动作描述")
        hit_categories = emotion_categories(positive)
        if len(hit_categories) < 2:
            bad.append(f"镜{num}: 情绪描述不足（部位+动作共现类别<2个，现有: {sorted(hit_categories)}）")
        for word in vague_words:
            if word in positive:
                bad.append(f"镜{num}: 使用笼统情绪词「{word}」，须改为具体微动作")
                break
    for num, duration, prompt in seedance:
        total_duration += duration
        positive = strip_negative_cells(prompt)
        for layer in ("第一层", "第二层", "第三层", "第四层"):
            if layer not in prompt:
                bad.append(f"镜{num}: 缺Seedance{layer}")
        if not (reference_bindings_ok and
                reference_has_use(prompt, 1, r"人物|身份|东亚女性") and
                reference_has_use(prompt, 2, r"场景|咖啡馆|空间")):
            bad.append(f"镜{num}: @图1/@图2未分别绑定人物与场景用途")
        if re.search(r"同上|沿用前镜|使用全局锁定层|参照前镜|前镜一致", prompt):
            bad.append(f"镜{num}: 使用跨镜缩写")
        if "第四层：负面约束" not in prompt or not NEGATIVE_LABEL_RE.search(prompt):
            bad.append(f"镜{num}: 缺负面约束区")
        limit = talking_head_max if is_talking_head or re.search(r"口播", prompt) else max_shot
        if duration > limit:
            bad.append(f"镜{num}: 单镜时长{duration:g}s超过上限{limit:g}s")
        shot_is_talking_head = is_talking_head or bool(re.search(r"口播", prompt))
        if not dialogue_exempt(prompt, shot_is_talking_head):
            bad.extend(speech_errors(num, prompt))
        cats = emotion_categories(positive)
        if len(cats) < 2:
            bad.append(f"镜{num}: 情绪描述不足（部位+动作共现类别<2个，现有: {sorted(cats)}）")
    # 2026-08-20 P0.2：时长检查参数化——目标时长可来自项目状态（PROJECT_CHARTER），
    # 注册表为 null 且项目未声明时不检查（不再硬编码 30s±1s）
    target_duration = rules.get("target_total_duration_seconds")
    try:
        raw_tolerance = rules.get("total_duration_tolerance_seconds", 1)
        if isinstance(raw_tolerance, bool):
            raise ValueError
        duration_tolerance = float(raw_tolerance)
        if duration_tolerance < 0:
            raise ValueError
    except (TypeError, ValueError):
        bad.append("total_duration_tolerance_seconds 必须是非负数")
        duration_tolerance = 0.0
    if target_duration is None:
        target_duration = project_duration_override(proj)
    if target_duration is not None:
        try:
            if isinstance(target_duration, bool):
                raise ValueError
            target_duration = float(target_duration)
            if target_duration <= 0:
                raise ValueError
        except (TypeError, ValueError):
            bad.append("PROJECT_CHARTER 的目标时长必须是正数")
        else:
            if not target_duration - duration_tolerance <= total_duration <= target_duration + duration_tolerance:
                bad.append(
                    f"总时长{total_duration:g}s不在目标{target_duration:g}s±{duration_tolerance:g}s范围"
                )
    if bad:
        print(f"BLOCKED:G_CREATIVE_READY:分镜不合格（{os.path.basename(sb_path)}，共{len(rows) + len(seedance)}镜）:")
        for item in bad:
            print(f"  - {item}")
        return False
    track = "8列表格" if rows else "Seedance四层"
    print(f"分镜合格：{len(rows) + len(seedance)} 镜全部通过（{track}/台词/时长/画面/情绪微动作）")
    return True


def check_voice(proj, reg=None):
    sb_path = locate_storyboard(proj, reg or load_registry())
    if not sb_path:
        return False
    with open(sb_path, encoding="utf-8", errors="ignore") as f:
        content = f.read()
    header, rows = parse_storyboard_rows(content)
    clauses = []
    if rows:
        # 2026-09-29 闸本体修复（§6.1-1）：旧实现只认表头命中「声音|语音|voice|audio」的列，
        # 而标准 8 列分镜表的列名是「说话人|台词」，于是 voice_indexes 恒为空、
        # 本函数在标准格式上从未真正生效。现在：声音承载列扩到 VOICE_COLUMN_RE；
        # 并兜底纳入任何含「语速/配音/语气/音色/人声」的单元格（声音指令可能写在画面动作/连续性列）。
        voice_indexes = [
            i for i, cell in enumerate(header or [])
            if VOICE_COLUMN_RE.search(cell)
        ]
        for _, cells, _ in rows:
            selected = [cells[i] for i in voice_indexes if i < len(cells)]
            selected += [c for c in cells if VOICE_HINT_CELL_RE.search(c)]
            clauses.extend(selected)
    # 兜底（2026-09-29）：huolong 标准 8 列模板首列是「时段」而非「镜号」，
    # parse_storyboard_rows 认不出这些行；因此无论 8 列行是否被识别，都把所有表格行里
    # 含声音指令的单元格纳入扫描，保证「说话人|台词」布局也真正被覆盖。
    for _line in content.splitlines():
        if _line.count("|") < 2:
            continue
        for _cell in _line.strip().strip("|").split("|"):
            if VOICE_HINT_CELL_RE.search(_cell):
                clauses.append(_cell)
    else:
        for _, _, prompt in parse_seedance_shots(content):
            positive = strip_negative_cells(prompt)
            clauses.extend(
                clause for clause in re.split(r"[。；;\n]", positive)
                if re.search(r"声音|人声|语速|节奏|吐字|speed", clause, re.I)
            )
    positive_voice = "\n".join(clauses)
    # “禁止语速快”等否定要求不是正向声音指令，整段否定子句剔除。
    positive_voice = re.sub(
        NEGATED_PREFIX_RE.pattern + r"[^，,；;。\n|]*", "", positive_voice
    )
    if FAST_VOICE_RE.search(positive_voice):
        print("BLOCKED:G_CREATIVE_READY:分镜含正向快速语速/节奏描述（须用「语速适中，吐字清晰」）")
        return False
    return True


SIX_CHECKS_CANDIDATES = (
    "/home/ubuntu/.hermes/skills/newmedia-operations/huolong-replica-template/scripts/huolong_six_checks.py",
    "/home/ubuntu/workflow/projects/rules_fix_20260929/work/gate_fix/patched/home/ubuntu/.hermes/skills/newmedia-operations/huolong-replica-template/scripts/huolong_six_checks.py",
)
MULTI_SEGMENT_RE = re.compile(r"段\s*[2-9]")


def six_checks_script():
    return next((p for p in SIX_CHECKS_CANDIDATES if os.path.isfile(p)), None)


def _is_multi_segment(proj, reg=None):
    """六项判据的 ①③④ 面向「多段/双人」片；单段片没有段间衔接表/台词分配表，不该被误拦。

    判据用脚本自身的段标记（段2..段9），与 huolong_six_checks.py 的解析口径一致；
    单段片返回 False -> 闸打印 SKIP，不拦。
    """
    sb = locate_storyboard(proj, reg or load_registry())
    if not sb:
        return False
    with open(sb, encoding="utf-8", errors="ignore") as f:
        return bool(MULTI_SEGMENT_RE.search(f.read()))


def _run_six_checks(cmd, target, gate_id, extra=None):
    """按闸该有的方式调六项判据：脚本缺失 fail-closed（拒绝），FAIL 即 BLOCKED。"""
    checker = six_checks_script()
    if not checker:
        print(f"BLOCKED:{gate_id}:六项判据脚本 huolong_six_checks.py 不在受管路径（fail-closed）")
        return False
    args = [sys.executable, checker, cmd, target] + list(extra or [])
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        print(f"BLOCKED:{gate_id}:六项判据 {cmd} 超时（fail-closed）")
        return False
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if out:
        print(out)
    if r.returncode != 0:
        print(f"BLOCKED:{gate_id}:六项判据 {cmd} FAIL（退出码 {r.returncode}）")
        return False
    return True


def check_huolong_six_storyboard(proj, reg=None):
    """①③④文本层 + ②写法层：分镜阶段硬判（2026-09-29 用户批）。单段片 SKIP。"""
    if not _is_multi_segment(proj, reg):
        print("SKIP:六项判据 storyboard：非多段片（无「段2..」段标记），①③④ 不适用")
        return True
    return _run_six_checks("storyboard", proj, "G_CREATIVE_READY")


def check_huolong_six_subtitle(proj):
    """⑤字幕同音占位：成片阶段硬判；项目内找到的每个 .ass 都要过。没有 .ass -> SKIP。"""
    import glob as _glob
    ass = sorted(set(_glob.glob(os.path.join(proj, "**", "*.ass"), recursive=True)))
    if not ass:
        print("SKIP:六项判据 subtitle：项目里没有 .ass 字幕文件")
        return True
    ok = True
    for path in ass:
        if not _run_six_checks("subtitle", path, "G_TECHNICAL_QC_PASS"):
            ok = False
    return ok


def run_legacy(proj, pairs):
    for script, gate in pairs:
        result = subprocess.run(
            ["python3", os.path.join(SCRIPTS, script), "check", proj, gate],
            capture_output=True, text=True)
        if result.returncode != 0:
            print(f"BLOCKED:{gate}:{result.stdout.strip() or result.stderr.strip()}")
            return False
    return True


def record_gate(proj, reg, gate_id, status_value, node_id=None,
                cycle_id=None, piece_id=None, reason=None):
    state = load_state(proj)
    node_id = node_id or node_for_gate(reg, gate_id)[0]
    node = reg.get("nodes", {}).get(node_id, {}) if node_id else {}
    approved = status_value == ALLOWED_STATUS
    skipped = status_value == SKIPPED_STATUS
    cycle_id, piece_id = gate_context(gate_id, cycle_id, piece_id)
    hashes = {}
    for aid in node.get("required_artifacts", node.get("produces", [])):
        path = artifact_path(proj, reg, aid)
        hashes[aid] = sha256(path) if approved and path else None
    record = {
        "gate_id": gate_id,
        "cycle_id": cycle_id,
        "piece_id": piece_id,
        "status": ALLOWED_STATUS if approved else (SKIPPED_STATUS if skipped else None),
        "artifact_hashes": hashes,
        "node": node_id,
    }
    if reason:
        record["reason"] = reason
    upsert_gate_record(state, record)
    save_state(proj, state)


def approved_record_is_current(proj, reg, gate_id, record):
    """只识别 approve 命令写入的审批记录，不改变存量 ALLOWED 记录的复检行为。"""
    if not record or record.get("status") != ALLOWED_STATUS:
        return False
    if not record.get("approval_by") or not record.get("approved_at"):
        return False
    _, node = node_for_gate(reg, gate_id)
    if not node:
        return False
    expected_hashes = record.get("artifact_hashes", {})
    for aid in node.get("produces", []):
        path = artifact_path(proj, reg, aid)
        expected = expected_hashes.get(aid)
        if expected is None or sha256(path) != expected:
            return False
    return True


def approve(proj, gate_id, approval_by, evidence):
    """人工审批放行；重复审批覆盖同一项目级门禁记录。"""
    reg = load_registry()
    if gate_id not in reg.get("gates", {}):
        print(f"BLOCKED:{gate_id}:未知 gate_id")
        return 2
    if not approval_by or not approval_by.strip():
        print(f"BLOCKED:{gate_id}:审批人不能为空")
        return 2
    if not os.path.isfile(evidence):
        print(f"BLOCKED:{gate_id}:审批证据不存在 ({evidence})")
        return 2
    if os.path.getsize(evidence) == 0:
        print(f"BLOCKED:{gate_id}:审批证据为空 ({evidence})")
        return 2

    node_id, node = node_for_gate(reg, gate_id)
    if not node:
        print(f"BLOCKED:{gate_id}:注册表中缺少对应生产节点")
        return 2

    # 审批必须锁定 produces 中每个产物的实际字节版本，禁止写入空哈希。
    hashes = {}
    for aid in node.get("produces", []):
        path = artifact_path(proj, reg, aid)
        digest = sha256(path) if path else None
        if digest is None:
            print(f"BLOCKED:{gate_id}:无法计算产物哈希 {aid} ({path})")
            return 2
        hashes[aid] = digest

    state = load_state(proj)
    cycle_id, piece_id = gate_context(gate_id)
    record = {
        "gate_id": gate_id,
        "cycle_id": cycle_id,
        "piece_id": piece_id,
        "status": ALLOWED_STATUS,
        "artifact_hashes": hashes,
        "node": node_id,
        "approval_by": approval_by.strip(),
        "approved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evidence": os.path.abspath(evidence),
        "evidence_sha256": sha256(evidence),
    }
    upsert_gate_record(state, record)
    save_state(proj, state)
    print(ALLOWED_STATUS)
    return 0


def check_artifacts(proj, reg, gate_id, node):
    artifact_ids = node.get("required_artifacts", node.get("produces", []))
    for aid in artifact_ids:
        path = artifact_path(proj, reg, aid)
        if not path or not os.path.isfile(path):
            print(f"BLOCKED:{gate_id}:缺产物 {aid} ({path})")
            return False
        minimum = MIN_MD_BYTES if path.lower().endswith(".md") else 0
        size = os.path.getsize(path)
        if size <= minimum:
            print(f"BLOCKED:{gate_id}:产物为空或过短 {aid} ({size}字节，须>{minimum}字节)")
            return False
    return True


def artifact_producer_gate(reg, artifact_id):
    for node in reg.get("nodes", {}).values():
        if artifact_id in node.get("produces", []):
            return node.get("exit_gate")
    return None


def gate_display_order(reg, gate_id):
    _, node = node_for_gate(reg, gate_id)
    return node.get("display_order") if node else None


def entry_route(reg, entry_type, gate_id):
    """返回 NORMAL、SKIP 或 BLOCK，集中定义四类入口的门禁路由。"""
    if entry_type == "FULL_SERVICE":
        return "NORMAL"
    if entry_type == "TEST_RUN":
        if gate_id == DELIVERY_GATE:
            return "BLOCK"
        return "NORMAL" if gate_id == TECHNICAL_GATE else "SKIP"
    if gate_id == "G_PROJECT_AUTHORIZED":
        return "NORMAL"
    order = gate_display_order(reg, gate_id)
    creative_order = gate_display_order(reg, CREATIVE_START_GATE)
    if order is not None and order < creative_order:
        return "SKIP"
    return "NORMAL"


def check_project_authorization(proj, reg, gate_id):
    """旁路入口仍须验证项目级授权门及授权登记文件的获批哈希。"""
    state = load_state(proj)
    record = get_gate_record(state, "G_PROJECT_AUTHORIZED") or {}
    if record.get("status") != ALLOWED_STATUS:
        print(f"BLOCKED:{gate_id}:项目授权门 G_PROJECT_AUTHORIZED 未获批")
        return False
    artifact_id = "A_AUTHORIZATION_REGISTER"
    expected = record.get("artifact_hashes", {}).get(artifact_id)
    path = state_artifact_path(proj, reg, artifact_id, state)
    actual = sha256(path) if path else None
    if expected is None or actual != expected:
        print(f"BLOCKED:{gate_id}:项目授权登记 {artifact_id} 缺获批哈希或已变化")
        return False
    return True


def client_copy_record(state, cycle_id=None, piece_id=None):
    for record in state.get("entry_inputs", []):
        if (record.get("artifact_id"), record.get("cycle_id"), record.get("piece_id")) == (
                "A_COPY_FINAL", cycle_id, piece_id):
            return record
    return None


def check_and_lock_client_copy(proj, reg, gate_id, cycle_id=None, piece_id=None):
    """首次通过合规检查后锁定客户原文；之后任意字节变化均阻断。"""
    state = load_state(proj)
    path = state_artifact_path(proj, reg, "A_COPY_FINAL", state)
    actual = sha256(path) if path else None
    if actual is None:
        print(f"BLOCKED:{gate_id}:客户文案 A_COPY_FINAL 不存在（{path}）")
        return False
    record = client_copy_record(state, cycle_id, piece_id)
    if record is None:
        state.setdefault("entry_inputs", []).append({
            "artifact_id": "A_COPY_FINAL",
            "cycle_id": cycle_id,
            "piece_id": piece_id,
            "sha256": actual,
            "path": os.path.relpath(path, proj),
        })
        save_state(proj, state)
        return True
    if record.get("sha256") != actual:
        print(f"BLOCKED:{gate_id}:客户文案 A_COPY_FINAL 哈希不符（原文已被改动）")
        return False
    return True


def locate_test_video_master(proj, reg, state):
    explicit = state_artifact_path(proj, reg, "A_VIDEO_MASTER", state)
    artifact_value = state.get("artifacts", {}).get("A_VIDEO_MASTER")
    has_explicit_path = isinstance(artifact_value, str) or (
        isinstance(artifact_value, dict) and bool(artifact_value.get("path"))
    )
    if has_explicit_path or (explicit and os.path.isfile(explicit)):
        return explicit
    candidates = []
    for root, _, files in os.walk(os.path.join(proj, "artifacts")):
        for name in files:
            if "A_VIDEO_MASTER" in name and name.lower().endswith(".mp4"):
                candidates.append(os.path.join(root, name))
    return candidates[0] if len(candidates) == 1 else None


def check_test_video_master(proj, reg, gate_id):
    state = load_state(proj)
    path = locate_test_video_master(proj, reg, state)
    if not path or not os.path.isfile(path):
        print(f"BLOCKED:{gate_id}:TEST_RUN 缺 A_VIDEO_MASTER 或文件定位不唯一")
        return False
    if not os.path.basename(path).startswith("_TEST"):
        print(f"BLOCKED:{gate_id}:TEST_RUN 的 A_VIDEO_MASTER 文件名必须以 _TEST 开头")
        return False
    return True


def bypass_upstream_gate(reg, entry_type, producer_gate):
    return entry_route(reg, entry_type, producer_gate) == "SKIP"


def check_upstream_hashes(proj, reg, gate_id, node, cycle_id=None, piece_id=None,
                          entry_type=DEFAULT_ENTRY_TYPE):
    """下游开门前确认上游获批版本未被篡改。"""
    state = load_state(proj)
    for aid in node.get("requires", []):
        producer_gate = artifact_producer_gate(reg, aid)
        if not producer_gate:
            print(f"BLOCKED:{gate_id}:上游产物 {aid} 无生产节点")
            return False
        if bypass_upstream_gate(reg, entry_type, producer_gate):
            continue
        gate_record = get_gate_record(state, producer_gate, cycle_id, piece_id) or {}
        if gate_record.get("status") != ALLOWED_STATUS:
            print(f"BLOCKED:{gate_id}:上游门 {producer_gate} 未获批（status != ALLOWED）")
            return False
        expected = gate_record.get("artifact_hashes", {}).get(aid)
        path = artifact_path(proj, reg, aid)
        actual = sha256(path) if path else None
        if expected is None:
            print(f"BLOCKED:{gate_id}:上游产物 {aid} 尚无获批哈希（{producer_gate}）")
            return False
        if actual != expected:
            print(f"BLOCKED:{gate_id}:上游产物 {aid} 哈希不符（{producer_gate} 获批版本已变化）")
            return False
    return True


def manual_checks(reg, gate_id):
    checks = reg.get("gates", {}).get(gate_id, {}).get("checks", [])
    return [item.get("id") for item in checks
            if isinstance(item, dict) and item.get("manual") is True]


def has_implemented_checks(reg, gate_id):
    checks = reg.get("gates", {}).get(gate_id, {}).get("checks", [])
    return any(isinstance(item, dict) and item.get("implemented") is True for item in checks)


def check(proj, gate_id, cycle_id=None, piece_id=None,
          session_client_id=None, session_context_loaded=None):
    # 会话级门不依赖项目注册表，也不写项目状态；必须在加载任何项目级数据前判定。
    if gate_id == "G_CLIENT_CONTEXT_LOADED":
        if not check_client_context_loaded(
                session_client_id=session_client_id,
                session_context_loaded=session_context_loaded):
            return 2
        print(ALLOWED_STATUS)
        return 0

    reg = load_registry()
    node_id, node = node_for_gate(reg, gate_id)

    def blocked(reason=None):
        if reason:
            print(f"BLOCKED:{gate_id}:{reason}")
        else:
            print(f"BLOCKED:{gate_id}:门禁检查未通过（具体原因见上方）")
        record_gate(proj, reg, gate_id, "BLOCKED", node_id, cycle_id, piece_id)
        return 2

    if gate_id not in reg["gates"]:
        return blocked("未知 gate_id")
    state = load_state(proj)
    entry_type = state["entry_type"]
    route = entry_route(reg, entry_type, gate_id)
    if route == "SKIP":
        reason = f"{entry_type} 跳过该门"
        record_gate(proj, reg, gate_id, SKIPPED_STATUS, node_id,
                    cycle_id, piece_id, reason)
        print(f"SKIPPED:{gate_id}:{entry_type}")
        return 0
    if route == "BLOCK":
        print(f"BLOCKED:{gate_id}:TEST_RUN 禁止进入交付出口")
        return blocked()
    approved_record = get_gate_record(state, gate_id, cycle_id, piece_id)
    if approved_record_is_current(proj, reg, gate_id, approved_record):
        print(ALLOWED_STATUS)
        return 0
    if entry_type == "TEST_RUN" and gate_id == TECHNICAL_GATE:
        if not check_test_video_master(proj, reg, gate_id):
            return blocked()
    if entry_type in {"CLIENT_COPY", "SINGLE_VIDEO"} and gate_id != "G_PROJECT_AUTHORIZED":
        if not check_project_authorization(proj, reg, gate_id):
            return blocked()
        if not run_legacy(proj, ENTRY_COMPLIANCE_CHECKS):
            return blocked()
        if entry_type == "CLIENT_COPY" and not check_and_lock_client_copy(
                proj, reg, gate_id, cycle_id, piece_id):
            return blocked()
    manual = manual_checks(reg, gate_id)
    has_implemented = has_implemented_checks(reg, gate_id)
    if manual and not has_implemented:
        print(f"MANUAL_REVIEW_REQUIRED:{gate_id}:{','.join(manual)}")
        record_gate(proj, reg, gate_id, "MANUAL_REVIEW_REQUIRED", node_id,
                    cycle_id, piece_id)
        return 3
    if node and node.get("requires") and not check_upstream_hashes(
            proj, reg, gate_id, node, cycle_id, piece_id, entry_type):
        return blocked()
    if LEGACY_MAP.get(gate_id) and not run_legacy(proj, LEGACY_MAP[gate_id]):
        return blocked()
    if gate_id == "G_STRATEGY_BY_CODEX" and not check_produced_by_codex(proj):
        return blocked()
    if gate_id == "G_CREATIVE_READY":
        # 2026-08-20 P1.3/P1.4：预读检查 + prompt 范围检查（架构修复）
        if not check_creative_preload(proj, entry_type) or not check_prompt_scope(proj):
            return blocked()
        # action_tie/high 强制拦截；其余意图维度仍处于 WARN 阶段。
        if not check_director_intent(proj, reg):
            return blocked()
        if not check_storyboard(proj, reg) or not check_voice(proj, reg):
            return blocked()
        # 2026-09-29 闸本体修复（§6.1-4）：把 huolong_six_checks.py 的 ①③④文本层+②写法层
        # 接进 G_CREATIVE_READY，六项不再靠人主动跑（⑤字幕在 G_TECHNICAL_QC_PASS 判）。
        if not check_huolong_six_storyboard(proj, reg):
            return blocked()
    # 2026-09-29 闸本体修复（§6.1-4）：成片阶段判 ⑤ 字幕同音占位（烧字幕前那道物理卡点
    # huolong_sub_gate.sh 仍在合成脚本里，两道同源、以同一脚本为准，不冲突）。
    if gate_id == "G_TECHNICAL_QC_PASS" and not check_huolong_six_subtitle(proj):
        return blocked()
    if gate_id == "G_RENDER_READY" and not check_three_view_structure(proj, reg):
        return blocked()
    if node and not check_artifacts(proj, reg, gate_id, node):
        return blocked()
    if manual:
        print(f"MANUAL_REVIEW_REQUIRED:{gate_id}:{','.join(manual)}")
        record_gate(proj, reg, gate_id, "MANUAL_REVIEW_REQUIRED", node_id,
                    cycle_id, piece_id)
        return 3
    record_gate(proj, reg, gate_id, "ALLOWED", node_id, cycle_id, piece_id)
    print("ALLOWED")
    return 0


def status(proj):
    state = load_state(proj)
    print(f"项目: {state['project_id']}")
    print(f"入口类型: {state['entry_type']}")
    print(f"活动节点: {state['active_node_id']}")
    print("产物状态:")
    for aid, info in state.get("artifacts", {}).items():
        if isinstance(info, dict):
            print(f"  {aid}: v{info.get('version')} {info.get('status')}")
        else:
            print(f"  {aid}: {info}")
    print("门禁状态:")
    for info in state.get("gates", []):
        scope = f"cycle={info.get('cycle_id') or '-'}, piece={info.get('piece_id') or '-'}"
        print(f"  {info.get('gate_id')} [{scope}]: {info.get('status')}")


def parse_check_context(args):
    cycle_id = None
    piece_id = None
    session_client_id = None
    session_context_loaded = None
    index = 0
    aliases = {"--cycle": "cycle", "--cycle-id": "cycle",
               "--piece": "piece", "--piece-id": "piece",
               "--client": "client", "--context-loaded": "context_loaded"}
    while index < len(args):
        flag = args[index]
        if flag not in aliases or index + 1 >= len(args):
            raise ValueError(
                "check 可选参数为 --cycle <cycle_id> --piece <piece_id> "
                "--client <cid> --context-loaded <0|1>"
            )
        value = args[index + 1]
        if aliases[flag] == "cycle":
            cycle_id = value
        elif aliases[flag] == "piece":
            piece_id = value
        elif aliases[flag] == "client":
            session_client_id = value
        else:
            if value not in {"0", "1"}:
                raise ValueError("--context-loaded 只接受 0 或 1")
            session_context_loaded = value == "1"
        index += 2
    return cycle_id, piece_id, session_client_id, session_context_loaded


def parse_approve_options(args):
    """解析 approve 的必填选项，严格拒绝重复或未知参数。"""
    values = {}
    aliases = {"--by": "approval_by", "--evidence": "evidence"}
    index = 0
    while index < len(args):
        flag = args[index]
        if flag not in aliases or index + 1 >= len(args):
            raise ValueError("approve 需要 --by <审批人> --evidence <路径>")
        key = aliases[flag]
        if key in values:
            raise ValueError(f"approve 参数重复: {flag}")
        values[key] = args[index + 1]
        index += 2
    if set(values) != set(aliases.values()):
        raise ValueError("approve 需要 --by <审批人> --evidence <路径>")
    return values["approval_by"], values["evidence"]


def main():
    try:
        if len(sys.argv) < 3:
            print("BLOCKED:CLI:缺少命令或项目目录")
            print(__doc__)
            return 2
        cmd, proj = sys.argv[1], sys.argv[2]
        if cmd == "check":
            if len(sys.argv) < 4:
                print(
                    "BLOCKED:CLI:check 需要 <项目目录> <gate_id> [--cycle ID] [--piece ID] "
                    "[--client CID] [--context-loaded 0|1]"
                )
                return 2
            cycle_id, piece_id, client_id, context_loaded = parse_check_context(sys.argv[4:])
            return check(
                proj, sys.argv[3], cycle_id, piece_id,
                session_client_id=client_id,
                session_context_loaded=context_loaded,
            )
        if cmd == "status":
            if len(sys.argv) != 3:
                print("BLOCKED:CLI:status 只接受 <项目目录>")
                return 2
            status(proj)
            return 0
        if cmd == "approve":
            if len(sys.argv) < 7:
                print("BLOCKED:CLI:approve 需要 <项目目录> <gate_id> --by <审批人> --evidence <路径>")
                return 2
            approval_by, evidence = parse_approve_options(sys.argv[4:])
            return approve(proj, sys.argv[3], approval_by, evidence)
        print(f"BLOCKED:CLI:未知命令 {cmd}")
        print(__doc__)
        return 2
    except Exception as exc:
        print(f"BLOCKED:CLI:{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
