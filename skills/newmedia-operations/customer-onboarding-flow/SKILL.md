---
name: customer-onboarding-flow
title: 新客户流程物理闸与接待规范
description: 新客户首单防绕过物理闸+保姆级欢迎语。触发：新客户首次对话、欢迎语输出、信息采集、权限判定。
version: 1.0
---

# 新客户流程物理闸与接待规范（2026-08-05 定稿）

## 背景（为什么必须有这个）

新客户首单被验证出「Agent 脑补信息直接开跑」——没输出欢迎语、自己编店名地址、没查权限就烧钱生图。**文字规则拦不住，必须物理脚本卡死。** 用户定案：物理约束 > 软规则。

## 四道闸（脚本在 ~/.hermes/scripts/）

| 闸 | 脚本 | 职责 | 用法 |
|:--|:-----|:-----|:-----|
| 闸1 | `onboarding_gate.py` | 欢迎语强制（新客户未输出一字不差欢迎语 → 拦截） | `check <profile_home> <user_id>` / `mark <profile_home> <user_id>` / `verify <文本>` |
| 闸2 | `info_gate.py` | 信息采集完整（店名/地址/平台/内容类型缺失 → 拦截） | `check <项目目录> <简报文件.md> [内容类型]` |
| 闸3 | `permission_gate.py` | 权限+配额（basic 拦截 / normal 查配额 / unlimited 放行） | `check <user_id> <video\|image>` / `consume <user_id> <action>` |
| 闸4 | `confirm_gate.py` | 客户确认（文案/生图/出片 3 确认点未确认 → 拦截）✅ 2026-08-05 已落地+7项测试全过 | `check <项目目录> <node4_copy\|node8_image\|node12_render>` / `confirm <项目目录> <点> <客户原话>` / `skip <项目目录>` |

**新客户首单强制顺序（物理不可绕）：**
```
欢迎语(闸1 verify通过→mark) → 信息采集(闸2) → 权限(闸3) → 文案 → 客户确认(闸4) → 出片
```

## 只在人工选择点停下（用户定案，关键）

- **不是每个节点都问客户！** 分析/搜索/拆解内部闷头跑，别烦客户
- 只在客户需要**拍板**的节点停：文案改不改 / 是否跳过分析 / 是否出片
- 新客户首单：每个节点详细介绍给客户看（客户感觉有人全程服务）
- 出成品时问一句「下次还需要这样详细吗？」→ 不需要则下次直达人工确认环节

## 陪跑服务机制（2026-08-05 已落地，SPEC 4.8）

**前期（新客户）：每节点产出 → 发客户白话版（陪跑服务感）**
- 「这一步我们做了XX，结果是这样的」，去内部术语/路径/工具名
- 画像/爆款/文案全同步，客户全程看得见进度

**后期（客户熟悉）：客户说「跳过确认/直接出片/不用给我看」→ confirm_gate skip 模式一次直达出片（合法跳过，非违规）**

**落地位置：**
- SPEC v4.8：12 个节点 post_checks 挂「客户可见简报」+ 节点4/8/12 挂 3 个确认点
- customer SOUL.md：「陪跑服务机制」章节
- changelog：`wiki/history_archive/changelogs/2026-08-05-confirm-gates.md`

## 客户人工确认环节（2026-08-05 盘点确认 → ✅ 已补齐）

原状：SPEC 里的「确认」全是内部确认（参数/URL/BGM），**没有客户拍板点**——这就是 Agent 闷头跑完全程的原因。已补 3 个人工确认点（SPEC 4.8 + confirm_gate.py 落地）：
1. 节点4 文案后 → 问「需要修改不？」（node4_copy）
2. 节点8 生图后 → 发预览确认风格（node8_image）
3. 节点12 出片前 → 「开始出片？」（node12_render，客户说跑才动付费）

## 欢迎语定位（2026-08-05 用户定案）

**定位：保姆级运营助手，不是俏皮客服。**

- 标准文本（一字不差，哈希校验）在 `onboarding_gate.py` WELCOME_TEXT
- 调性：专业「专属运营助手」/「剩下交给我」/ 一站式全包 + 数据分析
- SOUL.md 是 444 只读：先 `sudo chmod 644` 再改，改完恢复 444，更新哈希

