"""环境 → 真实抖音昵称缓存。

创作者后台页面会报当前登录账号的昵称（``/web/api/media/user/info/``）。
发布过程中顺手把它记下来，机器人下次就能显示「1号（漫半拍）」，
不用再让客户手填名字。只缓存昵称与时间，不含任何 cookie/token。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

FILENAME = "account_names.json"


def _path(layout) -> Path:
    return Path(layout.run) / FILENAME


def load(layout) -> dict:
    """{env_id: {"nickname": str, "updated": int}}；读不出来就当空。"""
    try:
        data = json.loads(_path(layout).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def record(layout, env_id, nickname) -> bool:
    """记下一个环境登录的抖音昵称；没有变化返回 False。"""
    env_id = str(env_id or "").strip()
    nickname = str(nickname or "").strip()[:24]
    if not env_id or not nickname:
        return False
    data = load(layout)
    entry = data.get(env_id)
    entry = dict(entry) if isinstance(entry, dict) else {}
    if entry.get("nickname") == nickname:
        return False
    entry["nickname"] = nickname
    entry["updated"] = int(time.time())
    data[env_id] = entry
    path = _path(layout)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(FILENAME + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        return False
    return True
