# 火龙通用口播模板后期合成执行全流程

> 来源：2026-08-27 实测执行，从5段快乐马底片到40s成片的完整ffmpeg后期管线
> 前置：底片已生成（HH-1~HH-5）、App录屏4段已归档、Logo白底PNG、BGM已选曲
> SKILL.md「后期合成四铁律」管辖时码/贴片/BGM纪律，本文件管ffmpeg具体执行技术
> ⚠️ 0827用户纠正：技术验收全通过但内容结构偏移严重——见第十节"内容验收教训"

## 一、环境预检

```bash
# ffmpeg必须有这些滤镜
ffmpeg -filters 2>&1 | grep -E "overlay|alphamerge|sidechaincompress|subtitles|loudnorm|alimiter|geq"
# 字体
fc-match "WenQuanYi Zen Hei"  # → /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc
```

本机（新加坡）ffmpeg 6.1.1 已含全部所需滤镜，WenQuanYi Zen Hei 字体已安装。

## 二、五段底片拼接 + 静帧补足到40s

### 时间轴

实际5段时长≠设计时长（HH-1=9.16s vs设计7s，HH-5=5.16s vs设计9s），总长38.76s，缺口1.24s用App选集页静帧补足。

```
0.00-9.16   HH-1 全屏人物
9.16-16.32  HH-2 全屏人物
16.32-24.44 HH-3 App选集页+画中画
24.44-33.60 HH-4 App分类/榜单/播放+画中画前2.5s
33.60-38.76 HH-5 回全屏人物+CTA
38.76-40.00 App静帧补足
```

### 坑：concat需要所有段都有音频流

静帧PNG段没有音频流 → concat报 `Cannot find a matching stream for unlabeled input pad concat`。

**正解**：给静帧段加 `anullsrc` 静音音频：
```bash
anullsrc=channel_layout=stereo:sample_rate=48000:duration=1.24[a5];
# concat时 [v0][a0][v1][a1]...[v5][a5]concat=n=6:v=1:a=1
```

### 完整拼接命令

```bash
ffmpeg -y \
  -i hh_01.mp4 -i hh_02.mp4 -i hh_03.mp4 -i hh_04.mp4 -i hh_05.mp4 \
  -loop 1 -framerate 30 -t 1.24 -i ui_select_hold.png \
  -filter_complex "
    [0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p,trim=duration=9.16,setpts=PTS-STARTPTS[v0];
    # ...每段同理，trim到实际时长
    [5:v]scale=1080:1920:...,trim=duration=1.24,setpts=PTS-STARTPTS[v5];
    [0:a]atrim=duration=9.16,asetpts=PTS-STARTPTS,aresample=48000:first_pts=0[a0];
    # ...每段同理
    anullsrc=channel_layout=stereo:sample_rate=48000:duration=1.24[a5];
    [v0][a0][v1][a1][v2][a2][v3][a3][v4][a4][v5][a5]concat=n=6:v=1:a=1[v][a]
  " \
  -map "[v]" -map "[a]" -t 40 \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -movflags +faststart work/hh_base_40s.mp4
```

## 三、App录屏→UI覆盖层

从4段真实App录屏抽帧/剪片段，拼成17.28s覆盖层（对应全局16.32-33.60s）。

```bash
# 静帧抽取
ffmpeg -y -i app_select_full.mp4 -ss 0.5 -frames:v 1 ui_select_before.png
# 动态片段
ffmpeg -y -i app_select_full.mp4 -ss 1.0 -t 2.0 -an -c:v libx264 -pix_fmt yuv420p ui_select_click.mp4
```

7段拼接（3静帧+3动态+1尾静帧），各段scale到1080:1920统一：
```
选集停留3.0 → 点击2.0 → 选集停留3.0 → 分类停留2.5 → 榜单滚动2.0 → 播放切换4.0 → 结果停留0.78 = 17.28s
```

**坑**：静帧loop输入的duration要用trim控制，不然concat总时长不对。

## 四、圆形画中画（alphamerge + geq）

14.0-24.5s右上角圆形画中画，从底片截取对应时段。

```bash
[pip_src]trim=start=16.32:end=26.94,setpts=PTS-STARTPTS,
  scale=320:568,crop=320:320:0:200,format=rgba[pip_rgb];
# 生成圆形mask：黑底白圆
color=c=black:s=320x320:r=30:d=10.62,format=gray,
  geq=lum='if(lte((X-W/2)*(X-W/2)+(Y-H/2)*(Y-H/2),(W/2-4)*(W/2-4)),255,0)'[pip_mask];
# 合并→加偏移→overlay
[pip_rgb][pip_mask]alphamerge,setpts=PTS+16.32/TB[pip];
[v_ui][pip]overlay=x=720:y=80:enable='between(t,16.32,26.94)'[v_pip];
```