### ✅ 最终版欢迎语（2026-08-05 用户拍板，6平台全收录）

```
您好呀，我是您的专属运营助手小鹿～ 从今天起，我将为你的账号运营提供保姆级的服务。

我能帮您做的：

📱 短视频 — 抖音、快手、视频号、B站（探店/口播，从文案到出片一站式）
📕 小红书 — 图文（6-9张图+文案）or 视频
📰 公众号 — 推文排版（标题+正文+图片）
📊 数据分析 — 账号复盘、爆款拆解、内容优化建议

怎么开始：

• 「帮我的[店名]在抖音上推一下」→ 我直接安排
• 「帮我整个小红书的种草文案」→ 马上写
• 「帮我做个公众号推文」→ 出稿子
• 不确定 → 跟我说说您的店，我帮您判断 😊

您只需要告诉我需求，剩下交给我。祝您发财！
```

### 🚨 欢迎语平台覆盖检查（2026-08-05 实测翻车：漏了 B站）

**症状：** 欢迎语只列了 5 平台（抖音/快手/视频号/小红书/公众号），用户问「包含所有平台了吗」——系统实际支持 **6 平台**：抖音、快手、小红书、视频号、B站、公众号（证据：WORKFLOW_SPEC 平台枚举 + `huoshan/references/multi-platform-adaptation-guide.md`「六平台核心差异」表 + `content-review-gate` 平台权重表）。

**规则：写/改欢迎语必须对照系统支持平台清单，逐项核。** 当前 B站并入短视频行：`📱 短视频 — 抖音、快手、视频号、B站（探店/口播，从文案到出片一站式）`。

**验证：** 改完对比三处一致（gate vs soul vs bot）时注意——customer-facing-bot 模板第一行是标题「**新用户欢迎模板…**」不是正文，提取正文要跳过标题行再比，否则虚报不一致。

### 🚨 改欢迎语必须全库搜旧词（2026-08-05 实测翻车：改了 SOUL 但飞书还是旧版）

**症状：** customer SOUL.md 欢迎语章节改成新版后，飞书小鹿首次对话仍输出旧版「贴心又皮皮」。用户贴出旧文本质疑。

**根因：欢迎语标准文本存在于 5 个位置，只改 1 处必然漏。**
1. `customer SOUL.md` 欢迎语章节
2. `customer SOUL.md` 第1层「强制身分」内嵌引用（`主动介绍自己。「哎呦…皮皮的小鹿...」`）——最容易漏
3. `customer-facing-bot/SKILL.md` 欢迎模板（小鹿首次对话**实际加载这份**，优先级高于 SOUL）
4. `customer-facing-bot/references/welcome-message-narrative-20260712.md` 历史演进（加「已废弃」标注即可，勿删）
5. `onboarding_gate.py` WELCOME_TEXT（物理闸哈希基准）

**正确流程：**
1. 改文本前先 `grep -rn "<旧版关键词>" /home/ubuntu/.hermes/profiles/customer /home/ubuntu/.hermes/skills /home/ubuntu/.hermes/scripts`——找出**所有**出现位置（搜「贴心又皮皮」这类标志性旧词，不是文件名）
2. 逐个位置替换为新版
3. customer-facing-bot 改完必须 `cp` 同步回主 skills（或反向），两侧一致
4. 更新 `onboarding_gate.py` WELCOME_TEXT + `hash-verify.sh` 里 customer_SOUL.md 的哈希
5. 清 skill 缓存 + 重启 customer gateway 才生效

**教训：改任何「必须一字不差」的标准文本（欢迎语/话术模板），先全库 grep 旧关键词定位所有位置，别只改自以为的那一处。**

## 🚨 闸没生效的根因：孤儿脚本（2026-08-05 实测翻车）

**症状：** 4 道闸脚本全写好、测试全过，但飞书小鹿首次对话仍自由发挥欢迎语（输出文件里根本不存在的「新媒体内容运营助手」版）。

