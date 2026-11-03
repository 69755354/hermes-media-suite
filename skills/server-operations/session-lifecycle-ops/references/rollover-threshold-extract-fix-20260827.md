# Rollover 阈值调高 + 交接包提取逻辑第二轮修复（2026-08-27 晚间）

## 背景

0827 白天修了 `at_hour: 'null'` TypeError 崩溃 + 双 service app_id 冲突后，gateway 恢复了，但 rollover 本身有两个遗留问题：

1. **阈值太低**：0827 白天把 hard-ctx 从 250K 降到 180K（为修活跃跳过），但 GLM 5.2 context window 比 DeepSeek 短 2-3 倍，180K 在 GLM 下频繁触发归档（一天7+次）
2. **`heuristic_extract()` 仍污染**：第一轮修复加了 `_is_noise()` 过滤 tool/告警，但 assistant 调试文本里的"需要""继续""下一步"仍被误抽为 pending_tasks

## 修复1：阈值调高（两机统一）

### 改前 vs 改后

| 参数 | 改前 | 改后 |
|:--|:--|:--|
| threshold | 160,000 | 300,000 |
| hard-ctx | 180,000（SG）/ 150,000（GZ） | 350,000 |
| fuse-ctx | 400,000（SG）/ 250,000（GZ） | 500,000 |

### 改的文件

**新加坡机** `~/.hermes/scripts/context_rollover_watchdog.sh`：
```diff
-    --threshold 160000 \
+    --threshold 300000 \
-    --hard-ctx 180000 \
-    --fuse-ctx 400000 \
+    --hard-ctx 350000 \
+    --fuse-ctx 500000 \
```

**广州机** `~/.hermes/profiles/customer/scripts/gz_rollover_watchdog.sh`：
```diff
-    --threshold 160000 \
+    --threshold 300000 \
-    --hard-ctx 150000 \
-    --fuse-ctx 250000 \
+    --hard-ctx 350000 \
+    --fuse-ctx 500000 \
```

### 依据

实测数据（广州机 state.db）：
- DeepSeek V4 Flash 会话能到 60-80 万 tokens 才触发归档
- GLM 5.2 会话 16-50 万就触发
- 同样 16 万阈值，DeepSeek 下很少触发，GLM 下一天7+次

GLM context window 比 DeepSeek 短 2-3 倍，但 30 万对 GLM 仍安全（实测 GLM 会话最高到 51 万才归档）。

## 修复2：heuristic_extract() 只从 USER 消息提取

### 改前问题

```python
# 改前：遍历所有消息（user + assistant）
for msg in messages:
    content = msg['content']
    for line in content.splitlines():
        if any(kw in line for kw in TASK_KEYWORDS):  # '待确认','需要','继续','下一步'
            pending_tasks.append(line.strip())        # ← assistant 说"需要修复"也被抽
```

实测最新交接包 `pending_tasks` 内容：
```
- `heuristic_extract` 用关键词匹配 `待确认/需要/继续/下一步`，匹配到的全是文件内容片段而不是对话
但 AGENTS.md 还是旧的——因为 injector 读的是...
```
这全是 assistant 的调试分析文本，不是用户实际待办。

### 改后

```python
# 改后：只从 USER 消息提取
for msg in messages:
    if msg.get('role') != 'user':
        continue
    content = msg.get('content', '') or ''
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(kw in line for kw in TASK_KEYWORDS):
            pending_tasks.append(line)
        if NEXT_STEP_KEYWORD in line:
            next_step_hint = line
```

### 验证

```bash
python3 /tmp/test_handoff.py
# 输出：
# 对话消息: 20 条
# === pending_tasks (should be clean) ===
# ''  ← 干净！之前有5段调试笔记
# === next_step_hint ===
# ''  ← 干净！
# === last_user_message ===
# '改这两个脚本'  ← 正常
```

## 修复3：structured_extract() 也只从 USER 提取

同原理，`task_goal` 和 `todo_items` 只从 `role=user` 提取；`completed_nodes` 和 `key_constraints` 保留从 user+assistant 提取（状态报告有意义）。

### 改前

```python
for msg in messages:
    if msg.get('role') not in ('user', 'assistant'):
        continue
    # 所有字段都从 user + assistant 提取
    if any(kw in line for kw in GOAL_KW):
        goal_lines.append(line)  # ← assistant 说"目标是"也被抽
    if any(kw in line for kw in TODO_KW):
        todo_lines.append(line)  # ← assistant 说"继续"也被抽
```

### 改后

```python
for msg in messages:
    role = msg.get('role')
    content = msg.get('content', '') or ''
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        # task_goal 和 todo_items 只从 user 提取
        if role == 'user':
            if any(kw in line for kw in GOAL_KW):
                goal_lines.append(line)
            if any(kw in line for kw in TODO_KW):
                todo_lines.append(line)
        # completed_nodes 和 key_constraints 从 user + assistant 提取
        if role in ('user', 'assistant'):
            if any(kw in line for kw in DONE_KW):
                done_lines.append(line)
            if any(kw in line for kw in CONS_KW):
                cons_lines.append(line)
```

## 广州机同步

```bash
# scp 修改后的脚本到广州机
scp -P 2222 ~/.hermes/scripts/handoff_builder.py ubuntu@127.0.0.1:~/.hermes/scripts/
scp -P 2222 ~/.hermes/scripts/handoff_injector.py ubuntu@127.0.0.1:~/.hermes/scripts/
scp -P 2222 ~/.hermes/scripts/handoff_injector.py ubuntu@127.0.0.1:~/.hermes/profiles/customer/scripts/

# 广州机 watchdog 阈值改
ssh -p 2222 ubuntu@127.0.0.1 'bash /tmp/fix_gz_watchdog.sh'
# 内含：
# sed -i 's/--threshold 160000/--threshold 300000/'
# sed -i 's/--hard-ctx 150000/--hard-ctx 350000/'
# sed -i 's/--fuse-ctx 250000/--fuse-ctx 500000/'

# 语法验证
ssh -p 2222 ubuntu@127.0.0.1 'python3 -c "import py_compile; py_compile.compile(\"/home/ubuntu/.hermes/scripts/handoff_builder.py\", doraise=True); print(\"SYNTAX OK\")"'
```

## 仍待解决

- **Hermes 内部 compression 触发的 rollover 不调 injector**：watchdog 归档后会调 injector，但 Hermes 自带的 context compression 超限直接 rollover 时没有 hook 调 injector。解法方向：改 Hermes 源码加 post-rollover hook，或把 injector cron 频率从 60min 改到 5min。
