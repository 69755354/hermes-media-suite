# 群消息防泄漏三层防护（2026-08-16 实测）

> 背景：群会话在群里发「打包 codex 深度分析（effort=high）」「SearXNG 挂了」等内部过程，老板多次纠正「群里不要把过程都发出来」「又在群里暴露工具了」。小鹿在群里不乱发，因为它 SOUL 有「🔒 附加安全规则」禁止泄露工具/路径/技术栈。我们主 SOUL 原本缺这条 → 现在三层防护。

## 三层防护（都做才有效）

1. **SOUL 规则层**（治本）：主 `~/.hermes/SOUL.md` 执行纪律第 12 条「对外信息安全铁律」——禁止出现工具名（codex/claude/ffmpeg/Seedream/婵镜/豆包/API/MCP/TTS 等）、内部路径（/home/、wiki/、outputs/ 等）、技术术语（token/effort/gateway/session 等）；只发结果不发过程；对外报告只写结论。参考小鹿 SOUL「🔒 附加安全规则」写法。改 SOUL 需按 soul-md-update-protocol 走（解锁→改→锁回 444→更新哈希→清群会话 DB→重启网关）。**第 13 条「客户任务受理回执铁律」（2026-08-17）**：客户下任务先回「收到，马上给您处理，预计 X 分钟」再干活，X 基于真实历史耗时不拍脑袋。

2. **skill 规则层**（feishu-group-delivery）：收到任务只回「收到+预估时间」；过程静默；@ 只加一次（文本里不写 `<at>`，feishu_send_gate 自动加）；报告精简铁律（含发给老板本人）。

3. **物理闸层 = 已停用（2026-08-17 老板定案「闸门设计有问题，先去掉」）**：
   - ❌ 曾加过：feishu_send_gate.py 过程词/结构黑名单 + node-entry-guard.py OUTBOUND 硬闸（observe 也强制 block）——**实测把正常消息（含老板 DM）全拦了**（12:11 飞书、12:17 微信 `customer outbound content blocked` + `Fallback send also failed`）→ 表现为「AI 卡死」假象（消息发不出去，老板连发「？」「喂」都没回复）
   - ✅ 已处理：guard OUTBOUND 硬闸 `if False` 禁用；feishu_send_gate.py 保留黑名单但不再自动拦发送（`check` 命令留作自查）
   - ✅ 老板定的正确姿势：**防泄漏靠「SOUL 规则 + 静默处理（只发结果不发过程）+ 发送前自查」**，不靠消息级自动拦截——拦截误伤比泄漏更糟（直接断联）
   - ⚠️ 教训：一刀切发送级硬闸会误伤老板 DM（老板需要知道内部进度，客户/群才要严拦）——必须区分「老板 DM」vs「客户/群」，不能同一套严闸
   - 历史保留（理解坑用）：pre_tool_call matcher 曾必须含 `send_message`（内置发送工具不匹配 `feishu_.*` 时 guard 完全不触发）；OUTBOUND 分支放在票据校验之前（发消息不要求票据）

## 排查路径（群会话为什么能发出内部信息）

1. 查 `python3 /tmp/feishu_group_msgs.py`（拉群最近消息看实际发出去的）——区分「群里发的是历史」vs「还在发新消息」
2. 确认 guard 是否被调用：`~/.hermes/guard/entry_guard_audit.jsonl`（observe 模式只记录；空=guard 没触发）
3. 检查 matcher：config.yaml `hooks.pre_tool_call` 的 matcher 是否含 `send_message`
4. 验证敏感词闸本身：`python3 ~/.hermes/scripts/feishu_send_gate.py check "打包 codex"` → 应 BLOCKED: 工具:codex

## 测试验证

`/tmp/verify_guard.py` 四连测：敏感词(codex)→block / 正常消息→allow / 路径泄露→block / 无票据正常消息→allow（OUTBOUND 不要求票据）。

## ⚠️ 关键坑：对客规则改了不生效（2026-08-16 实录）

**症状**：主 SOUL.md/skills 加了「报告精简铁律」「对外信息安全铁律」，但小鹿（飞书对话线）发的内容还带来源标注/置信度。

**根因**：小鹿 = customer profile（广州机），**skills 是独立副本**（目录结构都不同，没有 feishu-group-delivery/workflow-architecture 这些 skill），主目录改了不自动同步。

**修法**：
1. 改主目录 skill 后必须 cp 同步到 customer profile（soul-md-update-protocol 坑4）
2. **customer profile 没有对应 skill 时** → 直接把铁律补进小鹿 SOUL.md（广州机 `/home/ubuntu/.hermes/profiles/customer/SOUL.md`，注意它 444 只读，先 `chmod u+w` 再写，写完锁回 444）
3. 改完清小鹿会话缓存/重启网关才生效（session 缓存）
4. 验证：`grep -c '报告精简铁律' 广州SOUL` → 1
