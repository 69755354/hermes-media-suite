#!/usr/bin/env python3
"""confirm_gate.py — 客户确认闸（TTL + 产物哈希绑定）。

用法：
  confirm_gate.py check <项目目录> <确认点> [产物路径或sha256]
  confirm_gate.py confirm <项目目录> <确认点> <客户原话> [产物路径或sha256]
  confirm_gate.py skip <项目目录> [产物路径或sha256]
  confirm_gate.py status <项目目录>

TTL 由 CONFIRM_TTL_SECONDS 配置，默认 86400 秒（24 小时）。
可选产物参数一旦在 confirm 时提供，check 必须提供当前同一产物；哈希变化即重新确认。

存量兼容策略：
- 旧记录无 expires_at：以旧 at + 当前 TTL 作为一次性宽限，到期后必须重确认。
- 旧记录无 artifact_sha：check 未传产物时在宽限期内继续有效；check 传了产物时
  fail-closed，要求重确认并建立绑定。这样不会在部署瞬间误伤现有调用，又不会把
  新接入 artifact 参数的调用静默降级成无绑定。

2026-08-23 R7 返工（补上轮「条件 PASS」的残留绕闸口）：
- 上轮实测序列：confirm 绑定产物 → 改产物 → check 带产物 rc=2（对）→
  **check 不带产物 rc=0（错，放行）**。根因是 check_bound_record 只在
  `current_sha is not None` 时才比对，调用方省一个参数即可瓦解「改分镜即失效」。
- 本次改为：记录里**已经绑定过** artifact_sha 时，check 必须提供产物，否则
  fail-closed 拒绝。未绑定过的旧记录行为不变（保住存量宽限，不在部署瞬间误伤）。
- 即「绑定是单向棘轮」：一旦某确认点建立了产物绑定，之后就不能退回无绑定校验。
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

DEFAULT_TTL_SECONDS = 24 * 60 * 60

CONFIRM_POINTS = {
    "node4_copy": {
        "desc": "文案确认",
        "prompt": "发文案给客户，问「需要修改不？」",
        "accept": ["不用改", "可以", "行", "就这样", "ok", "好的", "没问题", "可以了", "定"],
    },
    "node8_image": {
        "desc": "生图风格确认",
        "prompt": "发预览图给客户，确认风格",
        "accept": ["可以", "行", "就这样", "ok", "好的", "没问题", "风格可以", "对"],
    },
    "node12_render": {
        "desc": "出片确认",
        "prompt": "问客户「开始出片？」",
        "accept": ["跑", "出", "开始", "可以", "行", "上", "搞", "发"],
    },
}

SKIP_WORDS = ["跳过确认", "不用给我看", "直接出片", "不用确认", "跳过这些", "不用问了", "直接来", "别问了"]
REJECT_WORDS = ["不行", "不用", "不要", "不好", "不对", "不合适", "改一下", "再改", "换一个", "重来", "重新", "有问题", "不对吧", "不是", "别", "等等"]
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def ttl_seconds():
    raw = os.environ.get("CONFIRM_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_TTL_SECONDS
    return value if value > 0 else DEFAULT_TTL_SECONDS


def state_path(project):
    return os.path.join(project, "CONFIRM.json")


def default_state():
    return {"confirmed": {}, "skip_mode": False}


def load_state(project):
    path = state_path(project)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                state = json.load(handle)
            if isinstance(state, dict):
                state.setdefault("confirmed", {})
                state.setdefault("skip_mode", False)
                if isinstance(state["confirmed"], dict):
                    return state
        except (OSError, ValueError):
            pass
    return default_state()


def save_state(project, state):
    target = state_path(project)
    directory = os.path.dirname(target)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".CONFIRM.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def artifact_sha256(value):
    value = (value or "").strip()
    if not value:
        return None
    if SHA256_RE.fullmatch(value):
        return value.lower()
    path = Path(value)
    if not path.is_file():
        raise ValueError(f"绑定产物不存在或不是文件: {value}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def legacy_expiry(record, timestamp_field="at"):
    """旧记录用原确认时间 + TTL 形成一次性宽限；无法解析则 fail-closed。"""
    raw = record.get(timestamp_field)
    if not isinstance(raw, str):
        return None
    try:
        confirmed_at = time.mktime(time.strptime(raw, "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError, OverflowError):
        return None
    return int(confirmed_at + ttl_seconds())


def record_expiry(record, timestamp_field="at"):
    value = record.get("expires_at")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return legacy_expiry(record, timestamp_field=timestamp_field)


def check_bound_record(record, current_sha, timestamp_field="at"):
    if not isinstance(record, dict):
        return False, "旧确认记录格式无效，需重新确认"
    expires_at = record_expiry(record, timestamp_field=timestamp_field)
    if expires_at is None:
        return False, "确认记录缺少有效时间，需重新确认"
    if time.time() >= expires_at:
        return False, "确认已过期，需重新确认"

    stored_sha = record.get("artifact_sha") or record.get("scope")
    if current_sha is not None:
        if not stored_sha:
            return False, "旧确认未绑定产物；当前已启用产物校验，需重新确认"
        if stored_sha != current_sha:
            return False, "确认绑定的产物已变化，需重新确认"
        return True, ""

    # 2026-08-23 R7：绑定是单向棘轮 —— 记录已绑定产物时，check 必须带上产物。
    # 否则调用方少传一个参数就跳过了整个哈希比对（上轮实测 rc=0 放行），
    # 「改分镜即失效」被瓦解。未绑定过的旧记录走下面的宽限放行，行为不变。
    if stored_sha:
        return False, "该确认已绑定产物，check 必须提供当前产物路径或 sha256 以校验绑定"
    return True, ""


def cmd_check(project, point, artifact=None):
    if point not in CONFIRM_POINTS:
        print(json.dumps({"ok": False, "msg": f"未知确认点: {point}"}, ensure_ascii=False))
        return 2
    try:
        current_sha = artifact_sha256(artifact)
    except ValueError as exc:
        print(json.dumps({"ok": False, "msg": str(exc)}, ensure_ascii=False))
        return 2

    state = load_state(project)
    if state.get("skip_mode"):
        skip_record = {
            "at": state.get("skipped_at"),
            "expires_at": state.get("skip_expires_at"),
            "artifact_sha": state.get("skip_artifact_sha"),
        }
        ok, reason = check_bound_record(skip_record, current_sha)
        if ok:
            print(json.dumps({"ok": True, "msg": "客户跳过确认仍在有效期内", "mode": "skip"}, ensure_ascii=False))
            return 0
        print(json.dumps({"ok": False, "msg": reason, "point": point}, ensure_ascii=False))
        return 2

    record = state["confirmed"].get(point)
    if record:
        ok, reason = check_bound_record(record, current_sha)
        if ok:
            print(json.dumps({"ok": True, "msg": f"{CONFIRM_POINTS[point]['desc']}已确认", "expires_at": record_expiry(record)}, ensure_ascii=False))
            return 0
        print(json.dumps({"ok": False, "msg": reason, "point": point}, ensure_ascii=False))
        return 2

    print(json.dumps({
        "ok": False,
        "msg": f"未确认: {CONFIRM_POINTS[point]['desc']}。{CONFIRM_POINTS[point]['prompt']}",
        "point": point,
    }, ensure_ascii=False))
    return 2


def cmd_confirm(project, point, user_text, artifact=None):
    if point not in CONFIRM_POINTS:
        print(json.dumps({"ok": False, "msg": f"未知确认点: {point}"}, ensure_ascii=False))
        return 2
    try:
        bound_sha = artifact_sha256(artifact)
    except ValueError as exc:
        print(json.dumps({"ok": False, "msg": str(exc)}, ensure_ascii=False))
        return 2

    text = user_text or ""
    now = int(time.time())
    expires_at = now + ttl_seconds()
    for keyword in SKIP_WORDS:
        if keyword in text:
            state = load_state(project)
            state["skip_mode"] = True
            state["skipped_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            state["skip_expires_at"] = expires_at
            state["skip_artifact_sha"] = bound_sha
            state["skip_text"] = text[:100]
            save_state(project, state)
            print(json.dumps({"ok": True, "msg": "客户声明跳过确认；本次跳过受 TTL 与产物绑定约束", "expires_at": expires_at}, ensure_ascii=False))
            return 0

    for keyword in REJECT_WORDS:
        if keyword in text:
            print(json.dumps({"ok": False, "msg": "识别到否定语义，打回修改，等待客户再次确认", "point": point, "text": text[:100]}, ensure_ascii=False))
            return 2

    for keyword in CONFIRM_POINTS[point]["accept"]:
        if keyword in text:
            state = load_state(project)
            state["confirmed"][point] = {
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": expires_at,
                "ttl_seconds": ttl_seconds(),
                "artifact_sha": bound_sha,
                "text": text[:100],
            }
            save_state(project, state)
            print(json.dumps({"ok": True, "msg": f"{CONFIRM_POINTS[point]['desc']}已确认", "expires_at": expires_at, "artifact_sha": bound_sha}, ensure_ascii=False))
            return 0

    print(json.dumps({"ok": False, "msg": "未识别到确认语义，继续等待客户", "point": point}, ensure_ascii=False))
    return 2


def cmd_status(project):
    print(json.dumps(load_state(project), ensure_ascii=False, indent=2))
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    command = sys.argv[1]
    if command == "check" and len(sys.argv) in (4, 5):
        return cmd_check(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) == 5 else None)
    if command == "confirm" and len(sys.argv) in (5, 6):
        return cmd_confirm(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) == 6 else None)
    if command == "skip" and len(sys.argv) in (3, 4):
        return cmd_confirm(sys.argv[2], "node12_render", "跳过确认", sys.argv[3] if len(sys.argv) == 4 else None)
    if command == "status" and len(sys.argv) == 3:
        return cmd_status(sys.argv[2])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