参数：
- PIP_X=720（1080-320-40边距）
- PIP_Y=80
- PIP_CROP_Y=200（人物脸部位置，中近景胸口以上）
- 直径320px

## 五、Logo白底去背（BFS flood fill）

### 坑：ffmpeg chromakey会误删Logo内部白色

火龙漫剧Logo是1254×1254白底RGB PNG。Logo主体含白色区域（如小龙脸部是纯白填充）。

`chromakey=color=white` 会删掉**所有**白色像素 → Logo透明度100%，全没了。

### 正解：Python PIL + BFS从四角flood fill

只去掉与四角连通的外围白色背景，保留Logo内部的白色区域：

```python
from PIL import Image
import numpy as np
from collections import deque

img = Image.open('logo.png').convert('RGBA')
arr = np.array(img)
h, w = arr.shape[:2]
r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
white = (r > 200) & (g > 200) & (b > 200)

# BFS从四角开始，只标记连通的背景白色
visited = np.zeros((h, w), dtype=bool)
bg = np.zeros((h, w), dtype=bool)
queue = deque()
for y, x in [(0,0), (0,w-1), (h-1,0), (h-1,w-1)]:
    if white[y, x] and not visited[y, x]:
        queue.append((y, x))
        visited[y, x] = True
        bg[y, x] = True

while queue:
    cy, cx = queue.popleft()
    for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
        ny, nx = cy+dy, cx+dx
        if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and white[ny, nx]:
            visited[ny, nx] = True
            bg[ny, nx] = True
            queue.append((ny, nx))

arr[:,:,3] = np.where(bg, 0, 255)
Image.fromarray(arr).save('logo_transparent.png')
```

实测：透明像素85.7%，不透明14.3%，Logo主体完整保留。

## 六、三层ASS字幕

三个独立ASS文件分层渲染，同屏不冲突：

| 文件 | 内容 | 样式 | 位置 |
|:---|:---|:---|:---|
| `captions.ass` | 全口播普通字幕 | 白字黑描边，54px，MarginV=240 | 底部居中 |
| `keywords.ass` | 关键词大字 | 黄字(`&H0000F8FF`)黑描边，88px，Alignment=8 | 上中部 |
| `risk.ass` | 风险提示全程固定 | 灰字(`&H00D0D0D0`)，28px，MarginV=50 | 最底部 |

### 时间码计算

先对每段底片做Whisper ASR（`word_timestamps=True`），拿到词级时间戳后加段偏移量算全局时间码。

```python
# 段偏移量
offsets = {'HH-1': 0, 'HH-2': 9.16, 'HH-3': 16.32, 'HH-4': 24.44, 'HH-5': 33.60}
# 关键词触发点 = 段内ASR时间 + 段偏移
```

### ffmpeg渲染多层ASS

```bash
[v_logo]subtitles=post/derived/keywords.ass:fontsdir=/usr/share/fonts/truetype/wqy[v_kw];
[v_kw]subtitles=post/derived/captions.ass:fontsdir=/usr/share/fonts/truetype/wqy[v_sub];
[v_sub]subtitles=post/derived/risk.ass:fontsdir=/usr/share/fonts/truetype/wqy[vout];
```

## 七、BGM侧链混音

```bash
[0:a]atrim=0:40,asetpts=PTS-STARTPTS,aresample=48000[voice0];
[voice0]asplit=2[voice_mix][voice_sc];
[3:a]atrim=0:40,asetpts=PTS-STARTPTS,volume=0.16,
  afade=t=in:st=0:d=2,afade=t=out:st=38:d=2[bgm0];
[bgm0][voice_sc]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=250[bgm_duck];
[voice_mix][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0,
  alimiter=limit=0.89[aout]
```

- BGM volume=0.16 + 2s淡入/38s淡出
- sidechaincompress：人声出现时自动压低BGM
- alimiter限幅防爆音

**注意**：与网赚版 `volume=3.0` 不同。通用口播模板用0.16是因为BGM选的是codex_Carefree（24.9s轻快钢琴曲），音量本身较大，0.16已足够。网赚版用3.0是因为BGM选曲不同+被ducking压太狠。**BGM音量需根据选曲实测调整，不照搬**。

## 八、最终合成命令

