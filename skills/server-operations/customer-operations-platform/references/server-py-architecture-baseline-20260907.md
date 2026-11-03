# 广州机 server.py 架构基线与 P0 止血计划

> 2026-09-07 实测快照。后续改造以此为准。

## 当前状态（P0 前）

| 项目 | 现状 |
|:-----|:-----|
| server.py | 1772 行单文件 Flask，直接跑（无 Gunicorn），监听 `127.0.0.1:8091` |
| 数据库 | SQLite（`/home/ubuntu/data/xiaolu_users.db`，188K），表：users/orders/transactions/feedback/user_tokens/rate_limits/chat_messages |
| Redis | 已安装已运行（`redis-server.service` active，PONG 确认）|
| Nginx | 无 |
| Celery | 无 |
| PostgreSQL | 无 |
| Gunicorn | 无 |
| Python | `/usr/bin/python3` 3.12.3 |
| 规格 | 4 核 3.6G RAM 59G 磁盘 |
| 内存 | 3723MB total，1354MB used，132MB free，2368MB available |
| Swap | 1987MB total，316MB used |

## 外部调用（全同步，在 server.py 内）

| 调用 | 方式 | 代码行 |
|:-----|:-----|:-------|
| GLM | `urllib.request` | 1149, 1155-1156, 1228, 1238-1241, 1404-1409 |
| 火山生图 | `urllib.request` | 1109, 1113, 1118 |
| DashScope 视频 | `subprocess.run` → `/home/ubuntu/.hermes/scripts/dashscope_video.py` | 1278, 1285, 1292 |

**风险**：任一外部调用超时/挂起 = Flask worker 被占满 = 全站卡死。当前无超时、无限流、无退避。

## 关键环境变量

- `XIAOLU_DB_PATH` — SQLite 路径
- `XIAOLU_UPLOAD_ROOT` / `XIAOLU_PUBLIC_ROOT` — 上传/公开目录
- `XIAOLU_PUBLIC_BASE_URL`（默认 `http://<GZ_HOST>`）
- `XIAOLU_GATEWAY_SEND` / `XIAOLU_FEISHU_HOME_CHAT_ID`（默认 `<ADMIN_CHAT_ID>`）
- `XIAOLU_ORDER_UPDATE_TOKEN_FILE`
- `XIAOLU_TEST_MODE`
- `CUSTOMER_ENV = Path("/home/ubuntu/.hermes/profiles/customer/.env")`
- `HERMES_CONFIG = Path("/home/ubuntu/.hermes/config.yaml")`
- `TOKEN_TTL` / `PBKDF2_ITERATIONS = 600_000`

## 端口对照（server.py 8091 ≠ ai-video-factory 8090）

| 端口 | 组件 | 说明 |
|:-----|:-----|:-----|
| 8090 | ai-video-factory | 网页工作流（`/access` 客户入口） |
| 8091 | server.py | Flask 单文件，客户运营平台后端（本文件对象）|
| 8080 | billing | FastAPI 账务 |
| 1889 | execute-api | 视频段2执行服务（Seedance 出片/记账）|

## P0 止血计划（5 步，3-4 人日，按顺序执行）

来自最终版架构方案 §9.1。止血 = 防止单点故障拖垮全站，不做架构升级。

1. **提交端点限流 + 输入限制**：per-user per-minute 提交上限、并发/排队任务上限、输入长度/大小限制；429/503 + `Retry-After` 头
2. **前端退避**：poll 抖动 + 指数退避 + 页面隐藏降频 + 遵守 `Retry-After` + 请求中禁用提交按钮
3. **外部调用全加超时 + 日志脱敏**：connect/read/total timeout；日志不记录完整 prompt/base64/图片视频响应体
4. **基础监控**：内存/swap/磁盘、端点延迟、上游延迟/错误率、429 计数
5. **Gunicorn 托管**：`workers=1, threads=4`——workers=1 是硬要求（当前 GLM 限流是进程内信号量，workers=2 会翻倍有效并发 ≈ 1.2GB OOM 风险）

## 改造路线图（4 段，10 周，32-50 人日）

| 段 | 周期 | 人日 | 范围 |
|:---|:-----|:-----|:-----|
| ① 止血版 | 1 周 | 3-4 后端 + 0.5-1 前端 + 1 运维 | P0 五步 |
| ② 工具任务版 | 3 周 | 8-12 后端 + 2-3 前端 + 2-3 运维 | 异步 API + Celery + PostgreSQL |
| ③ 工作流版 | 4 周 | 9-14 后端 + 2-4 前端 + 1-2 运维 | 17 节点状态机 + 完整工作流 |
| ④ 放量版 | 2 周 | 1-2 后端 + 0.5-1 前端 + 2-3 运维 | 水平扩展 + 监控告警 |

## SSH 访问

```bash
# 新加坡机 → 广州机（反向隧道）
timeout 15 ssh -p 2222 -o ConnectTimeout=8 -o StrictHostKeyChecking=no ubuntu@127.0.0.1 "<命令>"
```

## 文件位置（改造时参考）

- 生产代码：`/home/ubuntu/public/app/server.py`（广州机）
- 前端页面：`/home/ubuntu/public/app/index.html`（160 行）
- 架构方案：`/tmp/arch_plan_final.md`（742 行，12 章节，新加坡机）
- P0 项目目录：`/home/ubuntu/workflow/projects/gz-p0-hemostasis/`

## 注意

- server.py 里的 17 节点工作流是飞书会话内连续跑（不是独立调度器），DB 只存状态不做调度
- 三个确认停点：节点8文案 / 节点12出片 / 最终成品
- GLM 在飞书会话里连续跑 17 节点，运营助手网页提交→server.py 建订单发飞书→GLM 飞书会话跑
