#!/usr/bin/env python3
"""部署前硬闸：改过客户端发布链路后，没通过这里不许打包、不许推机。

    python3 scripts/predeploy_gate.py --build-dir build_1.2.x/<包目录> [--customer c_xxx]

检查项（任一失败 -> exit 1）：
  1. check_publish_invariants.py 全 PASS。该脚本第 7/8 条专守本次事故：
     星图选中必须点 label.semi-radio 并回读 checked；挂载回读必须接受
     form_card 结构，不能要求「任务:」与「更换/删除」是直接兄弟。
  2. 包内 VERSION 与 MANIFEST.json 顶层 version 一致（否则装机版本号会骗人）。
  3. 给 --customer 时，客户机现网 agent/winport/publish_exec.py 的 sha256
     必须等于包内值（防止「包里改了、机器上没改」或「机器被整包覆盖回去」）。

真机验收口径（脚本无法代替，必须人工跑一次 fill）：
  filled=true 且 xingtu.readback ok=true，readback_via=form_card；
  真机发布验收仍是「真发出一条带星图任务的」。
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", required=True)
    ap.add_argument("--customer")
    ap.add_argument("--program-path",
                    default="C:/Users/huang/Desktop/manju-publish-assistant-1/manju-publish-assistant-1.2.168-win64")
    ns = ap.parse_args(argv)
    root = Path(ns.build_dir).resolve()
    problems = []

    exe = root / "agent/winport/publish_exec.py"
    if not exe.exists():
        print("FAIL 找不到", exe)
        return 1
    r = subprocess.run([sys.executable, str(PROJECT / "scripts/check_publish_invariants.py"), str(exe)],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        problems.append("回归断言未通过（见上）")

    version_file = (root / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("version") != version_file:
        problems.append("VERSION=%s 与 MANIFEST.version=%s 不一致" % (version_file, manifest.get("version")))
    entry = manifest.get("files", {}).get("agent/winport/publish_exec.py", {})
    local_sha = sha256(exe)
    if entry.get("sha256") != local_sha or entry.get("bytes") != exe.stat().st_size:
        problems.append("MANIFEST 里 publish_exec.py 的 bytes/sha256 与文件不一致（需重跑 build_bundle）")

    if ns.customer:
        prog = subprocess.run(
            ["python3", str(PROJECT / "remote_pc.py"), "exec", "--customer", ns.customer,
             "--timeout", "60", "--", "cmd", "/c", "certutil", "-hashfile",
             ns.program_path + "/agent/winport/publish_exec.py",
             "SHA256"], capture_output=True, text=True, timeout=180)
        live = ""
        try:
            live = json.loads(prog.stdout).get("stdout", "")
        except Exception:
            live = ""
        if local_sha not in live.lower().replace("\r", "").replace("\n", ""):
            problems.append("客户机现网 publish_exec.py 与包内不一致（部署未生效或被整包覆盖）")

    if problems:
        print("BLOCKED")
        for item in problems:
            print("  -", item)
        return 1
    print("PASS version=%s publish_exec=%s" % (version_file, local_sha[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
