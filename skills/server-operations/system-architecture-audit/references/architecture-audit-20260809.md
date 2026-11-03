# 系统架构审计完整报告（2026-08-09，codex gpt-5.6-sol 执行）

范围：Hermes gateway + 微信通道 + 18节点工作流 + 模型分工 + 服务器资源（新加坡机 <SG_HOST>，2核/1.9GB）。

## 核心结论

| 项目 | 状态 | 判断 |
|---|---|---|
| Hermes gateway | RSS ~321MiB，峰值 1.2GiB | 2GiB 主机危险区 |
| Codex 单任务 | ~370MiB（Codex+Node+MCP） | 两个并发重任务→swap/OOM |
| helper_api 1888 | root、单线程、无 systemd、绑 0.0.0.0 | 严重安全+可用性问题 |
| execute_api 1889 | 无鉴权、单线程、绑 0.0.0.0 | 立即停用公网入口 |
| ARK 本地代理 18888 | 仅绑 127.0.0.1、ThreadingHTTPServer | 绑定合理但无 systemd |
| systemd | Restart=always 但无 MemoryHigh/CPU 限制 | 无限重启，无法防单任务拖垮 |
| swap | 1.9GiB 已用 ~104MiB | 已出现内存压力 |
| 磁盘 | 40GiB 34% 用 | 充足但媒体无 TTL/配额 |

## 高危漏洞（P0）

1. **1889 无鉴权**——调用者可制造 ARK 账单、提交任意本地文件路径并外发。立即停公网。
2. **1888 root 运行 + 密钥写死在源码**（token=9a52a11f..., AK <ARK_API_KEY>）。task_id 未做路径约束，`../` 可逃逸临时目录写入 root 可写位置。
3. **relay 是开放代理**——接收任意 url 转发 Authorization/body/响应，SSRF 风险。应拆固定路由 `/wechat-cdn/upload`、`/wechat-cdn/download`、`/ark/*`、`/tos/fetch` + 域名 allowlist + DNS 解析后检查 IP（禁私网/环回/元数据地址）+ HMAC 时间戳签名 + 方法白名单 + 大小限制。
4. **SSH 权限过宽**——PermitRootLogin yes、PasswordAuthentication yes、AllowTcpForwarding 无限制。应建专用 relay-tunnel 用户（仅远程转发+监听 127.0.0.1:8899，禁 shell/PTY/agent forwarding/X11），关 root/密码登录。
5. **微信 token 文件权限不统一**——有 0664 凭据文件。统一 0700 目录/0600 文件，现有 bot token 重新登录轮换。

## 微信通道脆弱点

- **8899 隧道是媒体+ARK 共同单点**：断开后图片上传/下载、ARK 视觉、Seedream、Seedance 全挂。广州必须 autossh/systemd：ServerAliveInterval=15、ServerAliveCountMax=3、ExitOnForwardFailure=yes、Restart=always、RestartSec=3。新加坡每 15-30s 检查 8899 TCP + /health + 真实转发探针，三次失败→DEGRADED_MEDIA 状态，文字回复「媒体已排队」恢复后补发。
- **token 过期无恢复闭环**：weixin.py 收到 -14 后休眠 600s 重试，不自动重扫码。应区分 context_token 失效（清单会话 token 无 token 重发）/ bot token 失效（AUTH_REQUIRED+外部报警，管理员扫码热加载）/ 网络错误（指数退避，不重登）。
- **无媒体发件箱**：隧道断时媒体直接丢。应建 durable media outbox + 入站重试队列，通道恢复后自动补发。
- **媒体处理放大内存**：_send_file 同时持有明文+AES密文+HTTP上传缓冲，100MiB 视频→200MiB+ 内存。改分块加密/下载、落临时文件后上传；大视频优先发受控下载链接。

## 配置不合理

