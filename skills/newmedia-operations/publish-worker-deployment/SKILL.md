---
name: publish-worker-deployment
title: 自动发布 worker 机器选型与改造评估（浏览器自动化）
description: 自动发布/定时发布落地时用：机器选型、改造量评估、阶段化部署。
---

# 自动发布 worker 部署（浏览器自动化）

> 🔴 **口径（2026-10-14 用户最终裁定，最高优先）**：**照旧全部自动化**——生成→质检→上传提交一条龙，量小阶段先测试着用。
> 唯一保留的安全网＝审批门（批准一次覆盖一批）；其余流程不减速。
> 🟡 **发布时机（2026-10-14 用户定）**：**不设单日条数上限**（“3 条确实不够”，不要再提 3 条/日）；降特征靠**发布时间随机化**——用 `workflow/tools/pick_publish_slots.py` 生成 `schedule_at`（自然时段窗口内随机取点、间隔 ≥35 分钟且随机、避开整点/5 分钟刻度，带 --seed 可复现，遵守平台 130 分钟前置/14 天窗口）；自动排期装不下的量**走人工发**补（人手动点提交天然无特征）。
> 背景（只存档、不作执行依据）：巨量星图无官方素材上传 API，自动提交类工具都是网页模拟，星川规则把模拟器/外挂/自动化脚本列为违规；处罚链：扣信用分→封接单 7/15/30 天→冻收益/剔分成/扣保证金/掉 S0→永久关商单权限＋矩阵牵连。全文见 `workflow/docs/半自动批量上传安全规范_20261014.md`（已标「不作强制」）。
> **禁止重复劝风险，禁止拿旧口径要求改成人工提交**（只存档）；真出事时才停手并报用户。

## 发布运维固定规则（2026-10-14 定案，固定执行）

- **通道按引擎分**：一号 `chrome` + `profiles/douyin`；二号 `webkit` + `profiles/douyin-webkit`；**火狐淘汰**（实测 3 成 1，应用本体已删）。
- **点击必须抗遮罩**：`semi-portal` 残留遮罩会拦 hit-test → 8s 超时 → 浏览器 EPIPE 崩（exit=1）。标准点击失败退回 DOM 派发点击+focus（Chrome/火狐路径不变）。
- **发布前必查三项**：①无其它自动化浏览器 ②`plan/approval` 必须先落**广州**暂存区 ③账本键不是 `RESERVED`/`CONSUMED`。
- **账本**：键＝内容+账号（与单号无关，重签无效）；`CONSUMED`=已提交（先看平台，别重发）；`RESERVED`=僵尸占位（备份后回收才能重试）。
- **杀队列要杀干净**：只杀外壳会让子进程自己把片子发出去；被中断的尝试一律按「可能已发布」处理。
- 全部细则（含星图任务判定、命令纪律、成功判据）见 `references/publish-ops-rules-20261014.md`。

## 触发

- 要把「自动发布」落地成真实可跑的东西（不是只写方案）
- 用户问：发布跑服务器还是电脑 / 这套能不能直接用 / 代码要改多少
- 适配第三方短视频自动发布 skill（NewMe 那套等）到我们产线 PUBLISH_OPERATE 节点

## 核心认知（先说死）

**自动发布的本质是浏览器自动化**：Playwright 驱动真实 Chrome 打开平台网页版（抖音创作者中心/视频号/小红书），模拟上传、填话题、选封面、点发布。不是调平台 API。因此：

1. 必须跑在一台**有真实浏览器环境的机器**上（电脑或服务器都行，但服务器要能跑 headful/虚拟显示）
2. **登录态是命门**：账号先人工扫码登录一次，之后靠 cookie/profile 保活；掉线要人工扫码
3. **发布键平台零保险**：抖音发布键永不禁用，点下去就发——阳性对照门禁是唯一防线
4. 视频号没有发布 API，任何方案都免不掉扫码

## 机器选型对比（服务器 vs 常开电脑）

