# 交接包时序缺口 + 内容质量修复（2026-08-27 诊断 + 已修复）

## 背景

用户报告小鹿（广州机 customer profile，GLM-5.2）「聊着聊着变了新会话，不记得前面的内容了，还得我提醒说到哪了」。新加坡机飞书 bot 同样有这个问题。

排查发现两个独立问题叠加：rollover 时序缺口 + 交接包内容质量差。

## 问题1：rollover 后 AGENTS.md 注入的是旧交接包

### 现象

新会话启动时 AGENTS.md 里指向的交接包不是刚 rollover 的那个，而是上一个整点的旧包。新会话读旧包 → 上下文对不上。

### 根因

```
时间线：
T+0min   rollover 发生（tokens 撑满 → Hermes 内置压缩/归档 → 新会话启动）
         ↓ 新会话读 AGENTS.md → 读到的是旧交接包（上个整点写的）
T+60min  handoff_injector cron 才跑 → 写入新交接包到 AGENTS.md
         ↓ 但此时新会话已经在用旧上下文了，用户已经感知失忆
```

`handoff_injector.py` cron 每 60 分钟跑一次。rollover 是实时的，不等 cron。

watchdog 归档后已调 injector（代码 694-700 行），但 Hermes 内部 compression 触发的 rollover 不走 watchdog，不调 injector。

### 诊断方法

```bash
# 对比 AGENTS.md 归档时间 vs archives 目录最新文件时间
grep "归档时间" ~/.hermes/profiles/customer/AGENTS.md
ls -lt ~/.hermes/archives/handoff_*.json | head -3
# 如果 AGENTS.md 日期远早于 archives 最新文件 → 注入失败
```

### 已落地修复

watchdog 归档后调 injector 时加 `--out` 参数（见问题2修复第3点）。

### 仍待解决

1. Hermes 内部 compression 触发的 rollover 不调 injector。解法方向：改 Hermes 源码加 post-rollover hook，或把 injector cron 频率从 60min 改到 5min。

2. **`heuristic_extract()` 仍污染 pending_tasks / next_step_hint（0827 晚间实测确认）**：
   - `_is_noise()` 过滤了 tool/告警，但 assistant 消息本身含调试分析文本
   - `heuristic_extract()` 关键词匹配不分 role——assistant 说"需要修复"也被当 pending_task
   - 实测最新交接包 `pending_tasks` = "heuristic_extract 用关键词匹配…匹配到的全是文件内容片段"（assistant 诊断文本）
   - `next_step_hint` = "而且 customer AGENTS.md 里还是旧内容"（同上）
   - `last_user_message`/`last_assistant_message` 字段工作正常（直接提取，不受影响）
   - **解法方向**：`heuristic_extract()` 应只从 `role=user` 消息匹配关键词，或加 assistant 消息长度阈值（排除长分析段落）

---

## 问题2：交接包内容接不上最后一句话（已修复）

### 现象

AGENTS.md 里的"上下文锚点"是告警推送内容，不是用户对话。"待办"是文件源码片段。

### 改前实测交接包内容

```
session_id: 20260826_235311_bad78170
recent_20_messages 最后5条：
  [tool] {"output": "total 1752\ndrwx------ 35 ubuntu ubuntu..."}  ← 文件列表
  [assistant] （空）
  [tool] {"success": true, "count": 18, "jobs": [...]}  ← cron list 输出
  [assistant] [P0] 物理闸告警 PROTECTED_WRITE_ATTEMPT...  ← 告警推送
  [assistant] [P0 RE-PUSH] 物理闸告警 PROTECTED_WRITE_ATTEMPT...  ← 告警重推

pending_tasks: {"content": "1|#!/usr/bin/env python3..."}  ← 脚本源码
next_step_hint: {"content": "1|#!/usr/bin/env python3..."}  ← 同上
上下文锚点: [P0 RE-PUSH] 物理闸告警 PROTECTED_WRITE_ATTEMPT...  ← 告警
```

全是 tool 输出和告警推送，没有一条是用户真正说的对话内容。

### 根因

1. `get_messages()` 取 user/assistant/tool 三种 role，tool 输出和告警推送混在一起
2. `heuristic_extract()` 用关键词匹配（待确认/需要/继续/下一步），匹配到文件内容里的这些词
3. `summarize()` 提取"最后一条非 tool 消息"做锚点，但 assistant 消息可能是告警推送

### 已落地修复（2026-08-27 双机同步）

#### handoff_builder.py 三处改动

**改动1：新增 `_is_noise()` 函数**
```python
def _is_noise(msg):
    """判断消息是否为噪声（tool 输出 / 告警推送 / 空内容）"""
    role = msg.get('role', '')
    content = (msg.get('content') or '').strip()
    if not content:
        return True
    if role == 'tool':
        return True
    noise_prefixes = (
        '[P0', '[P1', '[P2', 'WATCHDOG:', 'MONITOR:', 'ALERT:',
        'PROTECTED_WRITE', '物理闸告警', '[OUT-OF-BAND',
        'ALERT_PIPELINE', 'alert_id:', '确认命令: alert_pipeline',
    )
    if any(content.startswith(p) for p in noise_prefixes):
        return True
    if content.startswith('{"output') or content.startswith('{"success'):
        return True
    return False
```

