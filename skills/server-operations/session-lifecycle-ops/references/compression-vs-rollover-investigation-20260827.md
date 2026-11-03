# Hermes 内部 compression vs cron watchdog rollover 排查（2026-08-27）

## 问题

MEMORY.md 记着「Hermes 内部 compression 触发的 rollover 不调 injector」，列为待解决。用户要求排查修。

## 排查过程

### 1. 找 compression 相关代码

```
~/.hermes/hermes-agent/agent/conversation_compression.py — 压缩入口
~/.hermes/hermes-agent/agent/context_compressor.py — 压缩执行
~/.hermes/hermes-agent/gateway/session.py — 会话管理（advance_compression_session）
~/.hermes/hermes-agent/hermes_state.py — publish_compression_child / archive_and_compact
```

### 2. compression 触发链路

conversation_compression.py 行 3260-3360：
1. LLM 压缩旧会话消息 → 生成摘要
2. `publish_compression_child()` 创建子会话（新 session_id）
3. 压缩摘要作为 messages 注入子会话
4. `migrate_goal_to_session()` 迁移 /goal
5. `migrate_heartbeat_to_session()` 迁移 heartbeat
6. `get_next_title_in_lineage()` 继承标题
7. **不调 handoff_builder.py 或 handoff_injector.py**

### 3. compression 摘要质量（实测）

广州机会话 `20260827_121544_0758c83b` 的压缩摘要（message id=8517）：
- 总长 6868 字
- 包含：任务目标、关键文件路径（10+ 个）、关键约束、用户未回答问题、台词分配、模型规则差异
- 结构化字段：`## Relevant Files` / `## Critical Context` / `## Pruned Skills`
- 由 LLM 生成（不是关键词匹配），质量远高于 handoff_builder

摘要标记特征：`[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted into the summary below. This is a handoff from a previous context window`

### 4. compression 配置差异

| 机器 | compression 配置 | threshold 含义 | 是否触发 |
|:--|:--|:--|:--|
| 新加坡 | 无配置（默认 0.50） | 上下文用到 50% 才压缩 | GLM 5.2 下基本不触发 |
| 广州 | threshold: 0.16 | 上下文用到 16% 就压缩 | 频繁触发 |

### 5. 两套机制对比

| | compression（内部） | rollover（cron watchdog） |
|:--|:--|:--|
| 触发者 | gateway 进程内部 | cron 每 10 分钟 |
| 记忆传递 | 压缩摘要注入 messages 表 | handoff 包 + AGENTS.md |
| 摘要质量 | LLM 生成，高质量 | 关键词提取，低质量（已修） |
| 是否调 injector | 不调，不需要 | 调 |
| 新会话能否读到 | 能，messages 表 | 能，AGENTS.md |

## 结论

compression 不调 injector **不是问题**。两套机制独立：
- compression 走 messages 表传递记忆，新会话加载消息时能看到压缩摘要
- rollover 走 handoff 包 + AGENTS.md，是 cron 归档时的记忆传递

不需要修 compression 加 injector 调用。
