---
name: linux-task-serialization
description: 低内存服务器重任务并发锁(flock串行化)。触发:OOM/并发卡死/codex同时跑/ffmpeg并发。
---

# 低内存服务器重任务串行化（flock 并发锁）

2GB 内存机器上跑多个重任务（codex exec、ffmpeg、Seedance 轮询）会 OOM 或 swap 抖动。用 `flock` 文件锁把全局并发钉死为 1，排队执行，不并行。

## 何时用

- 服务器内存 ≤4GB，同时有多个「重任务」类型（LLM agent 调用、视频转码、大文件处理）
- 出现：swap 使用 >0、进程被杀（OOM killer）、系统无响应
- codex 审计结论：2GB 机两个 codex 重任务并发 = 必然 OOM（每个 codex 任务 ~370MB，Hermes gateway 峰值 1.2GB）

## 核心模式

```bash
# codex 全局并发锁 1：包住所有 codex exec 调用
flock /tmp/codex.lock -c "codex exec --skip-git-repo-check ... 2>&1 | tail -100"

# ffmpeg 全局并发锁 1
flock /tmp/ffmpeg.lock -c "ffmpeg -y -f concat -safe 0 -i list.txt -c copy out.mp4"
```

- 每个「资源类别」一把锁文件：codex 一把、ffmpeg 一把（跨多个服务共享同一把锁）
- 锁文件用 `/tmp/`（无需持久化），flock 自动释放（进程退出即解锁）
- 排队等待，不并行——用户要的是「不崩」，不是「更快」

## Python subprocess 里包 flock（helper-api 实测）

```python
def _ffmpeg(*args, **kwargs):
    """ffmpeg 全局并发锁1（2GB内存防OOM）"""
    cmd = args[0] if args else kwargs.get("args")
    cmd_str = " ".join(str(x) for x in cmd) if isinstance(cmd, list) else str(cmd)
    locked = f"flock /tmp/ffmpeg.lock -c {json.dumps(cmd_str)}"
    return subprocess.run(locked, shell=True, **{k: v for k, v in kwargs.items() if k != "args"})
```

注意：
- `json.dumps(cmd_str)` 给 shell 串加引号，防路径含空格/特殊字符断句
- 超时要放宽（排队等锁会吃掉一部分超时预算）：ffmpeg 120s→180s

## systemd 侧也要配内存上限（配套措施）

单靠 flock 管不到 systemd 服务本身的内存，两个都要：
```ini
[Service]
MemoryHigh=600M   # 软上限，超了进 swap 但不杀
MemoryMax=800M    # 硬上限，超了 OOM kill
```

- 服务级配置：helper-api 800M / execute-api 700M / ark-proxy 400M / codex 单任务 370M
- `Restart=always` 没配 MemoryMax = 单任务可拖垮整机

## 验证

```bash
flock /tmp/codex.lock -c "echo 锁可用"      # 单次调用验证锁文件可写
ss -tlnp | grep -E "1888|1889"               # 服务重启后端口正常
systemctl is-active helper-api execute-api   # 服务健康
```

## 踩坑

- **`pkill -f "helper_api.py"` 会匹配到自己的 shell 命令**（命令串里含该模式）→ 把自己杀了（exit -15）。用精确模式或先 `pgrep -f` 确认。
- pkill 后 systemd 重启端口被旧进程占（Address already in use）→ `fuser -k <port>/tcp` 清干净再 start。
- flock 等待期间被锁任务超时：给被锁命令留足 timeout 余量。
- **别反复 pkill codex/claude 腾内存（2026-08-14 翻车）**：内存紧张时反复 pkill 执行器，gateway 里的 agent 循环（飞书机器人接的任务）会**自动重试**重新调 codex，陷入「杀 → 重试 → 再杀」循环，任务永远完不成，还把飞书机器人连带搞卡。正确做法：加大 swap（治本一次）→ 派一次任务 → 不干预让它跑完。要杀之前先 `ps -o ppid,cmd -p <pid>` 看它是谁的子进程，别杀到 gateway 正在等结果的活。

## 并发槽上限更新（2026-08-19 天行者定案）

- `codex_exec_gated.sh` / `claude_remote_wrapper.sh` 已从「全局锁 1」改为 **4 并发槽**（fd 9-12 → `.0-.3`，`flock -n` 轮询），备份 `.bak_20260819_4concurrency`
- 本 skill 的「锁 1 防 OOM」仍适用于**直接调 codex/claude 的裸命令**（ffmpeg、临时脚本等）；走壳的重任务有 4 槽位
- **3.6G 新加坡机实测**：2 个 claude/codex 并发 + gateway 可用，4 个全开会吃紧——`free -h` 可用 <500M 或 swap >1G 时停止新派重任务

## cron script 字段规范（2026-08-19 加固，两机犯过 5 次的 bug）

