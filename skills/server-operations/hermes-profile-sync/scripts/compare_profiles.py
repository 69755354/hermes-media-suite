#!/usr/bin/env python3
"""对比两个 Hermes profile 的 skills 目录，并阻断同名 skill。

用法: python3 compare_profiles.py <A>/skills <B>/skills

检查维度：
1. A/B 独有文件与同路径内容差异；
2. 每个 profile 内 SKILL.md 父目录名重复（大小写不敏感）；
3. 每个 profile 内 frontmatter ``name`` 重复（大小写不敏感）；
4. 两个 profile 间同名 skill 的路径漂移。

发现 profile 内同名时仍输出完整报告，但最终退出码为 2，供同步流程 fail closed。
"""

import hashlib
import os
import re
import sys
import time
from collections import defaultdict


IGNORED_DIRS = {".hub"}
FRONTMATTER_NAME_RE = re.compile(r"^name\s*:\s*(.+?)\s*$", re.MULTILINE)


def walk(directory):
    out = {}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [
            name
            for name in dirs
            if not name.startswith(".hermes-tmp") and name not in IGNORED_DIRS
        ]
        for filename in files:
            if filename.startswith(".hermes-tmp"):
                continue
            full = os.path.join(root, filename)
            rel = os.path.relpath(full, directory)
            out[rel] = full
    return out


def md5(path):
    digest = hashlib.md5()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ts(path):
    try:
        return time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path))
        )
    except OSError:
        return "N/A"


def declared_skill_name(path):
    """读取 SKILL.md YAML frontmatter 的 name；无法解析时返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            text = file_obj.read(65536)
    except (OSError, UnicodeError):
        return None

    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    match = FRONTMATTER_NAME_RE.search(text[3:end])
    if not match:
        return None
    return match.group(1).strip().strip("'\"") or None


def skill_records(directory, walked):
    records = []
    for rel, full in walked.items():
        if os.path.basename(rel) != "SKILL.md":
            continue
        records.append(
            {
                "rel": rel,
                "full": full,
                "dir_name": os.path.basename(os.path.dirname(rel)),
                "declared_name": declared_skill_name(full),
            }
        )
    return records


def grouped_duplicates(records, field):
    groups = defaultdict(list)
    for record in records:
        value = record[field]
        if value:
            groups[value.casefold()].append(record)
    return {
        key: sorted(group, key=lambda item: item["rel"])
        for key, group in groups.items()
        if len(group) > 1
    }


def print_duplicate_report(label, records, hashes):
    by_dir = grouped_duplicates(records, "dir_name")
    by_declared = grouped_duplicates(records, "declared_name")
    print(f"=== {label} profile 内 skill 同名 ===")
    if not by_dir and not by_declared:
        print("  [OK] 0 组")
        return False

    for kind, groups in (("目录名", by_dir), ("声明名", by_declared)):
        for normalized_name, group in sorted(groups.items()):
            shown_names = sorted(
                {record["dir_name" if kind == "目录名" else "declared_name"] for record in group}
            )
            print(f"  [重复:{kind}] {normalized_name}  实际名称={shown_names}")
            for record in group:
                print(
                    f"    - {record['rel']}  md5={hashes[record['rel']]}  "
                    f"mtime={ts(record['full'])}"
                )
    return True


def print_path_drift(records_a, records_b, hashes_a, hashes_b):
    index_a = defaultdict(list)
    index_b = defaultdict(list)
    for record in records_a:
        index_a[record["dir_name"].casefold()].append(record)
    for record in records_b:
        index_b[record["dir_name"].casefold()].append(record)

    drift = []
    for name in sorted(set(index_a) & set(index_b)):
        if len(index_a[name]) != 1 or len(index_b[name]) != 1:
            continue
        record_a, record_b = index_a[name][0], index_b[name][0]
        dir_a = os.path.dirname(record_a["rel"])
        dir_b = os.path.dirname(record_b["rel"])
        if dir_a != dir_b:
            drift.append((name, record_a, record_b))

    print(f"=== 同名 skill 路径漂移 ({len(drift)}) ===")
    for name, record_a, record_b in drift:
        content = (
            "内容相同"
            if hashes_a[record_a["rel"]] == hashes_b[record_b["rel"]]
            else "内容不同"
        )
        print(
            f"  [路径漂移:{content}] {name}  "
            f"A:{os.path.dirname(record_a['rel'])}  B:{os.path.dirname(record_b['rel'])}"
        )


def main(a, b):
    if not os.path.isdir(a) or not os.path.isdir(b):
        missing = [path for path in (a, b) if not os.path.isdir(path)]
        print(f"错误：skills 目录不存在或不可读: {', '.join(missing)}", file=sys.stderr)
        return 1

    walked_a, walked_b = walk(a), walk(b)
    try:
        hashes_a = {rel: md5(path) for rel, path in walked_a.items()}
        hashes_b = {rel: md5(path) for rel, path in walked_b.items()}
    except OSError as exc:
        print(f"错误：文件读取失败: {exc}", file=sys.stderr)
        return 3
    records_a = skill_records(a, walked_a)
    records_b = skill_records(b, walked_b)

    duplicate_a = print_duplicate_report("A", records_a, hashes_a)
    duplicate_b = print_duplicate_report("B", records_b, hashes_b)
    print_path_drift(records_a, records_b, hashes_a, hashes_b)

    only_a = sorted(set(walked_a) - set(walked_b))
    only_b = sorted(set(walked_b) - set(walked_a))
    diffs = []
    for rel in sorted(set(walked_a) & set(walked_b)):
        if hashes_a[rel] != hashes_b[rel]:
            mtime_a = os.path.getmtime(walked_a[rel])
            mtime_b = os.path.getmtime(walked_b[rel])
            if mtime_a > mtime_b:
                newer = "A"
            elif mtime_b > mtime_a:
                newer = "B"
            else:
                newer = "CONFLICT"
            diffs.append((rel, newer, ts(walked_a[rel]), ts(walked_b[rel])))

    print(f"=== A 独有 ({len(only_a)}) — A→B 应同步 ===")
    for rel in only_a:
        print(f"  [新增] {rel}")
    print(f"=== B 独有 ({len(only_b)}) — B→A 应同步 ===")
    for rel in only_b:
        print(f"  [新增] {rel}")
    print(f"=== 内容不同 ({len(diffs)}) ===")
    for rel, newer, time_a, time_b in diffs:
        if newer == "A":
            direction = "A更新→同步到B"
        elif newer == "B":
            direction = "B更新→同步到A"
        else:
            direction = "冲突：mtime相同，禁止自动判定方向"
        print(f"  [{direction}] {rel}  (A:{time_a} B:{time_b})")

    if duplicate_a or duplicate_b:
        print("错误：检测到 profile 内同名 skill；拒绝作为安全同步前置检查通过。", file=sys.stderr)
        return 2
    if any(newer == "CONFLICT" for _, newer, _, _ in diffs):
        print("错误：存在内容不同但 mtime 相同的文件；必须人工判定同步方向。", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python3 compare_profiles.py <A>/skills <B>/skills")
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2]))
