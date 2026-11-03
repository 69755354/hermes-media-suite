# ffmpeg 后期合成复刻管线（口播底片 + App录屏 → 成片）

> 2026-08-27 火龙漫剧刘姐版复刻实测。不同于 Seedance 逐镜生成方案，这里是拿到预生成的口播底片（快乐马/wan3.0等）+ 用户提供的App录屏素材，用 ffmpeg 后期合成复刻原片视觉结构。

## 适用场景

- 原片结构 = 数字人口播 + App界面/剧情交替 + 片尾卡
- 口播底片已由其他工具生成（快乐马/wan3.0/婵镜），是连续口播视频
- 用户提供App录屏素材（选集页/分类页/热播榜/播放页）
- 需要用 ffmpeg 把底片和录屏拼合成匹配原片时间轴的成片

## 核心原则

1. **先验原片身份再复刻**——项目目录里的"原片"可能是加工过的母版/模板，不是参考视频真原片。验证三步：① ffprobe 看时长/分辨率/fps 跟抖音ID对应数据是否一致；② md5sum 对比 `wiki/teardowns/` 里的原始下载；③ 不一致 = 用 `wiki/teardowns/` 里的原始下载作唯一事实源，项目里的母版不抽帧不复刻
2. **先抽帧真原片建立时间轴**——真原片每2秒抽1帧，vision逐帧标记画面类型（口播/App/剧情/片尾），记录画中画出现/退出时间点
3. **App录屏素材含剧情画面**——用户给的录屏素材前几秒通常是播放页（含短剧剧情画面+App UI），不是纯UI界面。拆分使用：前段剧情+后段UI各取所需
4. **自验对比**——成片和真原片同时间点各抽帧，vision对比画面类型是否一致

## 管线步骤

### 0. 验证原片身份（必做第一步）

```bash
# 真原片路径：wiki/teardowns/原始素材/<批>/videos/<抖音ID>.mp4
# 项目母版路径：projects/<项目>/post/output/*original*.mp4

# 对比时长/分辨率/fps
ffprobe -v quiet -print_format json -show_format -show_streams "真原片.mp4" | python3 -c 'import sys,json; d=json.load(sys.stdin); s=d["streams"][0]; print(f"{s[\"width\"]}x{s[\"height\"]}, duration={d[\"format\"][\"duration\"]}s, fps={s[\"r_frame_rate\"]}")'

ffprobe -v quiet -print_format json -show_format -show_streams "项目母版.mp4" | python3 -c 'import sys,json; d=json.load(sys.stdin); s=d["streams"][0]; print(f"{s[\"width\"]}x{s[\"height\"]}, duration={d[\"format\"][\"duration\"]}s, fps={s[\"r_frame_rate\"]}")'

# md5对比
md5sum "真原片.mp4" "项目母版.mp4"
```

⚠️ 火龙实测：真原片 720×1280, 39.84s, 60fps（MD5: f68889139352cbd7470d3af0926671b1）；项目母版 1080×1920, 50.6s, 30fps（MD5: e372a99f7f5f879eae5471ac42bcce47）——完全不同的文件。对母版抽帧得到的时间轴是错的，照做出来的复刻必然全错。

### 1. 原片时间轴分析

**⚠️ 必须用scdet场景检测，不能用2秒间隔抽帧（0827-V2修正实测）**：2秒间隔会漏1-2秒的短段（如画中画过渡段），且容易误判画面类型。正确流程：①先`ffmpeg -vf "scdet=threshold=10"`拿全部切换点时间戳；②在每个切换点±1秒密集抽帧（1秒间隔）；③关键过渡区加密到逐秒；④contact sheet拼图4×2网格vision逐帧核验画面类型/画中画有无/大字内容。完整V2修正时间轴见 `dashscope-r2v-replica-workflow` skill 的 `references/huolong-original-timeline-0827.md`。

```bash
# 场景检测找切换点
ffmpeg -i "真原片.mp4" -vf "scdet=threshold=10" -an -f null - 2>&1 | grep "scdet"

# 在切换点附近密集抽帧
mkdir -p /tmp/orig_frames
for t in 0 1 2 3 4 4.5 4.87 5 5.5 6 6.32 7 8 ...; do
  ffmpeg -y -ss $t -i "真原片.mp4" -frames:v 1 /tmp/orig_frames/$(printf "%02d_%05.2fs" $count $t).png 2>/dev/null
done

# 拼contact sheet (4x2网格)
ffmpeg -y -framerate 1 -i /tmp/orig_frames/frame_%02d_*.jpg -vf "scale=360:640,tile=4x2" -update 1 -frames:v 1 -q:v 3 /tmp/contact_sheet.jpg
```

