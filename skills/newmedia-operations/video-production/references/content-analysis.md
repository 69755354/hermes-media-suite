---
name: video-production
description: 触发：分析视频内容/口播转写/抖音链接分析。三通道：音频转写/画面分析/结构拆解。
version: 1.0.0
author: hermes
license: internal
metadata:
  hermes:
    tags: [douyin, whisper, transcription, video-analysis, content]
    related_skills: [content-hunter, video-production]
---

# 短视频内容分析（三通道）

分析短视频内容时按需选通道——**口播说了什么、画面长什么样、结构怎么设计**是三个独立需求，不要混。

## When to Use
- 用户发抖音/快手/B站链接说「分析这个视频」
- 需要知道口播文案（知识口播/探店口播/剧情台词）
- 需要画面分析（角色/场景/色调）或结构拆解（钩子/金句）

## 通道选路（先判断用户要什么）

| 用户需求 | 通道 | 依赖 |
|:---|:---|:---|
| 口播说了什么/文案内容 | **① 音频转写**（faster_whisper） | ffmpeg + faster_whisper（本机已装） |
| 画面长什么样/角色场景 | ② 视觉分析（豆包 Vision） | ARK_API_KEY + ARK_ENDPOINT（见 video-production） |
| 结构/钩子/金句/传播性 | ③ 结构拆解（基于转写文本） | ①的产物即可 |

**用户说「分析视频内容」默认画面视觉优先**（2026-07-10 用户纠正，见 video-production）；用户问「说了什么/文案/口播」走本技能①通道。

## 通道①：抖音口播音频转写（2026-08-11 实测跑通）

「分享链接 → 解析视频ID → 下载mp4 → 提音频 → faster_whisper转写」完整链路：

```bash
# 1. 分享链接重定向拿视频ID
curl -s -m 15 -L "https://v.douyin.com/<短码>/" \
  -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1" \
  -o /tmp/douyin_redirect.html -w "%{url_effective}"
# → 302 到 www.iesdouyin.com/share/video/<video_id>/...

# 2. 详情页拿元数据+播放URI
curl -s "https://www.iesdouyin.com/share/video/<video_id>/" -H "User-Agent: <手机UA>" -o /tmp/douyin_video.html
# 正则提取："desc":"..."（描述）、"nickname":"..."（作者）、"duration":<ms>、"play_addr":{"uri":"<URI>"}

# 3. 下载视频（⚠️ 必须 -L 跟重定向，否则只存 628 字节 HTML）
VIDEO_URI="<上面提取的uri>"
curl -s -m 20 -L "https://www.iesdouyin.com/aweme/v1/play/?video_id=${VIDEO_URI}&ratio=720p&line=0" \
  -H "User-Agent: <手机UA>" -o /tmp/douyin_video.mp4
file /tmp/douyin_video.mp4  # 应为 ISO Media, MP4

# 4. 提取音频
ffmpeg -y -i /tmp/douyin_video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 /tmp/douyin_audio.wav

# 5. faster_whisper 转写
python3 -c "
from faster_whisper import WhisperModel
model = WhisperModel('small', device='cpu', compute_type='int8')
segments, info = model.transcribe('/tmp/douyin_audio.wav', language='zh')
for seg in segments:
    print(f'[{seg.start:.1f}s-{seg.end:.1f}s] {seg.text}')
"
```

### 要点与坑
- **手机 UA 必须**（抖音对 headless/桌面 UA 触发验证码）
- 转写模型 `small`+`int8` 在 2 核 1.9GB 机器 36s 音频约 1-3 分钟；`base` 更快但中文略差
- 36.5s 口播实测完整还原 14 个时间戳分段（含「第一性原理递减链」结构）
- 拿到转写文本后即可做结构拆解（递减链/反直觉对比/金句收尾），无需再走视觉

## 通道③：结构拆解（基于转写文本的通用框架）

拿到口播全文后，按四维拆：
1. **钩子**：前 3 秒怎么留人（反直觉/地域点名/悬念）
2. **结构**：递进链/并列/故事线？每层怎么推进
3. **情绪**：共情点在哪（焦虑/爽感/认知升级）
4. **金句/传播点**：哪句可截图转发

## 注意事项
- 转写通道只能拿口播文字，**看不到画面**——画面仍需视觉模型（video-production 技能）
- 不要根据转写文本编造画面描述（「只提取不编造」铁律）
- 视频下载有时间性，下载后尽快转写

## 关联
- video-production（用户自有）：画面提示词反推 7 要素
- content-hunter（用户自有）：平台热门内容批量抓取
