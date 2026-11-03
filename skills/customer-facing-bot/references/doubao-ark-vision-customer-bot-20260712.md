# Doubao ARK Vision for Customer Bot Image Analysis

## Background

The customer bot (小天) needs to analyze images/videos sent by customers. The vision_analyze tool in Hermes doesn't work with Doubao models because the content format (image_url) isn't compatible.

## Key Findings

1. **Model version matters**: `doubao-seed-2-0-mini-260215` (text only) vs `doubao-seed-2-0-mini-260428` (vision capable)
2. **Endpoint type matters**: Even with a vision-capable model, the ARK endpoint must be created as a 多模态/vision endpoint, not a text-only endpoint
3. **vision_analyze tool doesn't work**: The Hermes `vision_analyze` tool sends `image_url` content type which Doubao models reject

## Architecture

```
Customer sends image on Feishu
  → Hermes Feishu adapter receives media, caches locally
  → Agent reads SOUL.md instruction → uses terminal + curl to call ARK API
  → Returns analysis result in plain text (no code blocks)
```

## SOUL.md Pattern

```markdown
### 🖼️ 图片/视频分析

客户发图片或视频过来，用以下方式分析：
1. 获取飞书传过来的图片本地路径或URL
2. 如果是本地文件，先转成base64
3. 用 terminal 执行 curl 调用 ARK API 分析图片内容
4. 直接告诉客户分析结果，不要展示命令/代码块/JSON/工具调用

🚨 绝对禁止：
- ❌ 不要运行 ffprobe、ffmpeg、mkdir 等命令
- ❌ 不要显示任何代码块
- ❌ 不要显示JSON/技术参数
- ✅ 只输出最终结论，纯文字描述
- ✅ 分析不了就直说「暂时无法分析哦」
```

## API Call Format

```bash
# Base64 image
curl -s https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d '{
    "model": "ep-<VISION_ENDPOINT>",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "描述这张图片里有什么"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,<BASE64>"}}
      ]
    }],
    "max_tokens": 300
  }'

# Image URL
curl -s ... -d '{
  ...
  "content": [
    {"type": "text", "text": "..."},
    {"type": "image_url", "image_url": {"url": "https://..."}}
  ]
}'
```

## Environment Setup

```bash
# .env
ARK_API_KEY=***
ARK_ENDPOINT=ep-<VISION_ENDPOINT_ID>

# SOUL.md should reference $ARK_ENDPOINT or ARK_ENDPOINT env var
```

## Error Chain Diagnosis

| Error | Root Cause | Fix |
|:------|:-----------|:----|
| `image format is not supported` | Endpoint is text-only model (e.g. 260215) | Switch to 260428 vision model endpoint |
| `Invalid image url: cannot identify image file` | Image format wrong or base64 broken | Use valid JPG/PNG, check encoding |
| `Image dimensions are too small. Minimum allowed dimension: 14 pixels` | Test image too small | Use properly sized image |
| vision_analyze fails with JSON deserialization | DeepSeek model doesn't support image_url | Use ARK API directly via curl |
