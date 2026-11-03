---
name: media-pipeline-hardening
description: 本地媒体服务安全加固与提速模板(1888/1889)。触发:端口绑定/systemd化/并发锁/OOM/Job API。
---

# 媒体流水线安全加固与提速（2026-08-09 新加坡机实装）

Hermes 媒体服务（helper-api 1888 / execute-api 1889 / ark-local-proxy 18888）的加固与提速模式。基于 codex 架构审计（P0/P1 清单）在 2GB 内存机上落地。

## P0 安全加固（先做这些）

### 1. 密钥不进源码
- 源码硬编码的 AK/token 全部移出，改从 `.env`（0600）或独立密钥文件读
- 例：`/opt/helper_api.py` 的 `AK = ""` + 启动时扫 `.env` 的 `ARK_API_KEY`；token 存 `~/.hermes/helper_auth_token`（0600）
- 关键坑：`config.yaml` 是安全敏感文件，agent 工具层拒绝写入——用 `hermes config set <path> <value>` 或 sudo 直改
- `hermes config set auxiliary.display.busy_input_mode queue` 改的是顶层 217 行，**display 段 68 行要单独 `config set display.busy_input_mode` 或 auxiliary 前缀**——改完 grep 确认两处

### 2. 端口只绑 127.0.0.1
- `HTTPServer(("0.0.0.0", port))` → `("127.0.0.1", port)`（三个服务全改）
- 启用 UFW：`ufw default deny incoming && ufw allow 22/80/443 && ufw --force enable`
- 验证：`ss -tlnp | grep 1888` 应显示 `127.0.0.1:1888`

### 3. systemd 化 + 非 root + 内存限制
```ini
[Service]
Type=simple
User=ubuntu
Group=ubuntu
ExecStart=/usr/bin/python3 /opt/helper_api.py
Restart=always
RestartSec=3
MemoryHigh=600M
MemoryMax=800M
```
- 三个服务各自独立单元；`systemctl enable --now` 开机自启
- 必须非 root（除非代码还在读 /root 文件——那种要改代码不是改 User）
- 旧 nohup 进程要先 `pkill` 干净，否则 systemd 起不来（Address already in use）

### 4. 输入校验 + 状态码
- `task_id` 白名单 `[A-Za-z0-9_-]` 截 64 位（防 `../` 路径逃逸写任意位置）
- 请求体上限 20MB → 超限 413
- 业务失败返回 4xx/5xx（compliance_fail→422，unknown path→404），不再全 200
- **单线程 HTTPServer 会卡死**：没有 do_GET 时一个 GET 请求就永久占住线程，后续全排队（Recv-Q 堆积）→ 必须 `ThreadingHTTPServer` + do_GET 快速返回 `{"status":"alive"}`

## 并发铁律（2GB 内存机）

- **重型任务锁 1**：codex 全局 `flock /tmp/codex.lock -c "codex exec ..."`；ffmpeg 全局 `flock /tmp/ffmpeg.lock -c "ffmpeg ..."`
- **等待型并行保留**：Seedance 2 并发（`ThreadPoolExecutor(max_workers=2)`，纯 API 等待不占内存）、节点 5/6/9 并行（3 个 API 调用线程）
- 不升内存时：绝不并行两个 codex 重任务（370MB×2 + Hermes 1.2GB 峰值 = OOM）

## Job API 模式（同步 → 异步持久化）

- `/job` 提交立即返回 job_id（uuid hex16），后台线程跑 pipeline，进度落盘 `/tmp/execute_api/jobs/<id>/state.json`
- `/job/status` 查进度；`/job/cancel` 取消
- 线程 daemon=True，数据落盘防进程重启丢失
- 大任务（28-56 分钟视频）必须走 Job API，不能同步阻塞 HTTP

## 无 sudo 免密时的 systemd 服务重启（2026-08-22 广州机实测）

**场景**：服务不在 sudoers NOPASSWD 列表，重启需要 root 但拿不到密码（广州 execute-api 只免了 helper-api/caddy/billing，root SSH 不通）。

**前提**：unit `User=<当前用户>` + `Restart=always` + `RestartSec=N`。

**做法**：
1. 先 `sudo -l` 查清 NOPASSWD 清单——别假设能 restart（`sudo -n true` 失败 = 没免密）
2. `systemctl show <unit> -p MainPID -p Restart` 确认参数
3. `journalctl -u <unit> --since '10 min ago'` 确认没有正在跑的任务再动
4. `kill -TERM <MainPID>`（属主相同，不需提权）→ systemd 按 Restart=always 自动拉起
5. 验证：`systemctl show <unit> -p MainPID -p ActiveEnterTimestamp` 换新 PID、进程 env（`cat /proc/<PID>/environ | tr '\0' '\n' | grep <KEY>`）确认 drop-in 环境变量保留、端口健康

