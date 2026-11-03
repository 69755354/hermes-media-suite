---
name: multi-model-failover
description: 触发：cc/codex挂了/健康检查/降级用DeepSeek替代/容灾方案。DS降级执行+三层健康检查判定。
author: Hermes curator
license: MIT
version: 1.0
metadata:
  hermes:
    tags: [disaster-recovery, failover, deepseek, health-check, degradation, claude, codex]
    category: server-operations
---

# 多执行器容灾降级（cc / codex 挂 → DS 顶班）

## When to Use

触发：Claude（cc）/ codex 挂了或不可用、需要判断执行器是否真挂、降级用 DeepSeek（DS）替代干活。核心结论（2026-08-12 实测）：**DS 顶不了「审查」，顶得了「执行」**——DS 缺的不是工具能力，是判断力和上下文长度。

## 一句话降级方案

- cc 挂 → `ds_fallback.sh cc-slot "<任务>" [workdir]`（claude 壳 + DeepSeek + deepseek-v4-pro）
- codex 挂 → `ds_fallback.sh codex-slot "<任务>" [workdir]`（codex 壳 + DeepSeek + deepseek-v4-flash）
- 两个都挂 → 内容生产无损（本来跑 DS）；写代码降级但可用（分支+单文件+测试兜底）；**架构审查不降级→冻结+排队**（DS 顶不了，硬顶=自己给自己签字）

落地文件（workflow repo，已 git 提交 a89061b）：
- `scripts/agent_health_check.sh`（三层健康检查；`--json` 给调度）
- `scripts/ds_fallback.sh`（降级执行）
- `outputs/DS_FALLBACK_PLAN_2026-08-12.md`（完整方案）

## 健康检查：怎么判断「真挂了」

**核心原则：三层里只有第三层失败才算挂。** 前两层是环境问题，降级会掩盖故障。

| 层 | 查什么 | 失败叫什么 | 该干什么 |
|---|---|---|---|
| L1 | 二进制在不在、沙箱好不好 | ENV_BROKEN | 修 PATH/换 sandbox。**别降级** |
| L2 | key 在不在、鉴权过不过 | AUTH_BROKEN | 换 key / login。**别降级** |
| L3 | 端到端：改一个坏函数并跑通测试 | DOWN | 真挂，走降级矩阵 |
| L3' | 限流/额度（429/503/quota） | DEGRADED | **等重试，别降级**（限流是暂时的） |

- L3 探针故意用「返回 a-b 的 add + 断言 add(2,3)==5」——一次验证读文件/改文件/跑 shell/看到失败后修正四件事。只 ping API 会把「鉴权通但改不动文件」误判为健康。
- 阈值：L3 连续失败 2 次（间隔 ≥5min）才置 DOWN（单次失败可能是网络抖动）。

## 通道参数（2026-08-12 实测跑通）

| 通道 | 命令要点 | 模型 |
|---|---|---|
| DS 顶 cc 位 | claude 壳 + `https://api.deepseek.com/anthropic` | deepseek-v4-pro |
| DS 顶 codex 位 | codex exec + `https://api.deepseek.com/v1` + `wire_api=responses` | **deepseek-v4-flash**（pro 走 codex 协议被拒） |
| DS 原生 API 顶 pro | `python3 scripts/ds_native_chat.py <prompt.md> <output.md> [model]`（直调 chat/completions，不依赖 claude/codex 壳） | **deepseek-v4-pro**（绕开 codex 协议拒 pro 的限制；纯文本生成类任务） |

### ✅ Ox Alpha 免费通道（2026-08-24 落地，codex 挂时第一个该试的降级）

OpenRouter 匿名免费模型 `stealth/ox-alpha`（$0/$0，1M 上下文，DeepSWE 80% 跑分压过 Claude Fable 5/GPT-5.6 Sol）。**codex 挂 → 先 ox_shell（免费），再 DS（付费）**。新加坡机已落地全套：

- `/home/ubuntu/workflow/ox_native_invoke.py`（规则注入版）+ `/home/ubuntu/workflow/ox_shell.sh`（配套壳），`hermes_task_dispatch.py --target ox_native` 已路由
- 规则注入 = 照广州 ds_gz_invoke.py 模式：AGENTS.md 铁律 + 基础三件套 + 任务类型 skill + 合规红线编译进 system prompt（rule_chars≈24K），验证 Ox 亲口确认收到五段规则
- key：`~/.hermes/.env` 的 `OPENROUTER_API_KEY`
- **坑**：①免费档 429 限流（上游共享池），重试即恢复 ②派 Ox 写代码必须带「输出格式硬约束」任务书（禁 markdown 代码块、字符串换行必须 `\n` 转义），否则第一版必 py_compile 失败
- 完整实测数据 + 格式坑任务书模板 + OpenRouter 注册/隧道踩坑：`references/ox-alpha-free-channel-20260824.md`

## 坑（别踩第二次）