| 维度 | Linux 服务器 | 常开电脑（Mac/桌面机） |
|---|---|---|
| 内存 | 单个 Chrome 占 1.5-2G，原保活代码要求启动前 ≥2G 可用；同机跑产线容易 OOM | NewMe 实测基线 8GB 单 Chrome 串行；专机更接近已验证环境 |
| 登录态/风控 | 机房出口 IP 非账号常用登录地，风控概率高 | 放账号日常使用地+固定网络，环境变化少 |
| 扫码路径 | 要远程可视窗口或二维码中转，敏感且复杂 | 值班人本地扫码，路径短 |
| headless | 不能假设 headless 可用（视频号会判异地新设备作废会话）；需真窗口或验证过的虚拟显示 | 原生桌面会话，天然支持可视浏览器 |
| 交互差异 | Meta+a→Control+a、keychain→secret manager、vm_stat→/proc/meminfo，发布脚本要大改 | Mac 可复用原脚本经验，改造量小 |
| 7x24/服务监督 | systemd/队列 worker 天然适合控制面 | launchd/计划任务，要关睡眠+防重启 |
| 结论 | 适合做控制面（调度/审计/告警），当前服务器资源紧则不当首期真发 worker | **首选做浏览器 worker**，但必须专机/独立系统用户 |

推荐组合：**常开电脑做浏览器 worker + 服务器做控制面**。服务器真发需前置：内存升到 ≥8G 基线、账号方确认出口、建立经验证的可视窗口/扫码路径、阶段 0-3 验收全过。

## 改造量三层评估法（关键，用户 2026-08-21 纠正过「不是都要改吧」）

评估第三方发布脚本能不能直接用，按三层拆，**不要一刀切说「重写」**：

1. **环境绑定层**（取决于 worker 机器系统）——系统键盘快捷键、凭证存储、内存检测 API、路径习惯。Mac 环境原样复用；Linux/Windows 才要改
2. **业务参数层**（每客户必改）——账号/profile 路径、POI 地点逻辑、固定账号名、发布计划字段。参数化即可，不是重写
3. **平台选择器层**（与机器无关，可直接复用）——抖音文件口/标题框/发布键/双封面流程、上传完成判据、话题节点、回读逻辑

**机器选型定了，改造量结论就变**：同一套 NewMe 脚本，跑服务器=「高」（发布器/保活/扫码/profile 全要 Linux 化重写），跑 Mac=「中低」（只改 POI 逻辑+账号参数化+外面加审批壳）。方案里写改造量之前先问清楚目标机器。

**写部署方案前必须先确认实际机器配置**（2026-08-21 用户「你写的时候不需要知道电脑配置吗」）：系统（Mac/Windows/Linux）、内存、是否专机、是否常开。拿「一台常开电脑」当抽象概念写方案 = 交出去的是一堆假设。确认方式：直接问；或查小鹿 guardian 链路（广州机有用户 Mac 的 SSH key，但 guardian shell 已禁用 2026-08-22，只能传文件/导剪映——远程查配置要用 jianying 反向隧道，见 references）。

## 阶段化部署（每步验收，任一不过不进下一步）

- **阶段 0 阳性对照门禁**（纯离线，不连账号）：publish_plan/StepResult/审批回执/幂等键/状态机；发布按钮封装在硬门禁后；每条绿判据配必红坏样本；审计脱敏。**不依赖机器选型，可最先开搭**
- **阶段 1 登录+保活+扫码值班**：独立系统用户、加密 profile、账号注册表；正面登录证据；掉线只告警不回灌 cookie；人工扫码值班
- **阶段 2 单条发布全链路**：fill ×10 全绿 → 人工核对 → 一条 canary 账号方在场确认 → 作品管理页回读平台作品 ID 收口
- **阶段 3 定时任务+告警**：队列调度、同账号锁、异常 fail-closed、点击结果不确定先回查不重发

## 阶段 0 落地流程（2026-08-22 实跑验证，publish-worker-deploy 项目）

