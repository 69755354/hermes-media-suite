# 小鹿（客户Profile）技能同步须知

> 2026-07-15 本会话发现：小鹿（customer profile）有自己的独立skills目录，与主Hermes skills目录**不是同一个文件系统**。

## 核心问题

```bash
# 主Hermes skills（我编辑的地方）
/home/ubuntu/.hermes/skills/newmedia-operations/shuziren/SKILL.md

# 小鹿加载的skills（实际执行的地方）
/home/ubuntu/.hermes/profiles/customer/skills/newmedia-operations/shuziren/SKILL.md
```

**它们是独立文件（不同inode），不是软链接。** 编辑主skills不会自动同步到小鹿的skills。

## 同步步骤

1. 改完主skills后，手动cp到小鹿的skills目录：

```bash
cp /home/ubuntu/.hermes/skills/newmedia-operations/shuziren/SKILL.md \
   /home/ubuntu/.hermes/profiles/customer/skills/newmedia-operations/shuziren/SKILL.md

cp /home/ubuntu/.hermes/skills/newmedia-operations/huoshan/SKILL.md \
   /home/ubuntu/.hermes/profiles/customer/skills/newmedia-operations/huoshan/SKILL.md
```

2. 重启小鹿网关清缓存：

```bash
kill -SIGTERM $(cat /home/ubuntu/.hermes/profiles/customer/gateway.pid)
# 等15-20秒自动重启，再检查状态
```

3. 验证：

```bash
# 检查文件和启动时间
stat -c "%s" /home/ubuntu/.hermes/profiles/customer/skills/newmedia-operations/shuziren/SKILL.md
stat -c "%i" /home/ubuntu/.hermes/profiles/customer/skills/newmedia-operations/shuziren/SKILL.md
# 应该等于主目录的size，但不能是同一个inode
```

## 涉及到的skills

- `shuziren`（婵镜数字人工作流）
- `huoshan`（火山探店工作流）
- 其他`newmedia-operations`分类下的skill都需要同步

## SOUL.md

小鹿的SOUL.md单独在 `/home/ubuntu/.hermes/profiles/customer/SOUL.md`，编辑主目录的SOUL.md不影响。直接编辑这个路径即可。

### SOUL.md修改后不生效的完整排查（2026-07-15 踩坑总结）

**根因：** SOUL.md在会话创建时加载到state.db的system_prompt字段缓存，改文件不自动生效。

**完全生效链条（三步必须全走）：**
1. 改文件
2. 清state.db（sessions表 + gateway_routing表）
3. 杀网关（让它自动重启加载新文件）

**清缓存脚本：**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/ubuntu/.hermes/profiles/customer/state.db')
c = conn.cursor()
c.execute('DELETE FROM messages')
c.execute('DELETE FROM sessions')
c.execute(\"DELETE FROM gateway_routing WHERE session_key LIKE 'agent:main:feishu:%'\")
conn.commit()
conn.close()
print('会话和路由已清')
"
```

**不生效的三大原因（按概率排序）：**
1. **gateway_routing表没清** — 删了sessions但routing还在，网关会匹配旧路由 → 重建旧会话ID
2. **网关没重启** — 改文件后进程不知道文件变了，重启后才能加载
3. **DeepSeek服务端KV缓存** — API有5分钟TTL的服务端前缀缓存，等几分钟或换不同文案触发cache miss

**关于欢迎模板：** LLM可能把欢迎模板当"参考"而不是"必须输出的指令"。如果模板没被逐字遵守，把提示改成"必须一字不差输出以下内容，不准自己编不准改词"。

### 群聊 vs 私聊行为差异

群里发的消息可能走`on_xxx`线程路由，这类会话可能不完整加载SOUL.md。如果群聊更新了但私聊没更新 → 检查数据库中系统提示词长度是否为0 → 如果是则清路由+会话后让用户重新发消息。

## 缓存说明

- gateway有`cache_ttl: 5m`的prompt缓存
- DeepSeek有服务端prompt缓存（约5分钟TTL）
- **重启gateway是清缓存最彻底的方式**
- 如果重启后老会话仍然显示旧行为，开新会话即可

## 验证清单

□ 主skills已更新
□ 小鹿skills已同步（cp）
□ 小鹿gateway已重启
□ 新会话测试已通过