**边界**：本技巧只能「重启」，改 `/etc/systemd/system/<unit>.service.d/*.conf`（root:root 644）仍需 root——改配置前先确认提权路径，或请用户手动跑一条命令。

## execute-api 门禁软硬模式切换（2026-08-22 广州机实测，切前必读）

execute-api（1889）有四道闸：闸0 project_dir fail-closed → 闸1 confirm_gate 渲染确认 → 闸2 workflow_gate G_RENDER_READY（要求上游 G_CREATIVE_READY ALLOWED，19 节点主链）→ 闸3 billing 余额预检（rc==2 拦，其余容灾放行）。软模式（`HERMES_GATE_SOFT=1`，systemd drop-in 写死）下 `_verdict()` 把一切 BLOCK 转 SOFT_PASS 审计放行。

**切硬模式（摘 HERMES_GATE_SOFT）前必查三步，否则正常业务全断：**
1. **审计日志分布**：`grep -oE 'SOFT_PASS entry=[^ ]+' /home/ubuntu/.hermes/guard/gate_chain_audit.log | sort | uniq -c`——SOFT_PASS 若全是同一端点/同一原因（如缺 project_dir），说明正常业务长期靠软模式放行，切硬 = 全拦
2. **请求侧是否漏参**：小鹿调用脚本 body 常缺 `project_dir`（38 条 SOFT_PASS 同因实证）——软模式掩盖了请求侧漏传，切硬前必须先修调用侧
3. **补参后闸2是否真能过**：`python3 /home/ubuntu/.hermes/scripts/workflow_gate.py check <project_dir> G_RENDER_READY` 实跑——轻量直调路径（确认剧本后直接提交）没有 19 节点主链，`G_CREATIVE_READY 未获批` 照样 BLOCK

**结论**：软模式是迁移期观察手段，不是门禁已生效。切硬前先统计并清零正常业务的 SOFT_PASS 原因，或做分层门禁（轻量直调只查确认+权限）。「代码已部署」≠「硬模式已启用」——改 drop-in 需要 root，无 root 通道时别误判。

## chrome-cdp 203/EXEC 崩溃循环（2026-08-22 广州机实测）

`systemctl --user status chrome-cdp` 显示 `activating (auto-restart) (Result: exit-code)` + `status=203/EXEC` = ExecStart 二进制不存在（agent-browser 缓存的 chrome 丢失），systemd 每 5 秒空转重启耗资源。
修复：`sed -i 's|ExecStart=<旧路径>|ExecStart=/usr/bin/chromium-browser|' <unit>` + `systemctl --user daemon-reload && systemctl --user restart chrome-cdp`，验证 `curl http://127.0.0.1:9222/json/version`。
排查特征：203/EXEC 优先查 ExecStart 路径、文件存在性和执行权限，别让服务无限重启空转。

## SSH 加固（OpenSSH 坑）

- **OpenSSH 配置「第一个获得的值生效」**（不是最后一个）——cloud-init 的 `50-cloud-init.conf` 在 Include 顺序里排前面，它写 `PasswordAuthentication yes` 会盖掉后面所有 no。改 drop-in 无效，必须改最早读到的文件
- 验证生效：`sudo sshd -T | grep passwordauthentication`（不看配置文件，看实际生效值）
- 加固项：`PermitRootLogin no` + `PasswordAuthentication no` + 保留 ubuntu 用户 PubkeyAuthentication（管理通道不能断）
- 专用 tunnel 用户（`relay-tunnel`）：`Match User relay-tunnel` + `ForceCommand nologin` + `PermitListen 8899`——附加层，替代不了 ubuntu 管理用户

## 相关文件
- 审计产出：`/tmp/arch_audit2.log`（19 项 P0/P1/P2 清单）
- DAG 定义：`~/workflow/wiki/spec/workflow_dag.py`（SPEC 唯一真相 + execute_api 函数映射 + 并行组 + 关键路径）
- outbox 模块：`~/.hermes/scripts/media_outbox.py` + weixin.py send_document 失败分支入队
- codex 会话复用：`~/.hermes/scripts/codex_task.sh`（按项目目录存 `.codex_session_id`，同项目 resume 消冷启动）
- 隧道 watchdog：`~/.hermes/scripts/tunnel_watchdog.py`（60s 探测 8899，3 次失败写 DEGRADED 标记）
- 广州 relay 隧道运维细节（autossh systemd 的 `~` 路径坑、GET 转发、断链行为）：`references/guangzhou-relay-lifecycle.md`

## When to Use
- 1888/1889/18888 服务要改端口绑定、systemd 化、加鉴权、防 OOM → P0 清单
- 视频任务慢、要提速 → 并发铁律 + Job API + 节点并行
- 改完 helper/execute 后服务卡死（GET 请求挂住）→ ThreadingHTTPServer 坑
- 要动 sshd / 防火墙 / 密钥 → SSH 加固节 + OpenSSH 第一个值生效坑
