# 飞书发视频的正确方式

> 源自 2026-08-26。`hermes send -t feishu "MEDIA:视频.mp4"` 发的是文件附件不是视频消息，用户看不到视频预览。需要直接调飞书 API 发 media 消息。

## 一、问题

用户说"视频发出来"或"发飞书"，用 `hermes send` 发的 MEDIA 附件在飞书里显示为文件下载，不是可播放的视频卡片。用户要的是飞书里直接能看的视频预览。

## 二、正解：飞书 API 直接发 media 消息

```python
import os, json, requests

# 1. 读凭证
env = {}
with open(os.path.expanduser("~/.hermes/.env")) as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            env[k] = v

app_id = env.get('FEISHU_APP_ID', '')
app_secret = env.get('FEISHU_APP_SECRET', '')

# 2. 获取 tenant_access_token
resp = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id": app_id, "app_secret": app_secret}, timeout=15)
token = resp.json()["tenant_access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 3. 上传视频文件到飞书
video_path = "/path/to/video.mp4"
with open(video_path, 'rb') as f:
    upload = requests.post("https://open.feishu.cn/open-apis/im/v1/files",
        headers=headers,
        data={"file_type": "mp4", "file_name": "video.mp4", "duration": str(int(40500))},
        files={"file": ("video.mp4", f, "video/mp4")}, timeout=120)
file_key = upload.json()["data"]["file_key"]

# 4. 发送 media 消息（不是 video！）
chat_id = "oc_xxx"  # 目标聊天ID
requests.post("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
    headers={**headers, "Content-Type": "application/json"},
    json={
        "receive_id": chat_id,
        "msg_type": "media",
        "content": json.dumps({"file_key": file_key, "file_type": "mp4"})
    }, timeout=30)
```

## 三、关键经验

- **DM（私聊）发视频用 `msg_type=media` + `file_type=mp4`**，不用 `msg_type=video`
- `msg_type=video` 会报错：`230001 invalid msg_type: video`
- video 类型仅限特定场景（如通过视频通话），media 类型才是通用视频发送方式
- 上传时要带 `duration` 参数（毫秒），如 40500 = 40.5 秒
- `FEISHU_DOMAIN` 环境变量值是 `feishu`（不是 API 域名），飞书 API 域名固定为 `https://open.feishu.cn`
- 飞书群发视频同样用 media 类型（从 memory 已知：群发视频 msg_type=media+file_type=mp4）

## 四、大文件发送失败处理（0827实测）

**问题**：成片 30MB（1080×1920/50s/CRF18）通过 MEDIA 内联发送或 `hermes send` 均报 `Couldn't deliver the video attachment`。飞书 API 上传文件有大小限制（约 25-30MB）。

**解法**：压缩后再发。CRF 提高到 28 + AAC 128k，30MB → 8.4MB，飞书正常接收。

```bash
ffmpeg -y -i output/big.mp4 \
  -c:v libx264 -preset fast -crf 28 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -ar 48000 -ac 2 \
  -movflags +faststart \
  output/compressed.mp4
```

- CRF 28 对口播视频画质损失极小（人物静态坐姿+背景简单），文件从 30MB 压到 8.4MB
- 如果压缩后仍超限，进一步降 CRF 到 30 或降分辨率到 720×1280
- `hermes send --to "feishu:<chat_id>" --file <compressed.mp4>` 发送
