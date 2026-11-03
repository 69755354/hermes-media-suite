#!/usr/bin/env python3
"""飞书群发文件：上传文件 → 发文件消息到群（2026-08-16 实测可用）

正解场景：给群里的达人/客户交付文档，用飞书原生文件消息（不用 COS 链接——
默认域名未备案国内打不开、加速域名签名 URL 403）。

用法：
  python3 feishu_send_file.py <文件路径> [群chat_id]
  默认群 = 素材群 <MATERIAL_GROUP_CHAT_ID>

流程：tenant_access_token → im/v1/files 上传拿 file_key → im/v1/messages 发 msg_type=file
"""
import sys, json, time, urllib.request, uuid, os

def load_env():
    env = {}
    with open(os.path.expanduser('~/.hermes/.env')) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

def get_token(app_id, app_secret):
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                                 data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read())
        if resp.get("code") != 0:
            raise Exception(f"token失败: {resp}")
        return resp["tenant_access_token"]

def upload_file(token, file_path, file_name):
    """上传文件，返回 file_key（im:resource 权限）"""
    boundary = uuid.uuid4().hex
    with open(file_path, 'rb') as f:
        content = f.read()
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file_type\"\r\n\r\nstream\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file_name\"\r\n\r\n{file_name}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode())
    parts.append(content)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/files",
        data=body,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
        if resp.get("code") != 0:
            raise Exception(f"上传失败: {resp}")
        return resp["data"]["file_key"]

def send_file_msg(token, chat_id, file_key):
    content = json.dumps({"file_key": file_key}, ensure_ascii=False)
    data = json.dumps({"receive_id": chat_id, "msg_type": "file", "content": content},
                      ensure_ascii=False).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        data=data, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        resp = json.loads(r.read())
        if resp.get("code") != 0:
            raise Exception(f"发送失败: {resp}")
        return resp["data"]["message_id"]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 feishu_send_file.py <文件路径> [群chat_id]")
        sys.exit(1)
    file_path = sys.argv[1]
    chat_id = sys.argv[2] if len(sys.argv) > 2 else "<MATERIAL_GROUP_CHAT_ID>"
    file_name = os.path.basename(file_path)

    env = load_env()
    app_id = env.get("FEISHU_APP_ID")
    app_secret = env.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        print("BLOCKED: 缺少 FEISHU_APP_ID/FEISHU_APP_SECRET (~/.hermes/.env)")
        sys.exit(1)

    print("1. 获取token...")
    token = get_token(app_id, app_secret)
    print("2. 上传文件...")
    file_key = upload_file(token, file_path, file_name)
    print(f"   file_key: {file_key}")
    print("3. 发送到群...")
    msg_id = send_file_msg(token, chat_id, file_key)
    print(f"✅ 已发送, message_id={msg_id}")
