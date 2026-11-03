# 火龙漫剧原片素材插入模式（2026-08-28 逐帧拆解）

> 源文件：`7651520678046771450.mp4`（39.8s，刘姐原片）
> 拆解方法：每秒1帧共40帧，接触印样图vision全局分析 + 关键帧逐帧vision确认

## 原片完整时间线

| 时段 | 类型 | 画面内容 | 花字关键词 | 画中画 |
|------|------|----------|------------|--------|
| 0-4s | A=数字人全屏 | 吐槽段开头 | 逐词弹出 | 无 |
| 5-6s | B=上下分屏 | 上=圆形数字人 + 下=签到日历App界面 | "才能" | 无（分屏本身就是PIP效果） |
| 7-9s | A=数字人全屏 | 继续吐槽 | 逐词 | 无 |
| 10-11s | D=数字人+小画中画 | 弹出火龙漫剧App图标 | "火龙漫剧" | 小图标级 |
| 12-15s | C=全屏App界面 | 抖音短剧播放页（闪婚成宠） | "直接看全集" | 无 |
| 16-24s | C=全屏App界面 | 分类筛选页（题材/设定/看点/画风/排序） | "题材丰富""悬疑脑洞" | 右上角圆形数字人 |
| 25-26s | C=全屏App界面 | 热播榜（漫榜/剧榜/热搜榜） | "新剧上架" | 右上角圆形数字人 |
| 27-31s | C=全屏App界面 | 短剧播放页（另一段短剧） | "丝滑流畅""快进快退" | **无画中画** |
| 32-39s | A=数字人全屏 | 收尾段 | "追剧体验""划算" | 无 |

## 关键发现

1. **交替切换**：原片不是一段素材从头盖到尾，是5种不同App界面在不同内容点出现
2. **分类页最长**：分类筛选页占9秒（16-24s），是最长的App素材段
3. **画中画只在分类/热播榜段出现**：播放页段没有画中画数字人
4. **上下分屏**：签到日历段是上下分区布局，不是全屏覆盖
5. **硬切无渐变**：所有App素材切换都是硬切，不做半透明渐变

## 映射到33.7s版本

| 我们的时段 | 画面 | 对应原片 | App素材 |
|-----------|------|----------|---------|
| 0-10s | 数字人 | 0-9s | 无 |
| 10-15s | 数字人+底部分屏选集页 | 5-6s上下分屏 | app_select_full |
| 15-24s | 全屏分类页+圆形PIP | 16-24s | app_category_full |
| 24-28s | 全屏热播榜+圆形PIP | 25-26s | app_hotlist_full |
| 28-32s | 全屏播放页(无PIP) | 27-31s | app_play_swipe_full |
| 32-34s | 数字人收尾 | 32-39s | 无 |

## ffmpeg合成命令

