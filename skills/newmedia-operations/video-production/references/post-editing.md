---
name: video-production
title: AI生成视频后期处理（口型救急/BGM/字幕/拼接/验证）
description: 触发：AI口播口型生硬、加BGM字幕、卖点卡穿插剪辑、多段拼接。人声连续+画面插卡盖住生硬段。
version: 1.0.0
status: historical_incident
parameter_authority: director-thinking
---

> **硬规则｜用户于 2026-09-14 定案**
> 1. 任何成片的最终合成都必须经过 HyperFrames（HF），禁止用 ffmpeg 拼接合成成片。
> 2. 源视频片段作为 video 素材嵌入 HF；字幕、花字、叠加层、免责声明、CTA 全部在 HF 的 HTML/CSS/JS 内排版，并使用 `npx hyperframes check && npx hyperframes render -o out.mp4` 渲染。
> 3. ffmpeg 仅保留用于质检抽帧和纯转码，不算剪辑。
> 4. 已跑通项目参考：`/home/ubuntu/workflow/projects/hyperframes_test/my-video`。

# AI 生成视频后期处理

> 本文的秒数、字数和拆段数只描述历史故障与成本案例；生产参数不得从案例数字反推。

Seedance 等 AI 生成视频的后期救急与合成。核心场景：AI 口播口型生硬/发音含糊 → 用剪辑手段盖住，而不是重跑（省 API 钱）。

## 核心认知：剪辑能救什么、救不了什么

| 问题 | 剪辑能否解决 | 手段 |
|:---|:---|:---|
| 口型不精确 | ❌ 救不了（画面内容） | 只能盖（切换画面） |
| 发音含糊（个别词糊） | ✅ 盖住 | 卖点卡/特写插在含糊段 |
| 表情生硬 | ✅ 转移注意力 | 卖点卡、字幕强化、景别切换 |
| 台词与文案不一致 | ⚠️ 看程度 | whisper 转写验证；真不一致才重跑 |

**核心策略：人声连续 + 画面插卡。** 口播人声/BGM 全程不断，画面在含糊/生硬段切卖点卡——观众看字卡就懂，不盯口型。比重新生成省 15 元/条。

## 工作流

### 1. 台词保真验证（先做这个！）

AI 口播的发音可能有偏差。交付前必须 whisper 转写对比文案，不能拍胸脯说"台词一样"：

```python
import subprocess, os
os.environ["HF_HUB_OFFLINE"] = "1"; os.environ["HF_HUB_DISABLE_XET"] = "1"
subprocess.run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", wav], capture_output=True, timeout=60)
from faster_whisper import WhisperModel
model = WhisperModel(os.path.expanduser("~/.cache/huggingface/faster-whisper-small"), device="cpu", compute_type="int8")
for seg in model.transcribe(wav, language="zh", beam_size=5)[0]:
    print(f"[{int(seg.start//60):02d}:{int(seg.start%60):02d}] {seg.text.strip()}")
```

- 逐句对比文案，标出 ⚠️ 含糊段（whisper 听不清/听错的位置）
- 含糊段就是卖点卡要盖住的位置
- whisper 自身有错字误差（"红果"可能听成"后果"）——结合上下文判断，别把 whisper 误差当真问题

### 2. 卖点卡生成（PIL）

用文案里的**原词**做卖点卡大字（不加戏，用户铁律）：

```python
from PIL import Image, ImageDraw, ImageFont
font_big = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 120)
# 720x1280，垂直渐变背景 + 白色大字居中 + 装饰圆点
```

样式要点：
- 渐变背景（红/蓝/绿不同卡区分），大字白字，清晰易读
- 720x1280 竖屏匹配视频分辨率
- 主文字+副文字两行（如「多样故事」+「持续上新」）

### 3. ffmpeg 时间轴剪辑（人声连续+画面插卡）

时间轴设计：口播清晰段保留原画面，含糊段插卖点卡。音频用原音轨全程。

