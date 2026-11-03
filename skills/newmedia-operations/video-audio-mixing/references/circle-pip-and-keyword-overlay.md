# 圆形画中画 + 花字关键词 + App素材照原片合成（0828实测）

> 用户要求"按照原片的素材插入方式"做后期。本文记录完整技术路径。

## 原片素材插入模式（逐帧vision分析）

**铁律：必须1秒1帧密集抽帧，不能2-3秒抽1帧。** 2-3秒间隔会漏掉画面切点，导致把原片的交替结构误判为连续覆盖。

```
ffmpeg -ss <ts> -i ref.mp4 -frames:v 1 -q:v 2 /tmp/ref_<ts>s.jpg
```

### 原片（刘姐39.8s, 720x1280, 60fps）1秒1帧分析结果

**原片是交替切换模式，不是一段素材从头盖到尾：**

| 时段 | 画面 | 叠加元素 |
|:---|:---|:---|
| 0-22s | 数字人口播 + 小画中画闪App界面 | 黄字黑边花字关键词 + 白字字幕 + 风险提示小字 |
| 23-26s | 全屏App分类页 | 花字"题材丰富" |
| 27-29s | 回数字人（小PIP弹窗） | 花字 |
| 30-32s | 全屏App播放页 | 花字"丝滑流畅" |
| 33-34s | 回数字人 | 花字 |
| 35-36s | 全屏App界面 | 花字 |
| 37-39s | 数字人收尾 | 花字"该知道去" |

**三个关键区别**（原片 vs 初版错误）：
1. **花字关键词**：原片全程叠黄字黑边关键词，跟着口播变
2. **圆形画中画**：App素材段右上角有圆形数字人小窗，人没断
3. **交替不是连续**：原片在数字人和App画面之间来回切换，不是一段15秒的App录屏从头盖到尾

### 正确的素材映射（按口播内容匹配App页面）

| 口播内容 | 对应App页面 | 我们视频的时段 |
|:---|:---|:---|
| "全集了""直接看到大结局" | 选集页（全屏动态视频） | 9.8-15.2s |
| "题材丰富""悬疑脑洞""穿越逆袭" | 分类页（全屏动态视频） | 15.2-24.0s |
| "热门题材""全都有""新剧上架" | 热播榜/上新页（全屏动态视频） | 24.0-27.7s |
| "画质高清""丝滑流畅""快进快退" | 播放页（全屏动态视频） | 27.7-31.9s |
| 痛点段/收尾段 | 纯数字人，不插素材 | 0-9.8s / 31.9-33.7s |

**0828用户最终纠正（铁律）**：说到"全集了"之后插的就是选集页那段动态录屏，**后面所有App素材全是全屏动态视频**。不要做分屏（上下分屏是原片5-6秒签到日历的格式，不适用于选集页）。选集页跟分类页/热播榜/播放页一样：全屏覆盖动态视频。

## 圆形画中画技术要点

### geq 滤镜超时 → PIL mask 替代

```python
from PIL import Image, ImageDraw
mask = Image.new('RGBA', (600, 600), (0, 0, 0, 0))
draw = ImageDraw.Draw(mask)
draw.ellipse([20, 20, 580, 580], fill=(255, 255, 255, 255))
mask.save("circle_mask_600.png")
```

### libx264 不保留 alpha

不能单独导出 PIP mp4 再 overlay。必须在同一 filter_complex：
1. crop 底片人脸区域
2. alphamerge 应用圆形 mask
3. scale 缩小到 200x200
4. overlay 到已叠加 App 素材的画面上

### 人脸定位流程

1. 从底片抽帧（如第5秒）
2. vision_analyze 问"脸部中心坐标和额头到下巴范围"
3. 根据 vision 给的坐标算 crop 左上角
4. 720×1280 底片实测：人脸约 x=60-660, y=30-630，600×600 crop at (60,30) 覆盖全脸
5. 做完再抽帧 vision 验证 PIP 里脸完整

## 花字关键词 ASS