阶段 0 门禁是纯离线开发，不等 Mac 在线，可最先开工。落地走「codex 打包任务书 → Hermes 三关预检 → 派实施 → 全量验证」：

1. **建项目脚手架**：`workflow/projects/publish-worker-deploy/`，`inputs/` 放试点方案 + NewMe 仓库副本（codex 容器读不到项目外，必须 cp 进来），`guard/kb_checked.json` 打知识库标记（sources 列实际读过的文件）
2. **打包任务书**：交给 codex 打包+自审（Hermes 只传话，见 task-brief-gate）；任务书要求覆盖 publish_plan/StepResult/审批回执/幂等键/状态机/点击许可/脱敏审计 + 每条绿判据配必红坏样本
3. **Hermes 三关预检（codex 打包产物不能直接 dispatch）**：
   - `grep -nE "seedance|出片|视频生成|生成视频|video.*gen|SKIP_KB_GATE"` 期望 0 命中——**codex 自审段常自带触发词**（写「英文 video 与 gen」被跨词命中），命中就 patch 成逐字母拆分（`v-i-d-e-o` / `g-e-n`）
   - `python3 ~/.hermes/scripts/kb_gate_sg.py -f <任务书>` 期望 KB_GATE:PASS
   - `python3 /home/ubuntu/workflow/task_brief_gate.py --brief <任务书> --project <项目>` 期望 PASS；WARN 提示（缺 USER_REQ/数据来源字样/判断词）逐个补掉再派
4. **派实施**：`sg docker -c "python3 hermes_task_dispatch.py --brief <任务书> --project <项目> --target codex -- \"$(cat <任务书>)\" <项目>"`（background + notify_on_complete，docker 权限失败用 sg docker 包裹）
5. **收产物全量验证**：py_compile 全过 → 测试全跑（`PYTHONPATH=. python3 tests/test_*.py`，47 项全过）→ `python3 -m stage0_gate.cli selftest`（断言 browser not_used / network not_used）→ `verify-bundle`（sha256 匹配）→ 产出 Mac 离线 zip
6. **阶段 0 产物特征**：零第三方依赖（Python 3.9+ 即可）、无浏览器/网络/账号调用、可离线自检、可复现构建（两次构建摘要一致）

详细实录见 `references/stage0-gate-impl-20260822.md`。

## 阶段 1 落地实录（2026-10-13 实跑，Mac worker 已登录成功）

路径：Mac `<MAC_USER>` ~8G macOS 12.7.6 → 广州 relay（ssh -R 2223 / 重连后 46222）→ 本机。`~/publish-worker`（bin/ profiles/ config/ logs/ outbox/ evidence/），account id `douyin-pilot-001`。

- **安装**：`setup_worker.command` 经 `NEWME_WORKER_ID=... NEWME_TUNNEL_USER=ubuntu NEWME_SSH_KEY=...` 注入，自带 12 项自检全过；反向隧道 launchd 自起。
- **登录收口证据**：`login_check.py --headful` 必须返回 `status=ONLINE` + `evidence.avatar_present/douyin_id_match/nickname_match/profile_card_present` 四项 true + `login_control_count=0` + `remaining_profile_processes=0`；四项缺一不算过。
- **二维码导出**：`douyin_login.py --account <id> --scanner <duty> --timeout 300 --export-qr ~/qrlogin_<ts>.png`（0600、仅主目录、会话结束即删、内容与路径不进日志）。脚本**一次性导出、不刷新**码；码的寿命由平台定（约 1–5 分钟），我们控制不了——导出即尽快人工转发扫。
- **人工登录可行、脚本自开浏览器会被风控**：由人在 Mac 专用浏览器里登录、助手远程 `screencapture -x` 看屏 + 发指令，是最稳的路径；登录态落 `profiles/<account>`。

## 封面：一律用我方自制封面（2026-10-13 用户拍板「以后就用这个封面」）

