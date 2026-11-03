# ffmpeg 圆形画中画 + App录屏白屏修复（2026-08-27 实测）

## 场景

火龙通用口播复刻：底片（数字人口播）+ App录屏覆盖层 + 右上角圆形画中画 + Logo + ASS字幕 + BGM，一步合成。

## 圆形画中画 ffmpeg 实现

从底片 split 出副本，截取 14-24.5s 做 PiP，圆形遮罩叠加到右上角：

```bash
# 输入: [0:v]=底片, [1:v]=UI覆盖层, [2]=Logo, [3]=BGM

[0:v]split=2[base][pip_src];

# UI覆盖层 14-31.2s
[1:v]format=yuva420p,fade=t=out:st=31.0:d=0.2:alpha=1,setpts=PTS-STARTPTS+14/TB[ui];
[base][ui]overlay=x=0:y=0:enable='between(t,14,31.2)'[v_ui];

# 圆形PiP 14-24.5s
[pip_src]trim=start=14:end=24.5,setpts=PTS-STARTPTS,
  scale=320:568,crop=320:320:0:120,format=rgba[pip_rgb];
color=c=black:s=320x320:r=30:d=10.5,format=gray,
  geq=lum='if(lte((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2),(W/2-4)*(W/2-4)),255,0)'[pip_mask];
[pip_rgb][pip_mask]alphamerge,setpts=PTS+14/TB[pip];
[v_ui][pip]overlay=x=720:y=80:enable='between(t,14,24.5)'[v_pip];
```

**关键参数：**
- `PIP_X = 1080 - 320 - 40 = 720`（右边距40px）
- `PIP_Y = 80`（顶部距80px）
- `PIP_CROP_Y = 120`（脸部在568高度中的位置，需根据实际人物调整）
- 圆形mask用 `geq` 画，半径 `W/2-4`（留4px边）
- `enable='between(t,14,24.5)'` 控制出现/退出时段
- **画中画只在该有的时候出现**——照原片时段，不是全程叠加

## App录屏白屏修复

### 问题

App选集页录屏素材只有4.77秒：前3秒是播放页（剧情画面），第4秒点选集按钮后白屏加载，选集列表只闪了不到1秒。直接使用导致成片对应时段大面积白屏。

### 修复方案

从素材最后一帧（选集列表加载完成）抽静帧，冻结延长替代白屏段：

```bash
# 1. 抽选集列表静帧
ffmpeg -y -ss 4.5 -i app_select_full.mp4 -frames:v 1 select_list_frame.png

# 2. 抽播放段（0-2s剧情画面，跳过白屏段）
ffmpeg -y -i app_select_full.mp4 -t 2 -c copy select_play_0_2.mp4

# 3. 重新拼接：静帧3s + 播放段2s + 静帧3s = 8s（跳过白屏）
ffmpeg -y \
  -loop 1 -framerate 30 -t 3.0 -i select_list_frame.png \
  -i select_play_0_2.mp4 \
  -loop 1 -framerate 30 -t 3.0 -i select_list_frame.png \
  -i category.mp4 -i hotlist.mp4 -i play.mp4 ... \
  -filter_complex "[0:v]scale=1080:1920...[u0]; ... [u0][u1]...concat=n=7:v=1:a=0[ui]" \
  -map "[ui]" -an -t 17.2 output.mp4
```

### 像素检测白屏

```python
from PIL import Image
img = Image.open(frame_path)
px = img.load()
w, h = img.size
cb = px[w//2, int(h*0.75)]  # 下半部分中心
def is_white(p): return all(v > 240 for v in p[:3])
if is_white(cb): print("白屏！")
```

**注意**：选集页加载完成后的页面底色是白色——"下半白"不一定是故障，需vision确认内容。区分方法：加载中白屏 = 中心有三个黑色小圆点（loading动画）；加载完成 = 有集数按钮网格。

## 分段拼接完整流水线（2026-08-27 实测定案）