`hermes cron create --script` 只接受**单文件名（相对 ~/.hermes/scripts/）**：
- ❌ 带参数 `context_rollover_watchdog.py --threshold 160000` → `Script not found`
- ❌ 内联 bash（含 shebang/多行）→ 被当路径拼接出荒诞错误（`Script not found: .../scripts/#!/usr/bin/env bash...`）
- ❌ 软链 → 被 `cronjob_tools.py` 安全校验拦（路径穿越）
- ✅ 正确范式：**参数固化进包装脚本**（如 `context_rollover_watchdog.sh` 内含 `exec python3 ... --threshold ...`），cron 只指向 .sh

修复已在 `cronjob_tools.py:_validate_cron_script_path` 加校验（带空格/换行/#! 直接拒绝），gateway 重启后生效。跨 profile 共享脚本**复制**而非软链（软链会被校验拦，2026-08-19 广州合库实测）。

## 双 cron 库坑（2026-08-19 广州机实测，审计前必读）

广州机存在**两个** cron 存储，唯一调度器绑定 customer profile：
- `/home/ubuntu/.hermes/cron/jobs.json` = 默认库（**无调度器，僵尸**）——若 `hermes-gateway.service` 是 disabled/inactive，里面的任务全不跑
- `/home/ubuntu/.hermes/profiles/customer/cron/jobs.json` = customer 库（**活的**，真正在跑）

**判断方法**：先查 `systemctl --user is-enabled hermes-gateway.service`（disabled=默认库僵尸）+ `ps aux | grep hermes_cli.main` 看 gateway 绑定哪个 profile（`HERMES_HOME` 环境变量）。**看板会骗人**：僵尸库任务仍显示 enabled/ok，但 next_run_at 冻结、last_run 停在调度器死亡时刻。审计 cron 前先确认调度器活着，再看任务列表。合库方案：任务迁到 customer 库、清默认库、放 `README.DEPRECATED` 标记。

## 膨胀会话手动归档流程（交接包闸拦截时，2026-08-19 实测）

`context_rollover_watchdog.py` 归档前强制过 `handoff_gate`：
- `NO_HANDOFF`（无交接包）→ 先 `handoff_builder.py --session-id <sid> --db <db> --out-dir ~/.hermes/archives` 生成
- `MULTI_HANDOFF`（多个交接包）→ 删旧的保留最新（`rm handoff_..._<旧日期>.json`）
- 生成后 `handoff_gate.py check <sid>` 返回 `HANDOFF_OK` 才能归档
- 归档属不可逆操作，**活跃会话跳过**（10 分钟内有消息不归档），超静默 + 交接包 OK 才归档；大会话归档前先 `cp state.db state.db.bak` 兜底

## 交接包死锁（2026-08-19 claude 实测，自动化归档率恒 0 的根因）

**循环依赖**：watchdog 先 `handoff_gate check`（要求交接包已存在）→ 才调 `session_rollover` → 而交接包唯一生产者 `handoff_builder` 只在 `session_rollover.py` 内部被调（全仓 grep 确认）。新会话永远无交接包 → 闸永远 `NO_HANDOFF` → rollover 永不被调 → 交接包永不生成。

**症状**：cron 日志连续多个周期 `BLOCKED:NO_HANDOFF` 且 token 值冻结（如 04:00-08:00 五次相同 BLOCK，token 冻在 266,044）。此时会话早已静默，活跃跳过不是障碍——纯死锁。

**解法（方案已出，实施中）**：在闸**前**插入幂等 `prebuild_handoff()`——已有包复用（校验 checksum）/ 无包调 builder 生成 / 多包返回 `MANUAL_REVIEW_REQUIRED` 交人工（**绝不覆盖、绝不自动删多余包**）。物理闸逻辑一字不动，`NO_HANDOFF`/`MULTI_HANDOFF`/`BAD_CHECKSUM` 拦截语义全保留。手动能归档是因为手动先跑了 builder，自动化路径本身死锁。

**「静默才归档」是活锁（设计缺陷，2026-08-19）**：判定（token 超限，单调递增）与执行（静默 10min，由客户打字节奏控制）解耦，高频会话可无限期「已判失控但永不执行」——小鹿 241 万 token 就是这么拖出来的。`skipped_active` 无计数器/宽限期/升级路径。解法：三层升级 L1 静默归档（保留）→ L2 **任务边界归档**（最后消息 role=assistant 且 ≥90s 且 5min 无 tool 调用，客户无感；实测中位消息间隔 172s > 90s，正常节奏下命中率高）→ L3 熔断强制（`--force`，宽限耗尽或 FUSE 阈值，每周期限 1 个，pinned 会话豁免）。「静默」是体验的粗糙代理指标，真正该保护的是「不在任务执行中途切换」——L2 直接检测任务边界。

## gateway 卡死根因：内存被「gateway + 重任务」叠加挤爆（2026-08-14 实测）

**症状**：飞书/微信消息进来后 Flushing text batch 但永远不回 response，日志反复出现「final stream delivery not confirmed」「Persisted transcript lagged live cached history」。重启 gateway 好一会又卡，用户感知「机器人又卡死了」「小鹿就不会」。

