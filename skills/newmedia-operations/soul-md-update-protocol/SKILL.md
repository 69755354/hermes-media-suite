---
name: soul-md-update-protocol
title: SOUL.md更新生效协议
description: 修改SOUL.md或其他技能文件后，强制执行的缓存清理+重启流程，确保改动100%生效。
---

## 🚨 为什么要这套流程

Hermes系统提示词分三层缓存：**stable（身份/SOUL.md）→ context → volatile（时间戳/路径）**。

- SOUL.md在**会话创建时**加载一次，存入`state.db`的`system_prompt`字段，中途改文件**不会**更新已存在的会话
- `gateway_routing`表独立于`sessions`表，光删会话不删路由，网关会恢复旧会话
- 网关进程内`kill -SIGTERM`会被拦截（提示"不能从网关进程内自杀"），需走后台进程

## 🚨 排坑经验（本会话沉淀）

### 坑0：不生效时先查官方文档，不靠试猜

**本会话中用户多次纠正的重灾区。** 改完不生效时，第一反应不是试各种操作，是**查官方文档理解缓存机制**。

**✅ 正确调试路径：**
1. 读官方文档 https://hermes-agent.nousresearch.com/docs/ → Prompt Assembly → 理解三层缓存（stable/context/volatile）
2. 看SOUL.md文档 → Personality & SOUL.md → 理解`$HERMES_HOME/SOUL.md`加载机制
3. 排查已知issue（搜索GitHub issues + Reddit）
4. 先搞清楚「为什么」再动手修

**❌ 错误调试路径（本会话反复踩的坑）：**
- 不改文件就删DB → 无效 ❌
- 改了文件只删sessions不删routing → 无效 ❌  
- 杀了网关不验证system_prompt → 以为生效了实际没 ❌
- 把海外服务器地址记错导致胡乱归因 ❌

### 坑1：SOUL.md指令不够强硬 → LLM不照搬

首次对话欢迎语要求「一字不差输出」，但LLM会自行摘要成简洁版。本条skill第1步已修正：模板前加「必须一字不差输出以下内容，不准自己编不准改词」。

### 坑2：会话system_prompt字段可能为NULL

清完DB重启后，群聊会话自动重建时可能system_prompt为空（sp_len=0），LLM用fallback默认身份回复，看不到新SOUL.md。修复：验sp_len>100才通过，为0必须重走全套。

### 坑3：群聊通知线程 vs 私聊DM走不同会话路由

群聊的@/回复消息走`agent:main:feishu:group:xxx:on_xxx`路由（thread notification），这类会话的system_prompt加载机制与私聊DM不同。清DB时**必须连gateway_routing一起清**，否则网关用旧路由恢复旧会话。

### 坑4：skills改完主目录≠客户profile生效

`/home/ubuntu/.hermes/skills/`和`/home/ubuntu/.hermes/profiles/customer/skills/`是独立副本（不同inode），改了主目录必须cp同步到客户profile。

### 坑5：DeepSeek API级KV缓存

即使DB清了、网关重启了、新会话system_prompt正确加载了，DeepSeek服务端的disk-level prefix caching可能还命中旧前缀，导致输出看起来没变。前缀字节变化后（SOUL.md改了第一段），下一轮请求自动miss。如果验证时发现新会话system_prompt正确但输出仍是旧的，等1-2分钟再试（缓存TTL）。

### 💡 调试铁律：不生效时先查官方文档，不靠试猜

本会话中用户反复纠正：改完后不生效，**第一反应不是试，是查文档**。

**正确路径：**
1. https://hermes-agent.nousresearch.com/docs/ → 查Prompt Assembly页面理解缓存层级
2. 查state.db确认system_prompt是否正确加载（sp_len>100）
3. 查gateway_routing表确认路由已清
4. 所有步骤确认完再尝试

**常见错误路径：**
- ❌ 试了一圈才去查文档 → 浪费时间，用户不满
- ❌ 不知道原因就去问用户「为什么没变」
- ❌ 反复改内容但不走完整三步

## 完整操作链

### 🚨 安全锁步骤（2026-07-20 新增，必须先改权限再写，写完后锁回+更新哈希）

