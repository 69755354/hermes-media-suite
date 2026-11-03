---
name: server-security-hardening
description: 服务器安全加固(密钥/端口/SSH/systemd/并发锁)。触发:安全审计/加固/端口暴露/密钥硬编码/OOM/并发。
---

# 服务器安全加固实战（2026-08-09 新加坡机全量加固沉淀）

2GB 内存小机跑 Hermes + 本地 API 服务的完整加固清单。每项都是实测踩坑后确认的。

## 1. 密钥安全（P0 最高优先）

- **源码零硬编码**：AK/token 从源码移到 `.env`（0600）或独立密钥文件（如 `~/.hermes/helper_auth_token`，0600）
- Python 从 .env 读 key 模式：
  ```python
  for _l in open("/home/ubuntu/.hermes/.env"):
      if "ARK_API_KEY" in _l and "=" in _l:
          AK = _l.split("=", 1)[1].strip().strip('"').strip("'")
  ```
- 改 `/opt/` 下文件需 `sudo`（工具层 patch 会 Permission denied），先 `sudo cp` 备份再改
- 微信账号文件统一 0600：`chmod 600 ~/.hermes/weixin/accounts/*.json`
- ⚠️ 改完用 `grep` 验证源码里确实没有硬编码残留，别只信「改成功了」

## 2. 端口暴露（P0）

- 本地 API 服务一律绑 `127.0.0.1` 不是 `0.0.0.0`：`HTTPServer(("127.0.0.1", port), Handler)`
- UFW 防火墙：`default deny incoming` + 只放 `22/80/443`，`ufw --force enable`
- 绑 127.0.0.1 后外网不可达，但本地仍要鉴权（token 校验），两层都要

## 3. systemd 化（P0）

```ini
[Service]
Type=simple
User=ubuntu          # 非 root！
Group=ubuntu
ExecStart=/usr/bin/python3 /path/to/app.py
Restart=always
RestartSec=3
MemoryHigh=600M      # 软限制
MemoryMax=800M       # 硬限制（防 OOM 拖垮整机）
```

- `systemctl daemon-reload && systemctl enable --now <svc>`
- ⚠️ systemd 以普通用户跑时，代码里不能有 `/root/.xxx` 读取（PermissionError）——改读用户自己的密钥文件

## 4. ⚠️ 单线程 HTTPServer 卡死（大坑）

- `HTTPServer`（单线程）+ 只有 `do_POST` 没有 `do_GET` → 任何 GET 请求永远挂起占住唯一线程 → 后续全部请求排队超时（Recv-Q 累积，curl 连上无响应）
- **修复**：换 `ThreadingHTTPServer` + 给 Handler 加 `do_GET` 快速响应：
  ```python
  from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
  class Handler(BaseHTTPRequestHandler):
      def do_GET(self):
          self.send_response(200); self.end_headers()
          self.wfile.write(b'{"status":"alive"}')
  ```
- 判断卡死：`ss -tlnp` 看 Recv-Q 不为 0 + curl 超时

## 5. 输入加固（P0）

- **task_id/路径参数防逃逸**：只允许 `[A-Za-z0-9_-]`，截断 64 字符，防 `../` 写任意路径
- 请求体上限：`Content-Length > 20MB → 413`
- 业务错误返回正确状态码（422/404），不全部包 200
- ⚠️ 改代码后用 `python3 -m py_compile` 验证语法

## 6. 并发锁（2GB 内存机必做）

- codex/ffmpeg 等重任务全局并发锁 1，防两个重任务并发 OOM：
  ```bash
  flock /tmp/codex.lock -c "codex exec ..."        # codex 锁
  flock /tmp/ffmpeg.lock -c "ffmpeg ..."           # ffmpeg 锁
  ```
- helper/execute 里 subprocess 调 ffmpeg 全部包 flock（shell 方式拼命令）

## 7. OpenSSH 配置优先级（大坑）