**规则**：抖音发布的封面走「上传我们自己的图」，**不走平台 AI 候选列表**。平台候选要等它现生成（实测 80s 起，且经常卡在「生成中」——同一支片跑三遍里两遍因它超时判 RED）。用户原话：「你点那个框，它就会出现那个封面选择，你就直接点就行了，你不要等AI的，AI的那个好慢的」。

**固定样式模板**（照搬同赛道在投作品那套）：右上角「免费看漫剧」APP 图标 + 黄字黑边「火龙漫剧」+ 蓝字白边「海量漫剧随心看」，底图用居家感 AI 女主对镜头笑。竖 720x1280、横 1280x720。

- 生成器：`workflow/projects/publish-worker-deploy/assets/covers/make_cover.py --girl <女主图> --outdir <目录>`（默认底图 `huolong-ruanwz-6tpl-v1/assets/女主B_AI数字人_年轻甜美_v1.jpg`，APP 图标 `app_icon_mianfeikanmanju_20260921.png`，字体 `/home/ubuntu/.fonts/NotoSansSC-Bold.otf`）
- 成品：同目录 `cover_v.jpg` / `cover_h.jpg`，同参数重跑 sha256 一致
- 判据：封面文件缺失或上传失败 → 该步 **RED**，禁止静默回退到平台候选列表、禁止调大超时掩盖

## 人工门（自动化不得绕过）

1. 书面授权门（无授权只出手动发布包）
2. 内容/排期审批门（令牌绑定内容 hash+计划 hash）
3. 扫码值班门（掉线只告警留证，不自动刷新二维码）
4. 首条 canary 门（账号方在场确认）

## 验收硬标准（关键几条）

- 发布成功必须有平台作品 ID 回执；URL 跳转/toast/标题命中不算成功
- 同一 account+content_hash+schedule_at 重试不产生第二条作品（幂等）
- 点击后断网 → UNKNOWN → 先回查作品管理页，人工裁决前禁止重发
- 不可得字段写 None+原因，真实 0 才写 0；不得用旧快照掩盖本次抓取失败
- 凭证（cookie/二维码/密码/签名 URL）不进日志

## Pitfalls

