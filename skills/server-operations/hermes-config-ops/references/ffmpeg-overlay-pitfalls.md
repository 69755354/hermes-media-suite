# ffmpeg 合成踩坑集（火龙复刻 2026-08-26 实测）

> 触发：视频成片合成、贴片 overlay、BGM 混音、字幕烧录时反复出问题。
> 适用场景：复刻视频后期合成、APP 推广视频贴片、任何 ffmpeg overlay + amix 合成。

## 1. overlay 视频素材必须 stream_loop -1

**症状：** 贴片用视频素材（如 APP 界面录屏），overlay 后画面只动了一小段就变成静态截屏。用户说"发的是截图"。

**根因：** ffmpeg overlay 输入视频素材时，如果不加 `-stream_loop -1`，视频只播一次就停在最后一帧。overlay 的 `enable='between(t,25,30)'` 时间窗口内，2秒的视频播完后剩下3秒全是定格。

**正解：**
```bash
# 视频素材必须 -stream_loop -1（无限循环）
-stream_loop -1 -i "双列动态_用户提供.mp4" \
-stream_loop -1 -i "竖屏页动态_孙悟空_clean.mp4" \
```

**验证是否动态：** 抽同一段内 0.5s 间隔两帧，用 Python 比较像素差异：
```python
from PIL import Image
import numpy as np
img1 = np.array(Image.open('frame_29.0s.jpg'))
img2 = np.array(Image.open('frame_29.5s.jpg'))
diff = np.abs(img1.astype(int) - img2.astype(int))
pct = (diff > 10).sum() / diff.size * 100
print(f'changed={pct:.1f}%')  # >10% = 动态
```

## 2. BGM 音量调到够响的正确方法

**症状：** 用户反复说"BGM太小"，volume 从 3.0 改到 6.0 再到 8.0 都不够响。

**根因链：**
1. BGM 源文件可能极度安静：`volumedetect` 显示 mean=-45dB（几乎听不到）
2. `amix` 默认把两路音频各取 50% 混合 → BGM 被人声再压一半
3. `volume=3.0` 只 +18dB，BGM 变成 mean=-27dB，混合后更低
4. 需要量级判断：人声 mean=-17dB，BGM 要接近人声音量才听得清

**正确方法：**
```bash
# 1. 先测 BGM 源文件电平
ffmpeg -hide_banner -i bgm.wav -af "volumedetect" -f null - 2>&1 | grep mean_volume

# 2. 算需要的 volume 倍数
# 目标：BGM 混合后 mean ≈ -18dB（跟人声差不多）
# BGM源 mean=-45dB → 需 +27dB → volume=22倍
# 但 amix 各取50%再压3dB → 多给一倍 → volume=30+

# 3. 实战经验：volume=20.0 + amix normalize=0 + weights='1 1'
ffmpeg -y -i overlay.mp4 -i bgm.wav \
  -filter_complex "
  [1:a]volume=20.0[bgm_boost];
  [0:a][bgm_boost]amix=inputs=2:duration=first:dropout_transition=0:normalize=0:weights='1 1'[aout]
  " \
  -map "[aout]" -c:a aac -b:a 160k out.mp4

# 4. 验证成片电平
ffmpeg -hide_banner -i out.mp4 -af "volumedetect" -f null - 2>&1 | grep mean_volume
# 目标：mean ≈ -15dB（人声+BGM混合后合理范围）
```

**经验值：** BGM源 mean=-45dB 时，volume=20.0 是最低线。用户觉得小就继续翻倍到 30-40。别从 3.0 开始一点点试。

## 2b. BGM 源文件选择——不要用噪音文件，用 BGM 库

**🚨 BGM 源文件质量差时放大 50 倍 = 噪音（2026-08-26 用户原话："不知道什么东西跟噪音一样"）**

`环境音与轻BGM_43s.wav`（mean=-44.9dB）放大 50 倍后底噪也放大 50 倍 = 听起来像白噪音，不是 BGM。

**✅ BGM 库位置（广州机）：** `/home/ubuntu/assets/bgm/` — 29 首 mixkit 免版权音乐 + 2 首 codex 生成音乐
```bash
# 从新加坡拉 BGM 到本机
scp -P 2222 -o ConnectTimeout=10 ubuntu@127.0.0.1:/home/ubuntu/assets/bgm/mixkit_834.mp3 /tmp/bgm.mp3
# mixkit_834: 52秒 mean=-15.6dB — 音量正常，适合 40 秒短视频
```

**选 BGM 原则：**
1. 时长 ≥ 成片时长（40.5 秒视频选 ≥45 秒的 BGM）
2. mean ≥ -20dB（源文件本身够响，不用放大太多）
3. 音乐风格匹配视频调性（广告/推广选轻快节奏）
4. 拉到本机后 `volumedetect` 验证音量

## 2c. BGM 提取——禁止用音频相减（2026-08-26 事故）

**🚨 事故：** 想从 V19_BGM 版本提取纯 BGM，用 `V19_BGM音频 - V19纯人声音频 = BGM`。但两版人声文案不同（中年下沉版 vs 夜店版），相减把人声也减出来了，用户骂："傻逼把配音给提取了"

**规则：** 不同文案的两个版本音频不能相减提取 BGM。同一版本的无 BGM 版和有 BGM 版才能相减（且人声必须完全一致）。如果找不到纯 BGM 源文件，直接用 BGM 库换一首，不要尝试提取。

## 3. overlay 素材位置与字幕重叠