原片是「AI数字人口播 + App录屏交替」的混剪结构，口播音频从头到尾不停。复刻不是一步合成——是分段预处理再拼接。

### 第1步：预处理App录屏段（逐段scale+截取+冻结）

每段录屏素材分辨率不同（540×1116 / 620×1280），先统一scale到720×1280，按目标时长截取：

```bash
# 分类页 5s
ffmpeg -y -i app_category_full.mp4 -t 5 \
  -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24,format=yuv420p" \
  -an -c:v libx264 -preset fast -crf 18 ui_category_5s.mp4

# 选集页 5s（素材只有4.77s，用tpad冻结末帧补到5s）
ffmpeg -y -i app_select_full.mp4 \
  -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24,format=yuv420p,tpad=stop_mode=clone:stop_duration=0.3" \
  -t 5 -an -c:v libx264 -preset fast -crf 18 ui_select_5s.mp4

# 热播榜 4s / 播放页 5s（同上模式）
# 播放页末帧冻结2s（29-31s收尾用）
ffmpeg -y -ss 4.5 -i app_play_swipe_full.mp4 -frames:v 1 play_lastframe.png
ffmpeg -y -loop 1 -framerate 24 -t 2 -i play_lastframe.png \
  -vf "format=yuv420p,fps=24" -c:v libx264 -preset fast -crf 18 ui_play_freeze_2s.mp4
```

**踩坑**：ffmpeg `filter_complex` 里5路concat+builtin filter链容易报 `Error linking filters`。改用 **concat demuxer**（`-f concat -safe 0 -i list.txt`）更稳，list.txt里写绝对路径。

### 第2步：拼接App覆盖层（concat demuxer）

```bash
# ui_concat_list.txt
file '/abs/path/ui_category_5s.mp4'
file '/abs/path/ui_select_5s.mp4'
file '/abs/path/ui_hotlist_4s.mp4'
file '/abs/path/ui_play_5s.mp4'
file '/abs/path/ui_play_freeze_2s.mp4'

ffmpeg -y -f concat -safe 0 -i ui_concat_list.txt \
  -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -r 24 ui_layer_21s.mp4
```

### 第3步：画中画（从底片截数字人→圆形小窗→叠到App层前10s）

```bash
# 从底片截10s做PiP源
ffmpeg -y -ss 10 -i base_v3.mp4 -t 10 -an -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -r 24 pip_source_10s.mp4

# 圆形遮罩叠加
ffmpeg -y \
  -i ui_layer_21s.mp4 \
  -i pip_source_10s.mp4 \
  -filter_complex "\
[1:v]scale=180:180[pip_scaled];\
[pip_scaled]format=yuva420p,\
  geq=lum='p(X,Y)':cb='128':cr='128':a='if(gt(W/2, sqrt((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2))), 255, 0)'[pip_round];\
[0:v][pip_round]overlay=x=720-180-20:y=20:enable='between(t,0,10)'[out]" \
  -map "[out]" -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -r 24 ui_layer_with_pip_21s.mp4
```

**PiP参数**：尺寸180×180，位置 x=520 y=20（右上角，边距20px），只在0-10s出现（对应分类页+选集页段）。geq圆形mask半径=W/2。

**验证**：抽2s帧和12s帧——2s应有圆形小窗（分类页+PiP），12s应无PiP（热播榜段）。

### 第4步：PIL生成片尾搜索卡

