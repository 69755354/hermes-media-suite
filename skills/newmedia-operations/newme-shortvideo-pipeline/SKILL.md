---
name: "newme-shortvideo-pipeline"
description: "给 NewMe（迪拜智能家居）做短视频：从素材筛查、脚本、合片，到视频号/小红书/抖音三平台定时发布、数据回读与选题建议。涉及这三个平台发布自动化、剪映草稿、无口播 b-roll 选段时使用。"
---

# NewMe 短视频流水线

工作目录 `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft`（沙箱与本机桥的唯一互通目录是它下面的 `_pipeline`）。
本机只有 8 GB 内存 —— **同时只能开一个 Chrome**，重活排队。

## 一、铁规矩

- 素材是客户别墅实拍，**绝不上传任何第三方云**；ASR/TTS 只用本地。
- 每个平台一个专用 Chrome profile：`~/NewMe/profiles/{weixin,xiaohongshu,douyin}`。
  ⛔ 永远不要 `pkill -f chrome`，只能精确杀：
  `pkill -TERM -f "user-data-dir=$HOME/NewMe/profiles/<平台>"`。
- 开跑/收尾的 profile 纪律只有 `profile_guard.py` 一份：`solo(PROFILE)` 开场（清自己残留、
  别的平台在跑就 `BusyError` 停手）、`kill(PROFILE)` 收尾（回读确认真死）。
  ⚠️ `ctx.close()` **不保证进程死** —— 视频号 ×10 跑完那个 Chrome 活了 14 分钟，
  把接着的小红书 ×10 拖死两次；并且 ChatGPT.app 里的 Codex 副本用同一批 profile，
  两边同时跑一样会把当前这遍打死（实测过）。
- ⛔ 永远不要往活的 persistent profile 里 `add_cookies`（会顶掉登录态，还得重新扫码）。
- 扫码机会很贵，别浪费；抖音密码只从 keychain 取：
  `security find-generic-password -s NewMe-douyin -a creator.douyin.com -w`。
- 音频口径：**原声 + 字幕 + 背景音乐**，不用 TTS、不用声音克隆。
- 位置一律是**迪拜**，绝不能出现阿布扎比。
- 内容选题/文案口味归用户；技术方案自己定，不要把活推回去。

## 二、发布：只用这一个入口

```bash
cd ~/Movies/JianyingPro/User\ Data/Projects/com.lveditor.draft
python3 newme_post.py 方案.json --mode fill                 # 三平台填但不发（回归）
python3 newme_post.py 方案.json --mode publish              # 三平台真发（定时 北京19:30）
python3 newme_post.py 方案.json --only douyin --times 10    # 单平台连测
```

它串行调用三个**已过 fill ×10 全绿回归**的脚本：
`publish_weixin.py` / `publish_xhs.py` / `publish_douyin.py`
（统一 CLI：`方案.json --mode fill|publish [--video x.mp4] [--times N]`）。

⛔ 不要用 `newme_publish.py` 和 `publish_options.py`，已打 DEPRECATED：判据有假阳性。

跑长任务必须脱离桥进程，否则桥调用一超时就把它带走：

```bash
bash _run.sh <日志名> <脚本> [参数...]     # 内部走 detach.py（os.setsid）
```
轮询日志的每次桥调用 ≤55 秒。桥偶发 "Request timed out"，重试即可；
若日志文件压根没生成，说明那次启动没执行，重跑一次。
⚠️ 轮询时别用 `grep -q "https://"` 当结束判据：Python 的 urllib3 warning 里自带
一条 https 链接，会立刻假命中。按业务关键词（`登录成功` / `✅` / `❌`）匹配。

**别去换成现成的发布工具**（2026-08-20 调研过源码）：`dreammis/social-auto-upload`（9k★）
的视频号也是 patchright 开浏览器 + 抓 `qrconnect` iframe 的二维码让人扫，
能力表里视频号连 CLI 都没有；`rehatRobot/omnipost` 是它的二开、同一份 `tencent_uploader`；
商业工具（易媒助手/蚁小二）同样在本机 driver 浏览器。视频号个人号**没有发布 API**，
所以没有任何方案能免掉扫码 —— 我们这套还多做了定时/迪拜位置/双封面/数据回读，不该换。
值得借的只有一点：发布后把 `storage_state` 存一份做备份，profile 损坏能重建。

## 三、判据必须带阳性对照（这是全部教训的核心）

一个步骤"绿"必须能被真实缺陷打红。已被实测打出来的假判据：

1. **上传完成 ≠ 出现「重新上传」**（19.8 秒就出现，而「检测中 1%」才刚开始）。
   真判据：无「已上传 x/y MB」且无「检测中 N%」且有「重新上传」且标题框在，
   外加 `saw_busy` 阳性对照（必须真经过未就绪态）。