核心规则文件（SOUL.md、关键SKILL.md）已设为 **chmod 444（只读）**。编辑前必须先开写权限，编辑后必须锁回+更新哈希。

**编辑流程：**
```bash
# 1. 开写权限
chmod 644 /home/ubuntu/.hermes/SOUL.md

# 2. 编辑文件（用patch/write_file）

# 3. 锁回只读
chmod 444 /home/ubuntu/.hermes/SOUL.md

# 4. 更新哈希（hash-verify监控4个文件，改了几条就更新几条）
md5sum /home/ubuntu/.hermes/SOUL.md | awk '{print $1}' > /home/ubuntu/.hermes/guard/hashes/SOUL.md.md5
md5sum /home/ubuntu/.hermes/profiles/customer/SOUL.md | awk '{print $1}' > /home/ubuntu/.hermes/guard/hashes/customer_SOUL.md.md5
md5sum /home/ubuntu/.hermes/skills/newmedia-operations/huoshan/SKILL.md | awk '{print $1}' > /home/ubuntu/.hermes/guard/hashes/huoshan.SKILL.md.md5
md5sum /home/ubuntu/.hermes/skills/newmedia-operations/shuziren/SKILL.md | awk '{print $1}' > /home/ubuntu/.hermes/guard/hashes/shuziren.SKILL.md.md5
```

**⚠️ 漏了哈希更新 = 30分钟内hash-verify cron报安全告警「HASH_FAIL:MISMATCH」，终止所有任务。这不是可选项。**
**⚠️ 漏了哈希更新 = 30分钟内hash-verify cron报安全告警，终止所有任务。** 这不是可选项。

### 第1步：改文件

修改目标文件（SOUL.md / skill SKILL.md等）。

**💡 经验：SOUL.md里的指令要足够强硬**
- ❌「输出以下内容」→ LLM当参考，自己重新编
- ✅「必须一字不差输出以下内容，不准自己编不准改词」→ LLM照搬

### 第2步：同步skills（如果改了skill文件）

客户profile有自己的skills独立副本（inode不同），不是symlink。改了主目录后必须手动同步整个目录：

```bash
# 同步全套（SKILL.md + references + templates + scripts）
cp -r /home/ubuntu/.hermes/skills/<category>/<skill>/* \\
   /home/ubuntu/.hermes/profiles/customer/skills/<category>/<skill>/

# 清技能缓存（不改缓存文件，下次启动不生效）
rm -f /home/ubuntu/.hermes/profiles/customer/skills/.hub/index-cache/*
rm -f /home/ubuntu/.hermes/profiles/customer/skills/.hub/audit.log
rm -f /home/ubuntu/.hermes/profiles/customer/skills/.hub/taps.json
```

