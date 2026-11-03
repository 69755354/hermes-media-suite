---
name: hermes-cron-ops
description: Hermes cron/watchdog 运维。触发：cron/Script not found/膨胀会话归档。
version: 1.0.0
author: Hermes curator
license: MIT
metadata:
  hermes:
    tags: [cron, watchdog, 定时任务, 自动归档, 会话轮换, 膨胀会话]
    category: server-operations
---

# Hermes Cron 任务运维

## When to Use

触发：创建/排查/修改 Hermes cron 定时任务、watchdog、膨胀会话自动归档、cron 报 "Script not found"、跨机（新加坡/广州）配定时任务、会话轮换/交接包。

## 核心坑 1：script 字段不能带参数（2026-08-19 实测，两机都踩过）

**cron job 的 `script` 字段只接受 `~/.hermes/scripts/` 下的脚本路径，不能带参数。** 把 `context_rollover_watchdog.py --threshold 160000 ...` 整个塞进 script 字段，cron 把整串当路径找 → 每次运行报：

```
Status: script failed
Script not found: /home/ubuntu/.hermes/scripts/context_rollover_watchdog.py --threshold 160000 --max-calls 300 --db ...
```

**修复模式：包装脚本固化参数**（cron 只调 .sh，参数写死在包装里）：
```bash
#!/bin/bash
# context_rollover_watchdog.sh — 包装：参数固化，cron 只调本脚本
cd /home/ubuntu/.hermes || exit 1
exec python3 scripts/context_rollover_watchdog.py \
    --threshold 160000 \
    --max-calls 300 \
    --db /home/ubuntu/.hermes/state.db
```
`chmod +x`，cron `script: context_rollover_watchdog.sh`（相对 ~/.hermes/scripts/ 解析；.sh 用 bash 跑，其他用 python）。

**物理加固已落地（2026-08-19）**：`tools/cronjob_tools.py` 的 `_validate_cron_script_path` 已加「script 字段必须是单文件名」校验——含空格/换行/`#!` 直接拒绝并提示用包装脚本。此校验在 gateway 进程内生效，**改代码后需 gateway 重启才加载**（Python 模块启动时加载，别测完没生效就说坏了）。

**同源坑：软链被路径穿越校验拦（合库时踩）**：把共享脚本 `ln -sf` 到 customer/scripts/ 再建 cron，会报 `Script path escapes the scripts directory via traversal`——cron 安全校验用 `validate_within_dir` 解析真实路径，软链被当作越界。**正确做法是 `cp` 复制**（接受双份副本，或用 git 管理防漂移）。

## 核心坑 2：跨机 cron 必须在本机侧配（2026-08-19 实测）

- **新加坡机 Hermes 的 cronjob 工具建的任务只跑在新加坡机**。要配广州机（小鹿）的定时任务，必须 SSH 到广州机用它的 hermes CLI 配，不能在新加坡侧建（会建错机器）。
- 广州机 hermes 在 `~/.local/bin/hermes`，直接 `hermes` 找不到 → `export PATH=/home/ubuntu/.local/bin:$PATH` 再调。

**广州机配 cron 模板：**
```bash
ssh -p 2222 ubuntu@127.0.0.1 "export PATH=/home/ubuntu/.local/bin:\$PATH; hermes cron create '0 * * * *' '任务名' --name '任务名' --script <脚本名>.sh --no-agent --deliver local"
# 验证：hermes cron list | grep <job_id>
# 手动触发：hermes cron run <job_id>
# 看输出：ls -t /home/ubuntu/.hermes/cron/output/<job_id>/ | head
```

## 膨胀会话自动归档 watchdog（context_rollover_watchdog.py）

**链路**：watchdog（每小时）→ 扫 sessions 表未归档且 input_tokens>阈值(默认160K) 或 api_call_count>300 → 跳过最近 10 分钟活跃会话 → 过 `handoff_gate.py check` → 调 `session_rollover.py` 归档 → 同步刷新 AGENTS.md 交接包注入。

