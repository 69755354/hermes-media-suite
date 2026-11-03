# 微信/飞书语音消息转写（2026-08-05 实测成功）

## 场景
用户在微信/飞书发语音消息，Hermes 自动转写失败（`[voice message could not be transcribed automatically]`），音频存到 `/home/ubuntu/.hermes/cache/audio/audio_xxx.silk`。

## 链路（3 步，全部实测通过）

### 1. silk → wav（pilk 库）
微信语音是 SILK_V3 私有格式，ffmpeg 不认。用 pilk（已装在 venv）：
```python
import pilk
pilk.silk_to_wav("/home/ubuntu/.hermes/cache/audio/audio_xxx.silk", "/tmp/voice_msg.wav", 24000)
```

### 2. wav → 文字（faster-whisper）
用本地模型（small 已下载，离线加载）：
```python
from faster_whisper import WhisperModel
import os
local_dir = os.path.expanduser("~/.cache/huggingface/faster-whisper-small")
model = WhisperModel(local_dir, device="cpu", compute_type="int8")
segments, info = model.transcribe("/tmp/voice_msg.wav", language="zh", beam_size=5)
for seg in segments:
    print(f"[{int(seg.start//60):02d}:{int(seg.start%60):02d}] {seg.text.strip()}")
```

### 3. 环境变量（HF 网络被墙时必需）
```python
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"   # 模型已在本地，强制离线
```

## 已踩坑
- ffmpeg 读 silk 报 `Invalid data found when processing input` → 必须用 pilk
- huggingface_hub 下载 401（xet 协议）→ 设 `HF_HUB_DISABLE_XET=1` 走传统下载
- 首次下载模型走 hf-mirror.com（HF_ENDPOINT=https://hf-mirror.com）+ 禁 xet
- whisper small 模型中文识别质量可读（实测「我在每个节点…」等长句 OK），关键数据要再核对

## 相关脚本
- `~/.hermes/scripts/extract_video_content.py` — 视频→文字稿（ffmpeg 抽音频→whisper），同链路复用
- 模型缓存：`~/.cache/huggingface/faster-whisper-small`
