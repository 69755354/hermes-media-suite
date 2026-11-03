# Hermes Media Suite

媒体自动化系统源码合集。仓库包含三套可独立运行的子系统，以及配套的中文方法论技能库。

> 本仓库为**私有仓库**，包含客户项目与生产运维代码，未经授权不得公开或外传。

## 目录结构

```
.
├── publish-control/      自动发布：服务端控制面 + 飞书机器人 + Windows 客户端代理
├── video-factory/        客户运营与内容制作工作流平台（FastAPI）
├── video-team/           片级看板与阶段引擎（CLI）
├── skills/               中文方法论与提示词规则（Markdown 技能库）
└── docs/                 架构说明
```

---

## 1. publish-control · 自动发布

把「飞书里说一句话」变成「抖音创作者中心里真的发出去一条视频」，全链路可留证、可冻结、可人工接管。

### 组成

| 模块 | 路径 | 职责 |
|---|---|---|
| 控制面 | `server.py` / `rpc.py` | 单文件标准库 HTTP 服务（默认 `127.0.0.1:18977`）+ SQLite：客户注册、命令队列、回执、素材快照 |
| 飞书机器人 | `feishu_publish_bot/bot.py` | 长连接收私聊 / 群 @ 消息，解析指令、路由到对应客户、回话；含排期线程 |
| 客户端代理 | `client/agent/winport/` | 跑在客户 Windows 机上的 agent：轮询命令、唤起真实 Chrome、执行 prepare / dry-run / fill / approved_publish / collect |
| 运维脚本 | `scripts/`、`remote_pc.py` | 部署校验、不变量检查、设备绑定迁移、远程读写文件 |
| 运维文档 | `docs/OPERATIONS.md` | 现场踩坑与处置口径（必读） |

### 发布链路

```
飞书消息
  → bot 解析（客户 / 素材 / 标题 / 话题 / 星图任务 / 排期）
  → 控制面落命令（command_id 幂等）
  → 客户机 agentpoll 领取
  → winport CLI
       prepare              选素材、算指纹、生成计划
       dry-run              校验时间窗 / 素材 / 授权，签发确认令牌
       fill                 真实 Chrome 上传 + 填表，停在发布按钮前（不提交）
       approved_publish     校验签名回执后点击发布（需 --allow-submit）
       collect              回读作品数据
  → 证据落盘（截图 / HTML / 请求记录）+ 回执
```

### 关键安全机制

- **三级开关**：`fill`（只填表）→ `approved_publish`（需 Ed25519 签名回执）→ `--allow-submit`（显式点击）。缺一不发。
- **通道冻结**：验证码、风控、登录失效、结果未知都会写入 `run/publish_holds.json`；冻结后新任务直接被拦，只能人工核实后解除。
- **幂等账本**：`run/stage2-ledger.json` 以「素材指纹 + 账号 + 时间窗」为键，状态 `RESERVED → SUBMIT_INTENT → CONSUMED`，杜绝同一素材重复发布。
- **证据优先**：成功必须绑定平台作品号或页面级成功证据；拿不到就记 UNKNOWN，不猜。
- **启动链完整性**：`MANIFEST.json` 逐文件校验，改代码必须同步哈希，否则拒绝执行。

### 本地启动（控制面）

```bash
cd publish-control
export CONTROL_DB=./control.db
export CONTROL_PORT=18977
export CONTROL_ADMIN_TOKEN='<管理令牌>'
export CONTROL_INBOUND_TOKEN='<入站令牌>'
python3 server.py
```

### 本地启动（飞书机器人）

```bash
cd publish-control/feishu_publish_bot
pip install lark-oapi
# 在 .env 中配置飞书应用凭据与控制面地址（见 bot.py 顶部说明）
python3 bot.py
```

### 客户端要求

- Windows 10/11、Chrome、Python 3.11
- 需要 `playwright`：通过 CDP 附着到客户本机 Chrome，不另建无痕环境
- 程序目录需包含 `agent/`（对应本仓库 `client/agent`）与 `MANIFEST.json`

---

## 2. video-factory · 制作工作流平台

面向客户的积分制制作平台：客户用积分配额提交任务，平台排队执行、质检、交付。

- Web：FastAPI + Jinja2 SSR（`app/main.py`、`web/`）
- 任务：SQLite lease 队列 + durable worker，长任务 40 秒续租
- 媒体：调用系统音视频工具完成转码与拼接，全机共享并发槽
- 计费：对接外部积分台账（`app/billing.py`），未扣费不交付
- 审核：内部审核台独立口令（`XG_FACTORY_OPS_PASSWORD`）

### 启动

```bash
cd video-factory
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

export XG_FACTORY_OPS_PASSWORD='<内部审核口令>'
export XG_FACTORY_SESSION_SECRET='<至少32字符随机串>'
export XG_FACTORY_BILLING_BASE_URL='http://127.0.0.1:18080'
export XG_FACTORY_HOST=127.0.0.1
export XG_FACTORY_PORT=8090
python3 -m app
```

详细说明见 `video-factory/README.md`。

---

## 3. video-team · 片级看板

一条片子一条记录，九个阶段顺序推进，上游不 `done`，下游不能 `start`；每次 `done` 自动生成交接单。

```bash
cd video-team
python3 team.py add "片名" --batch B01 --account 一号
python3 team.py list
python3 team.py next
python3 team.py start V001
python3 team.py done V001 --artifact /abs/path --note "说明"
```

详细说明见 `video-team/README.md`、`video-team/ARCHITECTURE.md`。

---

## 4. skills · 方法论技能库

中文技能库（Markdown），沉淀了可复用的制作规则与方法，覆盖从前期策划到后期复盘的主要环节。

每个目录一份 `SKILL.md`，可被支持 skill 机制的 Agent 直接加载，也可作为人工规范阅读。

---

## 脱敏说明

本仓库**不含**以下内容，运行前需自行配置：

- 任何 API Key、飞书 App Secret、管理员令牌（`.env` 已在 `.gitignore`）
- 生产数据库（`control.db`）、素材、成片、运行日志、证据截图
- 客户机器码、授权文件、设备绑定数据

代码中的路径与客户名均为生产环境原样，部署到新环境时需按实际调整。

## 许可

内部项目，保留所有权利。未获授权不得复制、分发或商用。
