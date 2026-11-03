---
title: App录屏UI覆盖层构建 + 圆形画中画 + 白屏修复
description: 触发：用App录屏素材做UI覆盖层、做圆形画中画、修白屏加载段
author: Hermes curator
license: MIT
version: 1.0.0
metadata:
  tags: [ffmpeg, overlay, pip, app-recording, ui, 白屏, geq, alphamerge]
  related_skills: [screen-overlay-tracking, video-production]
---

# App录屏UI覆盖层 + 圆形画中画合成

## When to Use

触发：数字人口播视频需要在画面上叠加真实App录屏（选集页/分类页/热播榜/播放页），并做右上角圆形数字人画中画。与「手机屏跟踪贴图」的区别（⚠️ 后者已于 2026-09-17 用户定案废弃、skill 已删：手机屏内容改走「生成时把闪屏页/界面图当参考图喂给视频模型」）；本参考处理的是**全屏App录屏覆盖底片**（非跟踪贴图）和**从底片截取画面做圆形画中画**（非外部素材叠加）。

## 1. App录屏素材有白屏加载段（2026-08-27 实测）

**症状**：App录屏素材（如选集页录屏4.77秒）前3秒是播放页，第4秒点选集按钮后出现白屏加载，选集列表只闪了不到1秒。直接scale拼进成片→成片22秒处暴露大片白屏+加载圆点。

**解法：冻结最后一帧跳过白屏**
```bash
# 1. 提取选集列表加载完成的那一帧（素材最后一帧或倒数第二帧）
ffmpeg -y -ss 4.5 -i app_select_full.mp4 -frames:v 1 select_list_frame.png

# 2. 提取素材前段（剧情播放画面，无白屏）
ffmpeg -y -i app_select_full.mp4 -t 2 -c copy select_play_0_2.mp4

# 3. 用静帧冻结替代白屏段：
#    静帧3s + 播放段2s + 静帧3s + 分类页2.5s + 热播榜2s + 播放页4s + 播放页静帧0.7s = 17.2s
ffmpeg -y \
  -loop 1 -framerate 30 -t 3.0 -i select_list_frame.png \
  -i select_play_0_2.mp4 \
  -loop 1 -framerate 30 -t 3.0 -i select_list_frame.png \
  -i category.mp4 -i hotlist.mp4 -i play.mp4 \
  -loop 1 -framerate 30 -t 0.7 -i play_last_frame.png \
  -filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p,setpts=PTS-STARTPTS[u0]; ... concat=n=7:v=1:a=0[ui]" \
  -map "[ui]" -an -t 17.2 -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p ui_overlay.mp4
```

**关键**：选集页素材本身就是"剧情正片+选集列表"连着录的，不用拆开，剧情段当画面用、选集页静帧冻结补时长。

## 2. 圆形画中画（geq mask + alphamerge）

**问题**：方案要求14-24.5s右上角圆形数字人画中画，但合成时忘了做，或做了不生效。素材自带的原生App圆形浮窗（如金币任务图标、关注按钮）会被误认为画中画。

**正解：从底片split截取数字人画面，geq生成圆形alpha mask，alphamerge合成**
```bash
# 在完整合成命令的filter_complex里：
[0:v]split=2[base][pip_src];  # 底片split一份做画中画源

[pip_src]trim=start=14:end=24.5,setpts=PTS-STARTPTS,
  scale=320:568,crop=320:320:0:120,format=rgba[pip_rgb];
  # scale到320宽(高568)，crop 320x320从y=120开始截取脸部区域

color=c=black:s=320x320:r=30:d=10.5,format=gray,
  geq=lum='if(lte((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2),(W/2-4)*(W/2-4)),255,0)'[pip_mask];
  # geq生成圆形mask：距中心<=半径-4的像素=255(白)，其余=0(黑)

[pip_rgb][pip_mask]alphamerge,setpts=PTS+14/TB[pip];
  # alphamerge把mask应用到画中画画面

[v_ui][pip]overlay=x=720:y=80:enable='between(t,14,24.5)'[v_pip];
  # 叠加到底片+UI覆盖层上，右上角(720,80)
```

**参数说明**：
- `scale=320:568` → 底片1080x1920缩放到320宽，高度自动568
- `crop=320:320:0:120` → 从y=120开始截320x320正方形（调整120定位脸部）
- `geq` 圆形公式：`(X-W/2)²+(Y-H/2)² ≤ (W/2-4)²` → 圆内255圆外0
- `overlay x=720 y=80` → 右上角，右边距40px，顶部距80px
- `enable='between(t,14,24.5)'` → 14s出现，24.5s消失

## 3. 程序化像素采样QA（比逐帧送vision高效）

用Python PIL批量采样每帧四角+中心+下半部分中心，判断白屏/黑边：
```python
from PIL import Image
img = Image.open(frame_path)
px = img.load()
w, h = img.size
lt = px[10, 10]        # 左上
rt = px[w-10, 10]      # 右上
lb = px[10, h-10]      # 左下
rb = px[w-10, h-10]    # 右下
ct = px[w//2, h//2]    # 中心
cb = px[w//2, int(h*0.75)]  # 下半部分中心

def is_white(p): return all(v > 240 for v in p[:3])
def is_black(p): return all(v < 15 for v in p[:3])
# is_white(cb) → "下半白"（白屏信号）
# is_black(lb) → "左下黑"（黑边信号）
```

