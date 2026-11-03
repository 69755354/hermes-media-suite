# 客户运营工作流可视化平台 P1
> 执行者：codex

单机中文 SSR/API 应用。客户用广州积分客户编号验证余额后进入，不设客户账号/口令；项目创建时在广州唯一积分台账建任务，生成成功后结算，未扣费不能交付。内部审核员仍使用独立口令进入审核台。

## 运行要求

- Python 3.11+
- `codex` CLI（免费 reason 任务）
- `ffmpeg`、`ffprobe`（免费 compose 与技术质检）
- Linux（项目门禁原子链使用 `flock`）

安装依赖：

```bash
cd /home/ubuntu/workflow/projects/ai-video-factory
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

设置环境变量并启动：

```bash
export XG_FACTORY_OPS_PASSWORD='替换为内部审核强口令'
export XG_FACTORY_SESSION_SECRET='至少32字符的随机会话签名密钥'
export XG_FACTORY_BILLING_BASE_URL='http://127.0.0.1:18080'
# 二选一：短期 operator token，或由客户端自动换取24小时 token 的管理员口令
export XG_FACTORY_BILLING_AUTH_TOKEN='广州 billing operator token'
# export XG_FACTORY_BILLING_ADMIN_PASSWORD='广州 billing 管理员口令'
export XG_FACTORY_HOST='127.0.0.1'
export XG_FACTORY_PORT='8090'
export XG_FACTORY_WEB_WORKERS='4'
export XG_FACTORY_MEDIA_CONCURRENCY='2'
export XG_FACTORY_REQUEST_THREADS='48'
export XG_FACTORY_REMOTE_POLL_BATCH='20'
export PAID_API_ENABLED='false'
python3 -m app
```

默认数据库是 `runtime/platform.sqlite3`，项目文件在 `runtime/projects/`。可分别通过 `XG_FACTORY_DB`、`XG_FACTORY_PROJECTS_DIR` 覆盖。生产部署应在反向代理后启用 TLS，并设置 `XG_FACTORY_COOKIE_SECURE=1`。

4 核单机默认启动 4 个 Uvicorn 进程，每个进程各有一个 durable worker；任务由 SQLite lease 原子领取。长任务每 40 秒续租（默认租约 120 秒），每 30 秒回收过期任务。SQLite 默认启用 WAL、5 秒 busy timeout 与 NORMAL 同步；ffmpeg 在全机共享 2 个并发槽且每任务限 1 核。可用 `XG_FACTORY_WORKER_LEASE_SECONDS`、`XG_FACTORY_WORKER_RECONCILE_SECONDS`、`XG_FACTORY_SQLITE_BUSY_TIMEOUT_MS`、`XG_FACTORY_MEDIA_CONCURRENCY`、`XG_FACTORY_REQUEST_THREADS` 和 `XG_FACTORY_REMOTE_POLL_BATCH` 调整。该模式只适用于所有进程共享同一本地数据库和锁目录的单机部署；扩展到多主机前必须迁移到 PostgreSQL/Redis 队列。

广州 `8080` 只监听回环地址。新加坡机通过已有 `127.0.0.1:2222` SSH 反隧建立本地转发：

```bash
mkdir -p ~/.config/systemd/user
cp deploy/ai-video-factory-billing-tunnel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ai-video-factory-billing-tunnel.service
curl -fsS http://127.0.0.1:18080/openapi.json >/dev/null
```

访问地址：

- 客户端积分入口：`http://127.0.0.1:8090/access`
- 内部审核台与每日巡检：`http://127.0.0.1:8090/ops/login`

自动发布被编译期常量关闭，界面没有发布按钮。付费调用默认关闭；即使设置环境变量也只形成内部条件之一，接口不会直接放行单次付费请求。

## 火锅店演示路径

1. 客户输入天行者分配的数值客户编号；余额大于 0 才能进入并新建短视频项目。
2. 分别上传菜单、价目、门头、菜品、服务过程五类证据素材，可另传一条授权 MP4 用于免费合成。
3. 内部登录，在 O1 对项目授权执行“先检查依据”，取得 5 分钟短效 token 后再放行。
4. 通过内部接口导入不少于 3 条已核验洞察，然后逐步执行；增长打法和三版文案由本机 `codex exec` 真实生成。
5. 冻结门店事实；文案进入全文件红线扫描及事实、合规、授权、可执行四硬门。
6. 客户在 C1 明确选择“确认 / 修改 / 暂停”，没有超时自动通过。
7. 生成 8 列分镜并准备素材，流程到 `MEDIA_PREP` 后停在付费审批边界。
8. 内部选择已授权 MP4 执行合成；成片成功后调用广州 `/tasks/{id}/settle` 扣 750 积分，失败不扣。
9. 客户在 C2 明确确认成片。
10. 交付门同时断言广州任务已结算、授权链、C2、正式产物和无 MOCK，随后预生成 ZIP。
11. 客户下载 ZIP 前再次调用广州交付门禁；通过后才返回文件。
12. O9 查看队列、孤儿任务、待审核、磁盘与备份状态；审计接口验证哈希链。

可用验收脚本一键走完整路径：

```bash
# 完整验收：真实 codex exec + ffmpeg/ffprobe
python3 scripts/accept_p1_hotpot.py

# 快速回归：仅 reason 使用明确的确定性测试适配器，媒体仍由 ffmpeg 真合成
python3 scripts/accept_p1_hotpot.py --fast
```

脚本使用临时运行目录和隔离假账本，不污染广州正式台账；`--runtime-dir /绝对路径` 可保留演示结果。广州真实连通性应单独通过 SSH 转发和只读 OpenAPI/余额查询验证。

## 测试

```bash
python3 -m unittest -v tests.test_billing_alignment tests.test_p1_platform tests.test_factory_prefix
python3 -m compileall -q app scripts tests
```

测试覆盖 0 积分拦截、余额加 100 透支额预检、项目建任务、生成后只扣一次、未结算禁止交付、广州交付 token 消费，以及原有的一项目一 piece、项目创建幂等、跨客户 404 隔离、D_* 白名单重渲染、门禁、真合成、ZIP 下载和审计哈希链。

## 关键边界

- 不修改冻结门禁脚本或工作流注册表；应用只通过适配层调用现有脚本。
- 确认脚本只收到固定枚举 `可以`，客户原文不会作为其参数。
- `CONFIRM.json.skip_mode=true` 会被适配层直接拦截。
- D_* 是按冻结目录白名单重新渲染的 HTML，不复制内部文件；内部路径、执行器名、节点号和轨名触发拒绝。
- 正式 D_*、正式下载 token 和交付 ZIP 都拒绝 MOCK 产物。
- 首版洞察只允许人工导入，自动采集未接入主链。
- SQLite lease 任务在启动时 reconcile；取消状态为终态，旧 worker 不能复活任务。
- 平台只接受 billing 的数值 `customer_id`。当前广州 API 没有按手机号或 `external_id` 查询客户的接口，因此不能把任意手机号直接当数据库客户主键。
