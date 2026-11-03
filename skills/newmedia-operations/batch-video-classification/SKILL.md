---
name: batch-video-classification
description: 批量视频素材分类与模板匹配时用.
---
> ⚠️ **旧口径存档（2026-09-21 前）**：本文的利益点表述可能含新规禁项（无广告类／躺赚白嫖／吊打竞品／绝对免费／直接提现）。**只作历史参考，出片一律按优矩最新口径**，禁照搬。


# 批量视频分类与模板匹配

> 2026-08-30 实战提炼（10条抖音视频批量分析，判定属于火龙漫剧2种模板中的哪一种）。

## 触发
- 用户给一批抖音链接（3条以上），要求分析是否属于已有模板
- 用户问"这些素材属于哪个模板"
- 用户发一批视频要求归类

## 工作流（6步）

### 1. 批量下载
```python
# 用 video-content-extraction 的 douyin_download.py 逐条下载
subprocess.run(["python3", 
  "~/.hermes/skills/content-extraction/video-content-extraction/scripts/douyin_download.py", 
  vid, out_path])
```
- 下载到 `/tmp/template_match/`
- 已存在且 >10KB 的跳过
- 单条失败不阻塞，记下原因继续

### 2. ffprobe 规格提取
```python
# 每条提取：时长、分辨率、大小、编码
ffprobe -v quiet -print_format json -show_format -show_streams video.mp4
```
- 结果存 dict，后续比对用

### 3. 音频提取 + ASR 转写
```bash
# 提取音频
ffmpeg -y -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav

# faster-whisper small 模型（CPU int8，够用）
# 10条视频约7分钟
model = WhisperModel('small', device='cpu', compute_type='int8')
segments, info = model.transcribe(wav, language='zh', beam_size=1)
```
- 转写结果存 JSON（`{vid: {lines: [...], full_text: "..."}}`）
- small 模型够用，不需要 medium（省一半时间）
- ⚠️ whisper 中文输出可能是繁体，不影响关键词匹配

### 4. 抽帧（每条4帧）
```python
# 在 15%/40%/65%/90% 时长处各抽1帧
for pct in [0.15, 0.4, 0.65, 0.9]:
    ts = dur * pct
    ffmpeg -y -ss {ts} -i video.mp4 -frames:v 1 -q:v 2 frame.jpg
```
- 4帧覆盖头中尾，比等间距更能抓到关键画面
- 30s 视频=4帧，58s 视频=4帧

### 5. vision_analyze 批量画面分析
- **并行送4帧/轮**（4个 vision_analyze 调用放同一个 assistant turn）
- 每帧问：人物特征、场景、App界面、字幕文字、是口播还是录屏、有无提现/赚钱/金币元素
- 10条视频=40帧=10轮
- runtime 并行执行，比逐帧串行快4倍

### 6. 交叉比对分类

**分类维度（以火龙漫剧两种模板为例）：**

| 维度 | 通用口播版 | 夜店网赚版 |
|:---|:---|:---|
| 核心卖点 | 追剧体验/免费看全集/不被广告打断 | 赚钱/提现/红包/金币 |
| 关键词 | 白嫖/不卡顿/丝滑/全集/没限制 | 火龙币/提现/签到领红包/赚钱/0.3元提现 |
| 人物 | 单人口播 | 单人/双人/多人+App操作演示 |
| 画面形式 | 纯口播 或 口播+App录屏 | 口播+App操作 或 纯红包海报 |
| 免责字幕 | 有提现免责 | 有提现免责 |

**判定规则：**
- 台词含"赚钱/提现/红包/火龙币" → 夜店网赚版
- 台词含"白嫖/不被广告打断/全集免费/丝滑流畅" → 通用口播版
- 两者都有 → 按主旋律判定（哪类卖点占比 >60%）
- 两者都没有 → 不属于现有模板

> 模板分类标准应从对应的模板定义skill中提取。此处以火龙漫剧为例，其他项目替换为自己的模板定义。

**输出格式：**

| # | 视频ID | 账号 | 时长 | 形式 | 核心卖点 | 匹配模板 |
|:---|:---|:---|:---|:---|:---|:---|
| 1 | xxx | xxx | 29.8s | 真人口播 | 免费看全集 | ✅通用口播版 |

## 关键要点
- ASR 用 small 模型够了，不需要 medium（省一半时间）
- vision_analyze 并行送4帧/轮是关键加速手段
- 转写结果存 JSON 方便后续程序化比对
- 抽帧用 15%/40%/65%/90% 覆盖头中尾
- 单条下载/转写失败不阻塞，记下原因跳过
- 底部免责字幕"提现额度"两类模板都有，不能单独作为分类依据

## 相关技能
- video-content-extraction：单条视频提取（下载/转写/抽帧/OCR），本技能复用其 douyin_download.py 脚本
- huolong-replica-template：火龙漫剧复刻模板定义（通用口播版+夜店网赚版），分类标准来源（user-owned，如需更新模板判定规则需用户执行）
- content-hunter：批量抓取热门内容元数据（文本层），本技能补充画面+口播层分析