0.5. **生产脚本常态直连 DS = 门禁绕过，整改模式「codex 优先 + DS 降级」（2026-08-19 广州 execute_api.py 整改）**：广州 `execute-api.service`（1889 端口，视频工作流段 2）的 `node5_storyboard` / `node8_prompts` 直接 `deepseek_call("deepseek-chat", ...)` 产分镜/提示词——分镜属 `CREATIVE_BLUEPRINT/A_STORYBOARD`，是受 `G_STRATEGY_BY_CODEX` 约束的智力产物，常态直连 DS 违反「DS 仅容灾」。**整改模式（已验证）**：写 `call_coder(system_prompt, user_prompt, temp)` 函数——`subprocess.run(["bash", "codex_remote.sh", prompt], timeout=600)` 优先新加坡 codex，`returncode==0` 且输出非空且非 BLOCKED → 走 codex；否则 `ds_fallback()` 降级 DS 返回 `(text, "ds_degraded")`。node5/node8 主调用和 JSON 解析 fallback 全部改走 `call_coder`。语法 OK 后需重启 systemd 服务生效（`systemctl restart execute-api.service`，可能要 sudo）。**排查顺序**：先确认脚本是否在生产链路（systemd/进程/谁调用），别就地打补丁——废弃脚本直接归档移出生产目录。：ds_fallback.sh 是「调度器」不是「壳」——内部调的是裸 `codex exec` / `claude -p`，**不过 codex_exec_gated.sh / claude_remote_wrapper.sh、不过 codex_sandbox.sh、无 kb_gate**。修复后现状：① codex-slot 把 AGENTS.md 内容**实际拼进传给 codex 的 prompt**（原来只写进 PROMPT_FILE 但 codex 执行时没引用 = 摆设）；② 新增 kb_gate_sg.py 校验（与 codex_exec_gated.sh 一致，任务书未带 READ_SKILL/知识库标记直接 BLOCK；纯运维 SKIP_KB_GATE=1 放行）。**教训：降级 ≠ 裸跑**——DS 降级同样要带 AGENTS.md 强制加载链 + 知识库物理卡点，否则执行器在无规则上下文里脑补（本次 DS 写分镜全裸跑，红果规则/画面结构没进上下文）。配套：codex_sandbox.sh 挂载路径也修了（原 `/home/ubuntu/AGENTS.md` 不存在 → 实际在 `/home/ubuntu/workflow/AGENTS.md`，挂了个寂寞）。详见 agent-framework-layer 踩坑 12。

1. **`CLAUDE_CODE_USE_BEDROCK=1` 会劫持路由**——不 `env -u` 清掉，`ANTHROPIC_BASE_URL` 形同虚设，请求照样打 Bedrock，表现为 `400 model identifier is invalid`，看着像 DS 挂了其实是 Bedrock 不认 DS 模型名。
2. **codex 位降级只能用 flash**——`deepseek-v4-pro` 走 codex 协议被服务端明确拒（"available starting early August 2026"）。codex 位比 cc 位弱一档。
3. **`codex doctor` 常态报 2 fail** 是 npm prefix 冲突（运行 `/usr/lib/node_modules`，npm 指向 `~/.npm-global`）——不影响执行，**别当挂了的信号**。
4. **bwrap 沙箱坏**（`RTM_NEWADDR: Operation not permitted`）→ codex 位必须 `danger-full-access`，降级期 WORKDIR 白名单是唯一防线，不能再放宽。
5. **codex OpenAI 额度耗尽**（`You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage`）——**exit 0 ≠ 产出落盘**，报错前可能只写了任务书没写产物。降级前先 `ls` 项目目录确认产出文件，别信 exit code；额度恢复时间在报错里写死（如 Aug 20th）。
6. **DS 能接进 codex 壳，但成本爆炸，直调更优（2026-08-18 实测「你那个DeepSeek能接到Codex那个壳里面吗」后定案）**：codex 0.147 支持自定义 `model_provider`（`-c 'model_provider="deepseek"' -c 'model="deepseek-chat"' -c 'model_providers.deepseek.base_url="https://api.deepseek.com/v1"'`），链路能通，但三个原因不划算：① **token 成本 5-10 倍**——壳每次调用注入全部系统提示/AGENTS.md/skills 描述/工具定义，实测「回复OK」四个字就烧 212,160 tokens；直调同样任务 2-4 万；② **协议硬转换**——codex 0.147 只认 `wire_api="responses"`（chat 已禁），DeepSeek 原生只有 chat completions，走壳是硬转换 + 警告 `Model metadata for deepseek-chat not found, Defaulting to fallback metadata`，tool calling/reasoning effort 全是降级猜的；③ 直调通道（ds_native_chat.py / ds_fallback.sh）已带 AGENTS.md 注入 + kb_gate，功能完备。**结论：只有当任务需要 DS 自主多步 agent 循环（读文件→改代码→跑测试→再改）且 codex 长期不可用、Claude 禁用时才考虑接壳；单步分析/生成任务一律直调。**（注：DS 顶 codex 位的降级路径本就是 codex 壳+DS，走这条时优先 `ds_fallback.sh codex-slot` 而非手拼 model_provider。）

## 降级能力边界（DS 能验证，不能发现）

- ✅ DS 能顶：单文件/单函数审查、已知问题取证、跑测试解读失败、机械批量修改、按现成测试修到绿
- ⚠️ DS 半能：契约填模板、多文件垂直切片（必须拆单文件级串行喂）、新写单测（只写 happy path）
- ❌ DS 不能顶：攻击路径构造（找绕过）、从零定架构约束/非目标边界、终审签字（放行不可逆变更）、大重构/状态机改造、数据迁移
- 2026-08-12 实测：DS 审 workflow_gate.py 927 行能答对「可达 ALLOWED」并准确定位行号——但那是已知答案的复现，提问本身框定了正确问题。**DS 证明能验证，没证明能发现。**

### 降级用户偏好（2026-08-18 实测 + 2026-08-24 补充）

codex 额度用尽时，老板明确指示：**不要自动切 claude**（「不要用CLADU」）；要 DS 顶。0818 实测过程：老板先提「用V4PRO顶」，随后改口「等等 用FLASH顶」——**最终选定 flash**。内容生产（分镜/文案/报告等纯文本生成）降级顺序：

1. **DS flash 原生 API**（`scripts/ds_native_chat.py` 直调 chat/completions；老板 0818 最终拍板用 flash）
2. DS V4 Pro 原生 API——老板提过但改口，需再点名才用
3. claude/cc——**必须老板点名才用**（配合记忆：Claude 默认不调用）