**三个输出态（不是故障，是物理闸）：**
| 输出 | 含义 | 处理 |
|:--|:--|:--|
| `[OK] <sid> token超限` | 归档成功 | 正常 |
| `[BLOCKED:NO_HANDOFF]` | 会话无交接包，禁止归档 | **防失忆保护，不是 bug**。要归档先生成交接包 |
| `[BLOCKED:MULTI_HANDOFF]` | 存在多个交接包（脏数据） | 清理成一份再归档 |
| `[活跃跳过]` | 最近 10 分钟有消息 | 正常，下轮再查 |

**关键认知**：交接包是归档的前置物理闸——没交接包就归档 = 丢上下文。watchdog「扫得出但归档被拦」不是坏，是保护在起作用。修小鹿/客户侧大会话前先解决交接包（生成/清理），不要绕过闸。

**交接包处理实操（2026-08-19 实测通过）**：
```bash
# NO_HANDOFF → 用 builder 生成交接包（会话ID + 对应 db）
python3 ~/.hermes/scripts/handoff_builder.py --session-id <sid> --db <customer或默认 state.db> --out-dir ~/.hermes/archives
# MULTI_HANDOFF → 删旧留新（保留最新日期那份）
ls -la ~/.hermes/archives/handoff_<sid>_*          # 看有几份
rm -f ~/.hermes/archives/handoff_<sid>_<旧日期>.json # 删旧的
# 验证（两个都是 HANDOFF_OK 才能归档）
python3 ~/.hermes/scripts/handoff_gate.py check <sid> --db <db>
# 再跑 watchdog 真归档
python3 ~/.hermes/profiles/customer/scripts/context_rollover_watchdog.py --threshold 160000 --max-calls 300 --db <db>
```
- 归档前先快照兜底：`cp state.db state.db.bak_YYYYMMDD_arch`（本会话 85M 快照，归档不可逆）
- 主会话（正在活跃）会被 watchdog 正确跳过，不用担心打断用户

**排查顺序（watchdog 没干活）**：
1. `hermes cron list` → 看该任务 last_status
2. `ls -t ~/.hermes/cron/output/<job_id>/ | head` → 看最近输出内容
3. 手动跑一次脚本：`bash ~/.hermes/scripts/<script>.sh` → 看真实报错
4. 最常见的两个原因：script 字段带参数（坑 1）/ 任务配错机器（坑 2）

## 核心坑 3：跨机审计 cron 前先确认「哪个调度器活着」，别信 jobs.json 状态（2026-08-19 血泪）

广州机有**两个** cron 存储：`/home/ubuntu/.hermes/cron/jobs.json`（默认 profile）和 `/home/ubuntu/.hermes/profiles/customer/cron/jobs.json`（customer profile）。8/15 重启后默认 gateway 服务 disabled，默认库 9 个任务全部停摆，但库内仍写 `enabled/scheduled/ok` —— **状态在说谎**。Hermes 快照审计时读错库、得出「广州 3 个任务 error」的错误结论，claude 实测纠正。

审计前必须验证活调度器：
```bash
# 1. 找 gateway 进程 + 读它的 HERMES_HOME（决定读哪个库）
ps aux | grep 'hermes_cli.main.*gateway run'
# /proc/<pid>/environ 里 HERMES_HOME=/home/ubuntu/.hermes/profiles/customer  ← 读 customer 库
# 2. 服务状态（enabled+active 才是活的）
systemctl --user is-enabled hermes-gateway.service hermes-gateway-customer.service
systemctl --user is-active  hermes-gateway.service hermes-gateway-customer.service
# 3. 交叉验证：jobs.json 的 next_run_at 冻结在过去 + last_run_at 不变 = 无调度器接管
```
- 新加坡机 gateway 跑默认 profile（唯一库）；广州机 gateway 跑 customer profile（customer 库活、默认库僵尸）
- 僵尸库任务「状态 ok 但 3.5 天没跑」是最高危形态——看板骗人，运维以为在跑
- 修复方向：合库（迁活任务到 customer 库 + 清默认库）优于起第二个 gateway（1.9G 小机 OOM 风险）