```python
fc = (
    "[0:v]trim=0:13,setpts=PTS-STARTPTS[v0];"          # 口播段1（清晰）
    "[1:v]zoompan=z='min(zoom+0.0012,1.12)':d=75:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=720x1280:fps=24[v1];"  # 卖点卡1（3s=75帧@24fps）
    "[v0][v1][...]concat=n=5:v=1:a=0[vconcat];"
    f"[vconcat]ass={ass_path}[vout]"                   # ⚠️ f-string 必须加 f 前缀！
)
cmd = ["ffmpeg", "-y", "-i", src, "-i", card1.png, "-i", card2.png, ...,
       "-filter_complex", fc, "-map", "[vout]", "-map", "0:a",
       "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "copy", out]
```

关键参数：
- zoompan d=帧数（3s×24fps=75），给静态卡加轻微推近动效不呆板
- concat 要求同分辨率同帧率（统一 720x1280@24）
- `-map 0:a` 原音频全程（人声+BGM 连续不断）
- 卖点卡区字幕继续走（ASS 全局烧录，信息重复可接受，抖音常见）

### 4. BGM 下载坑（SoundHelix）

```bash
curl -sL --max-time 25 -o bgm.mp3 https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3
```

- **curl 超时 ≠ 下载失败！** SoundHelix 慢，curl 报 timeout 但文件可能已完整下载（连接没退出）
- **必须 ffprobe 验证完整性**：`ffprobe -v quiet -print_format json -show_format bgm.mp3` → format_name 非空且 duration 正常 = 完整
- 多个 SoundHelix 曲目可换（Song-1~17），Bensound/incompetech 常失败，优先 SoundHelix

### 5. 合成终检（交付前必做）

- ffprobe：时长 30s±1s、720x1280（9:16）、h264+aac、≤50MB
- 抽帧 vision_analyze：卖点卡显示正常（大字清晰）、拼接点（14.8s/15.5s）无黑帧花屏、人物一致性
- 交付：MEDIA 原生发视频（微信/飞书），不发内部路径

## 已验证案例（2026-08-06 星广-红果漫剧小鹿口播）

- Seedance 2.0 Mini 2段×15s 拼接成 30s 口播，whisper 验证 2 处发音含糊（「多样故事持续上新」「画质清晰无卡顿」）
- 卖点卡 3 张（免费看结尾/持续上新/无卡顿）插 13-24s，盖住含糊段，人声+BGM 连续
- 结果：10MB 30.3s，卡点验证全过，交付剪辑版

## Pitfalls

- **f-string 漏前缀**：filter_complex 里的 `{路径}` 不替换 → ffmpeg 报 `ass_read_file({proj}/subtitle.ass): fopen failed`。所有含路径的 filter 串必须 f-string
- **zoompan 帧数**：d=75 = 3s@24fps，d=96 = 4s@24fps，改时长要同步改 d
- **不要为口型问题直接重跑生成**：先 whisper 验证，能盖就盖（免费），真不一致（台词都错了）才重跑（15元/条）
- **发音含糊的根因在生成侧（2026-08-06 血泪教训）**：Seedance 2.0 Mini 用 15s 长段塞 55 字（3.7字/秒）+ 提示词写「语速略快」→ 发音必然糊。正确纪律：分段 **4-12s/镜**、每镜台词 ≤36 字、提示词写「语速适中、吐字清晰、咬字准确、每句断句清楚」（禁止「语速略快」）。30s 口播 = 2×15s（~15元）或 3×10s（更稳）。生成后 whisper 转写：≤2 处含糊可剪辑盖住；>3 处大面积糊 = 生成失败改参数重跑。详见 `references/口播发音生成纪律.md`
- **用户说「以前生成的视频没这问题」= 检查是否违背已知纪律**：不是模型能力退化，是这次参数/分段不对
- **AI 生成写实角色图可直传 Seedance 参考图**：小鹿 xiaolu_selfie.jpg 直传通过真人检测；真人实拍照才拦。直传被拦不扣费，先试再绕检