**症状：** 大尺寸 overlay 素材覆盖了画面中下部，ASS 字幕正好落在素材内部，字幕和素材内容重叠看不清。

**排查方法：**
1. 算素材覆盖范围：y=185, height=820 → 底部到 y=1005（1280画面占78%）
2. 算字幕位置：Alignment=2, MarginV=380 → 字幕在 y=1280-380=900
3. 900 在 185-1005 范围内 → 重叠！

**解决方案（按优先级）：**
1. **缩小素材高度**：height 从 820→700，y 上移到 80，底部到 780，字幕在 900 不重叠
2. **素材上移**：y 从 185→80，给底部字幕留空间
3. **字幕用 \pos 逐句定位**：在素材出现的时间段，用 ASS override `{\pos(x,y)}` 把字幕移到素材下方

## 4. overlay 贴片坐标挡脸

**症状：** 贴片素材 y=230，高度 770px，覆盖了人物脸部区域。

**排查：** vision_analyze 抽帧确认"贴片遮挡了人物右半侧脸"

**解决：**
1. vision_analyze 抽帧确认挡脸
2. y 坐标下移：y=230→350，让素材从脸部下方开始
3. 或缩小素材高度
4. 改完抽帧 vision_analyze 验证不挡脸

**经验值：** 720x1280 画面，人物脸部约在 y=100-350 区域。贴片素材 y 起始值 ≥350 才不挡脸。

## 5. 素材时码必须跟口播对齐

**症状：** 口播 25.6 秒说"双列流界面随心滑动"，但双列流素材 28.6 秒才出现——素材比口播晚 3 秒。

**根因：** 从旧版成片照搬素材时码，但新版口播节奏不同，同一时码在旧版对得上但在新版对不上。

**解决：**
1. 用 silencedetect 或波形分析测实际语音段
2. 读 ASS 字幕每句的时码
3. 素材时码必须跟对应口播句子的开始时间同步
4. 例：字幕 25.620s"双列流界面随心滑动" → 双列流素材 enable='between(t,25.620,...)'

## 5b. 两个素材 enable 窗口重叠

**症状：** 用户说"双列流那个地方放了两个素材"，画面上两个贴片同时出现。

**根因：** 两个 overlay 的 `enable='between(t,...)'` 时间窗口有交集。
- filter_page: enable='between(t,25.800,27.200)'
- double_page: enable='between(t,25.620,30.400)'
- 25.620-27.200 之间两个素材同时在画面上

**解决：** 去掉不需要的素材（用户说"把静态那个去掉"），或调整 enable 时码使两个不重叠。在改素材时码对齐口播时，必须同时检查是否与相邻素材的时间窗口产生了新的重叠。

## 5c. 素材持续时间太长挡住下一镜人脸

**症状：** 用户说"火龙币能换成现金提走那个素材持续时间太长了，把镜2出来的人脸挡住了"。

**根因：** 金币页(提现界面) enable='between(t,9.500,11.200)'，但镜2在 10.040s 硬切进来。10.040-11.200 这 1.16 秒素材还贴着，挡住了镜2人物刚出来的脸。

**解决：** 素材结束时间必须 ≤ 下一镜硬切时间。`enable='between(t,9.500,10.040)'`——在镜2硬切前素材消失，让人物先露脸。不要只看素材开始时间对不对，还要看结束时间是否跨到了下一镜。

## 6. 复刻视频逐版迭代纪律

| 版本 | 修了什么 | 教训 |
|---|---|---|
| V6 | 尾卡砍掉、贴片下移、字幕对齐 | 基础版，4个用户反馈问题全修 |
| V7 | 双列/竖屏 stream_loop -1、BGM 6.0 | stream_loop 0 导致视频素材变截图 |
| V8 | 双列/竖屏时码对齐口播、BGM 8.0 | 素材时码必须跟口播同步不能照搬旧版 |
| V9 | BGM 20.0 | BGM源-45dB太安静，3-8倍不够 |
| V10 | 金币页y下移不挡脸、双列缩小不跟字幕重叠 | overlay坐标要vision验证 |
| V11 | BGM volume=50+limiter、尾部加logo+箭头 | 劣质BGM源放大50倍=噪音；尾部CTA跟口播"左下角"同步 |
| V12 | 金币页缩短到10.040不挡镜2脸 | 素材结束时间不能跨到下一镜硬切后 |
| V13 | 去掉BGM、去掉剧库筛选只留双列动态 | 劣质BGM不如不要；两个素材enable重叠要去掉多余的 |
| V14 | BGM从V19提取（失败） | 不同文案版本音频相减=提取出人声不是BGM |
| V15 | 用广州BGM库mixkit_834 | 广州机/home/ubuntu/assets/bgm/有29首免版权BGM |

**纪律：**
1. 每版只改用户反馈的具体问题，不额外动其他参数
2. 改完抽帧 vision_analyze 验证（不看图改不对）
3. BGM/音频用 volumedetect 量化验证，不靠感觉
4. 素材时码从 ASS 字幕时码反推，不从旧版照搬
5. overlay 坐标改完必须 vision 抽帧确认不挡脸、不重叠
6. 素材 enable 结束时间不能跨到下一镜硬切后（挡下一镜人脸）
7. 两个素材 enable 窗口不能重叠（改时码时检查相邻素材）
8. BGM 源文件质量差时换 BGM 库的，不要放大噪音
9. BGM 提取禁止用不同文案版本相减