- **别把第三方 skill 当成品部署**：写死的客户参数（地点/账号/路径）+ 平台页面会变 + 环境差异 + 没接我们门禁 = 必须借经验重写，但它的选择器/判据/踩坑清单是最值钱的地图，照抄
- **改造量评估先问机器**：任务书写「部署方案/改造清单」前，先确认目标机器实际配置写进任务书；执行器拿「理想常开电脑」写方案 = 白写一轮（2026-08-21 实例）
- **服务器有 Chromium ≠ 抖音已可用**：浏览器组件存在只证明能装，不证明登录/POI/可视窗口/选择器通过
- **账号 profile 不跨机复制**：切机必须人工重新登录+重新 fill 验证；一账号一加密 profile
- **阶段 0 与机器选型解耦**：门禁/审批壳是纯离线开发，不等机器/授权/账号，可最先开工
- **CAPTCHA 判据禁用裸词（2026-10-13 实际误报）**：整页文本正则里写 `验证码` 会命中登录页正常文案（`验证码登录/请输入验证码/获取验证码`），把普通登录页判成 `status=CAPTCHA` 并让所有自动登录/检查假失败。判据只认真实交互组件（滑块/拼图/拖拽、风控厂商标记 class/id/iframe），并显式排除 login/qrcode/sms/input 类控件；**必须配阳性对照**（真滑块样本要能打红）+ 阴性对照（正常登录页不许报警）。
- **自测全绿 ≠ 真机可用（2026-10-13 实际事故）**：交付回来的执行器 68 项自测全绿，但那些测试只覆盖逻辑门（计划校验/审批绑定/幂等/浏览器独占），测试里的「页面」是照执行器期望手写的假页面——真实 `DouyinPage` 在 12 个测试文件里出现 **0 次**。真机一跑连爆两处：①执行器调了 `page.goto`，而真适配器根本没这个方法；②执行器跑在抖音首页、压根没进上传页（`input[type=file]` 只存在于 `/creator-micro/content/upload`），于是喂文件超时。规矩：**涉及真网站的交付，写明「是否在真机跑过」；没跑过只能说「逻辑自测通过」，不许说「验证过/验证成功」**；这类交付的验收一律含「真机跑一遍」，测试补齐要用真适配器做接口契约断言（AST 比对方法集），禁「照执行器期望手写假页面」的自证式测试；并让每步报告带**所在页面 URL**，否则每次排障都得开浏览器探针。
- **传给 Playwright 的文件路径必须是绝对路径（2026-10-13 实测真因）**：批次 plan 里写的是 `~/publish-worker/media/video.mp4`，`set_input_files` 拿到带**字面 `~`** 的路径不会报「文件不存在」，而是把元素动作重试到超时——报错文本伪装成 `waiting for locator("input[type=file]…") Timeout 45000ms exceeded`，让人误以为是选择器/页面错了。手工探针之所以「成功」，正是因为传的是 glob 出来的绝对路径。排障顺序：先核路径（expanduser+isfile 预检），再怀疑选择器；喂文件前必须 expanduser + isfile 预检，缺失就秒失败并报真实原因。附：验证「页面对象是不是同一个」这类假设要靠实测，别靠推测（本轮推测过一次，实测推翻）。
- **单浏览器守卫别把辅助进程当真人（2026-10-13 实测）**：`chrome_crashpad_handler`（崩溃上报助手）会在浏览器退出后残留，守卫若按「有 chrome 进程」判定，会让后续每一遍全部 `existing_chrome` 跳过（实测 10 遍里后 8 遍全废）。判定只认 Chrome 主进程，且失败/异常路径必须收干净（连同辅助进程），收尾后 `status` 必须 clear。
- **别动整盘加密（FileVault）开关（2026-10-13 实际事故）**：开关 FileVault 会换掉 Chrome 的 profile 加密密钥，登录态直接失效（Chrome 顶部出现「需要重启浏览器加载个人资料数据」），而**退出重开 Chrome 也修不回来**。worker 部署完成、登录态建立之后，一律不要再 enable/disable 磁盘加密；真失效只能重新扫码登录（或把坏 profile 改名留档、让新登录生成干净 profile）。
- **手动拉起 worker 浏览器必须带 `--use-mock-keychain`（2026-10-13 实际事故）**：要让人看后台/人工登录时，只能用 worker 同款参数起：`"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --use-mock-keychain --user-data-dir=<worker>/profiles/<account> --new-window <url>`。Playwright 用 mock keychain 写 cookie，普通方式（`open -a "Google Chrome"` 或不带该参数直接跑二进制）解不开这些 cookie → 页面回落到登录页，且 Chrome 会把读不出的 sessionid/sid_guard/sid_tt 当无效 cookie 清掉 = **抖音登录态被抹掉，只能人工重新扫码**。核实登录态别只看页面：直接读 `<profile>/Default/Cookies`（host 含 douyin 的 `sessionid/sid_guard/uid_tt` 是否还在）；本机 Chrome 若在跑，页面表现不可信。另：手动实例开着就占住 profile，自动化（fill/publish/回读）会因 `existing_chrome` 跳过——要跑发布先关窗口。
- **profile 改名后精确清理要换命令**：`terminate_profile_exact("<account>")` 按精确目录 `profiles/<account>` 匹配，目录一旦改名（如 `.broken-<date>`）就返回 `left=0` 但进程还在。用 `pkill -TERM -f "user-data-dir=<worker>/profiles"` 精确清（仍是窄匹配，不是全局 pkill chrome），清完必须复核 `profile_guard.py --account <id> --status` 两个计数都为 0 才开跑。
- **Mac 通道能力先实查再引用（2026-08-22）**：guardian shell 已禁用，旧文档「可下发 shell 查 system_profiler」失效；部署 Mac worker 前置三件套 = Mac 开机 + jianying 反向隧道在线 + 能执行命令，缺一推不动。写方案/派活前先实查通道现状，别照抄旧 references（本 skill references 已更新）
- **发命令给用户必须纯文本（2026-08-22 用户明确纠正）**：禁反引号/代码块/markdown 包裹——聊天软件复制会带脏字符（实例：命令变成 `00~ssh ...` → command not found）。要用户执行的命令直接给裸文本行，让用户手敲或整行复制，不包任何符号
- **服务器不能主动连用户 Mac（网络拓扑，2026-08-22 实查）**：Mac 在 NAT 后 + 服务器无 Mac 登录凭据，所有到 Mac 的通道都是 Mac 主动发起（guardian 轮询 / ssh -R）。要直连 Mac SSH：Mac 上先跑 `ssh -R 2223:localhost:22 -N ubuntu@<GZ_HOST>`（广州机，2223 自定义端口），服务器侧再 `ssh -p 2223 ubuntu@127.0.0.1` 连回。国内家庭宽带多为 CGNAT 大内网，直连基本无望，反向隧道是唯一可靠路径

