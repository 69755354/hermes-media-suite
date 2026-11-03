---
name: customer-operations-platform
description: "广州机客户运营平台工作流速查。触发：广州机/ai-video-factory/billing/客户积分。"
version: 1.0.0
author: Hermes 主运营助手（新加坡机）
license: MIT
metadata:
  hermes:
    tags: [guangzhou, ai-video-factory, billing, customer-platform, architecture]
---

# 客户运营平台（广州机）架构与工作流

## When to Use

用户提到广州机/ai-video-factory/billing/客户积分/火锅店流程/客户运营平台/「把 XX 工作流画成图」时加载。用于：查广州机组件与端口、复述端到端客户流程、做工作流可视化图、判断跨机任务归属。

广州机（<GZ_HOST>）= 客户运营平台，与新加坡机（<SG_HOST>，本机=内容生产）分工。

## 身份与分工

- **广州机**：客户界面 + 账务。跑：ai-video-factory（8090 网页工作流）、billing（8080 账务，billing.db 真源）、小鹿（飞书客户机器人）、AstrBot、miniapp-frontend。
- **新加坡机**：内容生产（codex/claude 生成打法文案、Seedream/Seedance 出片、ffmpeg 合成）。
- 广州工厂的「增长打法+三版文案」由**新加坡机 codex exec 远程真实生成**（非 mock）。

## 组件与端口

| 组件 | 端口 | 说明 |
|:---|:---|:---|
| ai-video-factory | 8090 | 网页工作流，`/access` 客户入口、`/ops/login` 内部审核台 |
| billing | 8080 | FastAPI + SQLite WAL 单库强事务，`/tasks/{id}/settle` 扣费 |
| 新加坡→广州隧道 | 2222 反隧 + 18080 本地转发 | 工厂读 billing 用 `XG_FACTORY_BILLING_BASE_URL=http://127.0.0.1:18080` |

## 端到端工作流（火锅店 12 步，速查版）

客户侧：输入编号 → **余额>0 门禁** → 上传五类素材(菜单/价目/门头/菜品/服务)+授权MP4 → **C1 内容方案确认**(确认/修改/暂停,无超时自动通过) → **C2 成片确认** → 下载ZIP(下载前再验交付门禁)

工厂侧：**O1 授权执行**(内部登录,5分钟短效token) → 导入已核验洞察≥3条 → **codex 真实生成打法+三版文案** → 冻结门店事实+**红线四硬门**(事实/合规/授权/可执行) → 8列分镜 MEDIA_PREP(停在付费审批边界) → 合成 MEDIA_PRODUCTION(授权MP4) → **交付门 G_DELIVERY_READY**(结算/授权链/C2/正式产物/无MOCK) → 预生成ZIP → O9 巡检+审计哈希链

账务侧：预占积分(成功才执行) → 任务执行 → **settle 扣 750 积分(成片成功才扣,失败不扣)** → ledger 流水(不可改删只能冲正) → 交付门禁校验(无凭证不交付) → 对账

## 账务铁律

- 整数「厘积分」，禁浮点数
- tasks + reservations + ledger + delivery 同库（SQLite WAL）
- 流水不可修改/删除，只能冲正
- 创建任务先预占，预占成功才执行
- 无账务凭证，发送层不交付
- 所有写接口幂等（防微信重试重复扣费）

## 小鹿「卡了/没反应」诊断（2026-08-21 实测）

用户说小鹿卡了时，**先分清「进程死了」vs「在跑长任务没回话」**，别一上来就重启：

1. **进程层**：`ps aux | grep gateway`（customer profile gateway 的 pid）+ `ss -tlnp | grep -E ':8080|:8090|:6185'`（billing/工厂/AstrBot 端口）——**进程活着 ≠ 没卡**
2. **消息层（关键）**：gateway.log 搜用户消息后的 `response ready`——有「Received raw message」但长时间没有对应 response ready = 卡在长任务循环（消息收到了，agent 还在上一轮任务里排队）
3. **agent.log**：`API call #N` 持续增长 + `tool process completed (180s)` 出现 = 在跑重活（codex 远程调用/长任务），不是死
4. **errors.log**：查 `Ambiguous skill name` / 420s/600s timeout / exit_code -15（SIGTERM）——skill 重名会让 agent 读不到规则，是「反复重写还不对」的常见根因（2026-08-21 实例：customer profile 双份 `director-thinking`，小鹿 skill_view 报 Ambiguous → 分镜没按导演思维写 → 用户追问 → 卡在重写循环）

**长任务无回执是根因**：小鹿跑 2 小时+ 的任务期间，用户连发消息全被排队、一条不回 → 用户感知「卡了」。按受理回执铁律，长任务（分析/出片/搜索等耗时任务）启动前必须先回「收到，预计 X 分钟」，否则闷头跑 = 用户必然追问。诊断后汇报口径：进程活着 + 卡在哪条消息 + 根因（长任务/重名/超时），给修复选项，不擅动小鹿生产代码。

### 🚨 会话级死循环：杀进程断不了，唯一打断是「用户质问」或「重启+清pending」（2026-08-24 实测，最痛教训）

小鹿可能卡死在一个 **agent 会话死循环**——agent loop 死咬同一个目标不放，反复执行同一类任务。**这是比「长任务」严重一级的状态，单杀进程根本断不了：**

**识别信号（errors.log / agent.log 混合判定）：**
- 同一会话号（如 `20260824_090247_e9a56069`）在 agent.log 里 `API call #N` 持续增长（几百轮不停）
- **反复生成同类重试脚本**：`for attempt in 1 2 3; do ... sleep 30`、`ox_self_fix_run.py`、换沙箱再跑——agent 每次回到 loop 就新写一个变体脚本
- 进程被杀后**自动换 PID/换沙箱目录重起**（`hermes_sandbox_oxiwwijf/script.py`、新 PID）
- 上下文 token 涨到 12 万+ 还在跑（正常会话早压缩/收尾了）

