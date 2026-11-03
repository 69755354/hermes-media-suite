# 飞书 Session Key 分裂修复实录（2026-08-28）

## 问题

飞书 DM 和群聊每条消息创建新 session（history=0），AI 完全记不住之前的对话。

## 根因（代码+数据库双重验证）

飞书 lark_oapi SDK 的 `message.root_id` 在 DM 和群聊中都被设置为**消息自身的 ID**（`om_xxx`/`omt_xxx`），不是线程标识符。飞书适配器 `adapter.py` 行 3351：
```python
thread_id = getattr(message, "thread_id", None) or getattr(message, "root_id", None) or None
```

`build_session_key()` 在 DM 路径（行 1142）和群聊路径（行 1185）都把 `thread_id` 拼进 key。

**额外发现**：群聊混合策略——有 thread_id 时走 thread 隔离，没 thread_id 时走 per-user 隔离（拼 union_id），两种 key 互不匹配。

## 实际数据

### 飞书 DM（<HOME_CHAT_ID>）
- 25 个 session 全用 key `agent:main:feishu:dm:oc_c3e8253f...`（无 thread_id），1 个活跃，24 个已归档
- 8/16 路由 entry 的 origin.thread_id = `om_x100b67295c8...`（消息 ID），指向已删除 session
- 8/28 新消息无 thread_id → 新 session

### 飞书群聊（<MATERIAL_GROUP_CHAT_ID>）
- 6 个不同 session key：
  - 4 个带 `om_xxx`（消息 ID 作 thread_id）
  - 1 个带 `omt_xxx`（话题消息 ID）
  - 1 个带 `on_c1c12bab`（union_id，per-user 隔离）
- gateway_routing 表有 8 条飞书路由 entry，每条指向不同 session

## 代码改动（gateway/session.py，5 处）

### 1. DM 路径行 1146
```python
# 原: if source.thread_id:
# 改:
if source.thread_id and source.platform != Platform.FEISHU:
```

### 2. DM fallback 行 1163
同上 guard。

### 3. DM bare fallback 行 1166
同上 guard。

### 4. 群聊路径行 1195
```python
effective_thread_id = source.thread_id or source.prospective_thread_id
if source.platform == Platform.FEISHU:
    effective_thread_id = None
```

### 5. 群聊路径行 1219
```python
isolate_user = group_sessions_per_user
if effective_thread_id and not thread_sessions_per_user:
    isolate_user = False
if source.platform == Platform.FEISHU:
    isolate_user = False
```

## 验证脚本

```python
import sys
sys.path.insert(0, "/home/ubuntu/.hermes/hermes-agent")
from gateway.config import Platform
from gateway.session import build_session_key, SessionSource

# Feishu DM: 3 different thread_ids → same key ✓
dm1 = SessionSource(platform=Platform.FEISHU, chat_id="oc_xxx", chat_type="dm",
    thread_id="om_msg_1", user_id="ou_1", user_id_alt="on_1")
dm2 = SessionSource(platform=Platform.FEISHU, chat_id="oc_xxx", chat_type="dm",
    thread_id=None, user_id="ou_1", user_id_alt="on_1")
assert build_session_key(dm1) == build_session_key(dm2)

# Feishu group: different users, different thread_ids → same key ✓
g1 = SessionSource(platform=Platform.FEISHU, chat_id="oc_grp", chat_type="group",
    thread_id="om_msg_a", user_id="ou_a", user_id_alt="on_a")
g2 = SessionSource(platform=Platform.FEISHU, chat_id="oc_grp", chat_type="group",
    thread_id=None, user_id="ou_b", user_id_alt="on_b")
assert build_session_key(g1) == build_session_key(g2)

# Slack DM: different thread_ids → different keys (not affected) ✓
s1 = SessionSource(platform=Platform.SLACK, chat_id="D1", chat_type="dm",
    thread_id="t1", scope_id="T1")
s2 = SessionSource(platform=Platform.SLACK, chat_id="D1", chat_type="dm",
    thread_id="t2", scope_id="T1")
assert build_session_key(s1) != build_session_key(s2)
```

## 路由表清理 SQL

```sql
-- 删 DM 带 thread_id 的路由
DELETE FROM gateway_routing WHERE session_key LIKE 'agent:main:feishu:dm:oc_%:om_%';
-- 删群聊带 om_/omt_/on_ thread_id 的路由
DELETE FROM gateway_routing WHERE session_key LIKE 'agent:main:feishu:group:oc_%:om_%';
DELETE FROM gateway_routing WHERE session_key LIKE 'agent:main:feishu:group:oc_%:omt_%';
DELETE FROM gateway_routing WHERE session_key LIKE 'agent:main:feishu:group:oc_%:on_%';
```

## 边界情况

1. **飞书 DM 多线程？** 飞书 DM 是单一聊天流，没有 forum topics，不存在多线程
2. **群聊不同人消息混在一起？** 3-5 人协作群，共享上下文收益大于隔离；消息含 user_name + mention hint
3. **飞书 reply_to？** `parent_id`/`upper_message_id` 是消息回复链，不是线程。reply_to 信息已通过 reply_to_message_id/reply_to_text 传 AI
4. **旧 session 迁移？** 不迁移。归档 session 保留，session_search 可检索
5. **compression 够不够？** threshold=0.16 足够。DM 最大 579 条消息都扛住了，群聊量不会超过
6. **其他平台影响？** 零。5 处 guard 全用 Platform.FEISHU 条件

## 飞书没有真正的 Thread 概念

飞书消息有 parent_id（回复的上一条消息 ID）和 root_id（消息树根节点 ID），是消息回复链（类似邮件 in-reply-to），不是 Slack thread / Telegram forum topic 那样的独立线程空间。所有消息在同一个聊天流里。
