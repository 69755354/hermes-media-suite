---
name: hermes-safe-update
description: "Upgrade Hermes safely or fix upgrade crashes. 停服备份升级验尸全绿才重启。"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, update, upgrade, safe, backup, verification]
---

# Hermes 安全升级流程

## 背景（为什么必须有这个）

Hermes 每次升级都挂的历史根因（2026-08-05 实测诊断）：

1. **升级和运行抢同一环境** — `hermes update` 重建 venv 到一半，gateway 还在跑，读到一半的文件 → `[Errno 2] No such file or directory` + certifi cacert.pem 找不到 → API 全挂
2. **升级只升代码，不升环境** — Python 包装了，npm 依赖（agent-browser）没装、Chrome 二进制没有 → browser/CDP/image 工具全挂
3. **配置版本不迁移** — 代码 0.19.1 但 config 还是 v0（最新 v33）→ 新功能不识别
4. **老垃圾不清** — composio 假 key（占位符 YOUR_API_KEY）升级后被反复拉起报 401
5. **没有验尸** — gateway-exit-diag.log 显示挂了 9 次都是用户发现，不是自检
6. **备份默认关闭** — `updates.pre_update_backup: false`，裸奔升级

### ⚠️ 死穴：从 gateway 内部跑升级 = 自杀（2026-08-05 实测两次翻车）

**症状**：升级脚本日志卡死在「---- [1] 停服 ----」就断了，gateway 停 6 小时没人拉，customer 服务 failed 没人管。

**根因**：`hermes-gateway.service` 的 `KillMode=mixed` — systemctl stop gateway 时 SIGTERM 会传播给所有子进程。如果升级脚本是从 gateway 内部（terminal 工具/子 shell）启动的，**停服那一步就把脚本自己杀了**，后续移旧放新/重启全没执行。

**正确做法（已验证 0.19.1→0.20.0 成功）**：

```bash
# 从 gateway 内部（Hermes terminal 工具）启动升级：用 systemd-run 独立瞬态单元
systemd-run --user --no-block --unit=hermes-upgrade-020 bash -c 'export HOME=/home/ubuntu; bash ~/.hermes/scripts/<升级脚本>.sh'
```

- `systemd-run` 创建独立 cgroup，停服时 SIGTERM 不传播，脚本完整跑完
- 跑完 `systemctl --user status hermes-upgrade-020` 看状态
- 升级过程中当前会话会断（gateway 重启），等新 gateway 起来恢复

**相关物理约束**：Hermes 安全层会拦截 gateway 内部对 gateway 系服务的 systemctl 操作（报 `Blocked: cannot restart or stop the gateway from inside the gateway process`）。这是保护不是 bug，别绕。恢复 customer 用官方命令：

```bash
hermes -p customer gateway start   # 单启 customer，不碰当前 gateway
```

**升级后检查清单**（验尸全绿才收工）：
1. `hermes --version` 显示新版本
2. `hermes gateway list` — default 和 customer 都在跑
3. `curl -s http://127.0.0.1:9222/json/version` — Chrome CDP 活着
4. `grep _config_version ~/.hermes/config.yaml` — v33+
5. 升级日志尾部有 `========== Upgrade 完成 ==========`

## 正确流程（脚本已焊死）

**入口：** `bash ~/.hermes/scripts/hermes-safe-update.sh`（alias: `hermes-update`）
**安全演练（只验不升级）：** `bash ~/.hermes/scripts/hermes-safe-update.sh --check`

脚本自动执行 6 阶段：

| 阶段 | 内容 | 失败处理 |
|:---|:---|:---|
| 0 预检 | gateway 在跑？venv 存在？ | 否→exit 3 |
| 1 停服 | 停 hermes-gateway + customer + chrome-cdp | 进程没退→exit 3 |
| 2 备份 | config.yaml/.env/auth.json/skills/memories → ~/.hermes/backups/ | 不阻塞 |
| 3 升级 | config migrate → hermes update --yes --backup → npm install | 失败→exit 1 |
| 4 验尸 | 版本/证书/依赖/配置版本/占位符/Chrome/SSL | 累计 FAIL_COUNT |
| 5 判定 | FAIL_COUNT>0 → 不重启，exit 2 | 全绿才继续 |
| 6 重启 | chrome-cdp → hermes-gateway → customer | 起不来→exit 2 |

## 验尸检查项（每项都是真实翻车点）

1. `venv/lib/python3.11/site-packages/certifi/cacert.pem` 存在 — 证书挂 = API 全挂
2. openai/httpx/aiohttp/pydantic/mcp 依赖目录存在
3. `_config_version` ≥ 最新（v33）— 低了先 `hermes config migrate`
4. config 无 `YOUR_API` 占位符 key（composio 翻车点）
5. `~/.cache/agent-browser/chrome-linux64/chrome` 可执行 — 注意是 **~/.cache** 不是 ~/.hermes/.cache，systemd service 用的是前者
6. `hermes doctor` SSL 段

## Chrome 二进制修复（环境特有）

机器上的 chrome 是 snap 版（`/snap/bin/chromium`），**不支持 `--headless=new` 参数**（snap 包装限制，报 unknown flag）。正确做法：

```bash
# 下载 Chrome for Testing 官方二进制（支持 --headless=new）
# 从 https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json 拿最新 linux64 URL
curl -sL -o /tmp/chrome-testing.zip "<url>"
unzip -o -q /tmp/chrome-testing.zip -d /tmp/chrome-testing
cp -r /tmp/chrome-testing/chrome-linux64/* ~/.cache/agent-browser/chrome-linux64/
chmod +x ~/.cache/agent-browser/chrome-linux64/chrome
```

注意：旧 playwright 缓存的 chrome 是断链（指向不存在的 snap 路径），不要用。

## 常见问题

- **升级后飞书狂弹「Self-improvement review」系统通知（0.20.0 实测翻车）**：`auxiliary.background_review.enabled: false` 是**死配置**——0.20.0 代码根本不读这个字段，关了也拦不住。真正控制后台自评审通知的是 `memory.nudge_interval`（每 N 轮记忆自评审）和 `skills.creation_nudge_interval`（每 N 轮技能自评审），触发后通过 `background_review_callback` 直接推平台，**绕过 message_filters**（那是入站消息过滤，管不住出站系统通知）。修复：两个值归零即可（`nudge_interval: 0` + `creation_nudge_interval: 0`），改完重启 customer。记忆功能本身不受影响（memory_enabled 仍生效），只是不再主动弹「该更新记忆了」。
- **gateway 挂了但系统还活**：查 `~/.hermes/logs/errors.log` 尾部，看 `API call failed after N retries` — 那是升级中 venv 重建导致的
- **工具 check_fn 返回 False**：升级后 npm 没装 → `cd ~/.hermes/hermes-agent && npm install --workspaces=false`
- **composio 401**：config 里 mcp_servers.composio 的 key 是占位符 → `hermes mcp remove composio`
- **config migrate 后 gateway 没生效**：migrate 只是改文件，gateway 要重启才加载（`systemctl --user restart hermes-gateway`）

## 验证命令

```bash
# 当前版本
hermes --version
# 配置版本（应为 v33+）
grep _config_version ~/.hermes/config.yaml
# gateway 状态
systemctl --user status hermes-gateway chrome-cdp
# CDP 可用性
curl -s http://127.0.0.1:9222/json/version
```
