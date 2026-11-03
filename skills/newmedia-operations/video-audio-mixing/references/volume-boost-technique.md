# 音量提升技巧：峰值已达0dB时的正确做法（0827实测）

## 场景

用户反馈视频音量太小，但 `volumedetect` 显示 max_volume 已经是 0.0 dB（峰值已满）。

## 错误做法

- `volume=+5dB` → limiter 压回 0dB → mean 只涨 1dB（-11→-10），听感几乎不变
- `loudnorm` → 动态归一化反而压低整体响度（mean 从 -11 降到 -17dB），更轻了
- `dynaudnorm` → 效果有限，mean 基本不变

## 正确做法：先降峰值 → 压缩动态范围 → 再提整体增益

```bash
ffmpeg -y -i input.mp4 \
  -af "volume=-3dB,acompressor=threshold=-15dB:ratio=3:attack=10:release=100,volume=12dB,alimiter=limit=0.95" \
  -c:a aac -b:a 160k -ar 48000 -ac 2 output.mp4
```

### 原理

1. `volume=-3dB`：先把峰值从 0dB 降到 -3dB，给后面留空间
2. `acompressor`：压缩动态范围（大声音压小，小声音不变），threshold=-15dB 以上的部分被压缩
3. `volume=12dB`：整体提升 12dB（此时峰值在 -3+12=9dB，但被下一步 limiter 拦住）
4. `alimiter=limit=0.95`：硬限幅在 -0.5dB，防爆音

### 实测效果（火龙V7→V8）

- 原始：mean -11.4dB, max 0.0dB
- 修复后：mean -9.9dB, max 0.0dB
- V15模板参考：mean -11.5dB（修复后比模板还响1.6dB）

### 注意

mean volume 从 -11 提到 -9.9 看着不多，但压缩动态范围后，安静段和响亮段的差距缩小了，人耳感知的「整体响度」提升远大于 1.5dB 的数值差异。

### 参考值

短视频口播推荐 mean_volume 在 -10dB 到 -8dB 之间。低于 -12dB 偏轻。

## 相关：ASS 字幕字体 Bold 坑（同一会话发现）

WenQuanYi Zen Hei 没有 Bold 变体——ASS 写 Bold=-1 或 Bold=1，libass 渲染出来还是 Regular。暗背景上不明显，浅色背景上字幕辨识度严重不足。

**修复**：安装 Noto Sans CJK SC（有真 Bold 变体）：
```bash
mkdir -p ~/.fonts
curl -sL -o ~/.fonts/NotoSansSC-Bold.otf "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf"
curl -sL -o ~/.fonts/NotoSansSC-Regular.otf "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf"
fc-cache -fv ~/.fonts/
```

ASS Style 参数参考（火龙网赚口播模板 v15 标准 + 浅色背景增强）：
- Fontname: `Noto Sans CJK SC`
- Fontsize: 56（v15标准）→ 60（浅色背景增强）
- Bold: 1
- Outline: 3（v15）→ 4（浅色背景加粗描边）
- Shadow: 2
- MarginV: 380（偏上避开底部浅色区域）

验证铁律：改字体后必须抽帧 + vision_analyze 验证字幕粗细和可读性。