2. **话题 ≠ 页面上有 `#xxx` 文本**。真节点是编辑器里的 `div[data-mention]`。
   候选浮层会显示上一次查询的**残留**，挑不中要继续轮询别 return；只能按 **Enter** 选中
   （鼠标点候选会让编辑器失焦）。
3. **封面 ≠ 弹窗消失 + 助手不报缺**（直接点「完成」平台会拿视频帧凑数）。
   真判据：裁剪窗里的「保存」真点够 N 次（`saved == need`）。
4. **位置 ≠ 文字里含「迪拜」**（城市切换页签里就有）。真判据：占位符「输入地理位置」消失
   且含 `Dubai`。也不能读旁边那个 select（它永远显示字面「位置」）。
5. **一轮通过 = 每一步都绿**（`all(s["ok"] for s in steps)`），别让「收尾 ✅」盖住中间的红。
6. 删除类操作要有**前后计数**：删之前 n0>0、每删一次 n 必须真的 -1、收尾 n==0，
   否则立刻停手截图（点空了不报错是最危险的情况）。
7. **登录判据不能靠页面文字**：视频号顶层文档**常驻**「登录视频号助手」这段营销文案，
   已登录时也在（拿它当负面词 → 永远误报掉线）。
   同样地，**「有 qrconnect frame」也不能当反面硬判据**：扫码成功后 SPA 不会把那个
   iframe 从 DOM 摘掉，URL 一直挂着 → 会把已登录判成没登录（`wx_login_remote.py`
   为此傻等到超时一次）。正确顺序是**正面证据优先**：先找账号名 `Newme-Tanya` 或头像，
   命中即在线；都没有时才用 frame URL 兜底。
8. **解析出 0 条时必须把原始样本打出来**，并且别把 `evaluate` 的异常静默吞掉
   （吞过一次：页面渲染得好好的却报 0 段，白查半天）。

## 四、三平台各自的坑

**共同**：CDP `Emulation.setTimezoneOverride {timezoneId:"Asia/Shanghai"}` 必须先做
（本机在迪拜 UTC+4，不覆盖定时会差 4 小时），自检要看到 GMT+0800。
**回读也要做这一步** —— 后台是按浏览器时区渲染时间的，不覆盖会把北京 19:30 记成 15:30。
定时基准 = **北京时间 19:30**。日期可以在方案 JSON 里指定：
`schedule_bj_date: "2026-08-22"` + `schedule_bj_time: "19:30"`（两者都是北京时间）；
**不写 date 时行为完全不变**，还是「明天 19:30」。
解析与上限检查**只写在 `schedule_target.py` 一份**，三个脚本 import 它
（同一边界写在三处已经把这个项目坑过五次），自检：`python3 schedule_target.py --selftest`。
实测定时上限（冻结在 `WINDOW`，带绑定测试 + 阴性对照）：
**视频号 32 天 · 小红书 14 天 · 抖音 14 天**（抖音另要求 ≥2 小时后，留 130 分钟）。
⛔ 超出上限**报错退出**（`ScheduleError`，退码 2），不许静默顺延、不许当成功 ——
排期超过 14 天的条目必须**分批**：先拿三平台能排的，剩下的到时候再跑一次。

**视频号**（channels.weixin.qq.com，wujie 微前端）
- 表单 DOM **只存在于 wujie 沙箱 iframe 的代理 document 里**：顶层
  `querySelectorAll('input')` = 0，shadowRoot 深度遍历也找不到「请选择发表时间」，
  `page/frame.locator(...)` 一律 0 命中（老代码的 `deepAll(document)` 全是瞎的）。
  唯一可行三件套：`fr = url 含 /micro/content/post/create 的 frame` →
  `fr.evaluate` 读 DOM/取坐标 → `pg.mouse.click` / `pg.keyboard` 做真输入。
  新脚本别另写一套，直接 `from publish_weixin import wx_frame, click_xy, xy, PH_SCHED`。
- 定时时间要真写进 Vue 模型才算数：判据是 `mp-date-picker.__vue__.pick` 时间戳；
  只往外层 readonly 框写 value 只改显示，模型仍是默认 03:00 —— 内层「请选择时间」
  小框必须用**真键盘**打，然后 Enter。
