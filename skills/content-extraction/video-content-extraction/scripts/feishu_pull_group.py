#!/usr/bin/env python3
"""拉取飞书素材群最近消息（只读，触发：用户说「看看群里」「群里发了什么」）。

用法：python3 feishu_pull_group.py [chat_id] [page_size]
默认 chat_id = 素材群 <MATERIAL_GROUP_CHAT_ID>（新加坡群：天行者/晓森/方漠阳）
凭证从 /home/ubuntu/.hermes/.env 读 FEISHU_APP_ID/FEISHU_APP_SECRET。
输出：每条消息的时间戳/类型/发送者(脱敏)/内容摘要（text 全文前150字、file/media 的 key 前20位）。
"""
import json, os, sys, urllib.request, urllib.parse

def load_env(path="/home/ubuntu/.hermes/.env"):
    env = {}
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return env

env = load_env()
app_id = env.get("FEISHU_APP_ID")
app_secret = env.get("FEISHU_APP_SECRET")
CHAT = sys.argv[1] if len(sys.argv) > 1 else "<MATERIAL_GROUP_CHAT_ID>"
PAGE = sys.argv[2] if len(sys.argv) > 2 else "20"

data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
req = urllib.request.Request(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    data=data, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=15) as r:
    resp = json.loads(r.read())
token = resp["tenant_access_token"]

url = ("https://open.feishu.cn/open-apis/im/v1/messages?"
       + urllib.parse.urlencode({"container_id_type": "chat", "container_id": CHAT, "page_size": PAGE, "sort_type": "ByCreateTimeDesc"}))
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.loads(r.read())

items = data.get("data", {}).get("items", [])
print(f"=== 群最近 {len(items)} 条消息 ===")
for m in items:
    msg_type = m.get("msg_type")
    create_time = m.get("create_time", "")
    sender = m.get("sender", {}).get("id", "?")
    body = m.get("body", {}).get("content", "")
    if msg_type == "text":
        try:
            txt = json.loads(body).get("text", "")
        except Exception:
            txt = body[:100]
        print(f"[{create_time}] {msg_type} from={sender[:8]}... : {txt[:150]}")
    elif msg_type == "file":
        try:
            fname = json.loads(body).get("file_name", "")
            fkey = json.loads(body).get("file_key", "")
        except Exception:
            fname, fkey = "?", "?"
        print(f"[{create_time}] {msg_type} from={sender[:8]}... : file={fname} key={fkey[:20]}...")
    elif msg_type == "media":
        try:
            fkey = json.loads(body).get("file_key", "")
        except Exception:
            fkey = "?"
        print(f"[{create_time}] {msg_type} from={sender[:8]}... : media key={fkey[:20]}...")
    else:
        print(f"[{create_time}] {msg_type} from={sender[:8]}... : {body[:100]}")