**合库实操（2026-08-19 完成，广州机默认库→customer 库）**：
1. 备份旧库：`cp ~/.hermes/cron/jobs.json ~/.hermes/cron/jobs.json.bak_YYYYMMDD_premerge`
2. 脚本就位：把需要的脚本 **cp 复制**到 `~/.hermes/profiles/customer/scripts/`（不要软链，见坑 1；customer 库 cron 的 script 相对 customer/scripts/ 解析）
3. 用 customer 环境建任务：`export PATH=/home/ubuntu/.local/bin:$PATH; export HERMES_HOME=/home/ubuntu/.hermes/profiles/customer; hermes cron create ...`
   - 注意 `deliver`：原默认库任务若 `deliver=weixin:...` 而现役平台是飞书，会投递失败——迁移时改 `deliver=local` 或飞书目标
4. 删默认库僵尸：`hermes cron remove <job_id>`（逐个）
5. 放 `~/.hermes/cron/README.DEPRECATED` 说明去向，防下次审计被假状态骗
- 空操作脚本（如 `check-pairing.sh` 只有 `exit 0`）不要迁，直接弃用

## 核心坑 4：小机资源规划（1.9G/40G 广州机，2026-08-19 审计）

- **磁盘**：备份保留策略按盘校准——40G 盘 `-mtime +30` 保留 877M/日 ≈ 26G ≈ 5 天写满；应 `-mtime +5` + 异机/COS 副本
- **清理动作放脚本最前或 trap EXIT**：备份脚本 COS 上传超时（3600s 被杀）时第 5 步清理从未执行 → 磁盘涨到 89% 的直接原因；清理不能被可能超时的网络步骤拖住
- **临时脚本禁进 crontab**：`/tmp/restart_gw_cron.sh` 无 x 位每分钟失败 1487 次，一旦 `chmod +x` 会**每分钟重启 gateway**（地雷）；调试脚本放 `~/.hermes/scripts/`，用完删 crontab 条目
- 重任务（备份/归档）中期迁新加坡（59G/22G 余量），广州只留客户交互面

## 核心坑 5：交接包死锁 + 活跃会话活锁 + 指标口径错误（2026-08-19 claude 审计）

**死锁（P0，归档率恒为 0 的真凶）**：watchdog 先 `handoff_gate.py check`（要求交接包已存在）→ 才调 `session_rollover.py`，但交接包**只由 session_rollover 内部生成**（`handoff_builder.py` 唯一调用者）→ 新会话永远无交接包 → 永远 `NO_HANDOFF` → rollover 永不被调 → 归档率恒为 0。实证：新加坡 04:00-08:00 连续 5 周期 `BLOCKED:NO_HANDOFF`，token 冻结 266,044。
- **手动归档成功是因为先手动跑了 handoff_builder 生成交接包**才绕过的——自动化路径本身死锁，不是「保护在起作用」
- 解：闸**前**插入幂等 `prebuild_handoff()`（已有则复用、多份交人工 `MANUAL_REVIEW_REQUIRED`、损坏不覆盖），物理闸逻辑一字不动

**活跃会话活锁（P2）**：「静默 10 分钟才归档」是体验代理指标，不是安全条件——一直有消息的会话永不归档，token 无限涨（小鹿 241 万 token 就是这么来的，watchdog 一直「活跃跳过」）。「静默」≠任务完成（可能在等客户回图），有消息≠进行中（可能客户刚说完）。解：三层升级 L1 静默归档（保留）→ L2 **任务边界归档**（末条消息 role=assistant 且距今 ≥90s + 近 5min 无 tool 调用，客户无感，实测中位间隔 172s 能命中）→ L3 熔断强制（宽限耗尽、低峰时段、每周期限 1 个）。

**指标口径错误（P1）**：`sessions.input_tokens` 是**累计新增输入**，不是每次调用携带的上下文。真实单次上下文 = `cache_read_tokens / api_call_count`，两者无相关性（77 万累计的会话每次 316K，136 万累计的只有 271K）。按 `input_tokens` 排序会误杀高频短上下文、漏掉低频长上下文。成本按 `cum_cache_read` 计量（新加坡 136 万会话 3.25 亿缓存读 ≈ 65.5 元，比广州 241 万贵三倍）。

