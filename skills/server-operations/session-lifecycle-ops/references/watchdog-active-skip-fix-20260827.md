# Watchdog 活跃跳过修复实录（2026-08-27）

## 问题

小鹿（广州机 customer profile）会话跑到 180K tokens，超过 watchdog threshold 160K，但 watchdog 看会话活跃就 `活跃跳过`，等 180 分钟宽限期满才归档。用户感知"动不动就丢上下文"。

## 根因

watchdog 三层升级模型（L1 静默/L2 任务边界/L3 宽限耗尽强制），但小鹿一直活跃：
- L1 不触发（10 分钟内有消息）
- L2 等任务边界（`at_task_boundary`：最后消息 role=assistant + 90s + 无工具在跑），但用户连打 → 永不命中
- L3 要等 180 分钟宽限期 → 等到了但会话已太长触发 Hermes 内置压缩 → "失忆"

另外 `classify_hard` 只看 `ctx_per_call = cache_read_tokens / api_call_count`（单次上下文），不看累计 input。小鹿会话 222K 累计 token 但每次 ctx 仅 89K → 不超 180K 硬限 → 不触发硬判据。

## 三处代码改动

### 1. 主逻辑：去掉活跃跳过 + 宽限期等待

**文件：** `~/.hermes/scripts/context_rollover_watchdog.py`（两机同步）

**旧逻辑（L2/L3）：**
```python
# 未越硬阈值 / L3 未启用 / pinned → 活跃跳过
if not hard or not args.enable_force or pinned:
    skipped_active.append(...)
    continue
# L2：等任务边界
if at_task_boundary(cur, sid, now):
    do_archive(...)
    continue
# L3：宽限期耗尽 or 熔断 → 强制
if not (fuse or waited_min >= args.grace_minutes):
    skipped_grace.append(...)
    continue
```

**新逻辑：**
```python
# 越硬阈值 → 直接归档（先生成交接包），不等任务边界/宽限期
if not hard:
    skipped_active.append(...)
    continue
if pinned:
    skipped_active.append(..., "（pinned）")
    continue
# 有未闭合工具调用时顺延一次（防归档中断进行中的工具）
if has_open_tool_calls(cur, sid, now):
    if grace.extends(sid) < MAX_GRACE_EXTENDS:
        grace.bump(sid)
        skipped_inflight.append(...)
        continue
# 直接归档
st, detail = do_archive(sid, hard_reason, force=True, args=args)
```

### 2. classify_hard：新增累计 input 硬判据

**旧：** 只看 `ctx_per_call = cache // calls`
**新：** 增加 `if args.hard_ctx and calls > 0 and inp > args.hard_ctx: return ("HARD", f"累计token超硬阈({inp:,})")`

### 3. predict_level（dry-run 预测）：同步改

**旧：** `SKIP-ACTIVE` / `L2` / `L3-grace` / `L3-fuse` / `L3-force`
**新：** `SKIP-SOFT` / `SKIP-PINNED` / `L2-顺延(有未闭合工具调用)` / `L2-force(超硬限直接归档)`

### 4. 参数调整

`context_rollover_watchdog.sh` 两机都改 `--hard-ctx 250000` → `--hard-ctx 180000`。

## 部署步骤

1. `cp watchdog.py watchdog.py.bak_20260827`（两机各备份）
2. Python 脚本 patch（先改新加坡，scp 到广州）
3. `sed -i 's/--hard-ctx 250000/--hard-ctx 180000/' watchdog.sh`（两机）
4. `python3 -c "import py_compile; py_compile.compile(...); print('OK')"` 语法检查
5. `dry-run` 验证：膨胀会话从 `SKIP-ACTIVE` 变为 `L2-force` 或 `L2-顺延`
6. 新加坡机 crontab 补上：`*/10 * * * * /home/ubuntu/.hermes/scripts/context_rollover_watchdog.sh >> /home/ubuntu/.hermes/logs/watchdog.log 2>&1`

## 验证结果

```
WATCHDOG: 归档 2 个失控会话
  [DRY-RUN:L2-顺延(有未闭合工具调用)] 20260826_232722_093a8672 token超限(452,072)
  [DRY-RUN:L2-顺延(有未闭合工具调用)] 20260827_005302_037eba23 token超限(223,444)
```

两个会话都从 `SKIP-ACTIVE` 变为 `L2-顺延`（有工具在跑）→ 工具跑完后会直接 `L2-force` 归档。