**根因**：2GB 机上 gateway 本身（~400MB）+ 飞书机器人接的任务调的 codex（单个 230MB）+ 一堆 node 进程，**叠加**挤爆 2GB → 触发 swap（>400MB）→ 整机卡顿。flock 串行只管 codex/claude 之间的并发，**管不住「gateway + 单个重任务 + node 进程」的叠加峰值**。

**关键洞察**：同一个 default profile 的飞书和微信共享同一个 gateway + 同一台机器 + 同一个 flock 锁。飞书群任务调 codex（如「分析文档」），微信这边同时派 claude（双执行器），都在同一台 2GB 机上挤内存。小鹿（customer）的 gateway 在广州机（独立），但**她调 codex 时通过 `codex_remote.sh` SSH 到这台新加坡机（SG_HOST=<SG_HOST>）跑 `codex exec`**——广州机根本没装 codex（`which codex` 无、无 auth.json、.env 无 key），她的重活实际落在这台 2GB 机上。**根因是地理网络（2026-08-14 实测）**：国内服务器 `curl api.openai.com` 直接 000（被墙），codex 靠 OpenAI API、claude 靠 AWS Bedrock（us-east-1），国内都访问不了——所以 codex/claude 天生只能待在海外机（新加坡机）。用户问「codex 放国内服务器可行吗」→ 不可行，除非国内机配翻墙代理（合规风险 + 不稳）或像小鹿这样 SSH 到海外机远程跑。国内机内存再大也没用，卡点在网络不在内存。，跟 default 的重活叠加抢内存。所以「小鹿不卡 default 卡」的表象是误导：真正区别是 default 自己 + 小鹿远程 + gateway 三者都压在新加坡机这一台 2GB 上。排查跨机器卡死时，先确认另一台机是否 SSH 过来跑重活：读对方 `~/.hermes/scripts/codex_remote.sh` 看 SG_HOST、`ss -tn | grep :22` 看 inbound SSH 来源 IP。

**诊断顺序**：① `free -h` 看 swap 使用（>400MB = 内存紧张）→ ② `ps aux --sort=-%mem` 找大头进程（codex/claude/node/gateway）→ ③ 别急着断言 gateway bug，先确认是不是内存被重任务挤爆。

**处置**：短期加大 swap 缓冲 + 约束「同一时间只一个重活」；根治 = default 迁 4GB+ 机器，或把重任务（星广双执行器）挪到独立机器跑。

**加大 swap 的具体命令（2026-08-14 实测）**：磁盘充足时直接加一个 swapfile，不动现有 /swap.img，`swapon` 即时生效无需重启（实测总 swap 1.9G→3.9G，codex 跑得动了）：
```bash
sudo fallocate -l 2G /swapfile2 && sudo chmod 600 /swapfile2 \
  && sudo mkswap /swapfile2 && sudo swapon /swapfile2
free -h | grep -i swap   # 确认总量上去了
```
fallocate 报「operation not supported」（某些文件系统）时改用 `sudo dd if=/dev/zero of=/swapfile2 bs=1M count=2048 status=none`。swapfile 不写 fstab 就只是本次会话临时生效，重启后要重新 swapon——临时救急够用，根治仍是迁机器。

## 重活总锁 heavy.lock（2026-10-02 落地，用户点名 codex 与渲染不能同跑）

**问题**：codex（~370MB）+ HyperFrames 渲染（Chromium，1–2GB）+ whisper medium（1.9GB）+ gateway（峰值 1.2GB）叠加，低内存机必崩。用户直问：**codex 和渲染不能同时进行**——对。

**做法**：一把全局总锁 `/tmp/heavy.lock`，**whisper / HyperFrames 渲染 / ffmpeg 大合成 / codex 全部互斥串行**。包装器 `~/workflow/tools/heavy/heavy_run.sh <类别> <命令...>`：
- 先查余量红线：**可用内存 <500MB 或 swap 已用 >1G → 直接 `HEAVY_BLOCKED` 拒开**（exit 3），不排队干等
- 再拿 flock（`-w 3600` 排队，占用时打印「另一项重活正在跑，排队等待」）
- Python 侧用 `fcntl.flock`；`asr_run.py` 已在 `WhisperModel(...)` 外加 `HeavyLock` 上下文（2026-10-02）

**验证**：`flock -n /tmp/heavy.lock -c "echo 空闲"` 判占用；实跑转写 rc=0/588MB 正常。
**注**：`codex_exec_gated.sh` 的 4 并发槽只管 codex 之间，**管不住 codex 与渲染/whisper 的叠加**——跨类别一律走 heavy.lock。

## 关联

- local-http-service-hardening（P0 全套：systemd/非root/鉴权/卡死坑）
- codex-cli-ops（codex 参数与沙箱边界）
- 本模式来自 2026-08-09 新加坡机 P0-7 安全加固（2GB 机，codex+ffmpeg 并发锁 1）
