---
name: media-content-extraction
description: 媒体内容提取：看图/视频转文字/抖音链接抓数。触发：客户发图要看/发视频要转文字/给抖音链接查数据。
metadata:
  hermes:
    tags: [vision, ARK, 看图, 视频转写, 抖音, ffmpeg, 媒体提取]
    category: media
---

# 媒体内容提取（看图/视频转写/链接抓数）

## 触发场景
- 客户发图片 → 需要看懂内容
- 客户发视频 → 需要转文字/扒口播稿
- 客户给抖音/视频号链接 → 需要查数据（作者/时长/播放）

## 核心原则
- **不编造**：看不到就说看不到，不凭标题/关键词推断内容
- 工具打不开 → 直接说，不假装分析
- 数据来源标注：缓存数据要标「仅供参考」，实测数据标「精确」

## 一、看图（vision）

### 路径1：原生 vision_analyze（优先）
```python
vision_analyze(image_url="/path/to/image.jpg", question="详细描述内容")
```

### 路径2：ARK 直调（vision_analyze 不可用时）
当前模型不支持原生 vision → 手动调 ARK：
```bash
python3 /tmp/check_image.py  # base64 送图 → doubao-seed-2-0-mini
```

```python
# 核心：base64 编码图片 → POST ARK chat/completions
import base64, json, urllib.request
KEY = <ARK_API_KEY>
img_b64 = base64.b64encode(open(path, "rb").read()).decode()
payload = {
    "model": "doubao-seed-2-0-mini",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            {"type": "text", "text": "详细描述图片内容"}
        ]
    }]
}
# POST https://ark.cn-beijing.volces.com/api/v3/chat/completions
```

### 路径3：新加坡机 codex 看图（远程）
```bash
echo "描述这张图片" | ssh <SG> 'codex exec --skip-git-repo-check -C /tmp -i /tmp/img.jpg'
```

### 看图要点
- 文字提取优先于外貌描述（截图/菜单/价格先读字）
- 不编造：图中未显示的价格/时间等，用户补充
- 同城引流场景的电话/地址必须明确显示
- 分析完直接给结果，不反问「要不要看」

## 二、视频转文字（ASR）

### 触发
视频转文字 / 视频里说了什么 / 扒口播稿

### 流程
```bash
# 1. 提取音频
ffmpeg -i input.mp4 -vn -ar 16000 -ac 1 audio.wav
# 2. 语音转写（faster-whisper 或系统 TTS 工具）
whisper audio.wav --language zh --model small
# 3. 画面分析（需要时）：ffmpeg 抽帧 + 看图
ffmpeg -i input.mp4 -vf fps=1 frame_%03d.jpg
```

## 三、抖音链接抓数据

### 触发
客户发抖音链接 / 链接打不开 / 查视频数据

### 流程
```bash
# 1. curl + 合适 User-Agent 抓页面
curl -s -L -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)" "视频链接"
# 2. 从页面提取：视频ID、作者、时长、统计数据
# 3. 数据标注：页面缓存数据可能不精确，标「仅供参考」
```

### 限制（诚实声明）
- 视频内容/音频**无法直接获取**（抖音反爬）
- 需要：用户传文件，或 ffmpeg 截图 + 看图分析
- Tavily 来的赞数不准直接写进报告，必须标「缓存数据」

## 四、数据来源标注铁律

| 来源 | 标注 |
|:---|:---|
| Tavily/搜索缓存 | ⚠️ 缓存数据，非实时精确值 |
| CDP 页面实时 | ✅ 实时页面数据，未登录简化显示 |
| 用户发来截图 | ✅ 一手数据，可信度高 |
| 抖音 App 实测 | ✅ 精确值 |

## 五、验证

- 看图文案：提取的文字是否完整（数字/名字不能错）
- 视频转写：跟原视频内容核对（人名/术语不能错）
- 链接数据：标注来源可信度，不夸大数据