**压缩被架空（P3）**：`compression.threshold: 0.5` × 100 万窗 = 50 万上下文才压缩，watchdog 15 万就判失控 → 压缩一次没跑（compacted=0）。压缩不失忆、客户零感知，应先在 12 万触发（threshold 0.12），归档只做兜底。压缩与归档改动**分开灰度**，否则两个未验证机制同时变更无法归因。

完整方案：`workflow/projects/session-archiving-policy/会话归档策略_claude_20260819.md`（三层升级 diff + 灰度 G0-G3 + 回滚三级）。

## 核心坑 6：cron 一次性任务「没触发」先查 executions.db + agent.log，任务可能已触发只是 API 慢（2026-08-21 实测，朱雀三号复验）

用户报「到点没自动跑」时，`cronjob list` 可能仍显示 scheduled、next_run_at 已过、last_run_at=null、output 目录未建——表象像调度器没触发。但**任务可能已触发，只是模型 API 响应慢**（机器并发跑多个会话时，DeepSeek 首轮 90-100s+ 是常态，期间 cronjob list 状态还没翻篇）。

排查顺序（按证据强度）：
1. `~/.hermes/cron/executions.db` 的 executions 表：查该 job_id 有无 claimed_at + status=running 记录 = 调度器已认领（本次 12:00:41 claimed，但 jobs.json 仍显示 scheduled，**executions.db 才是触发真相**）
2. `~/.hermes/logs/agent.log`：grep `cron.scheduler: Running job '<任务名>' (ID: <job_id>)` + `[cron_<job_id>_<时间戳>]` 会话已建 = 任务真在跑
3. `ps aux | grep <实际业务进程>`（如 pipeline.py）：确认业务进程起来了
4. output 目录：`ls -t ~/.hermes/cron/output/<job_id>/`

确认「已触发只是慢」后：**别重启 gateway、别重建任务、别手动重跑**——等结果即可（重跑 = 双份付费）。一次性任务卡在 API 慢不是调度器故障，是高峰期并发把模型响应拖到 100s 级。

## 验证命令

```bash
hermes cron list                                  # 任务状态
hermes cron run <job_id>                          # 手动触发（立即）
ls -t ~/.hermes/cron/output/<job_id>/ | head      # 最近输出
python3 ~/.hermes/scripts/context_rollover_watchdog.py --dry-run --db <db>  # dry-run 只报告不归档
```

## Pitfalls

- **包装脚本不转发参数（0819 实测）**：`context_rollover_watchdog.sh` 里是 `exec python3 ... --threshold ...`（参数固化），**不带 `"$@"` 转发**——`bash watchdog.sh --dry-run` 的 `--dry-run` 会被吞掉，实际执行的是**真实归档**。想 dry-run 必须直接调 py：`python3 scripts/context_rollover_watchdog.py --dry-run --db ...`，不要通过包装 .sh 传参。本会话踩过：以为 dry-run 实际跑了真实归档，幸好交接包物理闸（BLOCKED:NO_HANDOFF）拦住没归档成功。如需包装脚本支持传参，加 `"$@"` 并在 exec 行追加。
- **schedule_display 与实际 expr 可能不一致（0819 审计 P2-3）**：`cost-meter-retry-5m` job_id 和 display 写 `*/5`，实际 `schedule.expr=*/30`——调度按 `schedule.expr` 走（cron/jobs.py compute_next_run），display 只供展示。运维看板会骗人；确定目标频率后统一三处（job_id/expr/display）
- **改 watchdog 阈值（160K/300 次）只改包装 .sh 里的参数即可**，不要改 py 默认值（py 默认值是对齐用的，包装才是线上值）
- 小鹿（广州机 customer profile）数据库在 `/home/ubuntu/.hermes/profiles/customer/state.db`，新加坡机在 `/home/ubuntu/.hermes/state.db`——跨机跑脚本要带对 --db
- 手动触发 cron run 后看输出要等几秒（脚本有扫描耗时），别立刻查 output 目录
- watchdog 输出文件在 `~/.hermes/cron/output/<job_id>/<时间戳>.md`，内容含 BLOCKED 原因，排障直接看这个