```bash
# 准备4段App素材（各自scale到720x1280, 24fps, 无音轨）
for each app_*.mp4:
  ffmpeg -y -ss 0 -i source.mp4 -t <dur> \
    -vf "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24,setsar=1" \
    -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -r 24 -an out.mp4

# 需要循环的素材用 -stream_loop -1
ffmpeg -y -stream_loop -1 -i source.mp4 -t <dur> \
  -vf "scale=720:1280..." ...

# 主合成（底片+4段App+圆形PIP mask）
ffmpeg -y \
  -i base_video.mp4 \
  -i app_seg_select.mp4 \
  -i app_seg_category.mp4 \
  -i app_seg_hotlist.mp4 \
  -i app_seg_play.mp4 \
  -loop 1 -i circle_mask_600.png \
  -filter_complex "
    [0:v]crop=600:600:60:30,setsar=1,format=rgba[pip_crop];
    [5:v]format=rgba,scale=600:600[mask_s];
    [pip_crop][mask_s]alphamerge[pip_circ];
    [pip_circ]scale=200:200[pip_small];
    [0:v][1:v]overlay=x=0:y=720:enable='between(t,9.8,15.2)'[v1];
    [v1][2:v]overlay=x=0:y=0:enable='between(t,15.2,24.0)'[v2];
    [v2][3:v]overlay=x=0:y=0:enable='between(t,24.0,27.7)'[v3];
    [v3][4:v]overlay=x=0:y=0:enable='between(t,27.7,31.9)'[v4];
    [v4][pip_small]overlay=x=500:y=60:enable='between(t,15.2,27.7)'[vout]
  " \
  -map "[vout]" -map 0:a \
  -c:v libx264 -preset fast -crf 19 -pix_fmt yuv420p \
  -c:a copy -r 24 -g 48 -t 33.733 \
  overlay_step.mp4

# 烧字幕+花字+BGM
ffmpeg -y \
  -i overlay_step.mp4 \
  -stream_loop -1 -i bgm.mp3 \
  -filter_complex "
    [0:v]ass='subtitle.ass',ass='keywords.ass'[vout];
    [1:a]atrim=0:33.733,asetpts=PTS-STARTPTS,volume=0.25[bgm];
    [0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0:weights='3 1'[aout]
  " \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset fast -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -ar 48000 -ac 2 \
  -r 24 -g 48 -t 33.733 -movflags +faststart \
  final_output.mp4
```

## 真录屏 vs 静态截图拼接素材

**0828翻车**：v8 用静态截图拼接（每秒换一张图）冒充动态素材，用户一眼看出"素材还是静态的"。

**识别方法**：抽帧间隔0.5s的两帧做 vision 对比——
- 真录屏：连续运动（滚动位置渐变、手指点击动画、视频播放进度变化）
- 截图拼接：离散跳变（画面瞬间切换，没有中间过渡帧）

**真录屏素材位置**：`workflow/projects/huolong_general_template_v1/assets/`
- `app_select_full.mp4`（540×1116, 4.77s, 30fps）— 播放页→选集页点击
- `app_category_full.mp4`（620×1280, 5.93s, 40fps）— 筛选页滚动
- `app_hotlist_full.mp4`（540×1116, 4.33s, 30fps）— 上新页滚动
- `app_play_swipe_full.mp4`（540×1116, 5.40s, 30fps）— 播放页滑动

**使用方式**：用 `-stream_loop -1` 循环填满时长 + `scale=720:1280` 统一分辨率：
```bash
ffmpeg -y -i base.mp4 \
  -stream_loop -1 -i app_select_full.mp4 \  # 真录屏循环
  -stream_loop -1 -i app_category_full.mp4 \
  -filter_complex \
  "[1:v]scale=720:1280,setsar=1[dyn_sel];" \
  "[0:v][dyn_sel]overlay=enable='between(t,9.8,15.2)'[v1];..."
```

## -c copy 裁切导致飞书黑屏

**0828翻车**：从 v8 用 `ffmpeg -t 9.8 -c copy` 裁切 clip 发飞书，用户反馈黑屏只有声音。

**根因**：`-c copy` 在非关键帧位置切出，片段首帧不是 I 帧，飞书播放器无法解码。

**修复**：裁切必须重编码视频流：
```bash
# ❌ 飞书黑屏
ffmpeg -i full.mp4 -t 9.8 -c copy clip.mp4
# ✅ 重编码
ffmpeg -y -i full.mp4 -t 9.8 -c:v libx264 -preset fast -crf 19 -pix_fmt yuv420p -c:a aac -b:a 128k clip.mp4
```

## DashScope 5段拼接版（0828 hh_segments）

独立于刘姐/夜店路线，用 DashScope 快乐马 r2v 5段拼接：

