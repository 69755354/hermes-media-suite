# 复刻出片：字幕对齐 + bfv 裁剪 + ASS 渲染踩坑（2026-08-18 火龙漫剧实测）

## 字幕必须跟 Seedance 原声对齐，不能照原片时间轴

AI 生成的镜（Seedance 原声）念台词节奏跟原片字幕时间轴**完全对不上**（实测偏差 0.5-1.7s），直接烧原时间轴字幕 = 用户说「字幕跟口播不匹配」。

**流程（每镜必做）：**
1. ASR 转录 AI 生成镜拿实际口播时间：
   ```python
   # faster_whisper 在 hermes-agent venv：/home/ubuntu/.hermes/hermes-agent/venv/bin/python
   from faster_whisper import WhisperModel
   model = WhisperModel("small", device="cpu", compute_type="int8", download_root="/tmp/whisper_model")
   segments, _ = model.transcribe("<镜视频>", language="zh", vad_filter=True)
   ```
2. 按 ASR 分段重写 ASS 时间轴（简体照画面，不照繁体 ASR）
3. AI 可能漏念台词（实测镜1 只念了 9/11 句）——没念的台词不要烧字幕

## bfv（原片手机屏裁出的播放页视频）裁剪坑——混入原片人物

从原片 32-35s 裁手机屏播放页视频时，**尾部会混入原片人物**（实测原 bfv 2.5s 后从孙悟空切到黑衬衫男，因为原片 34.8s 后播放页结束切人物镜头）。不逐帧检查尾部 = 成片播放页出现原片人物（用户当场点破「你把原视频的人都放进去了」）。

**铁律：裁完必须逐帧抽检尾部**（0.2s 间隔 vision 查最后 1s），确认全段纯界面；有混入就重裁更短（2.5s 内）。

## overlay 视频输入的 PTS 坑

overlay 视频素材如果 enable 开始时间 > 素材时长，素材早已播完会**冻结在最后一帧**（可能是错误内容）。
```bash
# ❌ 错：enable 9s 起，素材 3s 就播完了
[3:v]trim=duration=3,setpts=PTS-STARTPTS[bfv];
[v0][bfv]overlay=enable='between(t,9,13)'
# ✅ 对：setpts 延迟到 enable 起点才播，且 enable 窗口 ≤ 素材时长
[3:v]trim=duration=2.5,setpts=PTS+9/TB[bfv];
[v0][bfv]overlay=enable='between(t,9,11.5)'
```

## ASS 字幕不渲染的三个根因（全踩过）

1. **缺 `[Events]` 段头**：python 过滤生成 ASS 时把 `[Events]` 行丢了，Dialogue 直接跟在 Styles 后 → libass 完全忽略。生成后 grep 确认 `[Events]` 存在。
2. **字体不存在**：ASS 写 Noto Sans CJK SC 但系统没装 → 不渲染。查 `fc-list :lang=zh`，用系统有的 **WenQuanYi Zen Hei**（文泉驿正黑）。
3. 测试方法：`ffmpeg -f lavfi -i color=c=blue:s=720x1280:d=2 -vf "ass=xxx.ass" -frames:v 1 test.png` + vision 确认有字。

## ASS 颜色格式坑：&HAABBGGRR 顺序（2026-08-18 实测两次改错）

ASS 颜色是 `&HAABBGGRR`（Alpha-Blue-Green-Red），不是直觉的 RGB：
- 亮黄字 = `&H0000FFFF`（BB=00 GG=FF RR=FF）
- **蓝描边 = `&H00FF0000`（BB=FF GG=00 RR=00）** —— 写成 `&H0000FF00` 是绿色！本次就把蓝描边两次写成 `&H0000FF00` 渲染出绿色描边
- 紫色阴影 = `&H00800080`（BB=80 GG=00 RR=80）
改完用纯色背景单测抽帧 vision 验证描边颜色对不对，别只看代码。

## 原片字幕样式分时段，先确认用户要哪段（2026-08-18 用户选定）

原片不同时段字幕样式不同：5s 是「亮黄字+紫底蓝描边」（品牌词高亮），10s 是「白字+黑色半透明背景条」。**先抽多时段帧给用户选样式**，本次用户选「亮黄字+紫底蓝描边（像原片5s）」。实现：ASS Main 样式 `WenQuanYi Zen Hei,72,&H0000FFFF,&H0000FFFF,&H00FF0000,&H00800080,...,1,8,3,2,60,60,260,1`（Fontsize 72 加大、Outline=8 蓝描边、Shadow=3 紫阴影、MarginV=260 略上移避遮挡）。⚠️ 之前 SKILL.md 记的「黑底圆角框白字」是另一时段的样式——以用户当次选定为准。

## BGM 混音：先 volumedetect 验证源文件不是静音（2026-08-18 用户「把BGM加进去」）

原「环境音与轻BGM_43s.wav」全程 -44.5dB 几乎静音（mean_volume 检测），混入成片用户听不到 = 被当成「没加BGM」。**换 SoundHelix 真 BGM**（bgm-library.md：`curl -sL -o bgm_raw.mp3 https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3`）→ 截 40s + 淡出 `ffmpeg -i bgm_raw.mp3 -t 40 -af "afade=t=out:st=35:d=5" bgm_40s.m4a` → 合成 `volume=0.25` amix。**验证 BGM 真的混入**：抽成片一段 `-af volumedetect` 看 mean_volume 比纯人声段高（-22dB 左右说明有底），再发用户。

## 叠加界面不能挡人物脸（用户偏好）

用户明确要求「把脸露出来」：弹窗/剧库/播放页等悬浮叠加 UI 要放画面**左侧空白区**（人物通常在右侧/中央），先 vision 定位人物脸像素范围再定 overlay 坐标。原片即使挡脸（AI 生成的原片福利页/弹窗就挡人物），复刻版也要露脸。

## cv2.shape 维度

cv2.imread 返回 (h, w, c)——(1280, 720, 3) = 高1280宽720 = **竖屏 720x1280**，不是横屏！判断方向别被 shape 吓到，用 PIL size=(w, h) 对照。

## 镜2 多素材按台词切换（素材跟台词匹配）

原片镜2 福利中心段是**多个素材按时段切换**，不是一张图到底：
- 讲「添加桌面也有收益」→ 叠加「添加到主屏幕」弹窗（从原片 16.5s 抠，白底干净）
- 讲「刚注册的新人…新人福利」→ 显示「恭喜获得火龙币」奖励弹窗
- 抠弹窗用像素检测定位白块（>230 亮度连通域），从原片对应帧裁剪，vision 核验无人物/水印
