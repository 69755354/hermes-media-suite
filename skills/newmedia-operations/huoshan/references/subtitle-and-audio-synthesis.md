# 字幕与音频合成方案（本会话已验证）

## 背景

本方案源自熹园知味35s文艺探店视频的后期制作。节点11执行中暴露了三个关键问题：BGM忽大忽小、环境音缺失、中文字幕方框。本文件记录已验证的完整修复方案。

## 一、问题诊断：BGM忽大忽小

### 根因

各镜原始人声音量不一致：
| 镜号 | 内容 | mean_volume | 说明 |
|:---:|:----|:-----------:|:-----|
| 镜1 | 门头走进 | -15.1 dB | 中等 |
| 镜2 | 落座 | -11.9 dB | 大 |
| 镜3 | 点茶 | -12.4 dB | 大 |
| 镜4 | 品茶（无台词） | **-20.4 dB** | 最小 |
| 镜5 | 走向包间 | -11.8 dB | 最大 |
| 镜6 | 回头收尾 | -15.0 dB | 中等 |

**后果：** amix叠加BGM后，人声大的镜（2/3/5）BGM被压得几乎听不到，人声小的镜（4）BGM突然冒出来→用户觉得"每段bgm声音大小不一样"。

### 修复方案：loudnorm响度归一化

在amix前对原始音频做loudnorm标准化：

```bash
ffmpeg -i concat_raw.mp4 -i bgm.mp3 -i ambient.mp3 \
  -filter_complex "\
    [0:a]loudnorm=I=-16:LRA=11:TP=-1.5[a_norm];\
    [a_norm]volume=1.0[a_voice];\
    [1:a]volume=0.18[a_bgm];\
    [2:a]volume=0.35[a_ambient];\
    [a_voice][a_bgm][a_ambient]amix=inputs=3:duration=first:dropout_transition=2[a_mix];\
    [0:v]subtitles=/tmp/subtitles.ass:fontsdir=/usr/share/fonts/opentype/noto:charenc=UTF-8[v_out]" \
  -map "[v_out]" -map "[a_mix]" \
  -c:v libx264 -crf 18 -preset medium \
  -c:a aac -b:a 128k -ac 2 \
  final.mp4 -y
```

**loudnorm参数说明：**
| 参数 | 值 | 说明 |
|:----|:---|:-----|
| I | -16 | 综合响度目标（短视频推荐-16到-14 LUFS） |
| LRA | 11 | 响度范围（动态范围，默认7，放宽到11保留自然起伏） |
| TP | -1.5 | 真峰值上限（避免削波） |

## 二、三轨混音音量速查表

| 音轨 | 音量 | 适用场景 |
|:----|:----|:---------|
| 视频人声（原始音频 loudnorm） | 1.0 (100%) | 始终不变 |
| BGM | 0.15-0.20 | 有台词镜建议0.18，纯画面镜可到0.22 |
| 环境音 | 0.22-0.35 | 户外场景0.35，室内场景0.22-0.25 |

## 三、中文字幕烧录

### 常见错误

| 错误写法 | 后果 |
|:--------|:-----|
| ASS中Fontname=Arial | 中文字符显示为□□□□ |
| PlayRes太小+Fontsize太大 | 字幕巨大占半屏 |
| Seedance prompt中写`「」`引号 | Seedance渲染为画面字幕 |
| Seedance prompt中写「画面叠白色字幕」 | AI生成乱码emoji |

### 正确流程

**第一步：写SRT**
```srt
1
00:00:00,000 --> 00:00:04,100
第一段台词
跨行用空行

2
00:00:04,100 --> 00:00:09,200
第二段台词
```

**第二步：SRT转ASS**
```bash
ffmpeg -i subtitles.srt subtitles.ass -y
```

**第三步：改ASS字体行（关键步骤）**
```
# 原（Arial→方框）
Style: Default,Arial,16,&Hffffff,&Hffffff,&H0,&H0,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1

# 改（Noto Sans CJK SC→正常显示）
Style: Default,Noto Sans CJK SC,12,&H00ffffff,&H00ffffff,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,10,10,20,1
```

**ASS字段详解：**
| 字段 | 值 | 说明 |
|:----|:---|:-----|
| Fontname | `Noto Sans CJK SC` | 中文字体路径 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` |
| Fontsize | 12 | PlayRes 384x288时，720p竖屏放大后≈53px |
| PrimaryColour | `&H00ffffff` | ABGR格式=白色 |
| OutlineColour | `&H00000000` | 黑色描边 |
| Outline | 2 | 描边宽度 |
| Shadow | 1 | 阴影 |
| Alignment | 2 | 底部居中 |

**第四步：subtitles filter加载**
```bash
subtitles=/tmp/subtitles.ass:fontsdir=/usr/share/fonts/opentype/noto:charenc=UTF-8
```

### 字号与PlayRes对应关系

PlayRes决定了字号的实际大小。PlayRes 384x288（ffmpeg默认）下：

| Fontsize | 720p竖屏实际像素 | 视觉效果 |
|:--------:|:----------------:|:---------|
| 22 | ≈98px | ❌ 太大，占半屏 |
| 16 | ≈71px | ⚠️ 偏大 |
| 12 | ≈53px | ✅ 合适（两行共占屏幕约1/12） |
| 10 | ≈44px | ✅ 偏小但可接受 |

## 四、完整命令模板（一键合成）

```bash
# 参数
VIDEO="concat_raw.mp4"    # 已拼接的6镜视频
BGM="bgm_35s.mp3"         # 统一BGM，35s+版本
AMBIENT="ambient_36s.mp3" # 环境音轨（粉红噪音+鸟鸣混合）
ASS="subtitles.ass"       # 已改字体的ASS字幕文件
OUTPUT="final.mp4"

ffmpeg -i "$VIDEO" -i "$BGM" -i "$AMBIENT" \
  -filter_complex "\
    [0:a]loudnorm=I=-16:LRA=11:TP=-1.5[a_norm];\
    [a_norm]volume=1.0[a_voice];\
    [1:a]volume=0.18[a_bgm];\
    [2:a]volume=0.35[a_ambient];\
    [a_voice][a_bgm][a_ambient]amix=inputs=3:duration=first:dropout_transition=2[a_mix];\
    [0:v]subtitles=$ASS:fontsdir=/usr/share/fonts/opentype/noto:charenc=UTF-8[v_out]" \
  -map "[v_out]" -map "[a_mix]" \
  -c:v libx264 -crf 18 -preset medium \
  -c:a aac -b:a 128k -ac 2 \
  "$OUTPUT" -y
```

## 五、自检清单（出片前逐项）

| # | 检查项 | 通过 |
|:-:|:-------|:----:|
| 1 | 各镜人声音量是否统一 | ☐ |
| 2 | loudnorm已应用（I=-16） | ☐ |
| 3 | BGM全程统一曲目，不跳段 | ☐ |
| 4 | BGM音量0.15-0.20，不压人声 | ☐ |
| 5 | 环境音存在且可听（非静音） | ☐ |
| 6 | 环境音0.22-0.35，背景层不压人声 | ☐ |
| 7 | 字幕ASS中Fontname=Noto Sans CJK SC（非Arial） | ☐ |
| 8 | 字幕Fontsize适配分辨率（384x288→12号） | ☐ |
| 9 | ASS中无中文引号/emoji | ☐ |
| 10 | 总时长±1秒目标时长 | ☐ |
| 11 | 文件大小≤50MB（抖音） | ☐ |