**根因：脚本写了 ≠ 闸生效。** 排查发现 onboarding_gate.py 只在 skill 文档的说明里被「提到」，**没挂进任何实际执行链路**：
- WORKFLOW_SPEC 引用 0 次
- customer SOUL.md 没有「必须先跑闸」的硬指令
- customer-facing-bot 没有实际调用

小鹿接待客户时根本不跑这个闸 → 自然自由发挥。**就像写了防火墙配置但没启动服务——形同虚设。**

**修复（双保险）：**
1. **customer SOUL.md 加「欢迎语物理闸」硬指令**（系统提示词里，每次对话必读）：
   - 新客户首对话必须按顺序：`onboarding_gate.py verify <欢迎语全文>` 校验 → `mark <profile_home> <user_id>` 记录
   - 明确写「禁止自由发挥欢迎语」「必须用 terminal 跑脚本，ok:true 才算数」「谁违反 = 漏闸，全流程视为未完成」
2. **customer-facing-bot/SKILL.md 接待流程同步加硬指令**（主 + customer 两侧）

**原则：** 任何物理闸脚本必须满足「三挂载」才算生效——① SPEC 节点 pre/post_checks 引用 ② SOUL.md 硬指令（LLM 每次读到）③ 执行 skill 里写明调用命令。只写脚本文件 + 只在文档里提一句 = 没挂上。

## 🚨 改了 SOUL/欢迎语还是没生效：system_prompts 哈希缓存（2026-08-05 最深根因）

**症状：** 5 处全改完 + 哈希更新 + skill 缓存清理 + 重启 customer gateway，飞书小鹿**仍然输出旧版欢迎语**。用户连续两次说「还是没有更新」。

**根因：state.db 有独立 `system_prompts` 表（列 hash/prompt）缓存 system_prompt 全文，`sessions` 表用 `system_prompt_hash` 列关联。** 旧会话的 prompt 全文缓存在这张表里，光删 sessions / 改文件 / 重启 gateway 都不清它——新会话构建 system_prompt 时若命中旧哈希，直接复用旧版，**根本不重新读 SOUL.md**。

实测：customer state.db 里 6 条 system_prompts 缓存**全含旧版欢迎语**（`贴心又皮皮`），5 条被会话引用——这就是反复改不生效的原因。

**排查（先确认是不是这个坑）：**
```sql
-- 1. 看缓存里有没有旧文本
SELECT hash, prompt FROM system_prompts;
-- 2. 看哪些会话引用旧缓存
SELECT id, session_key, system_prompt_hash FROM sessions;
-- 3. 看会话 system_prompt 字段是否为空（空=每次重建，非缓存坑）
```

**修复（比删 sessions 表更轻量、更精准）：**
```python
import sqlite3, shutil
shutil.copy2('/home/ubuntu/.hermes/profiles/customer/state.db',
             '/home/ubuntu/.hermes/profiles/customer/state.db.bak-welcome-clean')  # 先备份
conn = sqlite3.connect('/home/ubuntu/.hermes/profiles/customer/state.db')
c = conn.cursor()
c.execute("DELETE FROM system_prompts")          # 清 prompt 全文缓存
c.execute("UPDATE sessions SET system_prompt_hash=NULL, system_prompt=NULL")  # 断关联，强制下次重建
conn.commit(); conn.close()
```
然后重启 customer gateway（systemd-run transient unit 方案）。下次任何会话启动都会强制重建 system_prompt（读最新 SOUL.md）。

**⚠️ 验证时注意：** 客户正在用的活跃会话在 gateway 内存里可能还有缓存的 system_prompt——必须重启 gateway 才能清内存缓存，光清 DB 不够。

**教训：改 SOUL.md/欢迎语后「还是不生效」的排查顺序——① 全库 grep 旧词（5位置）→ ② 清 skill 缓存 → ③ 查 system_prompts 表是否缓存旧版 → ④ 清缓存+断关联 → ⑤ 重启 gateway → ⑥ 新会话验证。跳过③=白改。**

## 🚨 平台决策权归机器人，不询问客户（2026-08-05 用户纠正，保姆级服务核心）

