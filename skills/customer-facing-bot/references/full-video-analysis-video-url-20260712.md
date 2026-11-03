# Full Video Analysis via video_url (2026-07-12)

## Background

`doubao-seed-2-0-mini-260428` supports full video analysis via `video_url` content type.
Older `260215` version is TEXT-ONLY — `image_url` calls fail with "image format not supported".

## How It Works

1. Bot receives video file in `cache/documents/` directory (via Feishu attachment)
2. Python script `/tmp/ark_vision.py` copies the video to `/tmp/img_serve/` (served by HTTP on port 8899)
3. Script sends HTTP URL to ARK API using `video_url` format:
   ```json
   {"type": "video_url", "video_url": {"url": "http://<GZ_HOST>:8899/ark_video_xxx.mp4"}}
   ```
4. Model analyzes full video (scenes, audio, text overlay, actions) and returns text description

## Key Differences from Frame Extraction

| Approach | Method | Audio | Full Timeline |
|:---------|:-------|:-----:|:-------------:|
| Frame extraction (2s mark) | ffmpeg截图 → image_url | ❌ | ❌ |
| 4-frame interval (old ark_vision) | ffmpeg多帧截图 → image_url x4 | ❌ | ✅ 大致覆盖 |
| **Full video_url (current)** | **HTTP URL → video_url** | **✅ 音频也被分析** | **✅ 完整视频** |

## Error Diagnosis

| Error | Likely Cause |
|:------|:-------------|
| `Invalid base64 image_url` | `data:video/mp4` prefix not accepted — must use HTTP URL |
| `image format not supported` | Model endpoint is 260215 (text-only). Re-create endpoint with 260428 |
| `Timeout while connecting: http://...` | HTTP server (8899) not running or firewall blocking |
| `分析失败: ...` (generic) | ARK_API_KEY wrong, endpoint wrong, or model overloaded |

## SOUL.md Pattern

```markdown
客户发图片或视频过来，用以下方式分析：
1. 找到文件路径（cache/documents/ 下）
2. 执行命令：`python3 /tmp/ark_vision.py <文件路径>`
3. 把返回的结果直接告诉客户，不要展示命令、代码块、JSON
```

## Required Infrastructure

- ARK endpoint pointing to `doubao-seed-2-0-mini-260428` (NOT 260215)
- HTTP server on port 8899 serving `/tmp/img_serve/` (already running)
- ARK_API_KEY in `.env` with `export ARK_API_KEY="..."` format
- Disk space for video copies (cleaned by daily cron at 3am)
- 120s API timeout for long videos