```bash
ffmpeg -y \
  -i work/hh_base_40s.mp4 \           # 底片
  -i work/ui_16_33.mp4 \              # UI覆盖层
  -loop 1 -framerate 30 -i logo_transparent.png \  # 透明Logo
  -stream_loop -1 -i bgm_cos_source.mp3 \          # BGM
  -filter_complex "
    [0:v]split=2[base][pip_src];
    [1:v]format=yuva420p,fade=t=out:st=17.06:d=0.2:alpha=1,setpts=PTS-STARTPTS+16.32/TB[ui];
    [base][ui]overlay=x=0:y=0:enable='between(t,16.32,33.60)'[v_ui];
    # ...画中画(第四节)
    # ...Logo overlay enable='between(t,10.06,12.50)+between(t,36.58,40)'
    # ...三层ASS(第六节)
    # ...BGM混音(第七节)
  " \
  -map "[vout]" -map "[aout]" -t 40 \
  -c:v libx264 -preset medium -crf 18 -profile:v high -level 4.1 \
  -pix_fmt yuv420p -r 30 -g 60 -keyint_min 60 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -movflags +faststart \
  output/huolong_oral_master_1080x1920_40s.mp4
```

## 九、技术验收（全通过）

```bash
ffprobe -v quiet -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,pix_fmt,sample_rate,channels -of json output.mp4
# 放行：40.00s±0.05, 1080×1920, H.264, yuv420p, 30fps, AAC, 48kHz, 双声道

# 黑帧检测
ffmpeg -v warning -i output.mp4 -vf "blackdetect=d=0.3:pix_th=0.10" -an -f null -
# 放行：无0.3s以上非设计黑帧
```

抽帧16个时间点用vision_analyze核对：人物/字幕/Logo/画中画/UI覆盖各时段正常。

## 十、ASR预检与拼接时长适配（0827原片台词版实测）

### ⚠️ ASR验证台词时间分布是拼接前必做步骤

合成方案预设7/7/8/9/9=40s截断，但原片台词版5段每段10.12s，ASR显示台词占满整个10s（末句结束在9.9-10.1s）。直接按7/7/8/9/9截断=砍台词。

**正确流程**：
1. 拼接前先对每段做 `faster-whisper word_timestamps=True` ASR
2. 检查每段末句结束时间 vs 设计trim点：如果 `speech_end > trim_point` 则台词会被截断
3. 台词占满时改用全量拼接（5×10.12=50.6s），不强行截断到40s
4. ASS字幕时码按实际段时长计算offset（0/10.12/20.24/30.36/40.48），不照搬设计方案的7/14/22/31

### loudnorm拼接极慢的解法

5段×loudnorm两遍分析 + `preset=medium` + `crf=18` → 120s超时文件没写完（moov atom not found）。

**解法**：分两步
- 步骤1（底片拼接）：`preset=fast -crf=20`，不加loudnorm（只aresample统一采样率），后台跑~3分钟
- 步骤2（最终合成）：`preset=slow -crf=18`，加字幕+BGM+Logo，后台跑~3-4分钟
- 两步合计~7分钟，比一步合成（14分钟+爆码率）快一倍

### ASS字幕从ASR自动生成（含全局时间码偏移）

```python
from faster_whisper import WhisperModel
m = WhisperModel('small', device='cpu', compute_type='int8')
offsets = [0, 10.12, 20.24, 30.36, 40.48]  # 各段全局偏移
for i in range(1, 6):
    segs, _ = m.transcribe(f'/tmp/hh_asr_{i}.wav', language='zh', beam_size=3)
    off = offsets[i-1]
    for s in segs:
        start = off + s.start  # 全局时间码
        end = off + s.end
        # 写入ASS Dialogue行
```

关键：offset用各段**实际时长**累加，不用设计时长（7/7/8/9/9）。Whisper输出繁体字可接受——字幕可读性不影响，如需简体可加 `initial_prompt` 参数。

### 最终合成命令（50s版，简化模板）