独立 ASS 文件，链式烧录：`ass='subtitles.ass',ass='keywords.ass'`

样式参数：
- Fontname: Noto Sans CJK SC
- Fontsize: 64
- PrimaryColour: `&H0000FFFF`（亮黄）
- OutlineColour: `&H00000000`（黑）
- Outline: 5, Shadow: 3
- Alignment: 8（中上）
- MarginV: 200

## overlay shortest=1 坑

不加 `shortest=1`，改用 `enable='between(t,start,end)'` 控制叠加时段。否则输出截断到较短流。

## App 素材用视频不用截图

用户给的是 App 录屏视频（.mp4），4段：
- app_select_full.mp4 (540x1116, 4.77s)
- app_category_full.mp4 (620x1280, 5.94s)
- app_hotlist_full.mp4 (540x1116, 4.33s)
- app_play_swipe_full.mp4 (540x1116, 5.40s)

**坑：拼接时每段只取1帧当静态图用=素材全静止。** 必须取完整视频流（`-t <dur>` 截取动态画面），不能用 `-frames:v 1` 只抽一帧。

每段截取约3.5-4秒动态画面，scale+crop统一到720x1280，24fps。按口播内容映射到不同时段（见上方素材映射表），不是全部拼成一条14秒连续素材。

### ⚠️ overlay enable='between()' 冻帧坑（0828实测，重大）

**症状**：用 `overlay=enable='between(t,start,end)'` 逐段叠加多段 App 素材，叠加时段内画面静止不动（只显示第一帧）。用 md5 比较同一时段内不同时间点的抽帧——如果 md5 相同说明冻帧了。

**根因**：当 overlay 的输入视频比主视频短时，ffmpeg 的 `enable` 参数会在非启用时段暂停处理该输入流。当 `enable` 再次为 true 时，输入流已耗尽（EOF），ffmpeg 停在该输入的最后一帧或第一帧，不继续推进。**`setpts=PTS-STARTPTS` 不能修复此问题**。

**修复方法**：把所有 App 素材按时间轴拼成一个与主视频等长的完整视频（非 App 段用黑场填充），再一次性 overlay。

```bash
# Step 0: 准备黑场填充段
ffmpeg -y -f lavfi -i "color=c=black:s=720x1280:d=9.8:r=24" \
  -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -r 24 -g 48 -an pad_pre.mp4    # 0-9.8s
ffmpeg -y -f lavfi -i "color=c=black:s=720x1280:d=1.833:r=24" \
  -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -r 24 -g 48 -an pad_post.mp4   # 31.9-33.7s

# Step 1: concat 黑场+App素材+黑场 = 与底片等长的完整时间轴视频
cat > ui_concat.txt << 'EOF'
file 'pad_pre.mp4'           # 0-9.8s 黑场
file 'app_seg_select.mp4'   # 9.8-15.2s 选集页
file 'app_seg_category.mp4' # 15.2-24.0s 分类页
file 'app_seg_hotlist.mp4'  # 24.0-27.7s 热播榜
file 'app_seg_play.mp4'     # 27.7-31.9s 播放页
file 'pad_post.mp4'          # 31.9-33.7s 黑场
EOF

ffmpeg -y -f concat -safe 0 -i ui_concat.txt -c copy ui_full.mp4

# Step 2: 一次性 overlay + eof_action=pass（不冻帧）
ffmpeg -y \
  -i base.mp4 \
  -i ui_full.mp4 \
  -loop 1 -i mask.png \
  -filter_complex \
  "[2:v]format=rgba,scale=600:600[mask_s];\
   [0:v]crop=600:600:60:30,setsar=1,format=rgba[pip_crop];\
   [pip_crop][mask_s]alphamerge[pip_circ];\
   [pip_circ]scale=200:200[pip_small];\
   [0:v][1:v]overlay=x=0:y=0:eof_action=pass[base_ui];\
   [base_ui][pip_small]overlay=x=500:y=60:enable='between(t,15.2,27.7)'[vout]" \
  -map "[vout]" -map 0:a \
  -c:v libx264 -preset fast -crf 19 -pix_fmt yuv420p \
  -c:a copy -r 24 -g 48 -t 33.733 \
  overlay.mp4
```