- **OpenSSH 是「第一个获得的值生效」**（不是最后一个）——`Include /etc/ssh/sshd_config.d/*.conf` 按字母序读，`50-cloud-init.conf` 里的 `PasswordAuthentication yes` 会盖掉所有后续 no
- 改加固配置必须改**最早读到的那个文件**（`50-cloud-init.conf` 本身），改 99-hardening 没用
- 验证生效：`sudo sshd -T | grep passwordauthentication`（不是看配置文件！）
- 加固：`PermitRootLogin no` + `PasswordAuthentication no` + 保留 ubuntu key 登录
- 重启姿势：`sudo sshd -t` 语法检查 → `sudo systemctl reload ssh`（不中断现有连接）→ 外部验证

## 8. 配置修改姿势

- `~/.hermes/config.yaml` 是安全敏感文件，工具层拒绝直接写——用 `hermes config set <path> <value>`
- ⚠️ config set 路径要对（如 `auxiliary.display.busy_input_mode` 而不是 `display.busy_input_mode`），改完 `grep` 验证所有出现位置

## 8.4 组权限未刷新 → 子进程 permission denied（2026-08-22 实测）

**症状**：`docker ps` 报 `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`，但 `id` 显示用户在 docker 组、socket 权限 `rw-rw---- root:docker` 也正常。

**根因**：长驻进程（Hermes gateway/systemd 服务）**启动早于**用户加入 docker 组——进程组 ID 是启动时快照，之后加组不生效，所有子进程继承旧组。不是 docker 配置坏了。

**判定**：`sg docker -c "docker ps"` 显式切组后正常 = 组权限未刷新问题。

**解法**：调用方用 `sg <group> -c '<command>'` 包裹重跑（如 `sg docker -c 'python3 .../hermes_task_dispatch.py ...'`）。不用改配置、不用重启网关。

## 8.5 执行器「物理防绕」三层加固（2026-08-22 广州出片确认闸实战）

**问题本质**：出片确认闸（客户确认 + 白名单 + 配额）如果执行器（AI 进程）能自己改文件，安全边界就是纸糊的。正确目标：**把「执行器改闸」变成物理不可能，不是「自觉不改」**。

**三层咬死（缺一层都不行）：**
1. **闸文件 root:root 444**——`execute_api.py` / `confirm_gate.py` / `permission_gate.py` 全部 `chown root:root` + `chmod 444`，执行器（ubuntu 用户）直接没写权限
2. **sudoers 删 `(ALL : ALL) ALL`**——ubuntu 有全权 sudo 是最大洞（实测存在！）。删掉后 NOPASSWD 白名单**绝不能含 execute-api 的 restart/stop**（否则执行器改了文件再重启服务就生效了）；`sudo -n -l` 验证
3. **root 属主哈希 watchdog**——类似 context_rollover_watchdog 模式：30 分钟校验闸文件哈希，变了立刻报警终止；watchdog 脚本 + systemd timer 必须 root 属主 444，执行器改不了

**关键逻辑**：执行器改文件 → 服务重启被 sudo 白名单挡 → 改动不生效 → 哈希校验又报警。三层互相咬死。

**claude 独立判断修正（2026-08-22，详见 `references/bypass-path-enumeration-20260822.md`）**：
- **chmod 444 不防 unlink**：POSIX 删除文件看父目录写权限。闸文件必须在 root 属主目录（`/opt/hermes/gates/`），只 chmod 不迁目录 = 白做
- **真正 root 通路是密码残留**：`.env.bak*`、state.db 里 SUDO_PASSWORD 明文 → 清残留 + **轮换密码** + 删 ALL 三者缺一不可
- **软模式是头号洞**：`HERMES_GATE_SOFT=1` + `_HARD_ENTRIES=set()` → 闸全放行，攻击者不用改文件（部署前必须删 drop-in + 填 HARD_ENTRIES）
- **哈希校验先查物理存在**：SOUL 声称「每30分钟校验」可能纯虚构（无执行位/无 crontab/清单无闸文件），校验器必须 root 属主 + systemd timer 调度 + 自校验
- **校验器基线必须与被执行对象不同属主**，否则改文件后重算 md5 覆盖基线，校验永远 PASS