```bash
ffmpeg -y \
  -i work/hh_base_50s.mp4 \
  -loop 1 -framerate 30 -i logo_transparent.png \
  -stream_loop -1 -i bgm_cos_source.mp3 \
  -filter_complex "
    [1:v]scale=220:-1,format=rgba[logo];
    [0:v][logo]overlay=x=430:y=1750:enable='between(t,17,50.6)'[v_logo];
    [v_logo]subtitles=keywords.ass:fontsdir=/usr/share/fonts/truetype/wqy[v_kw];
    [v_kw]subtitles=captions.ass:fontsdir=/usr/share/fonts/truetype/wqy[v_sub];
    [v_sub]subtitles=risk.ass:fontsdir=/usr/share/fonts/truetype/wqy[vout];
    [0:a]aresample=48000[voice0];
    [voice0]asplit=2[voice_mix][voice_sc];
    [2:a]volume=0.12,afade=t=in:st=0:d=2,afade=t=out:st=48.6:d=2[bgm0];
    [bgm0][voice_sc]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=250[bgm_duck];
    [voice_mix][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.89[aout]
  " \
  -map "[vout]" -map "[aout]" -t 50.6 \
  -c:v libx264 -preset slow -crf 18 -profile:v high -level 4.1 \
  -pix_fmt yuv420p -r 30 -g 60 -keyint_min 60 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -movflags +faststart \
  output/huolong_original_master_50s.mp4
```

注意：此版不含App录屏覆盖和画中画（底片确认后再加）。BGM volume=0.12（选曲不同需实测调整）。

## 十一、内容验收教训（0827用户"一大堆问题"）

### ⚠️ 技术验收≠内容验收

技术验收全通过（40.00s/1080×1920/无黑帧/抽帧正常），但用户对比原片后指出"一大堆问题"——只验了技术指标没验内容结构。

### 问题清单

| # | 问题 | 原片 | 我的成片 | 根因 |
|:---:|:---|:---|:---|:---|
| A | 缺剧情片段画面 | 9.8-15.2s切剧情片段 | HH-2还是全屏数字人 | 没有剧情素材，也没打算用 |
| B | App录屏顺序不同 | 筛选页→热播榜→播放页 | 选集页→分类页→热播榜→播放页 | 没实看原片，凭报告描述猜 |
| C | UI时间轴偏移 | 热播榜24.0s入 | 热播榜27s才入 | UI层拼接时长分配不对 |
| D | 人物回切太晚 | 31.9s回数字人 | 33.6s才回 | 底片时长分配没对齐原片切点 |
| E | App录屏有金币UI | 左上角金币720/880 | 直接用录屏没处理 | 没做UI清洁 |
| F | 大字内容不同 | 打断八次/非常的丰富/还有新剧上架 | 关键处/广告打断/第1集→第62集 | 台词是改过的合规版，大字跟着台词走（不算bug） |

### 根因

**只读拆解报告文字描述就动手合成，没有实际下载和逐帧观看原片。** 拆解报告3秒抽帧有1-3秒误差，且无法传达动态画面实际观感。

**更深层的根因（0827用户纠正「这个是你分析的？」）**：Hermes 拿拆解报告文字描述逐条推理"原片 vs 成片差异"，被用户点破这不是分析是文字对照。**SOUL.md 铁律11 适用此场景**：对比分析、问题清单、结构差异判定是智力活，必须打包丢执行器干，禁止 Hermes 直出。Hermes 只负责机械操作：下载原片、抽帧、vision_analyze 对比、收集结果转白话回传。

### 铁律

1. **合成前必须下载原片MP4逐帧/逐秒观看**——抖音需cookie/第三方接口，iesdouyin分享页SSR不返回视频数据
2. **对原片和成片各抽同一时间点帧用vision_analyze逐张对比**——vision_analyze提问不能太笼统（"画面是否正常"），要问"与原片第X秒对比有什么不同"
3. **对齐清单**：画面切换时间点(±0.5s)、App页面顺序、画中画入出时间、大字内容和时间、人物回切时间、画面类型完整性（是否缺原片有的画面类型）
4. **不允许只读报告就合成**——报告是理解用不是合成用
5. **合成方案时间轴按原片实际画面切点对齐**——不照搬底片段间硬切点，原片画面切点（如9.8s切剧情、16.5s切App、31.9s回人物）是合成时间轴的设计依据
6. **对比原片和列问题清单是智力活必须外包**（0827用户纠正）——Hermes 不自己推理结构差异，打包丢执行器干。如果原片下载不了，如实说"没拿到原片"不要拿报告文字推理替代实看
7. **原片抽帧也要核实来源**（0827实测）——`huolong-guide/复刻素材_v2/静态/原片_*.png` 实际是网赚版原片的抽帧，不是通用口播版原片的。不能拿来当通用口播原片对比基准
8. **vision_analyze 对比提问模板**——❌笼统「画面是否正常」「看看有什么问题」 ✅具体「这是我做的成片第X秒。原片在这个时间应该是什么画面？对比看看：1.画中画位置和大小 2.大字内容和位置 3.App录屏是不是对应页面 4.有没有不该出现的元素」