**2026-08-24 补充（新决策，覆盖「默认不切 claude」的例外场景）**：codex 额度尽（8/27 恢复）+ DS 直调打包失败（吐 tool-call XML，201 字节垃圾）后，老板先拍板「2=DS v4 pro 降级」试一轮，DS 失败后**明确拍板「3=claude 直接打包+分析」**，并对火龙链路指示「**先全部用claude**」。结论：**当 DS 直调也不可靠时，老板会显式选 claude 顶上（打包+分析+执行全走 claude）**。关键区分：**老板拍板选 claude = 允许；Hermes 擅自切 claude = 违规**（0818 教训仍在）。DS 打包失败时不要反复重试烧 token（模型行为不保证变），如实报老板选替代通道。

配套要求：
- 任务书**必须自包含**（上下文/逐字稿/知识库结论全内嵌），DS 降级时不指望它读文件
- 产出文件头打执行者标注（如 `> 执行者：DS V4 Pro（codex 额度用尽降级）`）+ 文件尾 `OUTPUT:` 路径，识别+可回滚
- 降级期 prompt 里写明「知识库引用步骤可跳过（_知识库引用.md 已由前置完成）」避免 DS 卡在物理卡点

### 🚨 降级执行纪律（2026-08-18 老板批评「你怎么老是不按照规则来」后定稿）

**违规复盘（血泪）**：codex 额度用尽后 Hermes 擅自切 claude 通道 → 老板「不要用CLADU」；随后在 V4PRO/FLASH 间反复切换 + 连续试跑多次付费调用 → 烧钱；过程中汇报过多 → 违反「不发过程只报结果」。

**纪律（降级期必守）**：
1. **codex/claude 挂 → 先汇报现状 + 等老板拍板通道，不擅自切**。降级方案写好放这，但「切哪个」是老板决策（0818 老板明示不要自动切 claude）。
2. **老板点名不用的通道绝不碰**（「不要用CLADU」= claude/cc 全禁，即使降级矩阵写着 cc 端到端顶）。
3. **切换通道前先确认，禁止来回试跑烧钱**。老板中途改主意（V4PRO→FLASH）→ 立即停当前进程，确认新通道后再启动，不连续发多个付费请求赌哪个能出。
4. **降级期只报结果不发过程**：通道切换、试跑失败、额度报错都不逐条报；闷头干完一次性交付。中间态只在老板主动问时才说。
5. **任务书要求的格式细节（如台词英文双引号）DS 可能不遵守**（0818 DS 生成了中文「」）——质检必查格式合规而不仅是内容正确，发现偏差主动修（批量替换台词引号）再交付，别把「内容对但格式错」交出去等老板挑。

### ⚠️ 三通道壳矩阵：codex/claude 有完整壳，DS 没有独立壳（2026-08-24 实证）

用户问「直调那些规则不会都没用了吧」「cc走的哪个壳」「ds没有自己专门的壳是吧」后逐通道实证：

| 通道 | 壳 | AGENTS.md | skill 注入 | kb_gate | token 校验 | 状态 |
|---|---|---|---|---|---|---|
| codex | `codex_exec_gated.sh` + `codex_sandbox.sh` | 有 | 有 | 有 | 有 | 完整 |
| cc/claude | `claude_remote_wrapper.sh` v4（`--append-system-prompt-file` + `--add-dir` wiki/skills） | 有 | 有 | 有（`kb_gate_sg.py -f`） | 有（TASK_GATE_ENABLED=1） | 完整 |
| DS 直调 | **无**（`ds_native_invoke.py` 裸调 chat/completions） | **无** | **无** | **无** | 有（token 硬校验） | 裸 |

**关键实证：**
- `ds_native_invoke.py` system prompt 只有一句「你是后台内容执行器，产出结果文件内容，不寒暄」——无 AGENTS.md、无 skill 注入、无 kb_gate。**任务书写什么它就只有什么**；任务书没写的规则（输出协议/不调工具/后台铁律）DS 不自动知道 → 行为会飘（见 tool-call XML 坑：把「打包任务书」理解成「执行 cat」）
- `ds_fallback.sh` 是**借壳**不是 DS 专属壳：cc-slot 借 claude 壳（deepseek-v4-pro）、codex-slot 借 codex 壳（deepseek-v4-flash）；借壳有 DEGRADED_RULES + AGENTS.md + kb_gate（2026-08-18 修复后），但**贵 5-10 倍**（见坑 6）
- **缺口：DS 缺一个专属轻量壳**——带 AGENTS.md + kb_gate、但不走 codex/claude 协议栈（避免协议硬转换和 token 爆炸）。识别到缺口后如实上报，不擅自改 ds_native_invoke.py（执行通道代码改动走执行器）

**执行规则：**
- 降级选 DS 直调时，任务书必须**自包含全部规则**（AGENTS.md 执行器铁律 + 输出协议 + 不调工具 + 落盘路径），因为直调没有壳注入
- 汇报「DS 直调」时不说「走壳/带规则」，如实说「裸直调、规则靠任务书自带」
- 派活前预检 DS 产物大小（`< 500 字节且含 <tool_calls>` = 模型行为异常，见 tool-call XML 坑），不能只看 dispatch PASS

### ⚠️ DeepSeek 官方 Harness 已开源（2026-08-13，改变「DS 没壳」结论）

2026-08-13 DeepSeek 发布 **DeepSeek Harness**（v0.1 开发者预览，MIT 开源，`everything is a plugin`）——模型/工具/技能/会话/沙箱/存储/循环/调度/UI 全部可插拔，上线当天 34k stars、一周 165k。这是 DS 官方自带的 agent 框架，理论上能补「DS 缺专属壳」的缺口（多步循环/工具/沙箱现成）。**注意**：v0.1 刚出 10 天，成熟度/与现有 TASK_GATE/kb_gate/attest 链整合均未知——**不能直接上生产，需先 claude/codex 拉源码实测**（插件机制、能否替代 ds_fallback 借壳、门禁对接点）。已建议排「DeepSeek Harness 实测分析」，未执行前维持「DS 直调裸、ds_fallback 借壳贵」现状判断。

