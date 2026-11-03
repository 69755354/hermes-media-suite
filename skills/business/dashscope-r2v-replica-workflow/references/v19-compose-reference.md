# V19 ffmpeg合成参考（火龙V20成片版）

> 来源：`work/compose_v19_fix.sh`，2026-08-24定案。
> 后续复刻的ffmpeg合成必须严格照此脚本的素材绑定+crop+scale+overlay链。
> 闪屏页/logo已通过@图3直接生成在片里，不在此贴。

## 素材绑定表

| 序号 | 变量名 | 素材文件 | 处理 |
|:---|:---|:---|:---|
| 1 | cash_page | 复刻素材_v2/静态/原片_11s.png | crop=360:770:180:150,scale=360:770 |
| 2 | long_page | 复刻素材_v2/静态/原片_15s.png | crop=365:810:177:120,scale=380:840 |
| 3 | reward_3888 | 复刻素材_v2/静态/原片_19s.png | crop=375:810:178:115,scale=390:840 |
| 4 | app_small | 火龙漫剧_logo_用户提供.jpg | scale=150:150（尾部小Logo） |
| 5 | signin_popup | 签到弹窗_7天必得_用户提供.jpg | scale=390:780 |
| 6 | add_home | 弹窗_添加到主屏幕_干净.png | scale=330:390 |
| 7 | episode_page | 界面_秒杀大帝弹窗_干净.png | scale=500:820 |
| 8 | filter_page | 界面_剧库筛选_干净.png | scale=500:890 |
| 9 | arrow_g4 | 箭头CTA_红色_透明.png | scale=130:161 |
| 10 | play_g1 | 播放页_千劫问道_用户提供.jpg | scale=500:820 |
| 11 | double_page | dynamic/双列动态_用户提供.mp4 | scale=370:820 |
| 12 | vertical_page | dynamic/竖屏页动态_孙悟空_clean.mp4 | scale=370:660 |
| 13 | coins | dynamic/金币动态.mp4 | scale=360:280 |

## 贴片时码表（去掉闪屏页和镜1 App小Logo，已通过@图3生成）

| 素材标签 | 入场(s) | 出场(s) | x | y | 说明 |
|:---|:---|:---|:---|:---|:---|
| play_g1 | 6.900 | 8.040 | 110 | 120 | 播放页截图 |
| cash_page | 9.320 | 11.120 | 180 | 150 | 金币页 |
| long_page | 12.500 | 14.360 | 170 | 145 | 剧库长页 |
| add_home | 15.240 | 16.560 | 195 | 405 | 添加桌面弹窗 |
| signin_popup | 16.560 | 18.080 | 165 | 210 | 签到弹窗 |
| reward_3888 | 18.080 | 20.040 | 165 | 145 | 福利页 |
| episode_page | 23.200 | 24.800 | 110 | 120 | 选集页(秒杀大帝) |
| filter_page | 24.800 | 27.200 | 110 | 100 | 分类页(剧库筛选) |
| double_page | 28.920 | 30.720 | 175 | 105 | 双列流(动态视频) |
| vertical_page | 33.360 | 36.860 | 175 | 95 | 竖屏播放(动态视频) |
| ~~app_small~~ | ~~39.200~~ | ~~43.800~~ | ~~40~~ | ~~920~~ | ~~尾部App小Logo（尾卡砍掉后不用）~~ |
| ~~arrow_g4~~ | ~~39.200~~ | ~~43.800~~ | ~~40~~ | ~~735~~ | ~~CTA箭头（尾卡砍掉后不用）~~ |
| ~~coins~~ | ~~43.040~~ | ~~43.800~~ | ~~240~~ | ~~660~~ | ~~金币动态（尾卡砍掉后不用）~~ |

> 0826用户定案"尾卡切掉"：39s后的贴片项不再使用，句26-28并入镜3b，成片约40s。

## BGM

- 文件：`audio/环境音与轻BGM_43s.wav`
- 混音链：BGM先 `volume=2.0` 翻倍 → 再 `amix=inputs=2:duration=first:dropout_transition=0:normalize=0` → 再 `sidechaincompress=threshold=0.45:ratio=8:attack=5:release=200:level_sc=1`
- 人声轨=基底片自带音频，BGM轨=独立wav

### ⚠️ BGM 听不到问题（0826 v5 修复实测）

**症状**：用户反馈"BGM声音太小，完全听不到"。

**根因**：原始 v3 合成只有 `amix` + `sidechaincompress` ducking，没有给 BGM 加 `volume`。`sidechaincompress` 在人声出现时把 BGM 压到几乎无声（ratio=8:1），人声间隙的 BGM 又因为 amix normalize=0 没有补偿，整体 BGM 几乎不可闻。

**修复**：在 amix 之前给 BGM 轨加 `volume=2.0`（或更高），让 BGM 基础音量翻倍，ducking 后仍能听到。

```ffmpeg filter_complex 片段：
[11:a]volume=2.0[bgm_boost];
[0:a][bgm_boost]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,
sidechaincompress=threshold=0.45:ratio=8:attack=5:release=200:level_sc=1[voice_bgm]
```

**验证**：合成后用 `ffmpeg -af volumedetect` 检查成片 mean_volume，如果低于 -20dB 说明 BGM 太弱。

## 字幕

- 文件：`字幕_简体核验_v17.ass`
- ASS格式，WenQuanYi Zen Hei 56px主字幕，18px风险提示
- 风险提示底层全程：`广告内容以产品实际规则为准；收益与提现条件请以官方页面为准；本片为复刻样片，投稿前需审核`

## ffmpeg编码参数

```
-c:v libx264 -preset medium -crf 19 -profile:v high -level 4.0
-pix_fmt yuv420p -r 30 -g 60
-c:a aac -b:a 160k -ar 48000 -ac 2
-movflags +faststart
```

## 注意事项

- **不能整图贴**：必须按crop参数从原片截图裁出手机屏区域。整图贴导致素材错位、挡脸
- **不能漏BGM**：模板写了BGM后期混音ducking人声，合成时必须加
- **不能漏字幕**：ASS字幕+风险提示底层必须加
- **split=2会报错**：如果同一个素材文件需要生成两个不同scale的输出，不用split，用两个独立-input（同一文件input两次）
- **广州Caddy目录**：`/home/ubuntu/public/`，URL是`http://<GZ_HOST>/文件名.png`
