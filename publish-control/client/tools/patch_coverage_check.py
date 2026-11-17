"""增量包覆盖检查：min_version 到目标版本之间每个版本改过的程序文件，必须全部在补丁里。

用法:
  python3 tools/patch_coverage_check.py --to-tag v1.2.218 \
      --patch-zip /path/patch-1.2.218.zip --manifest /path/manifest-1.2.218.json

判定:
  * 对每个 tag v（v < to-tag 且 v >= manifest.min_version）: git diff v..to-tag 的程序文件
    必须全部出现在补丁 zip 里；不在 = 该版本升级后文件不全，BLOCK。
  * manifest 的 min_version 必须 <= 最早被完整覆盖的版本，否则旧客户端会升成半成品。
  * 补丁 zip 的 sha256/size 必须与 manifest 一致，manifest.files 必须全部在 zip 内。
退出码: 0=PASS, 1=FAIL
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

CLIENT_PREFIX = "publish-control/client/"
# 进补丁的程序文件：这些目录下的全部 + 根目录的 .py/.bat（如 run_panel.py）
# 不含 tests/ tools/ runtime/ browsers/，也不含 VERSION/MANIFEST.json/SHA256SUMS.txt
PROGRAM_DIRS = ("agent/", "config/", "scripts/")
PROGRAM_TOPFILE_SUFFIX = (".py", ".bat")
META_FILES = {"VERSION", "MANIFEST.json", "SHA256SUMS.txt"}
EXCLUDED_DIRS = ("tests/", "tools/")


def run(cmd: list[str], cwd: Path) -> str:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout


def vkey(tag: str) -> tuple:
    body = tag.lstrip("v")
    return tuple(int(p) for p in body.split("."))


def list_tags(repo: Path) -> list[str]:
    tags = [t.strip() for t in run(["git", "tag", "-l", "v1.2.*"], repo).splitlines() if t.strip()]
    return sorted(tags, key=vkey)


def is_program_file(client_rel: str) -> bool:
    if client_rel in META_FILES or client_rel.startswith(EXCLUDED_DIRS):
        return False
    if any(client_rel.startswith(d) for d in PROGRAM_DIRS):
        return True
    return "/" not in client_rel and client_rel.endswith(PROGRAM_TOPFILE_SUFFIX)


def changed_files(repo: Path, base: str, target: str) -> tuple[list[str], list[str]]:
    """返回 (改动的程序文件列表[client 相对路径], 目标端已删除的文件)。"""
    out = run(["git", "diff", "--name-status", base, target, "--", CLIENT_PREFIX], repo)
    changed, deleted = [], []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        rel = path[len(CLIENT_PREFIX):] if path.startswith(CLIENT_PREFIX) else None
        if not rel or not is_program_file(rel):
            continue
        if status.startswith("D"):
            deleted.append(rel)
        else:
            changed.append(rel)
    return changed, deleted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to-tag", required=True)
    ap.add_argument("--patch-zip", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--from-tag", default=None, help="默认从最老 tag 开始扫")
    args = ap.parse_args()

    repo = Path(run(["git", "rev-parse", "--show-toplevel"], Path(__file__).resolve().parent).strip())
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    patch = Path(args.patch_zip)
    data = patch.read_bytes()
    problems: list[str] = []

    # 1. 补丁包与清单一致性
    sha = hashlib.sha256(data).hexdigest()
    if sha != manifest.get("patch_zip_sha256"):
        problems.append(f"补丁 sha256 不符: 实际 {sha} != 清单 {manifest.get('patch_zip_sha256')}")
    if len(data) != manifest.get("patch_zip_size"):
        problems.append(f"补丁大小不符: 实际 {len(data)} != 清单 {manifest.get('patch_zip_size')}")
    with zipfile.ZipFile(patch) as zf:
        in_zip = {n for n in zf.namelist() if not n.endswith("/")}
    for f in manifest["files"]:
        if f["path"] not in in_zip:
            problems.append(f"清单文件不在补丁内: {f['path']}")
    extra = in_zip - {f["path"] for f in manifest["files"]}
    if extra:
        problems.append(f"补丁内多出清单未登记文件: {sorted(extra)}")

    # 2. 逐版本覆盖检查
    tags = [t for t in list_tags(repo) if vkey(t) < vkey(args.to_tag)]
    if args.from_tag:
        tags = [t for t in tags if vkey(t) >= vkey(args.from_tag)]
    min_v = tuple(int(p) for p in str(manifest["min_version"]).split("."))
    uncovered_in_range = False
    earliest_covered = None
    rows = []
    for tag in tags:
        changed, deleted = changed_files(repo, tag, args.to_tag)
        missing = [p for p in changed if p not in in_zip]
        rows.append((tag, len(changed), missing, deleted))
        in_range = vkey(tag) >= min_v
        if missing and in_range:
            uncovered_in_range = True
        if in_range and not missing and not deleted:
            if earliest_covered is None or vkey(tag) < vkey(earliest_covered):
                earliest_covered = tag

    print(f"目标版本 {args.to_tag}  补丁 {patch.name}  补丁文件 {len(in_zip)}  清单 min_version {manifest['min_version']}")
    print(f"{'版本':<12}{'改动程序文件':>8}  {'缺失':<6} 说明")
    for tag, n, missing, deleted in rows:
        note = ""
        if missing:
            note = f"缺 {len(missing)}: " + ", ".join(missing[:6]) + (" ..." if len(missing) > 6 else "")
        if deleted:
            note += ("; " if note else "") + f"目标端已删除(补丁无法表达删除): {', '.join(deleted)}"
        print(f"{tag:<12}{n:>8}  {len(missing):<6} {note}")

    if uncovered_in_range:
        problems.append(f"min_version={manifest['min_version']} 区间内存在覆盖不全的版本（见上表）")
    # min_version 必须等于「第一个完整覆盖的版本」，否则存在半覆盖区间
    if earliest_covered is None:
        problems.append("没有任何版本被完整覆盖，无法确定可用 min_version")
    elif min_v != vkey(earliest_covered):
        problems.append(
            f"min_version 应为 {earliest_covered.lstrip('v')}（第一个完整覆盖版本），当前 {manifest['min_version']}")

    print()
    if problems:
        print("RESULT: FAIL")
        for p in problems:
            print(" -", p)
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