- 「请选择发表时间」这个 input **切到「定时」之后才渲染**，不能拿它去找 frame。
- 位置只能选「不显示位置」（POI 按出口 IP 走，搜迪拜出来的是阿布扎比同名店）。
- 列表页也在 wujie iframe 里，回读要深层遍历。`--mode draft` 只有它支持。
- **定时最远能排 32 天**（2026-08-20 实测：可选 08-21~09-21，9 月后没有「下一月」箭头；
  当天已灰掉，因为北京时间已 23 点、离得太近平台不收）。量它的工具：
  `wx_schedule_horizon.py`（只读，不上传不发表）。⚠️ 日历里混着上/下月的日子，
  必须按「数字回到 1」切月份再比大小，直接 `max(数字)` 会算出 2026-09-31 当场崩。

**小红书**（creator.rednote.com，⛔ 不是 xiaohongshu.com）
- 笔记列表真地址 `/new/note-manager`（`/publish/notes`、`/creator/notemanage`、
  `/statistics/data-analysis` 全是错的，试过）。
- 标题 `input.d-text[placeholder*='填写标题']`，正文 `div.tiptap`。
- ⛔ 发布栏里坐标左移 72px 是「暂存离开」（存草稿跳走，等于没发），右移 71px 才是「发布」。
- 位置故意留空（POI 按出口 IP 会标成阿布扎比）。
- **定时最远 14 天**（2026-08-21 实测：日期面板里 08-22~09-04 可点，09-05 起全灰；
  只读探针 `xhs_schedule_horizon.py`，不上传不发表不存草稿）。它比视频号短一半，
  所以一次能三平台齐发的只有前 14 天的那几条。
- fill 模式**每遍留一条草稿**，测完要清：`_xhs_clean_drafts.py`（`--probe` 只看）。
  草稿箱不在笔记管理里，入口是发布页顶部「草稿箱(N)」；草稿数按「保存于YYYY-MM-DD」
  出现次数算（按「删除」按钮个数算会把确认气泡里那个多算一条）；
  确认框是 popover 不是 modal，文字「草稿删除后不可找回 / 取消 / 删除」，
  按 `[class*=modal],[role=dialog]` 永远找不到它 —— 要找**同时含「不可找回」和「取消」**的最小层。
- 号里去重：`_xhs_dedup.py`。列表行的操作键**没有文字**，hover 才出现，是右上角四个 svg 图标，
  **最右那个**是垃圾桶（按文字找「删除」永远是空数组）。

**抖音**（creator.douyin.com）
- 最好自动化（轻 DOM），但**平台零保险**：发布键永不禁用，点下去就发 —— 体检是唯一防线。
- 表单高 1474px 而视口 879px：任何坐标点击前必须 `scrollIntoView` 并验 `inView`。
- 关键选择器：文件口 `input[type=file][accept*=video]`；
  标题 `input.semi-input[placeholder*='填写作品标题']`；正文 `div.zone-container`；
  定时框 `input.semi-input[placeholder='日期和时间']`（可键入）；
  发布键 `button.button-dhlUZE.primary-cECiOJ` 且文字**完全等于**「发布」；
  位置行 `[class*=anchor-item]`，POI 结果 `[class*=option-v2]`；
  封面图口 `input[type=file][accept*='image/png']:not([accept*=bmp])`。
- 双封面流程：「选择封面」→ 弹窗「设置竖封面/设置横封面」→ 喂上面那个 image input
  （喂 `semi-upload-hidden-input` 不弹裁剪窗；点「上传封面」会因隐藏 input 遮挡而超时）
  → 裁剪窗点「保存」→ 点右下「设置横封面」→ 再喂 → 保存 →「完成」。
  ⚠️ 这个弹窗是全屏遮罩，**无论成败都要关掉**，否则后面定时/位置/发布全静默点空。
- 位置是三平台里唯一能挂真实迪拜的：搜英文 **"Dubai"** 取城市级 POI
  （名 `Dubai`，址 دبي, الإمارات العربية المتحدة）；搜中文「迪拜」给的是具体商户，会报错地点。
- **没有原创声明**：「自主声明」是 AI/虚构风险声明，勾了降权 → 记为「平台无此项」而非失败。
- **定时只收 2 小时后 ~ 14 天内**：超过就 `ScheduleError` 报错退出，不许静默顺延。
  它的日期框默认是「今天 + 一个整点」，回读必须比对到**年月日都对**（只看时分会把
  「日期没写进去」当成功）。
- 号里去重：`_dy_dedup.py`。作品管理行的真特征是文字含「删除作品/修改定时」
  （按"文字短"找会命中作品描述层，它不含日期 → 假阴性）。

## 五、登录与扫码（只有视频号需要人）

实测 cookie 寿命：小红书约 1 年、抖音约 2 个月（还能用 keychain 密码自动登录）；
视频号 profile 里只有 `sessionid`/`wxuin` 两个 cookie、**有效期到 2027 年**，
但服务端会在 **≈26 小时**后把会话作废 —— 所以掉线不是 cookie 过期，找「免登录开关」是白费：
登录页只有扫码，没有密码、没有「7 天免登录」。

