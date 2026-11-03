# ARK File Upload for Seedream 图生图（2026-07-21 发现并验证）

## 问题背景

Seedream 4.5 的 `image_list` 参数需要公网图片 URL，但国内服务器无法访问外网图床（imgur/catbox/telegra.ph 全部被墙）。

## 解决方案

火山引擎 ARK 的 File API 可以上传图片，返回 `file-xxx` ID，可直接传给 `image_list`。

## 完整流程

### 1. 上传图片到 ARK

```bash
curl -s "https://ark.cn-beijing.volces.com/api/v3/files" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -F "file=@/path/to/image.jpg" \
  -F "purpose=user_data"
```

返回示例：
```json
{
  "object": "file",
  "id": "file-20260721130211-wv9ml",
  "purpose": "user_data",
  "filename": "image.jpg",
  "bytes": 206996,
  "mime_type": "image/jpeg",
  "created_at": 1784610131,
  "expire_at": 1785214931,
  "status": "processing"
}
```

约 1秒后状态变为 `active`。

### 2. 调用 Seedream 图生图

```bash
bash /home/ubuntu/.hermes/scripts/seedream_gen.sh \
  --ref_url "file-20260721130211-wv9ml" \
  "你的图生图prompt"
```

### 关键参数

| 参数 | 值 | 说明 |
|:----|:---|:-----|
| model | `doubao-seedream-4-5-251128` | 实测可用，4.5 比 5.0 更写实 |
| image_list | `["file-xxx"]` | 参数名是 `image_list`，不是 `image` |
| size | `1440x2560`（最小）或 `1920x1920` | 必须 ≥ 3,686,400 像素 |
| watermark | `false` | 不传默认 true，图片带水印 |
| negative_prompt | 见 seedream_gen.sh | 内置完整负面词 |

### 注意事项

- `image` 参数名无效，必须用 `image_list`
- 图片会过期（`expire_at`），过期后需重新上传
- 已验证：`file-xxx` ID 可直接在 ARK 内部传递，无需公网 URL
