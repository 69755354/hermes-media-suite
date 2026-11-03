# DS 全挂容灾方案评估（2026-08-24 codex 额度尽时讨论定案）

> 场景：codex 与 claude 都挂（或 codex 长期额度尽），工作流是否还能跑、怎么跑。
> 结论先行：**全挂时内容生产照跑（DS 直调），多步工程冻结排队等恢复，不可逆操作永远等人。**

## 一、执行器容灾现状（2026-08-24 实证）

| 执行器 | 状态 | 说明 |
|:--|:--|:--|
| codex | 额度尽（8/27 恢复） | 报错信息里写死恢复时间：`try again at Aug 27th, 2026 3:53 AM` |
| claude (Bedrock) | 健康 | 唯一健康主力；日常重活/分析/审查都靠它 |
| DS v4 pro/flash | 活着但裸 | 直调无壳注入；借壳贵 5-10 倍 |
| GLM 5.2 | **key 失效** | `34e34c...` 开头，`code:1000 身份验证失败`；第四条腿不存在 |
| 豆包 ark | 看图专用 | 不是编码 agent |

**结论：真正健康的执行器只有 claude 一个。** codex 额度尽期间（8/27 前）重活全压 claude；DS 只干机械单步。

## 二、DS 三条路的取舍（讨论结论）

### 1. DS 直调（ds_native_invoke.py）——便宜但裸
- system prompt 只有一句「你是后台内容执行器」，无 AGENTS.md、无 skill 注入、无 kb_gate
- 任务书写什么它就只有什么 → **行为会飘**（2026-08-24 实测：把「打包任务书」理解成「执行 cat」，输出 201 字节 tool-call XML）
- 处置：任务书必须自包含全部规则（执行器铁律+输出协议+不调工具+落盘路径）；产物 <500 字节且含 `<tool_calls>` = 模型行为异常，不能只看 dispatch PASS

### 2. DS 借壳（ds_fallback.sh codex-slot / cc-slot）——有规则但贵
- 借 codex/claude 壳 + DeepSeek 端点：有 DEGRADED_RULES + AGENTS.md + kb_gate
- 代价：token 成本 5-10 倍（壳每次注入全量系统提示/AGENTS.md/skills/工具定义，实测「回复OK」烧 212,160 tokens vs 直调 2-4 万）；codex 位只能 flash
- 适用：全挂时保命通道，只顶机械活；架构审查冻结排队

### 3. DS 轻量壳（提议未实现）——DS 专属壳
- 带 AGENTS.md + kb_gate + skill 预置注入，但不走 codex/claude 协议栈
- 性能只到单步（DS 原生 API 无 agent 循环），但 DS 在咱们工作流的职责（内容生产执行 + 盲评 judge）全是单步 → 轻量壳够用
- 状态：识别到缺口，未实现；改执行通道代码需派执行器

### 4. DeepSeek Harness（2026-08-13 官方开源）——观察不接
- v0.1 开发者预览，everything-is-a-plugin；性能评测未碾压 codex/claude（Composio 30 任务：Oh My Pi 17/30、Claude Code 16/30、Codex 16/30，DSH 未进前四）
- 长任务/并行不稳，对工具配置敏感；现阶段不接，登记等稳定版

## 三、全挂行动顺序（定案）

1. **救 codex/claude 优先**（L1/L2 环境问题别降级、L3' 限流等重试）——降级不是第一选择
2. 内容生产（文案/分镜/台词/judge）→ DS 直调 + 传话书规则模板（便宜，覆盖 80%）
3. 多步工程（改闸/改代码）→ **冻结排队**，等 codex/claude 恢复后批量过审，不让 DS 硬顶
4. 终审签字/红线操作 → 永远不 DS 顶，等人
5. 架构审查 → 冻结排队（DS 顶不了对抗审查，硬顶=自己给自己签字）

## 四、相关纪律提醒

- 降级通道选择顺序以用户拍板为准（2026-08-24：codex 额度尽用户先选「2=DS v4 pro」，DS 失败后才选「3=claude 一条龙」），Hermes 不擅自切
- 「任务书归 codex 打包」红线在 codex 不可用时可被用户显式批准绕过（本次用户选 claude 直接打包+分析）