逐帧 vision 问：画面类型（口播/App/剧情/片尾）？有画中画吗？有什么大字？

输出时间轴表：时间 | 画面类型 | 画中画 | 大字关键词

### 2. App录屏素材拆分

**关键发现：App录屏素材不是纯UI，前几秒是剧情播放页**

火龙实例（4个素材）：
- `app_select_full.mp4`（4.77s）：0-3s=千劫问道播放页剧情 → 3-4s=白屏加载 → 4-4.77s=选集列表页
- `app_play_swipe_full.mp4`（5.4s）：0-5.4s=未来儿子播放页剧情
- `app_category_full.mp4`（5.94s）：0-5.94s=分类/筛选页（纯UI）
- `app_hotlist_full.mp4`（4.33s）：0-4.33s=上新/热播榜页（纯UI）

**使用前先全段抽帧（0s/1s/2s/3s/4s/5s）vision确认每秒内容**——不要凭文件名猜用途。

### 3. 预处理各段

统一 scale 到目标分辨率（如720×1280），按目标时长截取/冻结：

```bash
# 播放页剧情段：截前3s + 冻结最后帧到5s
ffmpeg -y -i app_select.mp4 -t 3 -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24,format=yuv420p" -an -c:v libx264 -crf 18 seg_drama_3s.mp4
# 冻结帧
ffmpeg -y -ss 2.9 -i app_select.mp4 -frames:v 1 -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280" drama_last.png
ffmpeg -y -loop 1 -framerate 24 -t 2 -i drama_last.png -vf "format=yuv420p,fps=24" -c:v libx264 -crf 18 seg_freeze_2s.mp4
```

### 4. 拼接App覆盖层

用 concat demuxer（注意：必须用绝对路径 + `safe 0`）：

```bash
cat > /tmp/ui_concat.txt << 'EOF'
file '/abs/path/seg_drama_3s.mp4'
file '/abs/path/seg_freeze_2s.mp4'
file '/abs/path/seg_select.mp4'
file '/abs/path/seg_category.mp4'
file '/abs/path/seg_hotlist.mp4'
file '/abs/path/seg_play.mp4'
EOF

ffmpeg -y -f concat -safe 0 -i /tmp/ui_concat.txt -c:v libx264 -crf 18 -pix_fmt yuv420p -r 24 ui_layer.mp4
```

⚠️ concat filter_complex 方式（`[0:v][1:v]concat=n=N`）经常报 `Invalid argument`——优先用 concat demuxer。

### 5. 圆形画中画

用 `geq` filter 生成圆形alpha遮罩：

```bash
ffmpeg -y \
  -i ui_layer.mp4 \
  -i pip_source.mp4 \
  -filter_complex "\
[1:v]scale=180:180[pip_scaled];\
[pip_scaled]format=yuva420p,\
  geq=lum='p(X,Y)':cb='128':cr='128':a='if(gt(W/2, sqrt((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2))), 255, 0)'[pip_round];\
[0:v][pip_round]overlay=x=720-180-20:y=20:enable='between(t,5.5,13)'[out]" \
  -map "[out]" -c:v libx264 -crf 18 -pix_fmt yuv420p -r 24 ui_with_pip.mp4
```

- `scale=180:180`：画中画小窗尺寸
- `geq` 的 `a=` 是alpha通道：到圆心距离 < 半径 → 255（不透明），否则 0（透明）
- `enable='between(t,START,END)'`：画中画出现/退出时间（对应原片画中画段）
- `overlay x=720-180-20`：右上角，距右边缘20px

### 6. 最终合成

视频轨 = 口播底片段 + App覆盖层 + 口播底片段 + 片尾卡
音频轨 = 口播底片全程音频（不停）