| 文件 | 时长 | 素材类型 | 状态 |
|:---|:---|:---|:---|
| huolong_hh_final_v8.mp4 | 33.75s | 静态截图拼接 | ❌ 用户反馈"静态" |
| huolong_hh_final_v13.mp4 | 33.75s | 真录屏动态 | ✅ 换成真录屏 |
| huolong_hh_final_v14.mp4 | 33.75s | 真录屏动态 | 去黄字+logo放品牌提及点(错位) |
| huolong_hh_final_v15.mp4 | 33.75s | 真录屏动态 | 去黄字+logo放片尾(从V8裁切,文件被清理) |
| huolong_hh_final_v16.mp4 | 33.65s | 真录屏动态 | ✅ **V16定稿**：从底层重建(concat底片+4段动态录屏+无花字+片尾logo+BGM) |

路径：`/home/ubuntu/huolong_runs/hh_segments/` 或 `workflow/projects/huolong_general_template_v1/output/template_v6/`

## V16完整重建命令（定稿，0828）

三件事同时做（换动态素材+去花字+加logo）时，从concat底片开始一步重建最干净：

```bash
# Step 1: 5段r2v底片concat
ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy hh_base_merged.mp4

# Step 2: 4段动态录屏overlay + 字幕(无花字) + 片尾logo + BGM
ffmpeg -y \
  -i hh_base_merged.mp4 \
  -stream_loop -1 -i app_select_full.mp4 \
  -stream_loop -1 -i app_category_full.mp4 \
  -stream_loop -1 -i app_hotlist_full.mp4 \
  -stream_loop -1 -i app_play_swipe_full.mp4 \
  -loop 1 -i logo.jpg \
  -stream_loop -1 -i bgm.mp3 \
  -filter_complex \
  "[1:v]scale=720:1280,setsar=1[dyn_sel];\
   [2:v]scale=720:1280,setsar=1[dyn_cat];\
   [3:v]scale=720:1280,setsar=1[dyn_hot];\
   [4:v]scale=720:1280,setsar=1[dyn_play];\
   [5:v]scale=120:120,format=rgba[logo_s];\
   [0:v][dyn_sel]overlay=x=0:y=0:enable='between(t,12.0,17.8)'[v1];\
   [v1][dyn_cat]overlay=x=0:y=0:enable='between(t,17.8,22.8)'[v2];\
   [v2][dyn_hot]overlay=x=0:y=0:enable='between(t,22.8,26.0)'[v3];\
   [v3][dyn_play]overlay=x=0:y=0:enable='between(t,26.0,31.6)'[v4];\
   [v4]ass='hh_subtitle_v3.ass'[vsub];\
   [vsub][logo_s]overlay=x=580:y=1080:enable='between(t,31.6,33.652)':format=auto,format=yuv420p[vout];\
   [6:a]atrim=0:33.652,asetpts=PTS-STARTPTS,volume=0.25[bgm];\
   [0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0:weights='3 1'[aout]" \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset fast -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 128k -ar 48000 -ac 2 \
  -r 24 -g 48 -t 33.652 -movflags +faststart \
  huolong_hh_final_v16.mp4
```

**V16 vs V15区别**：V15从overlay_step_v9(含静态素材)裁切+overlay动态素材，文件被磁盘清理后丢失。V16从concat底片一步重建，不依赖中间产物，可复现。

**App素材时间轴映射**（按字幕内容段对位）：
- 12.0-17.8s: select页 → "题材丰富"段
- 17.8-22.8s: category页 → "悬疑脑洞/穿越逆袭"段
- 22.8-26.0s: hotlist页 → "新剧上架/不用担心没剧看"段
- 26.0-31.6s: play页 → "画质高清/丝滑流畅/快进快退/追剧体验"段

## 验证清单

- [ ] 抽帧确认每段App素材是动态的（不是同一帧重复）——用真录屏不是截图拼接
- [ ] 抽帧确认分类页/热播榜/播放页画面内容不同
- [ ] 确认圆形PIP只在指定时段出现（播放页段无PIP）
- [ ] 确认字幕和花字关键词对齐
- [ ] 确认BGM不盖人声
- [ ] 裁切片段发飞书时用重编码不用 -c copy
