# Customer Profile Architecture

## 小鹿的网关路径

| 资源 | 路径 |
|:-----|:-----|
| 网关PID | `/home/ubuntu/.hermes/profiles/customer/gateway.pid` |
| 状态文件 | `/home/ubuntu/.hermes/profiles/customer/gateway_state.json` |
| state.db | `/home/ubuntu/.hermes/profiles/customer/state.db`（含sessions表+gateway_routing表） |
| SOUL.md | `/home/ubuntu/.hermes/profiles/customer/SOUL.md` |
| .env | `/home/ubuntu/.hermes/profiles/customer/.env` |
| skills | `/home/ubuntu/.hermes/profiles/customer/skills/`（独立副本，非symlink） |
| sessions路由镜像 | `/home/ubuntu/.hermes/profiles/customer/sessions/sessions.json`（只读，实际在state.db） |
| 日志 | `/home/ubuntu/.hermes/profiles/customer/logs/agent.log` + `gateway.log` |

## 关键发现

### 1. skills独立副本

`/home/ubuntu/.hermes/profiles/customer/skills/` 下的文件与主目录 `/home/ubuntu/.hermes/skills/` 是**不同inode的独立文件**。改主目录后必须手动cp到客户profile，否则小鹿用旧版。

同步命令：
```bash
cp /home/ubuntu/.hermes/skills/<category>/<skill>/SKILL.md \
   /home/ubuntu/.hermes/profiles/customer/skills/<category>/<skill>/SKILL.md
```

### 2. state.db的两张表

| 表 | 用途 | 说明 |
|:---|:-----|:-----|
| `sessions` | 每个会话的完整记录，含`system_prompt`字段 | SOUL.md在此缓存，改文件不影响已有会话 |
| `gateway_routing` | 会话路由索引 | 独立于sessions表，存会话创建的session_key→session_id映射 |

**根因：** 只删sessions不改gateway_routing，网关用路由索引恢复旧会话→旧system prompt→改文件无效。

### 3. 网关进程的自杀限制

在网关进程内直接`kill -SIGTERM`会触发拦截提示「不能从网关进程内自杀」。正确做法：
- 走`terminal(background=True)`杀
- 或从外部shell执行

### 4. system_prompt为NULL的恢复

新会话的`system_prompt`字段为NULL（sp_len=0）时，LLM用fallback默认身份回复。修复办法：重走全套清除+重启流程。

## 常用SQL查询

```sql
-- 查看所有飞书会话及system_prompt状态
SELECT id, chat_type, length(coalesce(system_prompt,'')) as sp_len 
FROM sessions WHERE source='feishu';

-- 查看所有飞书路由
SELECT session_key FROM gateway_routing 
WHERE session_key LIKE 'agent:main:feishu:%';

-- 清理所有飞书数据
DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE source='feishu');
DELETE FROM sessions WHERE source='feishu';
DELETE FROM gateway_routing WHERE session_key LIKE 'agent:main:feishu:%';
```