**大坑——执行器自述权限不可信**：广州机小鹿声称「我只有普通权限改不了闸」，实测文件全是 ubuntu 可写（rw-------/rw-rw-r--）+ sudo 有 `(ALL : ALL) ALL`——**它的安全假设是假的**。判断执行器能不能绕，必须 `ls -la` + `sudo -n -l` 实测，**不采信执行器自述**。SOUL.md 里写「已设只读 + 每30分钟哈希校验」≠ 物理闸落地——规则写在 SOUL 里没有校验脚本就是软规则（天行者反对软规则当硬边界）。

**部署时机判断**：目标服务已停/生产已迁移时，这套是「切回前硬前置」而非「现在必须动 root」——先确认哪台是生产再决定时机，别在退役机器上白做加固。

## 8.6 sudoers 收敛后验证 + 重复 include 排查（2026-08-22 实测）

**收敛后必须 `sudo -n -l` 实测**（文件看了干净 ≠ sudo 解析干净）：白名单规则**只允许出现 1 次**、`(ALL : ALL) ALL` 必须消失。修复脚本若断言「白名单数量=1」失败 = 有重复规则。

**症状：所有 sudoers 文件逐个 cat 都干净（99-hermes-tighten 2 条白名单、90-cloud-init-users 全注释、/etc/sudoers 主文件 ubuntu 行注释），但 `sudo -l` 仍显示白名单各 2 份 + `(ALL : ALL) ALL`。**

**根因（codex 定位 + 手动修复确认）：`/etc/sudoers.d` 被 `#includedir` 解析两遍**（duplicate include）——同一个 99-hermes-tighten 被读两次 → 每条白名单显示 2 份；主文件规则只读一次所以 `(ALL : ALL) ALL` 只 1 条。修复后备份命名惯例：`/etc/sudoers.bak_20260822_dupincl`。

排查顺序（文件检查 → 解析层面，别绕圈）：
1. `sudo cat /etc/sudoers.d/*` 逐个看（90-cloud-init-users / 99-hermes-tighten / 其他 drop-in）
2. `sudo grep -n 'ubuntu\|ALL' /etc/sudoers` 主文件全文（不只看一条注释行）
3. **`sudo grep -n 'includedir\|@include\|#include' /etc/sudoers`**——重复 includedir 是首要嫌疑（本案例根因）
4. 其他候选：`%sudo`/`%admin` 组规则、NSS/SSSD 重复源（可能性低）
5. 修完验证：`sudo -n -l` 白名单各 1 条、无 ALL

**排查绕圈教训（2026-08-22 老板「你到底行不行啊 不行换CODEX来」）**：文件全检查干净但 sudo -l 矛盾时，自己硬啃 3 轮没进展就该**换 codex 定位**（打包现场信息：各文件内容 + sudo -l 输出 + 矛盾点，让它按可能性排序给命令清单）——codex 一次就给出「includedir 重复」首因，与手动修复一致。技术排查类问题外包比硬扛快。

## 8.7 Hash-Verify 基线刷新与 MISMATCH 定性（2026-08-26 实战）

物理闸 P0 修复后双机会出现 MISMATCH（guard 脚本重建、SOUL 更新等授权变更导致）。必须逐项定性后刷新基线，不能直接覆盖。

**定性方法：** 逐个文件 `stat --format='%y'` 看修改时间 → `git log --all` 查对应 commit → 对照已知授权操作（codex 修复、老板指示、P0 执行步骤）→ 双机当前哈希对比（一致=同版本，基线不同=建基线时间不同）。

**刷新方法：** hash_verify.py 只校验不刷基线。基线 = `/home/ubuntu/.hermes/guard/hashes/<filename>.md5` 文件。直接计算当前文件 MD5，备份旧基线（`.bak-refresh-<ts>`），写新哈希。广州走 SSH。刷新后跑 `hash-verify.sh` 验证全绿 `ALL_OK`。

**物理闸待人工项解决模式：** MISMATCH定性（Hermes可做）→ G10写权限隔离（root操作，AI准备命令用户终端执行）→ P1-3毕业（时间条件等满7天）→ 字符串自证残留（智力活派codex）→ 独立终审（派CC，实现者不自审）。

完整流程见 `references/hash-verify-baseline-refresh.md`。