**性能评测（2026-08-24 网上调研，未本机实测）：**
- Composio 30 项真实工具任务横评（同 V4 Flash 模型）：Oh My Pi 17/30（成功率最高但最慢 272s/任务）、Claude Code 16/30（最快 122s）、Codex 16/30、OpenCode 14/30（成本最低 0.073 美元/成功任务）——**DSH 未进前四**
- 另一组 30 任务横评（V4 Flash 接 8 套 harness）：Pi Agent 每成功任务 ≈0.028 美元、Claude Code ≈0.195 美元（差 7 倍）
- 媒体实测口碑：「能干活，但得盯着」——简单任务能完成、复杂任务纠错后完成度不错；**长任务和并行执行会出问题，对工具配置敏感**；特色能力=上层 DSH 可把 Claude Code 当子 Agent 调度（Claude Code 自己做不到）
- 结论：DSH 性能没有碾压 codex/claude（成功率同级 16-17/30），卖点是开放+便宜+可调度；**现阶段不接**，与「Hermes 调度 + codex/claude 干活」架构功能重叠；登记观察等稳定版

### ⚠️ DS 原生直调可能吐 tool-call XML 当正文（2026-08-24 打包任务书实测，201 字节垃圾）

`ds_native_invoke.py` 调 DS v4 pro 打包任务书时，DS 可能不写任务书正文，而是返回工具调用 XML（`<tool_calls><invoke name="exec">...`）原样落盘——落盘文件只有 201 字节，`decision=PASS` 且 exit 0，**格式校验不过才暴露**。这不是脚本 bug（token 校验/落盘都正常），是模型把「打包任务书」指令理解成要调工具执行。诊断：产物文件 `< 500 字节且含 `<tool_calls>`/`<invoke name=` 即实锤；不能只看 dispatch PASS/exit 0 就派下游。处置：DS 打包不可靠时不要反复重试烧 token（模型行为不保证变），如实报用户选替代通道——本次用户选「3=claude 直接打包+分析」，绕开「任务书归 codex」红线属用户显式批准。另：codex 额度尽时用户先拍板「2=DS v4 pro 降级」，DS 失败后才选 claude——降级通道选择顺序仍以用户拍板为准，Hermes 不擅自切。

### ⚠️ DS V4 推理 token 坑（2026-08-18 实测，白跑两轮）
`deepseek-v4-flash/pro` 走 chat/completions 时**默认开 reasoning**：`reasoning_content` 会**吃光整个 max_tokens 预算**，`content` 返回空字符串！实测：
- `max_tokens=8000` → `finish_reason: length`、`reasoning_tokens=8000`、content_len=0 → 落盘 0 字节文件
- `max_tokens=16000` → `reasoning_tokens=15999`（还是吃光）、content_len=0
- 测试 ping（`回复：OK`，max_tokens=100）正常返回 → 排除 key/网络问题，就是 token 预算分配问题

**诊断顺序（脚本已内置，见 `scripts/ds_native_chat.py`）**：先打印 `finish_reason` + `usage.completion_tokens_details.reasoning_tokens` + `len(content)`，reasoning_tokens ≈ max_tokens 且 content 空 = 推理吃光预算，不是模型没干活/网络挂了。**别只看 exit 0 或文件存在就交付**——0 字节文件是 exit 0 落盘的。

**修复方向（0818 实测验证）**：
- `max_tokens` 拉大（≥30000，DS 输出上限 384K）——**已验证有效**：`max_tokens=30000` + `chat_template_kwargs: {'thinking': False}` 时 `finish_reason=length`、`reasoning_tokens=24880`、**content_len=7523** → 内容成功落盘
- 注意：`chat_template_kwargs: {'thinking': False}` 未完全关掉 reasoning（reasoning_tokens 仍 24880），**大 max_tokens 是出内容的主因**；两参数一起用即可，别只开 thinking 关闭不带大预算

### ⚠️ 长输出仍会截断 → 续写拼接（2026-08-18 实测，分镜 43s 任务）
`max_tokens=30000` 能出内容了，但长文档（分镜定稿等）**仍会中途截断**：本次分镜 55s 定稿在镜头 5 中途 `finish_reason=length`，缺镜头 6 + 声音清单 + 合规标注，且**落盘文件是半截的，exit 0 不会提醒你**。

**续写拼接模式（已验证跑通）**：
1. 主任务照常跑 → 落盘半截文件
2. 拆缺失部分为续写任务：prompt 里**内嵌已有内容摘要 + 缺失字段的完整规格**（总表行/要求），明确「只输出缺失的剩余部分，不要重复已有内容」
3. 续写单独跑（同样大 max_tokens），产出存独立文件
4. python 拼接：主文件截到断点前 + 续写字段 + 尾部 → 写回定稿文件
5. **拼接后必跑结构校验**：`grep`/python 检查所有章节标记（### 镜头 N / ## 声音清单 / OUTPUT:）齐全 + 台词一致性（原片逐字稿每段首 6 字在成品中）——本次靠这步抓出「镜头 5 字段缺失」和「台词 28 段全在」两个结论
6. 多段续写可并行跑（每段一个独立 prompt 一个文件），再统一拼接

配套坑：**拼接口径**——续写只补缺失字段时，主文件截断点那行本身可能也是半句（本次「画面与动作」被截在行中），拼接时先补全截断行再插字段，别直接把两个文件硬拼。

## 硬红线（禁止降级，等 cc/codex 恢复）

判据不是任务大小，是**这一步错了能不能撤回**：
- 门禁注册表/状态机改写（一个 return 错了 = 19 门全锁或全放）
- skills 树删除/合并（Git 之外，删了不可回滚、审核无原文可比对）
- 任何主干 push / 外部平台发布 / 客户交付物定稿
- 数据迁移、schema 变更、批量删文件
- 安全边界改动（wrapper 白名单/key 处理/allowedTools/sandbox_mode）
- 首次客户方案/报价/策略定稿

灰区处理：拿不准当红线。降级期 prompt 写死：遇不可逆需求输出 `BLOCKED_NEEDS_PRIMARY:<原因>` 并停止。

## 恢复后清理

1. `git log --all --grep=DS_DEGRADED` + 扫 `outputs/degraded/` 列降级产出
2. 逐个过 cc 审查（排队那批）
3. 重点复核降级期新写的测试（DS 负向用例最可能不足）
4. 查有没有 `BLOCKED_NEEDS_PRIMARY` 被绕过执行

## 已知弱点（诚实说）

- DS 顶 cc 位能力评估只有 1 个样本（gate 审计），且是已知答案复现——未知问题表现无数据
- 没测长任务（128k 上下文跑 1h+ 会不会漂移未知）
- 单点依赖 DeepSeek——config 里 GLM-5.2/豆包标注可做第四条腿，但 **2026-08-24 实测：GLM key 已失效**（`34e34c...` 开头，POST open.bigmodel.cn 返回 `code:1000 身份验证失败`，glm-5.2 和 glm-4-flash 都一样，见 claude-code-ops 踩坑）；豆包只有看图不是编码 agent。**第四条腿实际不存在**——容灾补法：换新 GLM key 或开 Gemini/Kimi/Qwen 按量 API，或等 codex 恢复维持三执行器常态
- `danger-full-access` 无沙箱是最大残余风险

## ⚠️ DeepSeek 8/17 涨价：所有成本记忆作废，按新价重算（2026-08-24 调研确认）

DeepSeek 2026-08-17 生效新定价，引入峰谷计价（高峰=工作日 9-12/14-18，价格=空闲 2 倍；其余+周末=空闲）。**最高涨幅 1100%（缓存命中输入）**。旧价格记忆（0.025/3/6 元每百万、单镜 1.52 元等）全部过期，成本分析前先按新价重算：

| V4 Pro（元/百万 tokens） | 调价前 | 空闲 | 高峰 |
|---|---|---|---|
| 缓存命中输入 | 0.025 | 0.15 | 0.30 |
| 缓存未命中输入 | 3.0 | 4.5 | 9.0 |
| 输出 | 6.0 | 13.5 | 27.0 |

| V4 Flash（元/百万 tokens） | 调价前 | 空闲 | 高峰 |
|---|---|---|---|
| 缓存命中输入 | 0.02 | 0.05 | 0.10 |
| 缓存未命中输入 | 1.0 | 1.5 | 3.0 |
| 输出 | 2.0 | 4.5 | 9.0 |

**影响**：① 输出价涨 3.5-4.5 倍——DS 单步直调的便宜优势被削，单镜成本需按新价重算；② 缓存命中 vs 未命中差 30 倍——多轮循环（DSH 等 harness）的缓存命中率成为成本关键；③ 错峰省钱：空闲时段是高峰一半，能挪到非 9-12/14-18 跑的活省一半。详细价目与计算见 `references/ds-pricing-20260817.md`。

## ⚠️ 各家官方 Harness 已齐：ZCode / Qoder / DSH（2026-08-24 调研）

2026 年各家模型厂都出了官方编程 harness——「模型管推理，harness 管把推理变成结果」是行业共识（A good harness makes smart models smarter）。**「DS 没壳」是历史遗留**（2026-08-12 决策时 DSH 还没发布），现在选项变了：

| 模型 | 官方壳 | 状态 | 接入点 |
|---|---|---|---|
| GLM-5.2/5.3 | ZCode（智谱自研 Agent 内核，3.0 版 6/13 发布，用户破百万） | 成熟 | `zcode cli`，兼容 Anthropic/OpenAI 协议，open-ace PR #1074 已支持与 Claude Code/Codex 同等能力；**但本机 GLM key 已失效**（见 claude-code-ops），需换新 key |
| Qwen | Qoder（阿里，前身通义灵码，5/20 更名） | 成熟 | 全场景智能体，Quest Mode |
| DeepSeek | DeepSeek Harness（8/13 v0.1 预览） | 最晚、不稳 | 见上「DSH 已开源」节 |
| OpenAI | Codex | 成熟 | 现用 |
| Anthropic | Claude Code | 成熟 | 现用 |

**结论**：容灾补法不再是「给 DS 造壳」——哪家有成熟壳+便宜+能接工作流就接哪家。ZCode CLI 可以仿 codex_exec_gated.sh 姿势接入（AGENTS.md 注入 + kb_gate + token 校验），缺的是新 key。Qoder 同样可评估。**价格对比（2026-08-24 调研）：Qwen3.7-Max 限时 5 折（输出 18 元/百万）是旗舰里性价比最优，比 DS 高峰价还便宜；GLM-5.2/5.3 输出 28 元偏贵；Qwen3.8-Max 36 元最贵；DS 涨价后「最便宜」时代已过。完整表见 `references/cn-model-pricing-20260824.md`。**

### ⚠️ DS 轻量壳补不了多步循环：全挂容灾的正确姿势（2026-08-24 用户「轻量壳性能又不行」后定论）

用户连续质疑「直调规则没用了吧」「cc走的哪个壳」「ds没有自己专门的壳是吧」「如果加个harness呢」「轻量壳性能又不行」——逐层结论：

1. **轻量壳只补「规则注入」，补不了「多步 agent 循环能力」**：DS 原生 API 是纯文本 chat，无工具循环；轻量壳让 DS 从「裸奔」变「带规则的单步执行器」，适合打包/单步分析/盲评 Judge（DS 的 80% 职责），但改闸/改代码/跑测试收敛这类多步活仍然不行。
2. **给 DS 加 harness（自研 agent loop）= 造 codex 壳**：技术上可行（DS API 支持 function calling），但 tool calling 质量是「降级猜的」（codex 协议实测），无实测数据前是赌博；且 codex/claude 壳本身就是 harness，再造一个重复。
3. **DeepSeek Harness（官方）v0.1 预览版长任务不稳**：Composio 30 任务横评未进前四，成功率与 codex/claude 同级（16-17/30）；等稳定版。
4. **全挂容灾正解 = 主力执行器冗余，不是让 DS 完美顶班**：DS 只顶机械单步（冻结排队等恢复）；真正的保险是加一个同级第三执行器（ZCode/Qoder 接成熟壳），三选一同时挂概率断崖下降。GLM key 已失效是当前硬缺口（见「已知弱点」）。

### ⚠️ codex 报 401 但任务能跑：判断可用性看完整输出，不看错误日志（2026-08-24 实测，用户「codex不是升级pro了」后纠正）

codex exec 报 `401 Unauthorized: Provided authentication token is expired.`（models 列表刷新 + websocket 连接失败）时**任务仍可能成功**：fallback 通道照样执行、输出正常、tokens used 照扣（实测「只回复OK」→ OK + 11,194 tokens + EXIT=0）。本会话因此误报「codex 不可用」，被用户质疑后完整跑才发现能跑。判定步骤：
1. **完整跑一次小任务**看最终输出和 exit code——不是看前几行错误日志就下结论
2. `auth.json` 里 access_token exp 在未来 ≠ 服务端没吊销（本地缓存可能被别处刷新顶掉；exp 9/3 照样 401）
3. 401 是 websocket 通道的，HTTP fallback 可能正常
4. 可用性结论必须基于「端到端小任务跑通」，不是日志无错

### ⚠️ 执行器模型身份必须实测：attest 硬编码会失真（2026-08-24 用户「你确定我们用的sonnet？」后纠正）

claude 实际模型 = **claude-opus-5**（2026-07-24 发布旗舰），不是 attest 里硬编码的 `claude-sonnet-4`。判定方法（不能再靠 attest/文档断言）：
1. **实测自报**：`CLAUDE_CODE_USE_BEDROCK=1 AWS_REGION=<region> AWS_BEARER_TOKEN_BEDROCK="$(cat ~/.hermes/claude_bedrock_key)" claude -p "只回复你的模型ID" --output-format text` → `claude-opus-5`
2. **debug 日志**：`~/.claude/debug/*.txt` 里 `model=us.anthropic.claude-opus-5` + `[API REQUEST] /model/us.anthropic.claude-opus-5/invoke-with-response-stream`
3. **attest 记录不可信**：write_attest.sh 第 4 位参数是硬编码字符串，改 wrapper 时没同步 → 记录与实测不符（sonnet-4 vs opus-5）
4. **成本必须按实测模型算**：Opus 5 = $5/$25（输入/输出），不是 sonnet 的 $3/$15——估错模型 = 成本差 60%+

**转述执行器产出前先实读核验（2026-08-24 用户「8镜和7镜怎么来的」「我看原片后面男的不就两段」后纠正）**：Hermes 转述 claude/codex 交接包里的数字/结论前，关键数字必须自己实读原文件核对——本会话把交接包「门禁校验的是旧版分镜」转述成「新 8 镜 vs 旧 7 镜」，实读发现两版生成镜都是 7 个（S08 尾卡不算生成镜），转述时脑补了镜数差异。规则：①交接包/报告的「待确认项」不跳过 ②用户看过原片的直觉优先级最高（「后面男的不就两段」→ 实读 FULLSCAN 确认 23.950/34.600 是 UI 层切换不是人物硬切）③执行器报告是「待验证假设」不是「事实源」——reverse_prompt_merge 报告实读抓了旧报告 6 条漂移。

**成本估算基准（2026-08-24 实测 + claude 评审修正，⚠️「本地不记 usage」已被推翻）**：
- **claude jsonl 有完整 usage**：`~/.claude/projects/**/*.jsonl` 每条 assistant 消息的 `message.usage` 带 `input_tokens`/`cache_creation_input_tokens`/`cache_read_input_tokens`/`output_tokens`，`message.model` 有模型名——早前「无 usage 记录」是查询脚本 bug（查顶层 `d.get('usage')` 而非 `d.get('message',{}).get('usage')`）。对账可直接聚合，不用估。
- **codex rollout 有 token_count**：`~/.codex/sessions/**/rollout-*.jsonl` 带 `token_count`（992 个里 968 个 98% 覆盖，全量 13.7 亿 token）。
- **轮数统计必须按 message.id 去重**：同一次 API 调用的 text/thinking/tool_use 拆成多条 jsonl 记录——160 条记录去重后只有 68 次真实调用，按条数数轮虚高 ~2.4 倍。轮数 = 去重后 message.id 数 ≈ 工具调用数 × 1.9。
- **真实成本大头是 thinking token**（claude 评审实测 $12.78/会话）：输出 45.4%（其中 99% 是不落盘的 thinking）> 缓存写入 27.2% > 缓存读取 27.1% > 未缓存输入 0.3%。压固定前缀（AGENTS.md 注入）只省缓存读 $0.12/任务、改前缀触发缓存失效反而 $0.55；按字节估算成本会低估 thinking 78 倍。
- codex 一次完整分析任务实测 = **224,914 tokens**（codex CLI 输出 tokens used）
- Hermes 主对话侧成本账查 `~/.hermes/state.db` 的 `session_model_usage` 表（**first_seen/last_seen 是 unix 时间戳不是字符串**，按 datetime 比较会查不到；estimated/actual_cost_usd 全 0 未算钱）
- 优化方向（codex 报告 `projects/token-optimization/staging/TOKEN_OPTIMIZATION_PLAN_20260824.md` + claude 评审 `staging/CLAUDE_OPTIMIZATION_REVIEW_20260824.md`）：P0 任务书内嵌定案+一次性 Source Map+单一 verify 脚本+输出模板+工具预算（160→80-100 轮）；P1 规则投影+Context Bundle+usage ledger+attest 修正；P2 证据编译器双阶段+模型路由+会话 rollover（目标 35-55 轮）。**claude 反对 P1-1（压注入）主张 P2-1 证据编译器提前**（打 thinking 大头）；自检逐项跑 grep 是最大浪费（应合并成 verify_storyboard_checks.py 一次跑完）。
- **usage 对账直接跑 `scripts/usage_ledger.py`（2026-08-24 建，实测近 3 天 claude $528≈¥3803 / codex 70 亿 token）**：只读聚合 claude jsonl（message.usage）+ codex rollout（payload.type=token_count）+ Hermes state.db session_model_usage；`--days N` 按天出表、`--json` 出结构化。价格参数在脚本头部 PRICES 可调（opus-5 $5/$25/$0.5缓存读/$1.25缓存写）。任何「claude/codex 花了多少 token」类问题先跑它，不凭记忆估。
- **P0 落地产物（2026-08-24 合并拍板后已建，直接复用）**：`projects/token-optimization/templates/TASKBOOK_V2_TEMPLATE.md`（任务书五块结构：USER_REQ 原话/APPROVED_DECISIONS 定案胶囊带来源行号/SOURCE_MAP/OUTPUT_TEMPLATE/VERIFY_COMMAND+工具预算）；`projects/token-optimization/scripts/source_map.py`（Source Map 生成器，兼容新旧任务书格式——SOURCE_MAP 表格段或 DATA_SOURCE 逗号列表都认，输出文件 hash+行数+关键词命中行）；`projects/token-optimization/staging/MERGE_OPTIMIZATION_PLAN_20260824.md`（采纳/拒绝清单：P0-1~P0-5 采纳、P1-1 拒绝、P1-3 降级只读聚合器、P2-1 提前、harness 改壳换 DS）。派活任务书从旧格式换 v2 时用这三个文件。**任务书 READ_SKILL 必须每行一个、禁止逗号列表**（kb_gate_sg.py 字符串精确匹配 `"READ_SKILL=seedance-2-0-mini-workflow" not in prompt`，逗号列表连续两次被 BLOCK，见 task-brief-gate 4b）。

### ⚠️ 自建 DS 壳：规则层平移 + 执行方式切换（2026-08-24 用户「自建一个壳用DeepSeek来做」）

codex/claude 断供 → DS 转正时**不要从零造壳**：codex_exec_gated.sh 的 12 条规则（token 闸/kb 闸/flock 并发/workdir 白名单/attest 双签/日志/require-in-project/审计）**全部模型无关**，只有最后一行「调 codex」跟模型有关。方法：
1. 复制 codex_exec_gated.sh → 通用壳，只改执行段（codex CLI → DS API 调用）
2. 补 ds_native_invoke.py 差距：kb 闸、flock、attest、日志（当前只有 token 校验，4.2KB vs codex 壳 11KB）
3. **执行方式必须从「agent 工具循环」换成「喂饱直调」**：DS 原生 API 没有工具（不会自己读文件/跑命令），任务书必须自包含——数据源内容内嵌或 Hermes 预读拼接，DS 一次吐完
4. 代价：DS 直调无多轮自我修正，一次成型错了就错——质量防线 = 任务书写得比给 codex 更细 + 产物独立复核

**执行链路判断点（为什么 Flash/Pro 包不下「整个执行」，2026-08-24 用户连环追问后定论）**：执行不是纯机械，链路里嵌着判断点——①出片质检（抽帧看图判好坏，需视觉）②异常处理（API 报错/素材缺/门禁拦，弱模型会脑补方案）③内容微调（出片差一点改提示词重跑，镜2 教训）④不可逆提交（人工门）。弱模型在判断点上崩；正解 = 机械部分给 DS（MECHANICAL 全接 / ANALYTIC 出证据）、判断点回高级模型或人（CREATIVE 不碰 DS）。**「DS 只当手，不当脑」**；方案完备性（codex 出方案写到执行零判断）只能消掉部分判断点，异常/质检/主观裁决消不掉。

### ⚠️ GLM 5.2 同类推理 token 坑（2026-08-27 实测，广州机 glm_native_invoke.py）

GLM 5.2（阿里云百炼 MaaS）**也是推理模型**，和 DS V4 一样默认开 reasoning。症状完全相同：API 返回 200 但 `content` 为空、`finish_reason=length`、`reasoning_tokens` 吃光 `max_tokens` 预算、落盘 0 字节文件。

两个修复（已部署广州机）：
1. **`max_tokens` 8192→16384** — 推理 + 输出共用额度，8192 不够推理完就输出
2. **`extract_content()` 加 `reasoning_content` 回退** — content 为空时读 reasoning_content，避免拿到空字符串判定"无产出"

**任务书优化**：之前让 GLM 自己 `read_file` 读 4 份文件 + 10 维度分析，25 轮不够（轮次耗尽无产出）。改为**全部数据直接内嵌任务书**，GLM 不读文件直接干分析 + 写报告，2 轮就出活（11688 字符报告）。

完整修复细节 + SSH heredoc 变量不展开的坑 + 与 DS V4 对比表 + **GLM 5.2 思考不可关闭实测**（`enable_thinking` 无效，1+1 烧 84 reasoning token，relay 纯透传不修改参数）：`references/glm52-reasoning-model-fix-20260827.md`

### ⚠️ 主会话模型无 fallback：GLM relay 挂了全哑（2026-08-27 实测）

与执行器容灾（codex/claude → DS）不同，**主会话模型**的容灾是另一个层面。2026-08-27 实测发现：

**现状（新加坡机）：**
- 主会话模型 = GLM 5.2，走本机 `127.0.0.1:18890` relay → 广州中转 → 阿里百炼 MaaS
- relay 进程由 systemd 管理（`glm-aliyun-proxy.service`），当前活着
- **relay 是纯透传代理**（`glm_aliyun_proxy.py`），body 原封不动转发，不修改任何参数——config 里配什么就传什么
- **config.yaml 里 `fallback: NOT SET`** — 没有配自动切换
- WeChat + 飞书 DM + 飞书群全机共用这一条腿
- relay 挂 = 微信和飞书同时哑，无自动恢复
- **GLM 5.2 思考不可关闭**：即使 `1+1=?` 也烧 84 reasoning tokens，每次调用都在为思考付费

**config.yaml 当前 provider 布局：**
- `custom_glm`：GLM 5.2，本机 relay（active，主会话用）
- `custom_custom`：DeepSeek V4 Pro，api.deepseek.com（可用但未配为 fallback）
- `custom_ark`：豆包 Seed 2.0 Mini，ARK API（可用）

**广州机不同：** 广州机 active provider = `custom_custom`（DeepSeek），走 DS 直连不走 GLM relay。两机主会话模型不同。

**如果 GLM relay 挂了怎么办（当前手动流程）：**
1. 诊断：`curl -s http://127.0.0.1:18890/` 看有没有 `{"status":"ok"}`
2. relay 进程：`systemctl --user status glm-aliyun-proxy.service`
3. relay 无法恢复 → 手动改 config.yaml `model.provider` 切到 `custom_custom`（DS）
4. 重启 gateway 生效