### 第3步：删除DB会话 + 路由

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/ubuntu/.hermes/profiles/customer/state.db')
c = conn.cursor()
c.execute('DELETE FROM messages')
c.execute('DELETE FROM sessions')
c.execute(\"DELETE FROM gateway_routing WHERE session_key LIKE 'agent:main:feishu:%'\")
c.execute(\"DELETE FROM gateway_routing WHERE session_key LIKE 'agent:main:weixin:%'\")
conn.commit()
conn.close()
"
```

> ⚠️ 删所有会话和消息。如果只想清某个平台，改WHERE条件：`WHERE source='feishu'` 或 `WHERE session_key LIKE 'agent:main:feishu:%'`

### 第4步：杀网关（关键——不能直接kill）

**❌ 错误做法：** 在网关进程内直接`kill -SIGTERM $PID` → 报错"不能从网关进程内自杀"

**✅ 正确做法：** 走后台进程杀

```bash
terminal(command='sleep 3 && OLD_PID=$(cat /home/ubuntu/.hermes/profiles/customer/gateway.pid | python3 -c \"import json,sys; print(json.load(sys.stdin).get(\\\"pid\\\",\\\"\\\"))\") && kill -SIGTERM $OLD_PID && echo \"已杀 $OLD_PID\"', background=True, notify_on_complete=True)
```

### 第5步：等待自动重启 + 验证

网关被杀后**自动重启**。等25-30秒：

```bash
# 查新PID
cat /home/ubuntu/.hermes/profiles/customer/gateway.pid

# 查连接状态（微信+飞书都要connected）
cat /home/ubuntu/.hermes/profiles/customer/gateway_state.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
for p,info in d.get('platforms',{}).items():
    print(f'{p}: {info.get(\"state\",\"?\")}')
"
```

### 第6步：验会话system_prompt是否正常加载

关键检查：system_prompt长度>100才正常，为0说明SOUL.md没加载上，需重走全套：

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/ubuntu/.hermes/profiles/customer/state.db')
c = conn.cursor()
rows = c.execute('SELECT id, chat_type, length(coalesce(system_prompt,\"\")) as sp_len FROM sessions WHERE source=\"feishu\"').fetchall()
for r in rows:
    print(f'{r[0][:35]} | sp_len={r[2]} {\"✅\" if r[2] > 100 else \"❌ 为空！需重走流程\"}')
conn.close()
"
```

### 第7步：用户验证生效

让用户发新消息触发新会话创建，检查输出是否与SOUL.md匹配。

## 关于客户profile的skills同步（已合并到第2步）

客户profile的skills副本是独立文件（inode不同），不是symlink。改主目录的skill后**必须**cp同步到客户profile，否则小鹿仍用旧版。
```bash
cp /home/ubuntu/.hermes/skills/newmedia-operations/shuziren/SKILL.md \
   /home/ubuntu/.hermes/profiles/customer/skills/newmedia-operations/shuziren/SKILL.md
cp /home/ubuntu/.hermes/skills/newmedia-operations/huoshan/SKILL.md \
   /home/ubuntu/.hermes/profiles/customer/skills/newmedia-operations/huoshan/SKILL.md
```

## 关于persona文件（wiki/personas/）的特殊说明

**Persona文件不经过SOUL.md的会话缓存机制。** 它们在节点执行时通过 `skill_view()` 或 `read_file()` 加载，每次加载都读磁盘最新版本。

- ✅ 改完persona文件**不需要**清DB、重启网关
- ✅ 改完立即生效，下一节点执行时自动读取新版本
- ❌ 如果persona的规则写进了SOUL.md（如加载规则、人设映射表），改SOUL.md仍要走完整更新流程

## 深层原理

| 缓存层 | 位置 | 更新时机 |
|:-------|:-----|:---------|
| `sessions`表（state.db） | 每个会话的`system_prompt`字段 | 会话创建时写入，改文件/删路由不更新 |
| `gateway_routing`表（state.db） | 会话路由索引 | 独立于sessions表，删会话不删它 |
| DeepSeek服务端KV缓存 | API层 | 前缀缓存TTL未知，约5-30分钟 |
| Hermes prompt_caching（config） | cache_ttl=5m | 5分钟过期，网关重启立即清 |

**根因：** 光删`sessions`表不改`gateway_routing`，网关路由还在，恢复旧会话时用旧system prompt → SOUL.md改了但输出没变。

## 平台对应关系

| 小鹿（飞书/微信） | 走customer profile |
|:-----------------|:------------------|
| 网关PID | `/home/ubuntu/.hermes/profiles/customer/gateway.pid` |
| 状态文件 | `/home/ubuntu/.hermes/profiles/customer/gateway_state.json` |
| state.db | `/home/ubuntu/.hermes/profiles/customer/state.db` |
| SOUL.md | `/home/ubuntu/.hermes/profiles/customer/SOUL.md` |
| .env | `/home/ubuntu/.hermes/profiles/customer/.env` |
| sessions路由 | `/home/ubuntu/.hermes/profiles/customer/sessions/sessions.json`（只读镜像） |
| skills | `/home/ubuntu/.hermes/profiles/customer/skills/`（独立副本） |

## 自检清单

每次改完SOUL.md/skills后逐项打钩：

□ 改的文件已保存
□ customer profile的skills已同步（如果改的是skill）
□ `sessions`表已清理
□ `gateway_routing`表已清理
□ 哈希已更新（4个hash文件都check了，改了几个就更新几个）
□ 网关已重启（PID变化 + 微信/飞书connected）
□ 用户验证生效