```bash
# 拼视频轨
cat > /tmp/video_concat.txt << 'EOF'
file '/abs/path/base_0_10.mp4'
file '/abs/path/ui_with_pip.mp4'
file '/abs/path/base_31_37.mp4'
file '/abs/path/endcard.mp4'
EOF

ffmpeg -y -f concat -safe 0 -i /tmp/video_concat.txt -c:v libx264 -crf 18 -pix_fmt yuv420p -r 24 video_track.mp4

# 提取底片音频（全程）
ffmpeg -y -i base_full.mp4 -t 40 -vn -c:a aac -b:a 128k audio_40s.aac

# 合成
ffmpeg -y -i video_track.mp4 -i audio_40s.aac \
  -map 0:v:0 -map 1:a:0 \
  -c:v libx264 -crf 18 -pix_fmt yuv420p -r 24 \
  -c:a aac -b:a 128k -movflags +faststart \
  output.mp4
```

### 7. 片尾搜索卡

用 PIL 生成：
- 深蓝渐变背景
- Logo居中（圆形裁剪）
- 搜索框（左白右黑，"搜索" + "火龙漫剧"）
- 引导文案

```python
from PIL import Image, ImageDraw, ImageFont
img = Image.new('RGB', (720, 1280), (15, 23, 42))
# 渐变背景
for y in range(1280):
    r = int(15 + 10 * y/1280)
    g = int(23 + 12 * y/1280)
    b = int(42 + 28 * y/1280)
    ImageDraw.Draw(img).line([(0,y),(720,y)], fill=(r,g,b))
# Logo圆形裁剪
logo = Image.open('logo.jpg').convert('RGBA').resize((200,200))
mask = Image.new('L',(200,200),0)
ImageDraw.Draw(mask).ellipse([0,0,200,200], fill=255)
img.paste(logo, (260, 250), mask)
# 搜索框
draw = ImageDraw.Draw(img)
draw.rounded_rectangle([110,520,610,580], radius=30, fill=(255,255,255))
draw.rounded_rectangle([290,520,610,580], radius=30, fill=(20,20,20))
font = ImageFont.truetype('wqy-zenhei.ttc', 28)
draw.text((130,532),'搜索',fill=(0,0,0),font=font)
draw.text((310,532),'火龙漫剧',fill=(255,255,255),font=font)
img.save('endcard.png')
```

做成3秒视频：`ffmpeg -y -loop 1 -framerate 24 -t 3 -i endcard.png -vf "format=yuv420p,fps=24" -c:v libx264 -crf 18 endcard.mp4`

### 8. 自验对比

成片和真原片同时间点抽帧，逐帧对比：

```bash
for t in 0 5 10 15 20 25 30 35 39; do
  ffmpeg -y -ss $t -i "真原片.mp4" -frames:v 1 /tmp/orig_${t}s.png 2>/dev/null
  ffmpeg -y -ss $t -i "成片.mp4" -frames:v 1 /tmp/replica_${t}s.png 2>/dev/null
done
```

逐对 vision 问同一组问题：画面类型一致吗？画中画有无一致？

## V7 实测完整管线（2026-08-27 火龙刘姐版 V7 落地验证）

V7是第一条按 V2 修正时间轴 1:1 对齐的成功成片。以下是实测验证的完整步骤和关键参数。

### 关键决策：音频必须重新生成，禁止直接提取原片音轨

**⚠️ 2026-08-27 用户「不要直接抽出来」纠正；2026-08-28 用户「你又把声音提出来了？」二次纠正=同一错误重复犯。复刻音频必须重新生成，不能直接从原片提取音轨。**

**原因**：原片音轨是原片人物的声音，复刻换了人物，声音必须跟着换。直接提取原片音轨 = 偷原片声音，不是复刻。**用户对此错误零容忍——说过一次后第二次再犯=信任崩塌。**

**⚠️ 快乐马 r2v 只出视频不出音频（2026-08-28 实测推翻旧假设）**：`run_hh_original.py` 用 `happyhorse-1.1-r2v` 生成口播段，prompt 里写了「说话时嘴型与中文人声自然同步」+ 台词——但 ffprobe 确认生成产物 **只有视频流，没有音频流**。快乐马 r2v 不生成音频，只生成 AI 随机说话动作（嘴开合跟台词内容无关）。之前写的「②快乐马r2v整段台词生成时自带语音」**是错的**。

**⚠️ 三方对齐铁律（2026-08-28 用户「字幕和声音跟口型都对不上了」纠正后固化）**：口播复刻成片必须三方对齐：①音频（重新TTS或婵镜/wan2.7-r2v音频驱动生成）②字幕（跟最终台词一致）③口型（必须音频驱动，不能用快乐马/Seedance AI 随机说话动作贴音频）。