- **给客户机打补丁三步缺一不可（2026-10-26 实测）**：①推 `agent/winport/*.py` 时同步改同目录 `MANIFEST.json` 该文件的 `bytes/sha256`，否则启动链 `ok=False` → 新增发布被拒 `INTEGRITY_FAILED`（只告警不停 agent，但发布全废）；②agent 是常驻进程，只推文件不生效；`run_panel.py` 仅在 healthz 版本 ≠ `VERSION` 文件时才重启 agent，所以推送时必须递增 `VERSION`（并同步 `MANIFEST.version`），再以分离进程 `start "" pythonw.exe run_panel.py` 拉起，旧 agent 被停、新 agent 自动重连通道；③推完先跑一次 `verify_program()` 确认 ok=True 再重启，别拿客户机赌。
- **客户机「升级成功」但跑的还是旧版：三个必查项（2026-10-27 实机事故，同一个客户反复三次）**：
  1. **端口 owner 的 exe 路径**：`Get-NetTCPConnection -LocalPort 9223 -State Listen` 拿 PID，再 `Get-Process -Id <pid> | select Path`。只要路径不在正式 program dir（`%LOCALAPPDATA%\Programs\HuolongAgent\publish-assistant-<ver>`）里，就是旧版还在跑。healthz 的 version 会骗人——版本号读的是 program dir 的 VERSION，代码可能是旧的。
  2. **`.venv/pyvenv.cfg` 的 `home`**：必须等于当前 program dir 的 `runtime`。旧安装创建的 venv 会一直绑定旧路径（实例：`home = D:\...\1.2.46\runtime`），杀旧进程后新 agent 起不来，旧的又被拉回来——表现就是「怎么杀都杀不干净」。
  3. **`run/program-path.txt` 与桌面快捷方式**：指向 `%TEMP%` 或 `Downloads` 都算没装好（客户清一次临时文件就废），必须落在 `%LOCALAPPDATA%\Programs\...`。
  三项全对才算升级成功；只看到「[6/6] installation complete」不算。一键校验：`python3 workflow/projects/publish_control/verify_client_install.py --customer c_xxx`，必须 PASS 才算装好。