**验证方法**：抽帧后算 md5，同一 App 段内不同时间点的 md5 必须不同。
```python
import hashlib
for ts in [10, 12, 14, 28, 30]:  # 选集段和播放段
    # extract frame, compute md5
    # if md5 identical at different timestamps → still frozen
```

**为什么不用 enable='between()' 多段叠加**：每段 App 素材是独立输入，`enable` false 时该输入流暂停推进，enable true 时流已 EOF 冻帧。concat 成一条等长视频后用 `eof_action=pass` 只做一次 overlay，输入流从头到尾连续推进，不冻帧。

### 圆形画中画只在部分时段出现

圆形画中画用 `enable='between(t,15.2,27.7)'` 控制——只在分类页+热播榜段出现（15.2-27.7s），选集页和播放页段不叠画中画。这个 enable 是对 PIP overlay 的，不影响主叠加素材流，所以安全。

## 完整合成命令（concat+eof_action=pass 版·0828冻帧修复定案）

```bash
# Step 0: 黑场填充段
ffmpeg -y -f lavfi -i "color=c=black:s=720x1280:d=9.8:r=24" -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -r 24 -g 48 -an pad_pre.mp4
ffmpeg -y -f lavfi -i "color=c=black:s=720x1280:d=1.833:r=24" -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -r 24 -g 48 -an pad_post.mp4

# Step 1: concat 黑场+App素材+黑场
# file 'pad_pre.mp4'\nfile 'app_seg_select.mp4'\nfile 'app_seg_category.mp4'\nfile 'app_seg_hotlist.mp4'\nfile 'app_seg_play.mp4'\nfile 'pad_post.mp4'
ffmpeg -y -f concat -safe 0 -i ui_concat.txt -c copy ui_full.mp4

# Step 2: overlay（eof_action=pass 不冻帧）+ 圆形画中画
ffmpeg -y \
  -i base.mp4 \
  -i ui_full.mp4 \
  -loop 1 -i mask.png \
  -filter_complex \
  "[2:v]format=rgba,scale=600:600[mask_s];\
   [0:v]crop=600:600:60:30,setsar=1,format=rgba[pip_crop];\
   [pip_crop][mask_s]alphamerge[pip_circ];\
   [pip_circ]scale=200:200[pip_small];\
   [0:v][1:v]overlay=x=0:y=0:eof_action=pass[base_ui];\
   [base_ui][pip_small]overlay=x=500:y=60:enable='between(t,15.2,27.7)'[vout]" \
  -map "[vout]" -map 0:a \
  -c:v libx264 -preset fast -crf 19 -pix_fmt yuv420p -c:a copy -r 24 -g 48 -t 33.733 \
  overlay.mp4

# Step 3: Subtitles + Keywords + BGM
ffmpeg -y \
  -i overlay.mp4 -stream_loop -1 -i bgm.mp3 \
  -filter_complex \
  "[0:v]ass='subtitles.ass',ass='keywords.ass'[vout];\
   [1:a]atrim=0:33.733,asetpts=PTS-STARTPTS,volume=0.25[bgm];\
   [0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0:weights='3 1'[aout]" \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset fast -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -ar 48000 -ac 2 -r 24 -g 48 -t 33.733 -movflags +faststart \
  final.mp4
```

### App素材分段准备

```bash
# 每段App录屏截取对应时长，scale到720x1280
for seg in "app_category_full:0:4.0:app_seg_category" \
           "app_hotlist_full:0:4.33:app_seg_hotlist" \
           "app_play_swipe_full:0:4.2:app_seg_play"; do
  IFS=: read src ss dur out <<< "$seg"
  ffmpeg -y -ss $ss -i post/input/${src}.mp4 -t $dur \
    -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24,setsar=1" \
    -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -r 24 -g 48 -an \
    ${out}.mp4
done
```