**正确做法**：
1. 整条口播台词 → TTS生成完整音频（按原片语速5.0字/秒调时长到约40秒）
2. 用婵镜 create_video 或 wan2.7-r2v 传音频驱动口型生成口播画面（口型跟着音频走）
3. HH底片只提供视觉画面（mute HH视频的音频）
4. 合成时用新生成的音频轨，**不用原片提取的音轨**
5. 字幕跟最终台词一致

**之前V7的错误记录（已废弃，保留作警示）**：
~~HH口播底片说的是不同台词，所以音频必须从真原片提取。~~
~~ffmpeg -y -i "真原片.mp4" -vn -ac 2 -ar 44100 -c:a pcm_s16le orig_audio_full.wav~~
→ 这种做法已被用户纠正，禁止使用。

### 步骤A：从HH底片切口播视觉段

真原片口播段（需HH视频替换的时段）：
- ① 0.0-4.87s（4.87s）
- ② 4.87-6.32s（1.45s，有App日历画中画覆盖）
- ③ 6.32-12.65s（6.33s）
- ⑨ 31.50-36.85s（5.35s）

先 concat HH-01+HH-02（因单段10.12s不够覆盖所有口播段），再从拼接视频截取：

```bash
# 拼接HH-01+02（mute视频音频）
ffmpeg -y -i hh_01.mp4 -i hh_02.mp4 -filter_complex \
  "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=30,format=yuv420p[v0];\
   [1:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=30,format=yuv420p[v1];\
   [v0][v1]concat=n=2:v=1:a=0[v]" -map "[v]" -an hh_01_02_concat.mp4

# 按原片时间轴切口播段
ffmpeg -y -i hh_01_02_concat.mp4 -ss 0    -t 4.87 -c:v libx264 -crf 18 -an seg01_talking_4p87s.mp4
ffmpeg -y -i hh_01_02_concat.mp4 -ss 4.87 -t 1.45 -c:v libx264 -crf 18 -an seg02_talking_1p45s.mp4
ffmpeg -y -i hh_01_02_concat.mp4 -ss 6.32 -t 6.33 -c:v libx264 -crf 18 -an seg03_talking_6p33s.mp4
ffmpeg -y -i hh_01_02_concat.mp4 -ss 12.65 -t 5.35 -c:v libx264 -crf 18 -an seg09_talking_5p35s.mp4
```

### 步骤B：从App录屏素材切对应时段

按 V2 时间轴切App/剧情段：

```bash
# 段④ 剧情素材 12.65-15.15s (2.5s) → app_play_swipe前2.5s
ffmpeg -y -i app_play_swipe_full.mp4 -ss 0 -t 2.5 -vf "scale=720:1280:...,fps=30,format=yuv420p" -an seg04_drama_2p5s.mp4

# 段⑤ App选集 15.15-16.67s (1.52s) → app_select前1.52s
ffmpeg -y -i app_select_full.mp4 -ss 0 -t 1.52 -vf "scale=720:1280:...,fps=30,format=yuv420p" -an seg05_select_1p52s.mp4

# 段⑥a App分类 16.67-22.60s (5.94s) → app_category全段
ffmpeg -y -i app_category_full.mp4 -ss 0 -t 5.94 -vf "scale=720:1280:...,fps=30,format=yuv420p" -an seg06a_category_5p94s.mp4

# 段⑥b 分类冻结帧 22.60-24.02s (1.41s) → app_category最后帧定格
ffmpeg -y -i seg06a_category_5p94s.mp4 -vf "select=eq(n\,177)" -vframes 1 seg06_cat_lastframe.png
ffmpeg -y -loop 1 -framerate 30 -t 1.41 -i seg06_cat_lastframe.png -vf "scale=720:1280,fps=30,format=yuv420p" seg06b_cat_freeze_1p41s.mp4

# 段⑦ 热播榜 24.02-28.0s (3.98s) → app_hotlist前3.98s
ffmpeg -y -i app_hotlist_full.mp4 -ss 0 -t 3.98 -vf "scale=720:1280:...,fps=30,format=yuv420p" -an seg07_hotlist_3p98s.mp4

# 段⑧ 剧情素材 28.0-31.5s (3.5s) → app_play_swipe从1.9s开始取3.5s
ffmpeg -y -i app_play_swipe_full.mp4 -ss 1.9 -t 3.5 -vf "scale=720:1280:...,fps=30,format=yuv420p" -an seg08_drama_3p5s.mp4
```