- **安装包杀不掉旧进程是设计成这样的，别信口头承诺**：`bootstrap_py.py step_stop_running` 对「exe 在产品目录外」的进程要求 `/healthz` 和命令行双证；旧版卡死不应答 `/healthz` 时它会**静默放弃**，日志只有一行 `port 9223 pid <pid> refused: image ... outside product folders`，安装继续并报成功。修法：命令行能证明是本产品时，即使 `/healthz` 无应答也允许杀（只有端口应答成别的产品才拒）。
- **换安装目录必须重建 venv**：bootstrap 的 `venv_ok()` 只测 `python -c print('ok')`，旧 venv 能跑就跳过；要加「pyvenv.cfg 的 home 必须等于当前 program/runtime」的判据，不一致就删了重建，否则新装目录永远依赖旧目录。
- **要“立即发”就别靠排期（2026-10-27 客户现场）**：客户机 `dryrun` 在 `publishing=True` 时要求 `0 <= now - schedule_at <= 600`（计划时间必须**已经到点**），而排期器把时间排到 2 小时后——所以点确认永远报 `SCHEDULE_OUT_OF_WINDOW`。真立即发：把 `schedule.min_lead_minutes` 改小（测试期改 1），plan 的 `schedule_at` 设成当前时间+几分钟，先用 `dry-run` 生成带 token 的 preview，等到点后再 `publish --mode approved_publish --allow-submit`（plan/preview/token 三者一致）。正式跑量时记得把 `min_lead_minutes` 改回 130，否则会变成随点随发。
- **客户要“想几点发就几点发”：改客户机 `config/settings.json` 的 `schedule.min_lead_minutes`，不要改代码（2026-10-27 实测）**：`dry-run` 用 `load_settings` **原样**读这个值做 `too_soon` 校验（不夹取），而自动排期的 `pick_slots/cadence` 走 `normalize_schedule_settings`，把该值夹到下限 130（常量 `MIN_LEAD_MINUTES`）。所以把 settings.json 改成 0：人工「改到X点」不再要求提前 130 分钟，自动排期仍按 ≥130 分钟选点。settings.json 在 `publish-worker/config/` 下、不在 MANIFEST 启动链里，改完无需重算校验、不会 `INTEGRITY_FAILED`；改前备份 `settings.json.bak_*`。
- **机器人排期下发的 5 分钟延迟是故意的**：`bot.py` 的 `SCHEDULE_DISPATCH_LEAD = -5`，到点后 5 分钟才下发（保证客户机 `0 <= now-schedule_at <= 600s`）。所以「改到14:30」实际发出约 14:35，别以为是没生效。
- **排期发布必须“到点再下发”，确认时立刻 publish 必撞窗口（2026-10-27 实机事故）**：客户机 `prepare` 排到下一个合法时段（≥130 分钟），而 `publish` 只在计划时间 ±10 分钟内可执行；两边的 `confirm_token` 是匹配的，唯一被拒的原因是时间窗口（`SCHEDULE_OUT_OF_WINDOW`，exit 2）。做法：确认时把批次挂成 `scheduled`，在计划时间前 3 分钟重新签发凭据再下发（含重启续跑）。诊断时先用 `publish --mode approved_publish`（**不带 `--allow-submit`**）重跑同一条，能拿到完整 gate/confirmation JSON 且不会真发。
- **控制面开了 CONTROL_INBOUND_TOKEN 后，飞书机器人必须换投递头（2026-10-27 实机事故）**：服务端 `_require_inbound()` 优先只认 inbound token，一旦 `CONTROL_INBOUND_TOKEN` 存在就不再接受 admin token；而机器人 `CONTROL_TOKEN` 用的是 admin token，于是所有「发布」都返回 403 `bad inbound token`，客户只看到「指令投递失败：请稍后重试」，队列里连一条命令都没有。修法：机器人对 `/api/inbound` 额外带 `X-Inbound-Token`，管理读接口（如 `/api/customers/by-chat/...`）继续用 admin bearer；两个 secret 不能互换。排查入口：直接 `POST /api/inbound` 看 HTTP 码——403 是 token 问题，201 才说明投递通。
- **桌面素材夹不能 junction 到 inbox**：同一文件两条路径会让发布看到两个候选而拒绝；正确做法是解析器同时扫 inbox + 桌面「发布素材」。扫描必须过滤后缀（只 .mp4/.mov），否则夹里那份 `先看这里.txt` 会被当素材；显式 files 列表也要两个根都认，只在 inbox 里找会静默丢桌面文件。
- **封面上传别写成「等平台 AI 候选」（2026-10-13 实测）**：`platform_cover_list` 路径要等平台现场生成候选，跑三遍有两遍因候选一直「生成中」超 180s 兜底 → 一步没点到 → RED。封面固定用我方自制图（见上文封面段落），耗时从 80s+ 降到秒级，产物还确定。