```python
from PIL import Image, ImageDraw, ImageFont
W, H = 720, 1280
img = Image.new('RGB', (W, H), (15, 23, 42))  # 深蓝渐变
draw = ImageDraw.Draw(img)
# 渐变背景
for y in range(H):
    r = int(15 + (25-15) * y/H)
    g = int(23 + (35-23) * y/H)
    b = int(42 + (70-42) * y/H)
    draw.line([(0, y), (W, y)], fill=(r, g, b))
# Logo圆形裁剪
logo = Image.open('huolong_logo.jpg').convert('RGBA')
logo_resized = logo.resize((200, 200))
mask = Image.new('L', (200, 200), 0)
ImageDraw.Draw(mask).ellipse([0, 0, 200, 200], fill=255)
img.paste(logo_resized, ((W-200)//2, 250), mask)
# 搜索框（左白右黑）
draw.rounded_rectangle([110, 520, 610, 580], radius=30, fill=(255,255,255))
draw.rounded_rectangle([290, 520, 610, 580], radius=30, fill=(20,20,20))
# 文字
font = ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 28)
draw.text((130, 532), '搜索', fill=(0,0,0), font=font)
draw.text((310, 532), '火龙漫剧', fill=(255,255,255), font=font)
img.save('endcard_3s.png')
```

```bash
ffmpeg -y -loop 1 -framerate 24 -t 3 -i endcard_3s.png \
  -vf "format=yuv420p,fps=24" -c:v libx264 -preset fast -crf 18 endcard_3s.mp4
```

### 第5步：最终合成（视频段拼接 + 底片音频全程不停）

```bash
# 截底片各段
ffmpeg -y -ss 0 -i base_v3.mp4 -t 10 -an -c:v libx264 ... base_0_10.mp4     # 数字人0-10s
ffmpeg -y -ss 31 -i base_v3.mp4 -t 6 -an -c:v libx264 ... base_31_37.mp4    # 数字人31-37s

# 拼视频轨
cat > video_concat_list.txt << 'EOF'
file '/abs/path/base_0_10.mp4'
file '/abs/path/ui_layer_with_pip_21s.mp4'
file '/abs/path/base_31_37.mp4'
file '/abs/path/endcard_3s.mp4'
EOF

ffmpeg -y -f concat -safe 0 -i video_concat_list.txt \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 24 video_track_40s.mp4

# 提底片完整音频（40s不停）
ffmpeg -y -i base_v3.mp4 -t 40 -vn -c:a aac -b:a 128k audio_40s.aac

# 合视频+音频
ffmpeg -y \
  -i video_track_40s.mp4 \
  -i audio_40s.aac \
  -map 0:v:0 -map 1:a:0 \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 24 \
  -c:a aac -b:a 128k -movflags +faststart \
  huolong_replica_v4.mp4
```

### 时间轴总结

| 时间 | 画面 | 来源 |
|:--:|:--|:--|
| 0-10s | 数字人全屏口播 | base_0_10 |
| 10-15s | 分类页+PiP | ui_layer_with_pip 前5s |
| 15-20s | 选集页+PiP | ui_layer_with_pip 5-10s |
| 20-24s | 热播榜（无PiP） | ui_layer_with_pip 10-14s |
| 24-29s | 播放页（无PiP） | ui_layer_with_pip 14-19s |
| 29-31s | 播放页冻结 | ui_layer_with_pip 19-21s |
| 31-37s | 数字人收束 | base_31_37 |
| 37-40s | 片尾搜索卡 | endcard_3s |

### 关键教训

1. **concat demuxer比filter_complex concat稳**：5路concat在filter_complex里容易报Error linking filters，改用`-f concat -safe 0 -i list.txt`（绝对路径）一步过。
2. **App录屏素材分辨率不统一**（540×1116/620×1280），必须逐段`scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280`统一，否则拼接后黑边/变形。
3. **tpad冻结末帧**：素材时长不够（4.77s需5s）用`tpad=stop_mode=clone:stop_duration=0.3`补齐，避免concat时长不匹配。
4. **音频和视频分离合成**：底片音频从头到尾不停（40s），视频分段拼接后单独合音频，这样App覆盖段声音连续不断。
5. **PiP的geq圆形mask**：`geq=lum='p(X,Y)':cb='128':cr='128':a='if(gt(W/2, sqrt(...)), 255, 0)'`画圆形alpha mask，比color+geq两步法更简洁。
6. **PIL做片尾卡**：渐变背景+圆形Logo裁剪+搜索框模拟，比ffmpeg drawtext灵活得多。
