# LAS Video Understanding for Customer Bot (2026-07-12)

## Why LAS Instead of Chat API

The standard ARK Chat API (`/api/v3/chat/completions`) uses `image_url` for images and videos.
For images, `data:image/...;base64` works. For videos, `data:video/mp4;base64` is **NOT supported**
by the ARK Chat API — it returns `Invalid base64 image_url`.

The LAS (Large-model Agent Service) Video Understanding API (`/api/v1/submit + /api/v1/poll`)
is purpose-built for video understanding:
- Async workflow: submit → poll (chat completions times out on long videos)
- Supports http/https video URLs directly (no base64 encoding needed)
- Returns structured `final_summary` with scene-by-scene breakdown
- Audio understanding supported with model `doubao-seed-2-0-mini-260428`
- No file size limit issues (server-side processing)

## Endpoints

```
Submit: POST https://operator.las.cn-beijing.volces.com/api/v1/submit
Poll:   POST https://operator.las.cn-beijing.volces.com/api/v1/poll
```

## Authentication

Requires **LAS_API_KEY** (not ARK_API_KEY). Created at:
https://console.volcengine.com/las/region:las+cn-beijing/next/api_key_management/list

**Note (2026-07-12):** The exact console path is: LAS控制台 > 算子服务 > API Key 管理.
Don't use the ARK console's API Key page — they are different systems.

Store in `.env`:
```
export LAS_API_KEY="las-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

## API Format

### Submit
```
POST /api/v1/submit
{
  "operator_id": "las_video_understanding",
  "operator_version": "v1",
  "model_name": "doubao-seed-2-0-mini-260428",
  "video_url": "https://example.com/video.mp4",
  "prompt": "请详细描述这个视频的内容"
}
```

### Poll
```
POST /api/v1/poll
{
  "operator_id": "las_video_understanding",
  "operator_version": "v1",
  "task_id": "task-xxxxx"
}
```

## Integration in ark_vision.py

The `/tmp/ark_vision.py` script has two modes:
- **Images**: uses ARK Chat API (`/api/v3/chat/completions`) with `image_url` base64
- **Videos**: copies to `/tmp/img_serve/`, generates http URL (port 8899), submits to LAS API

The script reads `LAS_API_KEY` from env or `.env`. Falls back to `ARK_API_KEY` if no `LAS_API_KEY`.

## Pitfalls

1. **Servers must reach each other.** The video URL must be accessible from LAS servers in Beijing.
2. **Task processing takes time.** A 60s video takes ~30-60s. Poll loop waits up to 120s (2s intervals).
3. **No `data:` URL support.** Only http/https URLs. File must be served via HTTP.
4. **`ApiKey.Invalid` means wrong key.** `ARK_API_KEY` does NOT work with LAS. Need separate `LAS_API_KEY`.
5. **Upgrade Hermes may reset feishu.py.** The `format_message` code block filter patch needs re-application after Hermes updates.
