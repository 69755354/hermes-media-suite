#!/usr/bin/env python3
"""
jianying-web.py — 桌面端剪映远程服务模板
服务器 Hermes 通过 SSH 反向隧道访问本服务，远程操作桌面机上的剪映。

用法（桌面机终端）：
    pip3 install flask
    python3 jianying-web.py

环境变量（可选）：
    JY_SKILL_ROOT   jianying-editor skill 的根目录
                    （默认 ~/.agent/skills/jianying-editor，改了就在这指定）

接口：
    GET  /health        健康检查
    POST /run           {"script": "python代码"} 在 skill 环境下执行脚本

注意：/run 强制检查 SKILL_ROOT 目录存在，不存在返回 500。
     只想用 /run 跑任意脚本时，JY_SKILL_ROOT 指向任意存在的目录即可。
"""

import os
import sys
import subprocess

from flask import Flask, request, jsonify

app = Flask(__name__)

SKILL_ROOT = os.environ.get(
    "JY_SKILL_ROOT",
    os.path.expanduser("~/.agent/skills/jianying-editor"),
)


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "skill_root": SKILL_ROOT,
        "skill_exists": os.path.isdir(SKILL_ROOT),
        "drafts_root": os.path.expanduser("~/Movies/JianyingPro Drafts"),
    })


@app.route("/run", methods=["POST"])
def run_script():
    data = request.get_json(silent=True) or {}
    script = data.get("script", "")
    if not script:
        return jsonify({"ok": False, "error": "no script"}), 400
    if not os.path.isdir(SKILL_ROOT):
        return jsonify({"ok": False, "error": f"skill 目录不存在: {SKILL_ROOT}"}), 500

    tmp = "/tmp/jy_run_script.py"
    with open(tmp, "w") as f:
        f.write(script)

    env = dict(os.environ)
    env["PYTHONPATH"] = SKILL_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    try:
        r = subprocess.run(
            [sys.executable, tmp],
            capture_output=True, text=True, timeout=600,
            env=env, cwd=SKILL_ROOT,
        )
        return jsonify({
            "ok": r.returncode == 0,
            "code": r.returncode,
            "stdout": (r.stdout or "")[-3000:],
            "stderr": (r.stderr or "")[-2000:],
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "执行超时（600s）"}), 500
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    print("jianying-web 启动 @ 127.0.0.1:8000")
    print(f"skill 根目录: {SKILL_ROOT}")
    app.run(host="127.0.0.1", port=8000)