**症状：** 小鹿对寄卖行客户说「1. 发哪个平台？抖音/快手/视频号 你选一个」——让客户做专业判断。用户批评：**「我要的是保姆级的服务，客户完全不懂，你让他做选择？我们之前定的规则里是这个流程吗」**

**规则：客户只需提供「他独有的信息」（店名/地址/实景照），专业判断全归机器人：**
- ❌ 不问「你想发哪个平台」——寄卖行实体店同城引流 → 机器人直接定 **抖音**（行业知识，非客户该操心的）
- ❌ 不问「方向你想怎么定」——给建议可以，但不说「你选」
- ✅ 只问：店名、地址、实景照（门头/店内/商品特写）、内容类型是否说清
- ✅ 平台策略在节点15「获客打法包」第④段给（抖音同城/小红书搜索/视频号私域按客户情况推荐）——那是机器人分析后的交付物
- ✅ 客户主动指定平台才按其指定（「帮我在小红书推」→ 记小红书）

**「每个环节只能做一件事，不准多问」的完整含义：** 问完必要信息（店名/地址/照片）→ 直接走流程（判断行业→读策略→搜爆款→写文案→问改不改→查权限→出片）。把决策推回给客户 = 违背保姆级定位。

## 🚨 规则冲突排查法（2026-08-05 实测：小鹿「绕过规则」的真根因是规则冲突）

**症状：** 小鹿让客户选平台，用户问「为什么她绕过了规则」——排查后发现规则根本没丢（system_prompt 缓存里有「不准多问」「保姆级」），是**规则本身冲突**：

| 规则来源 | 说法 |
|:---|:---|
| huoshan skill 入口 | 「客户说做个视频后，先问第二句：你准备发哪个平台？」 |
| SPEC 节点15 交付 | 机器人分析后给「平台打法策略」 |
| SOUL 做视频流程 | 判断行业→读策略→搜爆款→写文案（没提平台） |
| 保姆级定位 | 「剩下交给我」 |

小鹿按 huoshan skill 问了平台——**它有规则依据**，但这条规则跟「机器人做平台策略」+「保姆级服务」矛盾。模型在规则空白/冲突处自由发挥。

**排查顺序（行为偏离预期时，先查是不是这个）：**
1. **规则在不在上下文？** → 查 state.db `system_prompts` 表缓存是否含该规则（规则丢了=缓存坑，见上文 system_prompts 章节）
2. **规则有没有覆盖这个点？** → 该场景在 SOUL/SPEC/skill 里有没有明确指令（平台决策权就曾是空白）
3. **有没有规则冲突？** → 同一个决策点在不同文件说法是否矛盾（huoshan 入口 vs SPEC 交付 vs SOUL 定位）

**原则：** 模型在规则空白/冲突处必然自由发挥——不是模型坏，是规则没写死。修法是把决策点**显式写死**（如「平台由机器人定」），并让所有文件说法一致。

## 用户偏好（本会话沉淀）

1. 客户对接走飞书（小鹿通道），交付推客户飞书 DM
2. 推送用 `hermes -p customer send --to "feishu:oc_xxx"`，不用 outbound webhook（推不了飞书私聊）
3. 新客户信息必须一步步问，但**只问客户独有的**（店名/地址/实景照），专业判断（平台/方向/策略）机器人自己定——禁止让客户做选择（2026-08-05 用户纠正：客户完全不懂，你让他选平台？）
4. 付费 API（生图/出片）前必须查权限+配额，客户说「跑」才动
5. 微信语音自动转写失败时，用 `references/wechat-voice-transcription.md`（pilk 解码 silk + faster-whisper 转写，3 步实测通过）
6. **customer skills 同步坑：** huoshan/shuziren 的 SKILL.md 是 **chmod 444 只读**（用户物理约束设计），`cp` 报 Permission denied 是正常的——同步流程：`sudo chmod 644` → cp → 恢复 `sudo chmod 444`；只读的是 SKILL.md 本体，references/ 子文件一般可写；同步后更新 `hash-verify.sh` 对应哈希。改 customer SOUL.md 同理（先 644 后恢复 444）
