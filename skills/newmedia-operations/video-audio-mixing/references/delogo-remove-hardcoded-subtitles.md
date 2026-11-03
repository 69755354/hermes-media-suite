# delogo 去硬字幕（无无字幕底片时）+ 调音量（0828实测）

## 场景

用户发来一条视频，要求"把原来的小字幕去掉，声音再翻一倍"。字幕是烧进视频流的硬字幕（ASS 烧录或平台自带），**没有无字幕底片**可回退——只能从成片上去。

## 与 remove-subtitle-boost-volume.md 的区别

| 条件 | 方案 | 文件 |
|:---|:---|:---|
| 有无字幕底片 | `-c:v copy` 只调音频，画质零损 | remove-subtitle-boost-volume.md |
| 无底片，硬字幕烧死 | `delogo` 滤镜糊掉字幕区域，视频重编码 | 本文件 |

## 第一步：检测字幕区域坐标

用 Python PIL + numpy 分析像素，自动定位字幕的 x/y/w/h：

```python
from PIL import Image
import numpy as np

img = Image.open('/tmp/frame.jpg')
arr = np.array(img)
h, w = arr.shape[:2]

# 找字幕行：行内黑白交替多（文字笔画特征）
subtitle_rows = []
for y in range(int(h * 0.75), h):
    row = arr[y, :, :]
    is_dark = (row[:, 0] < 80) & (row[:, 1] < 80) & (row[:, 2] < 80)
    transitions = np.sum(is_dark[:-1] != is_dark[1:])
    if transitions > 15:
        subtitle_rows.append(y)

y_start = subtitle_rows[0]
y_end = subtitle_rows[-1]

# 找字幕左右边界
region = arr[y_start:y_end, :, :]
is_dark = (region[:, :, 0] < 80) & (region[:, :, 1] < 80) & (region[:, :, 2] < 80)
col_has_dark = np.any(is_dark, axis=0)
dark_cols = np.where(col_has_dark)[0]
x_start = dark_cols[0]
x_end = dark_cols[-1]

print(f"delogo=x={x_start-10}:y={y_start-5}:w={x_end-x_start+20}:h={y_end-y_start+10}")
```

**为什么用黑白交替检测**：字幕文字的特征是白色文字+黑色描边，行内有很多黑白像素切换。普通画面（衣服、墙壁）亮度均匀，不会有大量切换。阈值 >15 transitions/行 效果好。

**实测案例**（1080x1920 视频）：
- 字幕区域: x=88-1019, y=1575-1786
- 高度 212px（占画面 11%），用户称之为"小字幕"

## 第二步：delogo + 音量翻倍一条 ffmpeg

```bash
SRC="input.mp4"
OUT="output.mp4"

ffmpeg -hide_banner -y -i "$SRC" \
  -filter_complex "[0:v]delogo=x=80:y=1570:w=940:h=220[vout];[0:a]volume=2.0,alimiter=limit=0.95[aout]" \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset fast -crf 20 -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 160k -ar 48000 -ac 2 \
  -movflags +faststart \
  "$OUT"
```

### 参数要点

- `delogo=x=Y:y=Y:w=W:h=H`：坐标比检测到的略大 10-20px 留余量
- **delogo 没有 `t` 参数**（旧版有 `t=255`，新版报错删掉即可）
- `-c:v libx264 -crf 20`：视频必须重编码（delogo 改了画面），crf 20 画质好
- `volume=2.0`：+6dB 感知翻倍，`alimiter=0.95` 防削顶
- filter_complex 必须单行，换行会导致 ffmpeg 解析失败

## 第三步：验证字幕去除效果

```python
from PIL import Image
import numpy as np

# 处理后抽帧
img = Image.open('/tmp/after.jpg')
arr = np.array(img)

# 对比处理前后字幕区域的黑色像素和方差
region_before = arr_before[y_start:y_end, :, :]
region_after = arr_after[y_start:y_end, :, :]

dark_before = np.sum((region_before[:,:,0] < 80) & (region_before[:,:,1] < 80) & (region_before[:,:,2] < 80))
dark_after = np.sum((region_after[:,:,0] < 80) & (region_after[:,:,1] < 80) & (region_after[:,:,2] < 80))

# 黑色像素从 ~16000 降到 0 = 字幕去干净了
# 方差从 ~3764 降到 ~37 = 区域变平滑
```

### 验证清单

1. 字幕区域黑色像素降到 ≈0
2. 字幕区域方差大幅下降（文字纹理消失）
3. `volumedetect` 确认音量提升
4. vision_analyze 抽 2-3 帧确认无残留字幕（relay 超时时用像素检测代替）

## 效果实测

| 指标 | 处理前 | 处理后 |
|:---|:---|:---|
| mean_volume | -23.4 dB | -17.0 dB |
| max_volume | -8.1 dB | -1.7 dB |
| 字幕区黑色像素 | 16129 | 0 |
| 字幕区方差 | 3764 | 37 |
| 文件大小 | 22MB | 16MB |

## Pitfalls

- **delogo 对大面积字幕效果有限**：delogo 原设计给台标/logo 小面积用，大面积字幕可能残留模糊痕迹。但实测 932x212px 区域效果可接受（黑色像素归零）。如果残留明显，改用裁剪+补黑边或 crop+scale 方案。
- **vision relay 超时**：抽帧后 vision_analyze 可能 relay 超时（大图）。转 jpg 压小或直接用 Python 像素检测代替 vision 验证。
- **坐标要留余量**：delogo 坐标比检测到的字幕区域略大 10-20px，避免边缘残留。
- **filter_complex 不能换行**：多行写法导致 ffmpeg 报 "Option not found"，必须单行。