```bash
python3 wx_login_remote.py            # 出码 → 传 COS → 打印 1 小时签名链接（人在外面也能扫）
python3 wx_heartbeat.py               # 每 20 分钟一次轻量已登录访问（LaunchAgent com.newme.wxheartbeat）
python3 login_keepalive.py            # 三平台只读体检，掉线只告警
```

- 用户侧是双击 `扫码登录视频号.command`。微信「扫一扫」支持**相册选图**，
  所以二维码只要能到手机相册就能扫；一张码约 5 分钟过期，脚本会自动换新的。
- ⛔ 别用 headless 碰微信（UA 带 `HeadlessChrome`，可能被判异地新设备而作废会话）。
  用**屏幕外真窗口** `--window-position=-3000,0` + 真 Chrome UA。
- 心跳阈值别设太宽：`NEWME_MIN_FREE_MB` 留 700 会天天跳过，等于没保活（现在 420）。
- 减少扫码次数的正解是**摊薄**：一次登录把未来最多 32 天的内容排进定时队列。

## 六、数据回读与选题（已过 ×10 回归）

```bash
bash _run.sh stats.log stats_pull.py xiaohongshu douyin   # 抓 → 追加 _pipeline/stats.csv
python3 topic_next.py                                      # 出选题建议报告
bash _run.sh s10.log _stats_x10.py 10                      # 回归：小红书≥7、抖音≥10 条
```
用户侧是双击 `跑数据.command`。基线：单遍两平台约 35 秒，实测 10/10 全绿。

行解析必须**按平台写死**，别用通用卡片猜测器（它在抖音抓出过标题「平均浏览图片数」、
播放 59 这种数据面板碎片）：
- 取行的 JS：含日期、12–300 字、高 ≥40px 的容器，然后**只保留最内层**
  —— `keep = out.filter(a => !out.some(b => b!==a && a.includes(b)))`。
  ⚠️ 方向写反（丢掉被别人包含的）会只剩整页容器，小红书 9 行全被页头文字吃掉 → 解析 0 条。
  上限也别放宽到 400 字，否则多行父容器混进来做同样的坏事。
- 抖音行是**带标签**的（`播放 331 … 完播率 5.41% … 涨粉 4`），真行必含「删除作品/修改定时」；
  私密作品指标是 `-`，必须映射成 **None 而不是 0**。
- 小红书行**没有标签**，形状是 `[时长] 标题 YYYY-MM-DD HH:MM 播放 评论 点赞 收藏 分享`
  （注意第二个数是评论、第三个才是点赞）；含「定时发布」或导航词的行跳过。
- 列表**懒加载**：不能只 evaluate 一次（8 秒时小红书只有 1 条，轮询后 7 条）。
  轮到行数不再增长为止。
- 自检 `stats_pull.py --selftest` 里阳性、阴性对照都要有（阴性样本用真页面 dump 的
  面板碎片和未发定时行）。

## 七、内容侧

- 素材实测全是**无口播 b-roll**，转写不能当流水线入口 —— 必须脚本先行。
- 选段入口：ffmpeg 抽帧联系表 + 抖动/锐度/亮度指标挑可用窗口
  （注意 `tile` 滤镜只吃单路输入）。
- 选题讲**一个具体痛点**，不炫豪宅；30-45 秒。
- 剪映能读明文草稿（`newme_draft.py` 可生成），但剪映的朗读面板不可自动化；
  纯合片走 ffmpeg 更稳，剪映只在需要人工微调时开。
- 有 7 个 `moov atom not found` 的文件是 iCloud 占位 stub，不可读，别当素材。

## 八、回归与验收

改动任何发布脚本后，必须重跑：

```bash
bash _run.sh dy_x10.log  publish_douyin.py 方案.json --mode fill --video _pipeline/wx_probe12.mp4 --times 10
bash _run.sh wx_x10.log  publish_weixin.py 方案.json --mode fill --video _pipeline/wx_probe12.mp4 --times 10
bash _run.sh xhs_x10.log publish_xhs.py    方案.json --mode fill --video _pipeline/wx_probe12.mp4 --times 10
```

要求 **10/10 全绿**（单遍耗时基线：视频号 ~45s、小红书 ~46s、抖音 ~85s），
失败分布记进日志，红的当场修，不达标不许改这份 skill。
改动 `stats_pull.py` 后同样要重跑 `_stats_x10.py`。
测完清小红书草稿箱。发布后用作品管理页回读确认「定时发布中 + 时间」，并检查号里没有重复条目。