**建议的 fallback chain（需用户确认后落地）：**
- config.yaml 加 `fallback: custom_custom`，GLM relay 挂了自动切 DS
- 注意：DS 8/17 涨价后成本高（高峰输出 27 元/百万 token），不能长期当主模型
- 另一个选项：`fallback: custom_ark`（豆包），便宜但能力弱
- 广州机 GLM key 已失效（见「已知弱点」），不能作为 GLM 冗余

**关键区分：**
- 执行器容灾（codex/claude → DS）= 生成任务降级，影响内容产出质量
- 主会话容灾（GLM → DS）= 调度层降级，影响所有平台对话能力，客户直接感知
- 两个容灾层面独立，不能混为一谈

### ⚠️ GLM 内容审核拦截 data_inspection_failed（2026-09-06 实测）

GLM 5.2 内容审核（content moderation）判定会话上下文含敏感内容时返回 HTTP 400 `data_inspection_failed`，**不可重试**。用户看到 "⚠️ The model provider failed after retries" 误以为是网络问题，实际是内容审核拒绝。诊断：查 `errors.log` 找 `BadRequestError` + `data_inspection_failed`。修复：**开新会话**（旧会话上下文无法清洗）。handoff 归档文件字段可能为空，需从项目目录文件系统状态恢复进度。详见 `references/glm-content-moderation-400-20260906.md`。

