# 去字幕+调音量：回到无字幕底片用-c:v copy（0828实测）

## 场景

用户说"把原来的小字幕去掉，声音再翻一倍"。字幕是烧进视频流的（ASS 烧录），没法从成片上去掉——只能从无字幕底片重新合。

## 前提：找到无字幕中间产物

火龙项目版本链中，V13 = 贴片合成后、烧字幕之前的中间产物（无字幕、无BGM、纯人声 -17.2dB）。类似项目应保留此中间产物。

诊断方法：
```bash
# 确认底片无字幕：抽帧看画面底部
ffmpeg -i <底片.mp4> -ss 5 -frames:v 1 -update 1 /tmp/check.png -y
# vision_analyze 确认无字幕

# 确认底片有音轨
ffprobe -v error -show_entries stream=codec_type -of csv=p=0 <底片.mp4>
# 应输出: video,audio
```

## 做法：视频流 copy 只处理音频

```bash
ffmpeg -hide_banner -y \
  -i <无字幕底片.mp4> \
  -filter_complex "[0:a]volume=2.0,alimiter=limit=0.95[aout]" \
  -map "0:v" -map "[aout]" \
  -c:v copy \
  -c:a aac -b:a 160k -ar 48000 -ac 2 \
  -t 40.5 \
  -movflags +faststart \
  output.mp4
```

## 参数要点

- `-c:v copy`：视频流直接拷贝，画质零损，速度极快（21x realtime）
- `volume=2.0`：+6dB（感知约翻倍）。V13底片 -17.2dB → 成片 -12.2dB
- `alimiter=limit=0.95`：限幅防削顶（max_volume 到 0.0dB）
- 不写 `-vf`、不烧字幕、不引入外部音频
- `-t` 匹配底片时长

## 验证

1. 抽帧 vision 确认无字幕（2-3帧，含底部区域）
2. `volumedetect` 对比前后音量
3. 实测：底片 mean -17.2dB → 成片 mean -12.2dB = +5dB

## 与其他模式的关系

| 场景 | 视频流 | 音频 | 参考 |
|:---|:---|:---|:---|
| 去字幕+调音量 | `-c:v copy` 不编码 | `volume=2.0` | 本文件 |
| 调音量+烧新字幕 | `-c:v libx264` 重编码 | `volume` in `-af` | 6.7节 |
| 只调字幕参数 | 从无字幕底片重新烧 | 不变 | 5.5/5.5b节 |
| 只调音量不改字幕 | `-c:v copy` | `volume` in `-af` | 5.7节 |

**共同点**：都从无字幕中间产物出发，不调付费API。
