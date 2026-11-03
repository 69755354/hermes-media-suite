# Seedance 2.0 Mini API 调用格式（已验证）

## 端点
`POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks`

**注意：** 不是 `/api/v3/video/generations`（那个返回404）

## 请求体格式（已验证可用的正确格式）

`content` 字段是**数组（类chat格式）**，不是字典。

```python
KEY = os.environ["ARK_API_KEY"]
BASE = "https://ark.cn-beijing.volces.com/api/v3"
headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
url = f"{BASE}/contents/generations/tasks"

content = [
    {"type": "text", "text": "prompt内容"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,角色图b64"}, "role": "reference_image"},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,场景图b64"}, "role": "reference_image"}
]

payload = {
    "model": "doubao-seedance-2-0-mini-260615",
    "content": content,
    "resolution": "720p",
    "ratio": "9:16",
    "watermark": False,
    "duration": 5  # 单镜时长，单位秒
}

resp = requests.post(url, json=payload, headers=headers, timeout=60)
data = resp.json()
task_id = data["id"]  # 提交成功返回task id
```

## 轮询结果

```
GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{task_id}
```

status值:
- `running` → 生成中，继续poll
- `succeeded` → 成功，`result["content"]["video_url"]` 获取下载链接
- `failed` → 失败，重试

单镜生成耗时：约2-4分钟。每5秒poll一次，超时5分钟(60次)。