## 相关

- **DS reasoning 开关与成本（2026-08-24 落地，含 pro 关思考决策）**：`references/ds-reasoning-toggle-cost-20260824.md`——DS flash/pro 默认开思考且按输出价计费（近30天 flash 30.5%、pro 42.9% 是 thinking），主对话/机械调度关掉纯赚；正确改法是 per-model overrides（`reasoning_effort: none`）；⚠️ **pro 不能一刀切关**——pro 挂着 codex 降级智力活（分镜/文案/分析/报告），降级到 pro 干智力活时必须**临时把 pro 思考开回来**（`hermes config set agent.reasoning_overrides.deepseek-v4-pro high` 或干脆删掉 pro 的 none override）。判断标准：DS 走主对话调度/机械 = 关 thinking；走降级智力活/深度分析 = 留 thinking。本机实测 pro 最后一次使用是 2026-08-14，当前 pro 空闲、关思考不误伤任何活跃任务。接「DS 关思考/省 thinking 成本」类问题先读该文件。
- **全挂容灾方案评估（2026-08-24）**：`references/ds-total-outage-failover-20260824.md`——codex+claude 都挂时的行动顺序、DS 三条路（直调/借壳/轻量壳）取舍、DSH 评估结论。**接全挂/容灾类问题先读该文件。**
- **GLM 5.2 沙箱 300s 超时 + codex_glm_fallback.sh token 自动生成（2026-08-27）**：`references/glm52-sandbox-timeout-20260827.md`——GLM agent 在沙箱里浪费时间探测 Ollama 风格 API 端点导致超时被杀（stdout/stderr 全空，0 tool calls），诊断方法和处置。codex_glm_fallback.sh 自己生成 gate token 不需要手动设。
- **任务书打包卡点（2026-08-18 已落地）**：`references/ds-direct-api-bypasses-executor-gates-20260818.md` 已更新为落地状态——gate_config.yaml + task_brief_gate.py + hermes_task_dispatch.py + ds_native_invoke.py 全套，主对话派活必须走统一入口带强制标记。**接内容生产任务先读该文件。**
- review-fix-verify-loop：审查-修复-验证循环（user-owned，建议 `hermes curator adopt` 后可写）
- claude-code-ops / codex-cli-ops：各执行器调用参数
- codex-bridge：Hermes 调 codex 的任务打包规则