## 关联
- `singapore-guangzhou-relay`（跨机隧道/relay 场景）
- `local-media-pipeline-ops`（helper-api 1888 / execute-api 1889 运维）
- `network-relay-ops`（海外机被墙时的 relay 排查）
## 异步 Job API 模式
长任务 HTTP 服务（如视频流水线 /execute 跑 28-56 分钟）改异步持久化 Job 的完整模式：提交立即返回 job_id、后台线程执行、进度落盘可查、节点并行化。见 `references/async-job-api-pattern.md`。

## 8.8 Hook 配置格式静默失效（2026-08-31 实战）

**症状：** guard 文件权限锁了（444/440 root:ubuntu）、Hermes 进程重启了、hook 脚本手动测试能跑能拦，但实际 terminal/write_file 操作全过没被拦，审计日志当天 0 条。

**根因：** `config.yaml` 里 `hooks.pre_tool_call` 被存成了 **JSON 字符串** 而非 **YAML 列表**。Hermes 的 `agent.shell_hooks` 解析器收到 str 类型直接跳过，日志报 `WARNING agent.shell_hooks: hooks.pre_tool_call must be a list of hook definitions; got str`，hook 根本没注册。

**三步定位法：**
1. 查审计日志当天条目：`grep $(date +%Y-%m-%d) entry_guard_audit.jsonl` → 0 条 = hook 没在跑
2. grep agent.log 找 shell_hooks 警告：`grep 'shell_hooks.*must be a list' agent.log` → 有 = 配置格式错
3. 用 python 检查 config 值类型：`python3 -c "import yaml; cfg=yaml.safe_load(open('config.yaml')); v=cfg['hooks']['pre_tool_call']; print(type(v), v)"` → `<class 'str'>` = 错，`<class 'list'>` = 对

**修复（config.yaml 锁了 440 root:ubuntu 时）：**
```bash
# 1. 临时解锁
sudo chown ubuntu:ubuntu /home/ubuntu/.hermes/config.yaml
sudo chmod 644 /home/ubuntu/.hermes/config.yaml
# 2. str → list 转换
python3 -c "
import yaml, json
with open('/home/ubuntu/.hermes/config.yaml') as f:
    cfg = yaml.safe_load(f)
raw = cfg['hooks']['pre_tool_call']
if isinstance(raw, str):
    cfg['hooks']['pre_tool_call'] = json.loads(raw)
with open('/home/ubuntu/.hermes/config.yaml','w') as f:
    yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
print('FIXED')
"
# 3. 重锁
sudo chown root:ubuntu /home/ubuntu/.hermes/config.yaml
sudo chmod 440 /home/ubuntu/.hermes/config.yaml
# 4. 重启 Hermes
kill $(ps aux | grep 'hermes_cli.main gateway' | grep -v grep | awk '{print $2}')
sleep 2
cd /home/ubuntu && nohup /home/ubuntu/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main gateway run > /dev/null 2>&1 &
```

**两个关键认知：**
- **手动测 hook 脚本能跑 ≠ hook 在生效：** `echo '{...}' | python3 node-entry-guard.py` 返回 block 只证明脚本逻辑没问题，不证明 Hermes 在调用它。必须查审计日志 + agent.log 确认 hook 是否实际被调用。
- **hermes_hook_config.yaml vs config.yaml 双源问题：** `workflow/guard/hermes_hook_config.yaml` 也存了一份 hook 配置（YAML 列表格式，正确的），但 Hermes 实际读的是 `config.yaml` 里的那份（可能是字符串格式，错的）。两个文件都有 hook 配置时，以 config.yaml 为准。修 config.yaml 才有效。

## 9. ARK 调用走 relay 的接入点（2026-08-09 生产链路打通）

新加坡机直连火山 ARK 不通，本地服务必须改走广州 relay（`127.0.0.1:8899/upload?url=<URL编码>`）：
- **helper_api `volc_api()`**：ARK 调用改走 relay，relay 失败回退直连
- **execute_api `http_request()`**：⚠️ **仅 volces.com 域名走 relay**，DeepSeek 保持直连（不能全改——DeepSeek 直连通）
- 排查 ARK 调用失败先确认调用方是否走 relay：`grep -n "8899" /opt/helper_api.py /home/ubuntu/execute_api.py`
- 验证：`curl -X POST 127.0.0.1:1888/seedream` 带鉴权头实测返回真实图片 URL
