---
name: video-production
title: 视频成片组装/字幕/终检/交付（跨三通道的后期合成纪律）
description: 触发：视频成片合成、字幕烧录、字幕贴底、终检交付、探店素材规划。
author: hermes-curator
license: internal
version: 1.0.0
metadata:
  tags: [video, subtitle, ffmpeg, delivery, 探店, 字幕]
  related_skills: [huoshan, video-production, workflow-execution-guard]
---

# 视频成片组装与交付

## When to Use

触发：视频成片合成、字幕烧录/位置调整、成片终检、交付；探店类视频的素材规划与服务过程镜设计。凡是「AI 视频生成完要变成可发布成片」的环节都先看本 skill。

三通道（探店/剧情/口播）共用的后期合成纪律。承接 huoshan 节点13-15（合成/检验/交付）与 video-production（后期救急），本 skill 收录**跨项目可复用的组装坑与验证纪律**。

> 注意：huoshan / video-production / workflow-execution-guard 是用户自有 skill，如本文件与它们冲突，以用户 skill 为准。建议 `hermes curator adopt huoshan video-production workflow-execution-guard` 以便统一维护。

## 1. 字幕烧录：ASS 的坑 vs drawtext 正解（2026-08-10 茗希血泪教训）

**用户要求「字幕放最下面」时——用 drawtext 滤镜 y=h-100 精确贴底，别死磕 ASS。**

踩坑链（茗希探店 30s 成片实测）：
1. **ASS MarginV 控制不精确**：Alignment=5（底部居中）时 MarginV 从 320 改到 480，字幕位置只从 45%→55%（远没到底）。MarginV 不是按 PlayResY 线性推到底——死磕参数浪费时间
2. **sed 改 ASS 会静默坏文件**：`sed -i 's/.../.../g' subtitles.ass` 处理含 `\N` 换行转义/格式行后，libass 可能解析失败但 **ffmpeg 不报错**——成片烧出来没字幕，抽帧才知道。改 ASS 必须**重写整个文件**，不 sed 局部替换
3. **字幕被推出屏幕**：MarginV 设太大（420+）时双行字幕会被推到画面外——不是「贴底」是「出屏」

**正解：drawtext 滤镜：**
```bash
ffmpeg -y -i concat.mp4 \
 -vf "drawtext=fontfile=/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc:text='字幕内容':fontsize=36:fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-100:enable='between(t,5,10)',\
drawtext=...第二条..." \
 -c:a copy out.mp4
```
- `y=h-100` = 距底部 100px（实测落 90-95% 高度，贴底且不出屏）
- 每条字幕一个 drawtext + `enable='between(t,开始,结束)'`
- 重点字（价格/店名/地址）用 `fontcolor=0xE87FB8`（浅粉）区分
- 单行完整显示（字号 36，一行 ≤18 字不出屏），别用 ASS `\N` 拆两行
- 字体：本机无 Noto CJK 时用 `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`（文泉驿正黑）

## 2. 字幕验证必须抽帧 + vision_analyze（不猜）

```bash
ffmpeg -y -ss <字幕时段> -t 1 -i out.mp4 -vf "fps=1,scale=540:960" /tmp/sub_check.png
```
→ vision_analyze 问「字幕在画面高度百分之多少（0%顶/100%底）、完整吗、什么颜色」→ 确认贴底且完整。
**不验证 = 可能交付一个没字幕的片子**（v5-v8 全踩过）。抽帧时机要取时段中间（如 5-10s 字幕取 8.5s），别抽在画面切换帧。

## 3. 探店素材与服务过程镜铁律（2026-08-10 用户两次纠正）

1. **服务过程镜必须存在**：探店视频要有「服务过程」镜（理疗师/技师手部在操作）——观众要看店是干嘛的。只拍「人坐着放松」= 空洞废镜（用户原话「你没有服务过程谁知道你干嘛的」）
2. **服务过程镜必须垫实景图**（客户真实门店环境，到店能对上），不能垫角色参考图生成 AI 想象背景——探店真实性崩溃。正确做法：双参考图（高端实景图 + 角色锁脸图）
3. **合规控制**：只拍保健按摩动作（揉/按/推），不拍针/艾灸/仪器等医疗器材；技师只露手部不露脸（AI 手部简单动作不易崩）
4. **实景图 AI 高端化**：客户实拍图「生活化」直接垫图显廉价——图生图升级光影/质感/氛围，但**保留场景结构 100% 不变**（客户到店要对上）
5. **客户给几张实景就做几张**（茗希给了 3 张：理疗室/服务区/美容室，漏做第 3 张被用户抓）
6. **素材规划先于生图**：写文案后先盘点素材分配（哪镜实景/哪镜 AI 出镜），确认无缺口再进生图——避免生到一半发现缺镜重出

## 4. STATE.json 补签（物理卡点正常工作信号）

codex 执行 AGENTS.md 会查 STATE.json——节点未标 DONE 时直接 BLOCKED 不干活（这是物理卡点生效，别当 bug 修）。补签：
```bash
python3 /home/ubuntu/.hermes/scripts/update_state.py write <项目目录> <NODE_ID> PASS
```
用法：`write <项目目录> <NODE_ID> <PASS|FAIL> | status <项目目录> | check <项目目录> <NODE_ID>`
节点实际做完才补签（先有产物，再标 DONE）。

## 5. 成片终检清单（交付前必做）

- ffprobe：时长 30s±1s、720x1280（9:16）、h264+aac、≤50MB
- 抽帧 vision_analyze：字幕贴底且完整、无黑帧花屏、人物一致性
- 交付：MEDIA 原生发视频（微信/飞书），不发内部路径
- 文档交付一律 Word(.docx) 不发 md（用户定案 0809，小说/文学正文也走 Word）

## 6. BGM 合成（2026-08-10 茗希：无版权音乐库时的 ffmpeg 方案）

分镜要求「木吉他 BGM 低音量铺底」但没有现成免版权音乐时，用 ffmpeg/python 合成：
```bash
# 方案A：C 大调和弦琶音（python 生成 wav，衰减包络模拟拨弦）
# 和弦进行 C-G-Am-F，每和弦1秒4个8分音符，指数衰减 env=exp(-i/(0.12*sr)) + 0.15泛音
# 归一化后 gain=0.25，淡入1.5s/淡出1.5s
# 方案B：ffmpeg sine 四音混合（更简陋，优先方案A）
```
混音（BGM 不压人声）：
```bash
ffmpeg -y -i 成片.mp4 -i bgm.wav \
  -filter_complex "[1:a]volume=0.35,afade=t=in:st=0:d=2,afade=t=out:st=28:d=2[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]" \
  -map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k out.mp4
```
- BGM 音量 0.35（低铺底），2s 淡入/2s 淡出
- 注意：纯正弦和弦 = 合成音色（电子感），比真吉他录音差一截；客户要真实音乐需从免版权库下载（成本更高）

## 7. Seedance 出片下载走 relay（2026-08-10 茗希 6/6 全失败修复）

**症状**：Seedance 任务提交成功（task_id 正常），但 `download_file` 用 urllib 直连 TOS URL 全部 0B 失败——新加坡机直连火山 TOS 不通（网络隔离）。

**修复**：download_file 里对 volces.com/tos-cn URL 改走广州 relay GET：
```python
if "volces.com" in url or "tos-cn" in url:
    url = "http://127.0.0.1:8899/upload?url=" + urllib.parse.quote(url, safe="")
```
- 修完重跑出片 6/6 成功（每镜 4.8-6.8MB）
- 规律：新加坡机所有火山系访问（ARK API/视频 TOS 下载）都要经广州 relay，直连不通