**致命教训（实测 2026-08-24）**：我远程连广州机杀了 **6 批**死磕进程（`kill`、`kill -9`、`pkill -f ox_native`），**每次都被会话自动重起**——它不是普通后台进程，是 gateway 内核里那个 agent 循环驱动的 tool 调用，杀掉子进程它回家 loop 再起新的。**手动杀进程这条路彻底走不通。**

**正确打断方式（两条都实测有效）：**
1. **用户直接质问**（最快）——boss 在飞书连发「你现在不是个传话的吗？」「为什么你一直卡在那？」，agent 注意力从死循环任务被拉回对话 → 立即转去响应新消息。**这就是为什么用户感知到「卡了」去问，反而能打断。**
2. **重启 gateway + 清 pending**（彻底）——`hermes gateway restart` 中断会话，但注意 `gateway/restart_loop_guard.py` 会在重启后恢复「restart-interrupted」会话自动重跑死磕任务（"next turn re-runs the offending"）。所以**重启前要归档/放弃那个死磕会话**，或接受它可能再跑一次。**此为大动作，不自作主张做，先问 boss。**

**汇报口径**：真实告知「这不是单个进程，是会话级死循环，杀 6 批都被重起；断法唯有用户质问（我已停当波进程）或重启+清pending（等你拍板）」——不继续无效杀进程（违背执行纪律：重复失败路径）。注意小鹿「卡了」时 boss 自己发消息质问往往就是解药，遥控侧先停当波进程 + 如实汇报即可，别越权重启生产 gateway。

## 跨机访问

```bash
# 新加坡机查广州机
timeout 15 ssh -p 2222 -o ConnectTimeout=8 -o StrictHostKeyChecking=no ubuntu@127.0.0.1 "<命令>"
```

关键文件：`/home/ubuntu/ai-video-factory/README.md`（12步演示路径）、`app/orchestrator.py`（状态机：WAITING_C1/WAITING_C2/INTERNAL_REVIEW/RUNNING 等）、`app/gates.py`（门禁 G_DELIVERY_READY、COPY_HARD_GATES_ALLOWED）、`/home/ubuntu/billing-system/ARCHITECTURE.md`。

## 广州机 execute-api（1889）运维速查（2026-08-22 实测）

`execute-api.service` = 视频段2执行服务（Seedance 出片/记账），端口 1889。**重启不需要 sudo**——execute-api 不在 sudoers 免密列表（只有 helper-api/caddy/billing 免密），但它是 `User=ubuntu` + `Restart=always`，同属主 `kill -TERM <PID>` → systemd 3 秒自动拉起新代码。验证：`systemctl show execute-api -p MainPID -p ActiveEnterTimestamp` 看 PID/启动时间变化。

- **软模式 drop-in**：`/etc/systemd/system/execute-api.service.d/10-gate-soft.conf` 写死 `HERMES_GATE_SOFT=1`——出片走审计放行不拦。切硬模式 = 摘掉/改这个 drop-in（需先给 sudoers 加 execute-api 免密或人工重启）
- **sudoers NOPASSWD（广州机现状）**：只有 hermes-egress-get、helper-api restart、caddy restart、billing restart——execute-api 不在，别傻等 `sudo systemctl restart execute-api` 要密码
- **部署纪律**：部署前 `md5sum` 核对广州生产 = inputs 基线（防被别人改过）→ 备份 `.bak-YYYYMMDD-predeploy` → scp → 远端 py_compile + md5sum 对比 staging → 重启 → 查新 PID/软模式 env/1889 端口
- **gate 链 + 出片记账细节**：见 `references/execute-api-gate-accounting.md`

## 可视化交付（流程图→图片）

用户要「把 XX 流程用图片做出来」时：

1. **先取真实资料**：ssh 广州机读 README/ARCHITECTURE/代码状态机，禁止脑补流程。图示内容必须能追溯到源文件。
2. **用 `architecture-diagram` skill** 做 dark 主题 HTML+SVG（泳道=角色边界：客户侧 cyan / 生产 emerald / 账务 violet / 门禁 rose / 扣费·远程执行 amber）。中文字体 fallback：`'JetBrains Mono', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', monospace`。
3. **截图转 PNG**：playwright + 本机已装 chromium。版本不匹配时（报缺 chromium_headless_shell-1234 之类）用 `executable_path` 指已存在的二进制（如 `/home/ubuntu/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome`），不要 `playwright install` 下新浏览器。
4. **交付前 vision 自检**：`vision_analyze` 查文字重叠/箭头压字/布局错位，通过才发 MEDIA。
5. 产物放 `/home/ubuntu/workflow/outputs/`，发图本体（MEDIA:路径），不发路径文本。

## server.py 架构基线与 P0 止血（2026-09-07 实测）

广州机 `server.py` = 1772 行 Flask 单文件，直接跑（无 Gunicorn），监听 8091。外部调用（GLM/火山生图/DashScope）全同步无超时。SQLite + Redis 已装。P0 止血 5 步（限流→前端退避→超时+脱敏→监控→Gunicorn workers=1）3-4 人日。完整路线图 4 段 10 周。

详见 `references/server-py-architecture-baseline-20260907.md`（当前状态/外部调用清单/P0 五步/改造路线图/环境变量/端口对照）。

## 详细参考

- `references/guangzhou-workflow.md` — 12 步流程完整细节、代码锚点、状态机节点
- `references/server-py-architecture-baseline-20260907.md` — server.py 架构基线与 P0 止血计划