逐秒采样整个UI覆盖层，输出白屏/黑边时间轴，比逐帧送vision_analyze快10倍+。先像素采样定位问题段，再针对性送vision确认内容。

## 4. ⚠️ vision会把素材自带原生UI误判为后期画中画

**实测教训（2026-08-27）**：逐帧vision分析成片时，vision报告"右上角有圆形画中画小窗"——但实际是App录屏素材自带的原生平台浮窗（金币任务/关注按钮），不是后期叠加的数字人画中画。合成方案要求的画中画根本没做。

**预防**：
- 确认画中画是否做了，不能只靠vision看"有没有圆形小窗"——要先看素材原始画面有没有自带圆形UI
- 正确判断方法：对比底片split前后的画面——画中画源是从底片截取的数字人，如果右上角小窗里是数字人（穿米白V领毛衣的中年女性）→是后期叠加的；如果是App原生UI（金币图标/关注按钮/头像）→是素材自带的
- 合成后用像素采样检查右上角区域是否有"非底片画面"的像素变化，比vision更可靠

## 5. ⚠️ 对比报告≠实际成片状态

**实测教训**：delegate_task生成的对比修正报告说"大字完全缺失""画中画没有"——但实际抽帧发现大字已有、画中画是素材自带原生UI。报告基于文档分析（读后期合成方案+拆解报告），没实际看成片画面。

**铁律**：验证成片状态必须实际抽帧+vision看，不能基于文档分析报告下结论。报告可以参考方向，但事实以抽帧为准。

## 完整合成命令模板

```bash
ffmpeg -y \
  -i work/hh_base_40s.mp4 \                          # 0: 底片
  -i work/ui_overlay_v2.mp4 \                        # 1: UI覆盖层
  -loop 1 -framerate 30 -i input/logo.png \           # 2: Logo
  -stream_loop -1 -i input/bgm.mp3 \                  # 3: BGM
  -filter_complex "
    [0:v]split=2[base][pip_src];
    [1:v]format=yuva420p,fade=t=out:st=31.0:d=0.2:alpha=1,setpts=PTS-STARTPTS+14/TB[ui];
    [base][ui]overlay=x=0:y=0:enable='between(t,14,31.2)'[v_ui];
    [pip_src]trim=start=14:end=24.5,setpts=PTS-STARTPTS,scale=320:568,crop=320:320:0:120,format=rgba[pip_rgb];
    color=c=black:s=320x320:r=30:d=10.5,format=gray,geq=lum='if(lte((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2),(W/2-4)*(W/2-4)),255,0)'[pip_mask];
    [pip_rgb][pip_mask]alphamerge,setpts=PTS+14/TB[pip];
    [v_ui][pip]overlay=x=720:y=80:enable='between(t,14,24.5)'[v_pip];
    [2:v]scale=220:-1,format=rgba[logo];
    [v_pip][logo]overlay=x=430:y=1400:enable='between(t,10,12.5)+between(t,36.5,40)'[v_logo];
    [v_logo]subtitles=derived/keywords.ass:fontsdir=/usr/share/fonts/truetype/wqy[v_kw];
    [v_kw]subtitles=derived/captions.ass:fontsdir=/usr/share/fonts/truetype/wqy[v_sub];
    [v_sub]subtitles=derived/risk.ass:fontsdir=/usr/share/fonts/truetype/wqy[vout];
    [0:a]atrim=0:40,asetpts=PTS-STARTPTS,aresample=48000[voice0];
    [voice0]asplit=2[voice_mix][voice_sc];
    [3:a]atrim=0:40,asetpts=PTS-STARTPTS,volume=0.16,afade=t=in:st=0:d=2,afade=t=out:st=38:d=2[bgm0];
    [bgm0][voice_sc]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=250[bgm_duck];
    [voice_mix][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.89[aout]
  " \
  -map "[vout]" -map "[aout]" -t 40 \
  -c:v libx264 -preset slow -crf 18 -profile:v high -level 4.1 \
  -pix_fmt yuv420p -r 30 -g 60 -keyint_min 60 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -movflags +faststart \
  output/master_1080x1920_40s.mp4
```

## 验收清单

1. 像素采样UI覆盖层逐秒：无白屏段（`is_white(cb)==False`）
2. 抽帧vision验证14-24.5s右上角：圆形小窗内容是数字人（不是App原生UI）
3. 抽帧vision验证24.5s后：右上角无圆形小窗（画中画已退出）
4. 大字、字幕、Logo、BGM逐项抽帧确认
5. 黑帧检测：`ffmpeg -v warning -i out.mp4 -vf "blackdetect=d=0.3:pix_th=0.10" -an -f null -`
6. ffprobe：时长、分辨率、编码、帧率符合目标
