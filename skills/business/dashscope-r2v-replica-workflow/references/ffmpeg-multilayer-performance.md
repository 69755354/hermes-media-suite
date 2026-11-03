# ffmpeg 多层 Overlay 合成性能与分步合成

> 源自 2026-08-26 火龙 V20 复刻 v5 合成。一条 ffmpeg 命令同时做 10 层 overlay + ASS 字幕 + BGM 混音，在 3.7GB 内存机器上跑 14+ 分钟没完，输出文件 100MB+（正常应 12MB）。

## 一、问题：一步到位合成爆码率+爆时间

**症状**：一条 ffmpeg 命令包含 10 个 `-loop 1` 图片输入 + 2 个动态视频输入 + base 视频 + BGM 音频，filter_complex 链做 10 层 overlay + ASS 烧录 + amix/sidechaincompress 混音。在 3.7GB 内存机器上：
- 渲染 14+ 分钟未完成
- 输出文件 100MB+（同参数分步合成只需 12MB）
- CPU 163%（满载），内存 1.8GB

**根因**：x264 编码器在处理多层数据叠加（overlay 链 + ASS 渲染）时，每帧需要把所有 overlay 层合成到内存再编码。层越多，内存占用越大，编码效率越低，码率越难控制。

## 二、正解：分两步合成

### 步骤 1：base + 贴片 overlay（无字幕无 BGM）

```bash
ffmpeg -y -i base.mp4 \
  -loop 1 -framerate 30 -t 41 -i 贴片1.png \
  -loop 1 -framerate 30 -t 41 -i 贴片2.png \
  ... 更多贴片 ... \
  -filter_complex "
[1:v]crop=360:770:180:150,scale=360:770,format=rgba[img1];
[2:v]scale=390:780,format=rgba[img2];
...
[0:v][img1]overlay=x=110:y=200:enable='between(t,6.9,8.0)'[o1];
[o1][img2]overlay=x=180:y=230:enable='between(t,9.5,11.2)'[o2];
...
" \
  -map "[o10]" -map 0:a \
  -c:v libx264 -preset fast -crf 20 -pix_fmt yuv420p -r 30 -g 60 \
  -c:a copy \
  -t 40.5 \
  overlay_step1.mp4
```

### 步骤 2：overlay_step1 + ASS 字幕 + BGM 混音

```bash
ffmpeg -y -i overlay_step1.mp4 -i bgm.wav \
  -filter_complex "
[0:v]ass='字幕.ass'[vout];
[1:a]volume=3.0[bgm_boost];
[0:a][bgm_boost]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]
" \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p -r 30 -g 60 \
  -c:a aac -b:a 160k -ar 48000 -ac 2 \
  -t 40.5 \
  final.mp4
```

**性能对比**：

| 方式 | 耗时 | 文件大小 | 码率 |
|:---|:---|:---|:---|
| 一步到位 | 14+ min（未完成） | 100MB+ | ~20000 kbps |
| 分两步 | ~3 min/步 = 6 min | 12MB | ~2200 kbps |

## 三、关键踩坑

### 1. `-loop 1` 图片输入必须加 `-t` 限制

**翻车**：10 个 `-loop 1 -framerate 30 -t 45` 图片输入，如果某个 overlay 的 `enable` 条件全部不满足（时间段已过），ffmpeg 可能继续解码无限帧，产出 1025 秒视频（应 40 秒）。

**修复**：
- 每个图片输入都加 `-t 41`（比视频长 1 秒余量）
- 输出端再加 `-t 40.5` 双保险
- 动态视频输入用 `-stream_loop 0`（不循环），不用 `-stream_loop -1`（无限循环）

### 2. sidechaincompress 语法错误

**报错**：`Cannot find a matching stream for unlabeled input pad sidechaincompress`

**错误写法**（amix 输出后直接接 sidechaincompress）：
```bash
[0:a][bgm_boost]amix=inputs=2:...,
sidechaincompress=threshold=0.45:ratio=8:...[voice_bgm]
```
amix 输出是单流，sidechaincompress 需要两个输入流（主+侧链），找不到第二个输入。

**正确写法**（如果要用 ducking）：
```bash
[0:a][bgm_boost]sidechaincompress=threshold=0.45:ratio=8:attack=5:release=200[ducked_bgm];
[0:a][ducked_bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]
```

**最简方案**（不用 sidechain，直接 volume+amix）：
```bash
[1:a]volume=3.0[bgm_boost];
[0:a][bgm_boost]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]
```

### 3. BGM 音量太低

**用户反馈**："BGM 声音太小，完全听不到"

**原因**：BGM 文件本身音量低（-43dB 平均），amix 的 `normalize=0` 虽然不自动归一化，但 BGM 没做前置放大。

**修复**：BGM 先 `volume=3.0` 翻 3 倍再 amix。实测 `volume=2.0` 可能还不够，`volume=3.0` 才能听清。

**验证**：
```bash
ffmpeg -i final.mp4 -af volumedetect -f null - 2>&1 | grep mean_volume
# mean_volume 低于 -20dB 说明 BGM 太弱
```