- `busy_input_mode: interrupt`——新消息中断正在执行的付费任务（Seedance/codex/ffmpeg），任务还在跑 Hermes 已放弃等待。改普通对话 queue、/cancel 显式中断、付费任务进后台队列。
- 任务预算过大：agent.max_turns=60、max_tool_calls=50、delegation.max_iterations=50。按任务类型设：普通问答 8-12、内容分析 15-20、工作流由状态机控制、codex 全局并发固定 1。
- 模型两套真相：顶层 deepseek-v4-flash，provider 内部又配 deepseek-v4-pro 显示 Pro。建单一模型注册表（逻辑角色/实际 model ID/provider/effort/超时/单价/fallback/生效日期）。
- 长任务通知全关（background_process_notifications/long_running_notifications=false）→ 28-56 分钟无进度回执，用户重复发消息又触发 interrupt。60s 发一次状态，节点完成/失败/需确认时通知。
- nemo_relay 缺失每次启动报错；ARK 辅助视觉 401 单次失败等 242s。不用的 relay instrumentation 关掉；ARK 代理恢复 fallback 链前先做真实图片回归测试。
- weixin.py relay 补丁未提交 git、pre_update_backup=false——升级会覆盖补丁。提交独立分支 + 固定 commit 部署 + 失败自动回滚。

## 工作流（三套实现漂移）

WORKFLOW_SPEC.yaml 18 节点 / execute_api.py 节点5-13 / helper_api.py 另一套——编号、模型、门禁、ARK 路由全不一致。1889 绕过确认门/数据门/初审/终审。结论：SPEC 为唯一流程定义，Python 服务只执行编译后的 DAG。

## 机器耗时瓶颈排序

1. Seedance 六镜串行 12-24 分钟（→2并发压测→3并发，4-8 分钟）
2. 高质量生图单张 2-4 分钟（→标准预览1张确认→high 并发终稿）
3. Codex 多次冷启动重复加载 AGENTS/skills/wiki/MCP（→每项目复用 session、codex exec resume；静态 wiki 摘要包+哈希缓存）
4. 节点5/10/11 连续 LLM 调用及重复质检（→结构检查代码化，语义保真一次批量 judge）
5. ffmpeg（一次 filter_complex + preset=veryfast，只省 5-30s，不要优先动）
6. relay 网络延迟（高可用风险不是耗时主因）

## DAG 目标

0 → [1用户分析 ∥ 2爆款拆解] → 3选题 → 4文案/初审 → 确认 → [5分镜 ∥ 6人设] → [8生图 ∥ 10提示词/质检 ∥ TTS/BGM/字幕] → 12六镜并发 → 13合成 → [14技术质检 ∥ 15终审] → 交付。16发布/17复盘移出单条关键路径（16客户外部动作、17发布7天后）。

## 服务器资源

- 1.9GiB 对单任务勉强、并发不够。最低生产规格 4GiB/2核（ffmpeg 单并发+媒体生成外部）；媒体留本机需 8GiB/4核；推荐新加坡只做控制面，广州做 relay/下载/ffmpeg/媒体缓存。
- 2 核对控制面足够（gateway/long poll/API提交轮询/轻量 ffmpeg）；多路 H.264 转码不够。
- 磁盘 40GiB：70% 告警、85% 停新任务；临时素材 72h 清理，成品按项目归档。
- gateway/Codex worker/ffmpeg worker 分别设 cgroup 限制。

## 优化路线图

- **P0 安全稳定（1-2天）**：轮换密钥删硬编码、1888/1889 绑 127.0.0.1+停 1889 公网、服务 systemd 化非 root、广州 autossh+新加坡 watchdog、专用 tunnel 用户、codex 并发锁 1+ffmpeg 锁 1（防 OOM）、关 nemo_relay 修 ARK 视觉 401。
- **P1 提速（2-3天）**：Seedance 2→3 并发、节点合并并行（1/2、5/6、8/10、14/15）、codex session 复用、生图标准预览→high 终稿、durable media outbox、节点级 p50/p95 埋点（先采集 20 条任务 p50/p95 再调并发）。
- **P2 资源**：新加坡升 4GiB；ffmpeg/下载/媒体缓存迁广州；relay 加 allowlist+HMAC+双实例；weixin relay 补丁提交固定 commit。