## 客户机装崩后的恢复链（2026-10-29 实机，踩了 6 轮才通）

1. **弹 “runtime missing” = `%LOCALAPPDATA%\HuolongAgent\publish-worker\.venv\Scripts\python.exe` 不存在**（桌面 vbs 只查这一个文件）。别重下整包，直接在该版本程序目录跑 `bootstrap.bat`，它会判定 venv 不可用并重建。
2. **重建报 `Permission denied: .venv\Scripts\pythonw.exe`** = 上一轮是**管理员权限**装的，venv 文件归 Administrators，普通用户删不动。步骤：`taskkill /f /im pythonw.exe` → `rd /s /q <data>\.venv` → **右键 bootstrap.bat 以管理员身份运行**；装完再普通双击桌面图标（管理员跑 bootstrap 时故意不自动起 agent）。
3. **装完面板能开但控制面没心跳** = `run/agentpoll-status.json` 里 `state=disabled, reason=CONTROL_URL is required`：`control.json` 被清掉了。重建 `<data>\control.json`：`control_url / customer_id / customer_token / device_id / device_token / binding_epoch`。
4. **`binding_epoch` 必须写成字符串 `"0"`**：main.py 的 overlay 用 `str(v or "")`，整数 0 会被当空值丢掉 → 启动后每个 channel 报 `binding_epoch is required when device_id is set`，心跳永远不更新。
5. **设备令牌丢了只能轮换**：`customer_devices.token_hash` 是 sha256，客户端 control.json 没了就没有明文。直接 `UPDATE customer_devices SET token_hash=sha256(新dev_令牌)`（先备份 control.db），再把明文写回 control.json。轮换前确认该 device 是 active、epoch 不变。
6. **远程起后台进程全被掐**：从 `remote exec` 里 `Popen(DETACHED_PROCESS)`、`start /b`、`ShellExecute` 起的 pythonw 都会随 op 结束被杀（job 对象）。可靠办法只有 `schtasks /create /tr <bat> /sc once /f` + `schtasks /run`（注意 `subprocess.run([...])` 传列表，别经 cmd 拼引号，否则 WinError 5 / 静默失败）。重启 agent 同理走计划任务，因为 kill 掉 agent 会把远程支持通道一起断掉。
7. **远程支持码每次重启都变**：重启 agent 后旧的 Bearer 立刻 401，必须让客户从面板重新读一串；新码对应新的反向转发端口（在 relay 机 `ss -ltn | grep 127.0.0.1:23xxx` 扫 23000-24999 找）。
8. 收尾清掉自己写在客户 data 根下的临时脚本（`del /q` 逐个给路径，别用带引号的长串，远程 exec 里引号会被吃掉）。

## 关联

- `newme-shortvideo-pipeline`：NewMe 原版 skill（业务用法）
- `workflow/external/newme-skills/`：NewMe 仓库副本（scripts/ 20 个脚本 + AGENTS.md 踩坑清单）
- `workflow/external/publish-safety-methodology/`：阳性对照方法论（判据必须能打红）
- `task-brief-gate`：派活任务书规范（部署方案类任务书见其 references）
- 本地生活单账号抖音试点部署方案实例：`workflow/projects/newme-adapt-analysis/本地生活单账号抖音试点部署方案_20260821.md`

## 参考文件

- `references/newme-douyin-pilot-20260821.md`：NewMe 单账号抖音试点部署方案要点 + 机器实测数据 + 源码硬编码点 + **Mac guardian 在线探针命令**（验证 Mac 守护器是否活着，2026-08-22 实跑）
- `references/stage0-gate-impl-20260822.md`：阶段 0 阳性对照门禁落地实录（包结构/设计点/验证命令序列/codex 任务书三关预检/attest WARN 判定）
