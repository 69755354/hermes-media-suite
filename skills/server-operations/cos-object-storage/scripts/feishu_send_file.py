#!/usr/bin/env python3
"""飞书群发文件（原生文件消息，不走 COS 链接）。

背景（2026-08-16 实测）：COS 预签名链接外部人打不开——
- 默认域名 cos.ap-guangzhou.myqcloud.com 未备案 → 国内手机超时
- 加速域名签名 URL 浏览器访问 403（SDK 拼接 bug）
正解：飞书原生文件消息（im/v1/files 上传 → im/v1/messages 发 msg_type=file），
群里直接点开下载，不依赖链接。

用法：
    python3 feishu_send_file.py <群chat_id> <文件路径> [文件名]

内部信息（路径/工具名）仍由 feishu_send_gate.py 的 check 兜底，
但文件消息本身不含路径，文件名注意用对外名（如「视频拆解_20260816.docx」）。
"""
import json
import sys
import uuid
import urllib.request
from pathlib import Path


def load_env():
    env = {}
    env_path = Path.home() / ".hermes" / ".env"
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def get_token(app_id, app_secret):
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read())
        if resp.get("code") != 0:
            raise Exception(f"token失败: {resp}")
        return resp["tenant_access_token"]


def upload_file(token, file_path, file_name):
    boundary = uuid.uuid4().hex
    content = Path(file_path).read_bytes()
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file_type\"\r\n\r\nstream\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file_name\"\r\n\r\n{file_name}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/files",
        data=b"".join(parts),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())
        if resp.get("code") != 0:
            raise Exception(f"上传失败: {resp}")
        return resp["data"]["file_key"]


def send_file_msg(token, chat_id, file_key, file_name):
    content = json.dumps({"file_key": file_key}, ensure_ascii=False)
    data = json.dumps({
        "receive_id": chat_id,
        "msg_type": "file",
        "content": content,
    }, ensure_ascii=False).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read())
        if resp.get("code") != 0:
            raise Exception(f"发送失败: {resp}")
        return resp["data"]["message_id"]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    chat_id = sys.argv[1]
    file_path = sys.argv[2]
    file_name = sys.argv[3] if len(sys.argv) > 3 else Path(file_path).name

    env = load_env()
    token = get_token(env["FEISHU_APP_ID"], env["FEISHU_APP_SECRET"])
    file_key = upload_file(token, file_path, file_name)
    msg_id = send_file_msg(token, chat_id, file_key, file_name)
    print(f"SENT: message_id={msg_id}")
