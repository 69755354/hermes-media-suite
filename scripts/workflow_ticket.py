#!/usr/bin/env python3
"""Hermes 节点票据：节点顺序、persona 注入与产物签收的文件级物理闸。

用法:
  workflow_ticket.py open <TRACK.NODE_ID> [--project DIR] [--session SID]
  workflow_ticket.py close <TRACK.NODE_ID> --artifact PATH [--artifact PATH ...]
  workflow_ticket.py skip <TRACK.NODE_ID> --reason REASON
  workflow_ticket.py status [--project DIR]
  workflow_ticket.py classify <原始需求文本>
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import yaml


REPO_ROOT = "/home/ubuntu/workflow"
NODE_MAP = os.path.join(REPO_ROOT, "wiki/spec/HERMES_NODE_MAP.yaml")
WORKFLOW_GATE = os.environ.get(
    "WORKFLOW_TICKET_WORKFLOW_GATE",
    os.path.join(REPO_ROOT, "scripts/workflow_gate.py"),
)
TICKETS_DIR = os.path.join(REPO_ROOT, "guard/tickets")
LEDGER_NAME = "ticket_ledger.jsonl"
TICKET_TTL_SECONDS = 86400   # 2026-10-04 客户授权：票期 2h → 24h
MIN_ARTIFACT_BYTES = 200
# 2026-08-17 天行者定案：产物不再要求执行者标注。此正则仅用于兼容剥离旧产物中的历史标注行。
EXECUTOR_RE = re.compile(
    r"^\s*>\s*执行者\s*[：:]\s*(codex|claude|DS|人)\s*$", re.I | re.M
)
SESSION_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
WORKFLOW_GATE_RE = re.compile(r"workflow_gate\.py\s*:\s*(G_[A-Z0-9_]+)")

# 对外交付正文禁止泄露内部实现信息。执行者首行在扫描前单独剔除，
# 否则“必须有执行者标注”和“对外禁执行器名”会形成不可满足的契约。
EXTERNAL_FORBIDDEN = (
    (re.compile(r"/home/ubuntu/"), "服务器内部路径 /home/ubuntu/"),
    (re.compile(r"(?:^|\s|`)MEDIA\s*[:/]", re.I | re.M), "MEDIA 内部前缀"),
    (re.compile(r"T-(?:CONTENT|ORCHESTRA|ATTRIBUTION|DECISION|OPS)(?:\.[A-Z0-9_]+)?", re.I),
     "内部轨名或节点号"),
    (re.compile(r"(?:huoshan#)?节点\s*\d+", re.I), "内部节点号"),
    (re.compile(r"(?<![A-Za-z])(codex|claude|DeepSeek|DS)(?![A-Za-z])", re.I), "执行器名"),
)


def utc_now():
    """返回稳定、可排序的 UTC 时间。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path):
    """流式计算文件 SHA-256。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_node_map():
    with open(NODE_MAP, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("tracks"), dict):
        raise ValueError("HERMES_NODE_MAP.yaml 缺少 tracks")
    return data


def locate_node(node_map, qualified_id):
    """按全限定 ID 返回 (轨名, 轨配置, 节点短 ID, 节点配置)。"""
    if "." not in qualified_id:
        return None
    track, node_id = qualified_id.split(".", 1)
    track_spec = node_map.get("tracks", {}).get(track)
    if not isinstance(track_spec, dict):
        return None
    node = track_spec.get("nodes", {}).get(node_id)
    if not isinstance(node, dict):
        return None
    return track, track_spec, node_id, node


def project_path(value=None):
    return os.path.abspath(value or os.getcwd())


def ledger_path(project):
    return os.path.join(project, LEDGER_NAME)


def resolve_session(value=None):
    session = value or os.environ.get("HERMES_SESSION_ID") or "manual"
    if not SESSION_RE.fullmatch(session):
        raise ValueError("session 只能包含字母、数字、点、下划线和连字符")
    return session


def ticket_path(session):
    return os.path.join(TICKETS_DIR, f"{session}.json")


def read_ledger(project):
    """完整读取 JSONL；损坏的审计台账不得静默忽略。"""
    path = ledger_path(project)
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"台账第 {line_number} 行损坏: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"台账第 {line_number} 行不是对象")
            records.append(record)
    return records


def latest_node_states(records):
    states = {}
    for record in records:
        node_id = record.get("node_id")
        if node_id:
            states[node_id] = record
    return states


def append_ledger(project, record):
    """用追加锁保证多个会话不会把 JSONL 行写穿。"""
    os.makedirs(project, exist_ok=True)
    path = ledger_path(project)
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_json_write(path, payload):
    """同目录临时文件 + replace，避免 guard 读到半张票据。"""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ticket-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def absolute_repo_path(path):
    return path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)


def validate_nonempty_file(path, label):
    if not os.path.isfile(path):
        print(f"NEED_INFO: {label}不存在 {path}")
        return False
    if os.path.getsize(path) == 0:
        print(f"NEED_INFO: {label}为空 {path}")
        return False
    return True


def upstream_ready(record):
    if not record:
        return False
    if record.get("status") == "closed":
        return True
    return record.get("status") == "skipped" and record.get("human_confirmed") is True


def upstream_workflow_gates(node_map, node):
    """取 requires 对应的既有统一门禁；ticket_close/旧适配器不伪装成 G_*。"""
    gates = []
    for required_id in node.get("requires", []):
        located = locate_node(node_map, required_id)
        if not located:
            raise ValueError(f"上游节点未在 NODE_MAP 定义: {required_id}")
        exit_gate = str(located[3].get("exit_gate", ""))
        for gate_id in WORKFLOW_GATE_RE.findall(exit_gate):
            if gate_id not in gates:
                gates.append(gate_id)
    return gates


def run_upstream_gates(project, gates):
    if gates and not os.path.isfile(WORKFLOW_GATE):
        print(f"NEED_INFO: 统一门禁脚本不存在 {WORKFLOW_GATE}")
        return 1
    for gate_id in gates:
        result = subprocess.run(
            [sys.executable, WORKFLOW_GATE, "check", project, gate_id],
            capture_output=True,
            text=True,
            check=False,
        )
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if result.returncode != 0:
            if output:
                print(output)
            elif result.returncode == 3:
                print(f"MANUAL_REVIEW_REQUIRED:{gate_id}:上游门禁待人工复核")
            else:
                print(f"BLOCKED:{gate_id}:上游门禁检查失败")
            return result.returncode
    return 0


def project_brief_path(track_spec, project):
    configured = track_spec.get("project_brief")
    if configured:
        return absolute_repo_path(configured)
    candidate = os.path.join(project, "BRIEF.md")
    return candidate if os.path.isfile(candidate) else None


def command_open(args):
    node_map = load_node_map()
    located = locate_node(node_map, args.node)
    if not located:
        print(f"BLOCKED: 节点不存在 {args.node}")
        return 1
    track, track_spec, _, node = located
    project = project_path(args.project)
    if not os.path.isdir(project):
        print(f"NEED_INFO: 项目目录不存在 {project}")
        return 1

    states = latest_node_states(read_ledger(project))
    missing_upstream = [item for item in node.get("requires", []) if not upstream_ready(states.get(item))]
    if missing_upstream:
        print(f"BLOCKED: {args.node} 缺少已签收上游: {', '.join(missing_upstream)}")
        return 2

    persona = absolute_repo_path(str(node.get("persona", "")))
    if node.get("persona_status") == "pending_create":
        print(f"NEED_INFO: persona 未建 {persona}")
        return 1
    if not validate_nonempty_file(persona, "persona"):
        return 1

    if track_spec.get("project_brief_status") == "pending_create":
        brief = project_brief_path(track_spec, project)
        print(f"NEED_INFO: 项目简报未建 {brief or track_spec.get('project_brief')}")
        return 1

    deps = [absolute_repo_path(str(path)) for path in node.get("deps", [])]
    missing = [path for path in deps if not os.path.isfile(path) or os.path.getsize(path) == 0]
    if missing:
        for path in missing:
            print(f"NEED_INFO: 依赖文档不存在或为空 {path}")
        return 1

    if track in {"T-CONTENT", "T-OPS"}:
        gate_rc = run_upstream_gates(project, upstream_workflow_gates(node_map, node))
        if gate_rc != 0:
            return gate_rc

    brief = project_brief_path(track_spec, project)
    if brief and not validate_nonempty_file(brief, "项目简报"):
        return 1

    session = resolve_session(args.session)
    opened_at = utc_now()
    dep_records = [{"path": path, "sha": sha256(path)} for path in deps]
    ticket = {
        "track": track,
        "node_id": args.node,
        "persona_sha": sha256(persona),
        "deps": dep_records,
        "deps_unread": [],
        "project": project,
        "session_id": session,
        "opened_at": opened_at,
        "ttl": TICKET_TTL_SECONDS,
        "status": "opened",
    }
    atomic_json_write(ticket_path(session), ticket)
    append_ledger(project, {
        "event": "opened",
        "status": "opened",
        "track": track,
        "node_id": args.node,
        "session_id": session,
        "project": project,
        "opened_at": opened_at,
        "persona_sha": ticket["persona_sha"],
        "deps": dep_records,
        "ttl": TICKET_TTL_SECONDS,
    })

    with open(persona, encoding="utf-8") as handle:
        persona_text = handle.read()
    print(f"【轨:{track}｜节点:{args.node.split('.', 1)[1]}】")
    print("=== PERSONA BEGIN ===")
    print(persona_text, end="" if persona_text.endswith("\n") else "\n")
    print("=== PERSONA END ===")
    print("=== 依赖文档清单 ===")
    if deps:
        for item in dep_records:
            print(f"- {item['path']} sha256={item['sha']}")
    else:
        print("- （无）")
    print("=== 项目简报 ===")
    if brief:
        with open(brief, encoding="utf-8") as handle:
            brief_text = handle.read()
        print(brief_text, end="" if brief_text.endswith("\n") else "\n")
    else:
        print("（未配置项目简报）")
    print(f"OUTPUT: {ticket_path(session)}")
    return 0


def load_ticket_file(path):
    with open(path, encoding="utf-8") as handle:
        ticket = json.load(handle)
    if not isinstance(ticket, dict):
        raise ValueError("票据内容不是对象")
    return ticket


def find_ticket(node_id, session=None, project=None):
    """优先当前会话；CLI 无会话时才按节点选择最新票据。"""
    candidates = []
    if session:
        explicit = ticket_path(resolve_session(session))
        if os.path.isfile(explicit):
            candidates.append(explicit)
    else:
        env_session = os.environ.get("HERMES_SESSION_ID")
        preferred = ticket_path(resolve_session(env_session))
        if os.path.isfile(preferred):
            candidates.append(preferred)
        if os.path.isdir(TICKETS_DIR):
            candidates.extend(
                os.path.join(TICKETS_DIR, name)
                for name in os.listdir(TICKETS_DIR)
                if name.endswith(".json") and os.path.join(TICKETS_DIR, name) not in candidates
            )
    matches = []
    wanted_project = project_path(project) if project else None
    for path in candidates:
        try:
            ticket = load_ticket_file(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if ticket.get("node_id") != node_id:
            continue
        if wanted_project and os.path.abspath(str(ticket.get("project", ""))) != wanted_project:
            continue
        matches.append((os.path.getmtime(path), path, ticket))
    return max(matches, default=(None, None, None), key=lambda item: item[0])


def read_artifact_text(path):
    with open(path, "rb") as handle:
        raw = handle.read()
    return raw.decode("utf-8", errors="ignore")


def validate_artifact(path, external=False):
    absolute = os.path.abspath(path)
    if not os.path.isfile(absolute):
        return None, f"产物不存在 {absolute}"
    size = os.path.getsize(absolute)
    if size < MIN_ARTIFACT_BYTES:
        return None, f"产物过短 {absolute}（{size}字节，须≥{MIN_ARTIFACT_BYTES}字节）"
    text = read_artifact_text(absolute)
    # 2026-08-17 天行者定案：产物不要求执行者标注。旧产物若有则剥离后走脱敏，没有则直接脱敏。
    if external:
        body = EXECUTOR_RE.sub("", text, count=1) if EXECUTOR_RE.search(text) else text
        for pattern, label in EXTERNAL_FORBIDDEN:
            match = pattern.search(body)
            if match:
                return None, f"对外交付脱敏失败（{label}: {match.group(0)}） {absolute}"
    return {"path": absolute, "sha256": sha256(absolute), "bytes": size}, None


def command_close(args):
    node_map = load_node_map()
    located = locate_node(node_map, args.node)
    if not located:
        print(f"BLOCKED: 节点不存在 {args.node}")
        return 1
    track, _, _, node = located
    _, path, ticket = find_ticket(args.node, args.session, args.project)
    if not ticket:
        print(f"BLOCKED: {args.node} 未找到活动票据")
        return 2
    if ticket.get("status") != "opened":
        print(f"BLOCKED: {args.node} 票据状态不是 opened")
        return 2

    artifacts = []
    for artifact in args.artifact:
        record, error = validate_artifact(
            artifact, external=node.get("output_class") == "external_delivery"
        )
        if error:
            print(f"BLOCKED: {args.node}: {error}")
            return 2
        artifacts.append(record)

    closed_at = utc_now()
    project = os.path.abspath(ticket["project"])
    ledger_record = {
        "event": "closed",
        "status": "closed",
        "track": track,
        "node_id": args.node,
        "session_id": ticket.get("session_id"),
        "project": project,
        "opened_at": ticket.get("opened_at"),
        "closed_at": closed_at,
        "artifacts": artifacts,
    }
    append_ledger(project, ledger_record)
    ticket.update({"status": "closed", "closed_at": closed_at, "artifacts": artifacts})
    atomic_json_write(path, ticket)
    print("OUTPUT: " + ", ".join(item["path"] for item in artifacts))
    return 0


def command_skip(args):
    node_map = load_node_map()
    located = locate_node(node_map, args.node)
    if not located:
        print(f"BLOCKED: 节点不存在 {args.node}")
        return 1
    track, _, _, _ = located
    _, path, ticket = find_ticket(args.node, args.session, args.project)
    project = project_path(args.project or (ticket or {}).get("project"))
    if not os.path.isdir(project):
        print(f"NEED_INFO: 项目目录不存在 {project}")
        return 1
    session = (ticket or {}).get("session_id") or resolve_session(args.session)
    skipped_at = utc_now()
    risk = "跳过该节点可能使下游缺少必要输入或质量保障"
    record = {
        "event": "skipped",
        "status": "skipped",
        "track": track,
        "node_id": args.node,
        "session_id": session,
        "project": project,
        "skipped_at": skipped_at,
        "reason": args.reason.strip(),
        "risk": risk,
        "human_confirmed": False,
    }
    append_ledger(project, record)
    if ticket and path:
        ticket.update(record)
        atomic_json_write(path, ticket)
    print(f"MANUAL_REVIEW_REQUIRED:{args.node}:跳节点待人工确认；原因={args.reason.strip()}；风险={risk}")
    return 3


def command_status(args):
    project = project_path(args.project)
    if not os.path.isdir(project):
        print(f"NEED_INFO: 项目目录不存在 {project}")
        return 1
    records = read_ledger(project)
    states = latest_node_states(records)
    print(f"项目: {project}")
    if not states:
        print("票据状态: 暂无")
        return 0
    print("票据状态:")
    for node_id in sorted(states):
        record = states[node_id]
        detail = ""
        if record.get("status") == "skipped":
            detail = f" human_confirmed={str(record.get('human_confirmed') is True).lower()}"
        print(f"  {node_id}: {record.get('status')}{detail}")
    return 0


def keyword_values(state_spec):
    values = []
    for condition in state_spec.get("any_of", []):
        if isinstance(condition, dict):
            values.extend(condition.get("keyword_any", []) or [])
    return values


def classify_text(node_map, text):
    """按 triggers 计分；同分时用轨提示词，仍同分则交 INTAKE。"""
    scored = []
    order = 0
    for track, track_spec in node_map.get("tracks", {}).items():
        for node_id, node in track_spec.get("nodes", {}).items():
            hits = [trigger for trigger in node.get("triggers", []) if trigger and trigger.lower() in text.lower()]
            if hits:
                # 长触发词信息量更高；命中数量次之。
                score = sum(len(item) for item in hits) * 100 + len(hits)
                scored.append((score, order, track, f"{track}.{node_id}", hits))
            order += 1
    scored.sort(key=lambda item: (-item[0], item[1]))

    classify_spec = node_map.get("classify", {})
    hints = classify_spec.get("track_hints", {})
    track_scores = {}
    for track, words in hints.items():
        if not track.startswith("T-") or not isinstance(words, list):
            continue
        track_scores[track] = sum(len(word) for word in words if word.lower() in text.lower())
    candidate_nodes = [item[3] for item in scored]
    if scored:
        top_score = scored[0][0]
        top_tracks = {item[2] for item in scored if item[0] == top_score}
        if len(top_tracks) == 1:
            track = next(iter(top_tracks))
        else:
            best_hint = max((track_scores.get(item, 0), item) for item in top_tracks)
            if best_hint[0] > 0 and sum(track_scores.get(item, 0) == best_hint[0] for item in top_tracks) == 1:
                track = best_hint[1]
            else:
                tie = hints.get("tie_breaker", "T-ORCHESTRA.INTAKE")
                track = tie.split(".", 1)[0]
                candidate_nodes.insert(0, tie)
    else:
        track = max(track_scores, key=track_scores.get) if any(track_scores.values()) else None

    state_specs = classify_spec.get("states", {})
    external_words = keyword_values(state_specs.get("external_delivery", {}))
    internal_words = keyword_values(state_specs.get("internal_interaction", {}))
    artifact_words = ("写", "实现", "制作", "生成", "产出", "报告", "文档", "脚本", "方案", "交付")
    external_candidate = any(
        locate_node(node_map, item[3])[3].get("output_class") == "external_delivery"
        for item in scored
    )
    if any(word.lower() in text.lower() for word in external_words) or external_candidate:
        state = "external_delivery"
    elif scored or any(word in text for word in artifact_words):
        state = "workflow"
    elif any(word.lower() in text.lower() for word in internal_words):
        state = "internal_interaction"
    else:
        state = "internal_interaction"

    mode = None
    if track == "T-DECISION":
        mode = "full" if any(word in text for word in ("策略", "决策", "分析", "方案", "方向")) else "card"
    matched = [
        {"node": item[3], "triggers": item[4], "score": item[0]}
        for item in scored
    ]
    return {
        "state": state,
        "track": track,
        "candidate_nodes": candidate_nodes,
        "mode": mode,
        "matched": matched,
    }


def command_classify(args):
    result = classify_text(load_node_map(), args.text)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Hermes 节点票据文件级物理闸")
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser("open", help="校验上游并打开节点票据")
    open_parser.add_argument("node", help="全限定节点 ID，如 T-CONTENT.DECONSTRUCT")
    open_parser.add_argument("--project", help="项目目录，默认当前目录")
    open_parser.add_argument("--session", help="Hermes 会话 ID，默认取 HERMES_SESSION_ID")
    open_parser.set_defaults(handler=command_open)

    close_parser = subparsers.add_parser("close", help="校验并签收节点产物")
    close_parser.add_argument("node")
    close_parser.add_argument("--artifact", action="append", required=True, help="产物路径，可重复")
    close_parser.add_argument("--project", help=argparse.SUPPRESS)
    close_parser.add_argument("--session", help=argparse.SUPPRESS)
    close_parser.set_defaults(handler=command_close)

    skip_parser = subparsers.add_parser("skip", help="申报跳过节点并进入人工复核")
    skip_parser.add_argument("node")
    skip_parser.add_argument("--reason", required=True)
    skip_parser.add_argument("--project", help=argparse.SUPPRESS)
    skip_parser.add_argument("--session", help=argparse.SUPPRESS)
    skip_parser.set_defaults(handler=command_skip)

    status_parser = subparsers.add_parser("status", help="列出项目票据状态")
    status_parser.add_argument("--project", help="项目目录，默认当前目录")
    status_parser.set_defaults(handler=command_status)

    classify_parser = subparsers.add_parser("classify", help="判定三态、轨与候选节点")
    classify_parser.add_argument("text")
    classify_parser.set_defaults(handler=command_classify)
    return parser


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if getattr(args, "reason", None) is not None and not args.reason.strip():
            print("NEED_INFO: skip 原因不能为空")
            return 1
        return args.handler(args)
    except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"BLOCKED:CLI:{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