### 步骤C：统一编码+concat拼接视频轨

**关键坑**：各段可能编码参数不一致（不同crf/preset），concat stream copy 会花屏。先统一重新编码：

```bash
# 每段统一重新编码
for f in seg01_talking_4p87s.mp4 seg02_talking_1p45s.mp4 ... endcard_3s.mp4; do
  ffmpeg -y -i "$f" -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=30,format=yuv420p" \
    -c:v libx264 -crf 18 -preset medium -an "uni_$f"
done

# concat list
cat > concat_uniform.txt << 'EOF'
file 'uni_seg01_talking_4p87s.mp4'
file 'uni_seg02_talking_1p45s.mp4'
...
file 'uni_endcard_3s.mp4'
EOF

# stream copy concat
ffmpeg -y -f concat -safe 0 -i concat_uniform.txt -c copy video_track_39p85s.mp4
```

### 步骤D：画中画+音频合成

**画中画用静态图片**（口播头像截图 + App选集页截图），不用视频：

```bash
# 提取画中画素材帧
ffmpeg -y -ss 8.0 -i hh_01.mp4 -frames:v 1 -vf "scale=720:1280" pip_avatar_frame.png  # 口播头像
ffmpeg -y -ss 0 -i app_select_full.mp4 -frames:v 1 pip_app_select_frame.png  # App选集页

# 最终合成（视频轨+原片音频+两段画中画）
ffmpeg -y \
  -i video_track_39p85s.mp4 \
  -i orig_audio_full.wav \
  -loop 1 -framerate 30 -t 1.45 -i pip_app_select_frame.png \   # PIP1: 4.87-6.32s
  -loop 1 -framerate 30 -t 7.35 -i pip_avatar_frame.png \        # PIP2: 16.67-24.02s
  -filter_complex "
    [2:v]scale=400:700,format=yuva420p,
      fade=t=in:st=0:d=0.2:alpha=1,fade=t=out:st=1.25:d=0.2:alpha=1,
      setpts=PTS-STARTPTS+4.87/TB[pip1];
    [3:v]scale=200:200,format=yuva420p,
      fade=t=in:st=0:d=0.3:alpha=1,fade=t=out:st=7.05:d=0.3:alpha=1,
      setpts=PTS-STARTPTS+16.67/TB[pip2_raw];
    color=c=black:s=200x200:r=30:d=7.35,format=gray,
      geq=lum='if(lte((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2),(W/2-4)*(W/2-4)),255,0)'[pip2_mask];
    [pip2_raw][pip2_mask]alphamerge[pip2];
    [0:v][pip1]overlay=x=160:y=520:enable='between(t,4.87,6.32)'[v1];
    [v1][pip2]overlay=x=260:y=80:enable='between(t,16.67,24.02)'[vout];
    [1:a]atrim=0:39.83,asetpts=PTS-STARTPTS,aresample=44100[aout]
  " \
  -map "[vout]" -map "[aout]" -t 39.83 \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 192k -ar 44100 -ac 2 \
  -movflags +faststart \
  huolong_v7_no_subtitles.mp4
```

**画中画位置参数（720×1280）**：
- PIP1（App日历小窗，4.87-6.32s）：400×700，x=160 y=520（下半部偏左）
- PIP2（圆形口播头像，16.67-24.02s）：200×200，x=260 y=80（顶部居中偏右）

### 步骤E：字幕烧录（分两步避免超时）

**⚠️ ffmpeg subtitles filter 性能坑（V7实测）**：在一个 filter_complex 里同时做画中画+字幕+logo，39.8s 720×1280 视频可能跑 300s+ 超时。分两步：
1. **第一步：只烧字幕**（30s内完成）
2. ~~第二步：加logo overlay~~（logo overlay步也可能超时，V7最终放弃logo直接用字幕版交付）

```bash
# ASS字幕文件需用系统可用字体（fc-list :lang=zh 查）
# 火龙实例：WenQuanYi Zen Hei 可用，Noto Sans CJK SC 不可用

# 第一步：只烧字幕（约30s完成）
ffmpeg -y -i huolong_v7_no_subtitles.mp4 \
  -vf "subtitles='v7_subtitles.ass':force_style='FontName=WenQuanYi Zen Hei'" \
  -c:v libx264 -crf 20 -preset fast -pix_fmt yuv420p -r 30 \
  -c:a copy \
  huolong_v7_final.mp4
```

