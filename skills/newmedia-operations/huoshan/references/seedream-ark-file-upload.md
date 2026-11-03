# Seedream 4.5 图生图：ARK File API 上传方案

> 发现于 2026-07-21 会话
> 痛点：服务器无公网端口，无法直接向 Seedream `image_list` 参数传图片URL

## 问题

Seedream 4.5 的 `image_list` 参数需要 HTTP/HTTPS 公网图片链接。服务器在腾讯云，安全组仅开放 22 端口，无公网HTTP服务。外部图床（imgur/uguu/transfer.sh/sm.ms）从国内服务器连接均超时或失败。

传入 `image_list` 参数时，支持两种标识方式：
1. **公网URL** — `https://xxx.jpg`
2. **ARK File ID** — `file-20260721xxxxxx`

## 解决方案：ARK File API 上传

### 上传图片

```bash
curl -s "https://ark.cn-beijing.volces.com/api/v3/files" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -F "file=@/path/to/image.jpg" \
  -F "purpose=user_data"
```

**返回示例：**
```json
{
  "id": "file-20260721130211-wv9ml",
  "object": "file",
  "bytes": 206996,
  "created_at": 1784617331,
  "filename": "xiaolu_reference.jpg",
  "purpose": "user_data",
  "status": "uploaded"
}
```

**关键参数：**
- `purpose` 必须是 `user_data` 或 `agent`（实测 `user_data` 可用）
- 返回的 `id`（`file-xxx` 格式）直接用于 `image_list` 参数
- 文件状态从 `uploaded` 变为 `active` 后可用（几乎瞬间）

### 在 Seedream API 中使用

```json
{
  "model": "doubao-seedream-4-5-251128",
  "prompt": "...",
  "image_list": ["file-20260721130211-wv9ml"],
  "size": "1440x2560",
  "n": 1,
  "watermark": false
}
```

### 注意事项

1. **文件 ID 有时效** — 建议每次生成前重新上传，不要复用旧 ID
2. **不支持 data: URI** — `image_list` 不接受 base64 data URI
3. **本地路径不可用** — `/home/ubuntu/xxx` 等路径不被接受
4. **最多 14 张参考图** — `image_list` 数组上限 14 个
5. **文件大小限制** — 未见明确文档，建议控制在 10MB 以内

## 与直接文生图的区别

| 方式 | 参数 | 适用场景 |
|:----|:-----|:---------|
| 文生图 | 仅 `prompt` | 无参考图，纯文本描述 |
| 图生图 | `prompt` + `image_list` | 有参考图，需保留人物/场景特征 |

## 在 seedream_gen.sh 中的集成

当前脚本已支持 `--ref_url` 参数接收 file ID：

```bash
bash seedream_gen.sh --ref_url "file-20260721xxxxxx" "参照这张图生成..."
```

完整流程：
1. 客户发图到聊天
2. 小鹿用 ARK File API 上传拿到 file ID
3. 传 `--ref_url "file-xxx"` 调 seedream_gen.sh
4. 出图 → 直接发图片给客户