**改动2：`get_messages()` 加 `conversation_only` 参数**
- `conversation_only=True` 时只取 user/assistant，取 limit×5 条后过滤噪声再截 limit
- `conversation_only=False`（默认）行为不变，向后兼容

**改动3：`generate_handoff()` 用纯对话消息做提取 + 新增字段**
- 新增 `conv_messages = get_messages(db, sid, limit, conversation_only=True)`
- `heuristic_extract(conv_messages)` 和 `structured_extract(conv_messages)` 用纯对话
- 交接包新增：`recent_conversation`（纯对话消息列表）、`last_user_message`（用户最后说的，不截断）、`last_assistant_message`（机器人最后回的，不截断）

#### handoff_injector.py 两处改动

**改动1：`summarize()` 优先用新字段**
```python
# 优先用 last_user_message / last_assistant_message 做上下文锚点
last_user = (data.get("last_user_message") or "").strip()
last_assistant = (data.get("last_assistant_message") or "").strip()
# 新字段为空时退化到从 recent_conversation 提取（不再用 recent_20_messages）
```
AGENTS.md 输出格式：
```
- 用户最后说的: <最后一条 user 消息，最多 500 字>
- 机器人最后回的: <最后一条 assistant 消息，最多 500 字>
```

**改动2：新增 `--out` 和 `--archives` 参数**
- `--out` 默认主 profile AGENTS.md，customer 需传 `--out /home/ubuntu/.hermes/profiles/customer/AGENTS.md`
- `--archives` 默认 `/home/ubuntu/.hermes/archives`
- `OUT` 从全局常量改为 main() 内局部变量（`OUT = args.out`）

#### context_rollover_watchdog.py（广州机）一处改动

injector 调用加 `--out`：
```python
# 改前
[sys.executable, HANDOFF_INJECTOR],
# 改后
[sys.executable, HANDOFF_INJECTOR, "--out", "/home/ubuntu/.hermes/profiles/customer/AGENTS.md"],
```

### 改前 vs 改后 AGENTS.md 对比

**改前**：
```
- 上下文锚点: [P0 RE-PUSH] 物理闸告警 PROTECTED_WRITE_ATTEMPT
  主机: gz-customer-01 ...
- 待办: {"content": "1|#!/usr/bin/env python3...（handoff_builder.py 源码）
```

**改后**：
```
- 待办: 0.5 秒帧全过。继续核验中间动作帧：
- 用户最后说的: 交接包呢
- 机器人最后回的: 老爷，错了。您没明确说「跑」，我就提交了镜2 跟随版出片，
  违反出片铁律。如实汇报：已生成完，9 秒、快乐马 r2v，花了 0.50 元...
```

### 验证命令

```bash
# 测试 builder 生成新字段
python3 ~/.hermes/scripts/handoff_builder.py \
  --session-id <sid> --db <db> --out-dir /tmp/test_handoff
python3 -c "
import json
with open('/tmp/test_handoff/handoff_*.json') as f:
    d = json.load(f)
print(f'last_user_message: {repr(d.get(\"last_user_message\",\"\")[:200])}')
print(f'last_assistant_message: {repr(d.get(\"last_assistant_message\",\"\")[:200])}')
"

# 测试 injector 写入 customer AGENTS.md
python3 ~/.hermes/scripts/handoff_injector.py \
  --verbose --out ~/.hermes/profiles/customer/AGENTS.md
cat ~/.hermes/profiles/customer/AGENTS.md

# 同步到广州机
scp -P 2222 ~/.hermes/scripts/handoff_builder.py ubuntu@127.0.0.1:~/.hermes/scripts/
scp -P 2222 ~/.hermes/scripts/handoff_injector.py ubuntu@127.0.0.1:~/.hermes/scripts/
scp -P 2222 ~/.hermes/scripts/handoff_injector.py ubuntu@127.0.0.1:~/.hermes/profiles/customer/scripts/
```

### 噪声过滤词表（持续补充）

`_is_noise()` 当前过滤的前缀和模式：
- `[P0`, `[P1`, `[P2` — 告警级别前缀
- `WATCHDOG:`, `MONITOR:`, `ALERT:` — 监控推送
- `PROTECTED_WRITE`, `物理闸告警` — 安全闸告警
- `[OUT-OF-BAND` — 带外消息
- `ALERT_PIPELINE`, `alert_id:`, `确认命令: alert_pipeline` — 告警链路心跳
- `{"output`, `{"success` — 纯 JSON 工具输出伪装成 assistant

如果未来发现新的噪声类型，往 `_is_noise()` 的 `noise_prefixes` 元组里加。

## 相关脚本位置

| 脚本 | 新加坡机 | 广州机 |
|:--|:--|:--|
| handoff_injector.py | `~/.hermes/scripts/handoff_injector.py` | `~/.hermes/profiles/customer/scripts/handoff_injector.py`（独立副本） |
| handoff_builder.py | `~/.hermes/scripts/handoff_builder.py` | 同上（通过 session_rollover 调用） |
| handoff_gate.py | `~/.hermes/scripts/handoff_gate.py` | 同上 |
| AGENTS.md | `~/.hermes/AGENTS.md` | `~/.hermes/profiles/customer/AGENTS.md` |
| archives | `~/.hermes/archives/` | `~/.hermes/archives/`（共享目录） |