### 步骤F：自验对比

```bash
# 成片和原片同时间点抽帧
for t in 0 5 10 15 18 20 25 30 35 38; do
  ffmpeg -y -ss $t -i "真原片.mp4" -frames:v 1 /tmp/orig_${t}s.jpg 2>/dev/null
  ffmpeg -y -ss $t -i "成片.mp4" -frames:v 1 /tmp/v7_${t}s.jpg 2>/dev/null
done

# 拼并排对比图
for t in 0 5 10 15 18 20 25 30 35 38; do
  ffmpeg -y -i /tmp/orig_${t}s.jpg -i /tmp/v7_${t}s.jpg \
    -filter_complex "[0:v]scale=360:640[a];[1:v]scale=360:640[b];[a][b]hstack" \
    -update 1 -frames:v 1 /tmp/compare_${t}s.jpg 2>/dev/null
done
```

**⚠️ vision 2秒间隔 contact sheet 会漏画中画**：V7的2秒间隔contact sheet显示18s帧"无画中画"，但单独抽18s帧vision确认画中画存在。验证画中画时必须抽单个精确时间点的帧，不能只看2秒间隔contact sheet。

### V7 还差的（后续迭代补）

1. **黄色大字/关键词** — 原片有"火龙漫剧""直接看全集"等黄色大字，V7只有白色普通字幕（ASS Default style）。需加 ASS Keyword style（黄字黑边、字号52-60、位置上中部）
2. **Logo贴纸** — 原片9.8s出现火龙logo，V7没加成功（ffmpeg overlay+subtitles 同步做超时）。解决方案：logo在字幕烧录前单独做一步
3. **App日历画中画内容** — 4.87-6.32s的画中画用了选集页截图替代，原片是日历解锁界面（1-30集带锁，仅第1集解锁）。需用户补提供日历解锁素材

## 常见坑（旧版，保留兼容）

1. **项目目录的"原片"不是真原片**——50s母版≠39.8s真原片，对母版抽帧做出来的复刻结构全错。先验身份（ffprobe+md5），用 `wiki/teardowns/` 里的原始下载
2. **concat filter_complex 方式报 Invalid argument**——优先用 concat demuxer（绝对路径 + safe 0）
3. **App录屏分辨率不一致**——540×1116 / 620×1280 / 540×1116 混合，统一 `scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280`
4. **tpad stop_mode=clone 不生效**——分开做：先截3s视频，再单独做冻结帧2s视频，最后concat
5. **画中画enable时间要对齐原片**——原片画中画在16.5-24s，成片App覆盖层在10-30.5s，画中画enable要算App层内偏移（16.5-10=6.5s起，24-10=14s止）
6. **App段开始时间要对齐原片**——不要自作主张提前开始App段，原片什么时候切App就什么时候切
7. **大字字幕**——原片几乎每段都有黄底黑边关键词大字，ffmpeg可用drawtext或ASS烧录
8. **HH底片台词≠原片台词**——HH底片说的是自己模板的台词（"追漫剧最烦的"），原片说的是"有些人我真是无语了"。复刻必须用原片原始音频，HH底片只提供视觉画面（mute HH音频）
9. **concat各段编码参数不一致=花屏**——先逐段统一重新编码到相同codec/crf/preset/fps/分辨率，再stream copy concat
10. **ffmpeg subtitles filter 极慢**——39.8s 720×1280视频烧ASS字幕约30s可接受，但同filter_complex里再叠logo overlay会超时（300s+）。分两步：先烧字幕，再叠overlay
11. **系统缺中文字体=字幕不渲染**——ASS里写Noto Sans CJK SC但系统只有WenQuanYi Zen Hei → libass静默不渲染不报错。`fc-list :lang=zh` 查可用字体，ASS FontName改为系统已装字体
12. **vision 2秒间隔contact sheet会漏画中画**——画中画出现在帧间，2秒间隔可能跳过。验证画中画时抽单个精确时间点帧vision确认，不靠contact sheet
13. **画中画用静态图片不用视频**——口播头像/App界面截图用 `-loop 1 -framerate 30 -t <duration>` 创建视频流，比截视频段更灵活且不会冻结帧穿帮
