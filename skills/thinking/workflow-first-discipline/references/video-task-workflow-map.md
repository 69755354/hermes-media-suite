# 视频任务工作流地图 + 已确认技术（2026-08-15 实测）

## 一、视频任务挂哪个节点（对照 huoshan 18 节点 + 框架文档）

| 任务 | 归属节点 | 框架/规则文档 | 出口闸 |
|:--|:--|:--|:--|
| 拆解视频/爆款拆解 | huoshan **节点2** | `newmedia-operations/huoshan/references/video-deconstruction-framework.md`（第八章=AI视频逆向提示词分析：六维+音频+置信度+复现风险，2026-08-15并入） | 依赖文档校验（拆解强制读 framework） |
| 提示词生产 | 节点10 | seedance-four-layer-prompt skill | ticket close |
| Seedance 生成 | 节点12 | seedance-2-0-mini-workflow skill | api-guard + security-middleware |
| ffmpeg 合成 | **节点13** | huoshan SKILL.md 节点13：统一BGM(0.15-0.20)、环境音叠轨(0.20-0.25)、loudnorm(I=-14)、字幕ASS必用Noto Sans CJK SC | ticket close（产物 local_file） |
| 视频质检 | **节点14** | huoshan 节点14：720p 9:16、h264+aac、音频≥128k、无≥0.5s黑帧、≤50MB | G_TECHNICAL_QC_PASS |
| 交付 | **节点15** | 交付铁律：优先原生发送 → 外部URL纯文本链接 → 禁内部路径/禁MEDIA(微信场景) | G_DELIVERY_READY + feishu_send_gate |

## 二、2026-08-15 实测确认的技术

### 1. 抖音视频下载（Playwright + 手机UA，不需要 cookie）
之前 skill 记录「下载需要登录 cookie」是错的——**遮罩挡的是显示，video 元素在 DOM 里照样加载**：
```
① Playwright + iPhone UA 打开 https://www.douyin.com/video/<video_id>
   (v.douyin.com 短链会 302 跳转，先 curl -L 拿 video_id)
② 页面加载后 document.querySelector('video').src → 播放直链
   (m.douyin.com/aweme/v1/playwm/?video_id=...&ratio=720p&line=0)
③ 用同一手机 UA + Referer: https://www.douyin.com/  curl 直链 → HTTP 200 直接下
```
关键：手机 UA 必须；分享链接自带 did/iid/share_sign 参数=「真实用户分享」凭证，与「谁看过」无关；匿名会话可拿。

### 2. Seedance 2.0 Mini API（火山 ARK 通道）
- 提交：`POST /api/v3/contents/generations/tasks` → 返回 `{"id":"cgt-..."}`
- 轮询：`GET /api/v3/contents/generations/tasks/<id>` **GET 不带 body**（传空 JSON body 会 400）
- 参数：`duration` 支持 4-15 整数；`resolution":"720p"`、`ratio":"9:16"`
- 下载：新加坡机直连 TOS 超时 → 走广州 relay 透传 `http://127.0.0.1:8899/upload?url=<URL编码>`
- 纯文本驱动（无参考图）生成：单动作镜头（举杯微笑）命中率高；复合动作（行走+回头+笑）做不好——2.0 Mini 能力边界，逆向复刻要写进「复现风险清单」

### 3. COS 上传选桶（新加坡机）
- **只有 sc 桶开了全球加速**（zz/cp 没开）——传大文件必须 `COS_ACCELERATE=1` + sc 桶，否则直连超时
- 先跑 `python3 ~/.hermes/scripts/check_cos_accelerate.py` 确认哪个桶加速 Enabled
- 加速域名：`<bucket>.cos.accelerate.myqcloud.com`（cos_manager.py 读 `COS_ACCELERATE=1` 自动切）

### 4. 飞书交付（用户 2026-08-15 明确纠正）
「飞书你可以直接发，不需要绕来绕去」——**飞书对话可直接 MEDIA: 发视频**（`MEDIA:/tmp/xxx.mp4`），不要绕 COS 上传发链接。COS 链接是微信场景或无法原生发送时的备选。

## 三、逆向拆解 → 生成验证 完整链路（已跑通）

```
下载视频(§二.1) → 抽帧(fps=1/2 粗抽或 ffprobe 查帧率全帧) → vision 逐帧分析
→ 按 video-deconstruction-framework.md 第八章六维反推提示词(带置信度)
→ Seedance 生成(§二.2) → 节点13合成(统一BGM+环境音) → 节点14质检 → 飞书 MEDIA 交付(§二.4)
```
