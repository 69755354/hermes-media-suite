# ffmpeg 贴片素材叠加踩坑集（2026-08-26 火龙夜店版 V6→V14 迭代）

> 复刻/仿拍类视频后期 ffmpeg overlay：APP 界面截图/录屏素材叠加到 AI 生成基底片上。

## 1. stream_loop：动态视频素材必须 -1

| 参数 | 行为 | 结果 |
|:----|:----|:----|
| `-stream_loop -1` | 无限循环播放 | ✓ 素材始终动态 |
| `-stream_loop 0` | 只播一次 | ✅ 播完后停最后一帧变静态截图 |
| 不带 `-stream_loop` | 默认只播一次 | ✅ 同上 |

V6 用了 `-stream_loop 0`，双列流和 AI 特效播完变静态截图。V7 改 `-stream_loop -1` 后正常。

**验证方法**：抽同一段素材 0.5 秒间隔两帧，像素变化率 >30% = 动态。
```python
from PIL import Image; import numpy as np
img1 = np.array(Image.open("frame_29.0s.jpg")); img2 = np.array(Image.open("frame_29.5s.jpg"))
pct = (np.abs(img1.astype(int) - img2.astype(int)) > 10).sum() / img1.size * 100
```

## 2. 贴片时码对齐当前版本口播，不能照搬参考片

不同版本文案不同、口播节奏不同。照搬 V19 的素材时码到 V6，素材出现时间跟口播不同步。

**正确做法**：
1. `ffmpeg -af silencedetect` 测当前版本每句口播的实际起止时间
2. 素材出现时码 = 对应口播句子的开始时间
3. 字幕 ASS 时码也按实际语音段调整

## 3. 贴片 y 坐标：算素材范围 vs 脸部范围

无脑 +80 下移不对——大素材（高 770px）y=230 时仍覆盖脸部（y=100-300）。

- 大素材：y 要大于脸部底部（如 y=350），或缩短素材显示时间在硬切前消失
- 双列流/竖屏：缩小高度（820→700）+ 上移（y=80），给底部字幕留空间
- 检查：素材顶部 y + 素材高度 < 字幕 MarginV 对应的 y 坐标

## 4. 素材时长不能跨镜

金币页素材 9.5-11.2s，但镜2在 10.04s 硬切——10.04-11.2s 素材挡住镜2人物脸。
**修复**：素材结束时间 = 镜2硬切时间（9.5-10.04s）。

## 5. 同时间段不能放两个贴片（重叠）

V8 双列动态提前到 25.62s，但剧库筛选（静态图）还到 27.2s 结束——25.62-27.2s 两个素材重叠。
**修复**：去掉静态素材，只留动态视频。

## 6. BGM 提取法：有BGM版减无BGM版 = 纯BGM

没有现成 BGM 文件，但有两个版本成片（一个有 BGM 一个没有），人声相同时可相减提取纯 BGM：

```python
import wave, numpy as np
def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32), w.getframerate()
novoice, _ = read_wav('v19_no_bgm.wav')
withbgm, _ = read_wav('v19_with_bgm.wav')
min_len = min(len(novoice), len(withbgm))
bgm = np.clip(withbgm[:min_len] - novoice[:min_len], -32768, 32767).astype(np.int16)
```

提取的 BGM mean=-10.4dB，可直接用。混音时 `amix weights='2 1'`（人声权重 2、BGM 权重 1）。

## 7. BGM 音量放大注意底噪

源文件极静（mean < -35dB），放大 50 倍会把底噪放大成噪音。用户反馈"跟噪音一样"。

**避免**：
- 优先找音质好的 BGM 源（mean > -15dB）
- 放大后加 `alimiter=limit=0.95` 防爆音
- 放大倍数从 3 倍开始逐步试
- 源文件质量差就直接换 BGM 或不用 BGM

## 8. 砍尾卡后的 logo + 箭头时码

V6 砍掉镜4尾卡（43s→40s），但 V19 的尾部 logo+箭头时码是 39.2-43.8s。需要重新对齐到当前版本口播"现在左下角"对应的时段（36.26s）出现。

## 9. 迭代验证流程

每次改贴片参数后：
1. 抽关键帧（每个素材出现的时间点）
2. 用 vision_analyze 确认素材位置、是否挡脸、是否动态
3. 用像素对比法确认动态素材是否在动
4. 发飞书给用户确认
5. 用户反馈后逐个修，不要一次改太多参数
