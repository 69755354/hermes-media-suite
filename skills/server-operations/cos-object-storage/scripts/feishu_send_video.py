#!/usr/bin/env python3
"""飞书直发视频消息（msg_type=media，2026-08-18 实测通过）
用法：python3 feishu_send_video.py <视频路径> <chat_id> [文件名]

关键结论（实测）：
- msg_type=video 返回 400 invalid msg_type（此 API 版本不认）
- 正确做法：im/v1/files 上传（file_type=mp4）+ im/v1/messages 发 msg_type=media（content={"file_key": ...}）
- receive_id_type=chat_id 对群/Home 频道；DM 用户用 open_id + receive_id_type=open_id
- 同名文件重复发送会被飞书缓存成旧消息（用户看到旧版）→ 每次换带时间戳的新文件名
- MEDIA:/绝对路径 语法在飞书不渲染（用户看不到），必须走本脚本原生消息

凭证：~/.hermes/.env 的 FEISHU_APP_ID / FEISHU_APP_SECRET
"""
import sys, json, time, urllib.request, urllib.parse, uuid, os

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

def upload_video(token, file_path, file_name):
    boundary = uuid.uuid4().hex
    with open(file_path, 'rb') as f:
        content = f.read()
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file_type\"\r\n\r\nmp4\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file_name\"\r\n\r\n{file_name}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_name}\"\r\nContent-Type: video/mp4\r\n\r\n".encode())
    parts.append(content)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/files",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
        if resp.get("code") != 0:
            raise Exception(f"上传失败: {resp}")
        return resp["data"]["file_key"]

def send_media_msg(token, chat_id, file_key):
    content = json.dumps({"file_key": file_key}, ensure_ascii=False)
    data = json.dumps({
        "receive_id": chat_id,
        "msg_type": "media",
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
        print("用法: feishu_send_video.py <视频路径> <chat_id> [文件名]")
        sys.exit(1)
    file_path = sys.argv[1]
    chat_id = sys.argv[2]
    file_name = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(file_path)

    env = load_env()
    app_id = env.get("FEISHU_APP_ID")
    app_secret = env.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        print("BLOCKED: 缺少飞书凭证 FEISHU_APP_ID/FEISHU_APP_SECRET")
        sys.exit(2)

    print("1. 获取token...")
    token = get_token(app_id, app_secret)
    print("2. 上传视频...")
    file_key = upload_video(token, file_path, file_name)
    print(f"   file_key: {file_key}")
    print("3. 发送 media 消息...")
    msg_id = send_media_msg(token, chat_id, file_key)
    print(f"OK message_id={msg_id}")
