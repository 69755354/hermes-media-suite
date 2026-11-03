---
name: codex-bridge
title: 转 Codex 桥（Hermes→Codex 任务分发）
description: Hermes 收到分析/创作/搜索/写码类任务时，打包上下文调 codex exec 干活，解析状态码回传。触发词：写文案/做分析/拆解/复盘/出方案/写代码/标题/选题/口播/剧情/探店/竞品/策略/搜索爆款/合规研判。
---

# 转 Codex 桥

## 定位
Hermes = 纯管道（对话/执行/质检/交付），Codex = 一切智力活（分析/创作/搜索/写码/研判）。

**规则：** 收到正经活（分析类/创作类/搜索类/写码类）→ 打包上下文 → 调用执行器 → 解析状态码 → 转白话回传。**禁止 Hermes 自己分析/创作内容。**

> 🚨 **执行器分流规则（2026-09-04 用户定案）：**
> - 用户明确说「用Claude」「用cc」「Claude来改/来分析/来写」→ 走 `claude -p`（本机 `/home/ubuntu/.npm-global/bin/claude`，Bedrock 认证），**不走 `codex exec`**
> - 用户明确说「用codex」或未指定执行器 → 走 `codex exec`（默认）
> - 判断依据：用户原话里有没有「Claude」「cc」「claude」字样，有就走 Claude，没有就走 codex
> - **禁止把用户说的「用Claude」自行翻译成 codex exec**

## 触发条件
用户提出以下需求时自动触发（不等用户要求）：
- **分析类**：爆款拆解/数据复盘/竞品拆解/行业洞察/策略方案/用户画像/合规研判
- **创作类**：口播稿/剧情/探店文案/标题/选题/台词/改稿/润色
- **搜索类**：搜爆款/搜同行/搜素材（3点法第1步）
- **写码类**：写脚本/搭工作流/写代码
- 拿不准 → 按「错得起/错不起」判：重写一次就够的 Hermes 干，全链路返工的给 Codex

> 🚨 **长文写作分流（2026-08-15 用户定案）：** **长文/小说/网文/长篇创作禁用 Codex，直接用 DeepSeek**（成本考量：codex 按 gpt-5.6-sol 输出 $30/M，DeepSeek 便宜一个量级）。短内容（口播稿/文案/标题/剧情）仍走 codex。长文写作任务：打包 prompt 给 DeepSeek（本机 hermes 默认模型），产物标注执行者 ds。

> 🚨 **硬指令（2026-08-10 用户定案）：** SOUL.md 已加「创作/分析/搜索类必须先调 codex，禁止 DeepSeek 直出」——本 skill 的触发规则与 SOUL.md 联动，不是可选项。广州机调用入口：`echo "任务" | bash ~/.hermes/scripts/codex_remote.sh`（SSH 远程新加坡 codex）。

## 调用命令模板

### Claude 调用模板（用户明确说「用Claude/cc」时走这个）

> ⚠️ **广州机不能直连 Bedrock**（中国 IP 被 Anthropic 地区限制，报 400 Access not allowed）。
> Claude 只能在新加坡机上跑。广州机小鹿调用时必须 SSH 到新加坡机执行。

**新加坡机本地直接跑：**
```bash
# Bedrock 认证（key 从文件读，不进 argv）
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-east-1
export AWS_BEARER_TOKEN_BEDROCK="$(cat /home/ubuntu/.hermes/claude_bedrock_key)"

# prompt 写文件再走 stdin（防中文分词拆碎）
printf '%s' "$PROMPT" > /tmp/claude_prompt.txt && chmod 600 /tmp/claude_prompt.txt
cd /home/ubuntu/workflow && claude -p --output-format text < /tmp/claude_prompt.txt 2>&1 | tail -100
```

**广州机小鹿通过 dispatcher 调 Claude（必须走 dispatcher 拿 token，不能直接跑 wrapper）：**
```bash
# 1. 写任务书（含 TASK_TYPE 字段）
cat > /tmp/claude_brief.txt << 'EOF'
TASK_TYPE=分析
PROJECT=test-claude
REQUEST=<用户原话或任务描述>
EOF

# 2. 写 prompt 文件
cat > /tmp/claude_prompt.txt << 'EOF'
<完整的 Claude prompt>
EOF

# 3. 走 dispatcher（它会在新加坡机上执行，自动签 token + 调 wrapper）
python3 /home/ubuntu/workflow/hermes_task_dispatch.py \
  --brief /tmp/claude_brief.txt \
  --project test-claude \
  --target claude \
  -- /tmp/claude_prompt.txt
```

> ⚠️ 不能直接跑 `claude_remote_wrapper.sh`——必须走 dispatcher 拿 TASK_GATE_TOKEN，否则被闸拦报 `BLOCKED: 缺少 TASK_GATE_TOKEN`

- claude 不支持 `-C` 参数（那是 codex 的），用 `cd <workdir>` 代替
- 并发锁与 codex 共用 `flock /tmp/codex.lock`（防 OOM）
- 详见 claude-code-ops 技能

### Codex 调用模板（默认执行器，用户未指定或说「用codex」时走这个）

```bash
# 机械执行类任务（写码/合规检查/数据搬运/分镜/生图/合成）→ effort=low 无情执行
cd /home/ubuntu/workflow && flock /tmp/codex.lock -c "codex exec --skip-git-repo-check -c model_reasoning_effort=low -C /home/ubuntu/workflow \"<PROMPT>\" 2>&1 | tail -100"

# 分析类任务（爆款拆解/数据复盘/竞品分析/策略方案/用户画像/合规研判）→ effort=high 深度推理
cd /home/ubuntu/workflow && flock /tmp/codex.lock -c "codex exec --skip-git-repo-check -c model_reasoning_effort=high -C /home/ubuntu/workflow \"<PROMPT>\" 2>&1 | tail -100"

# 创意类任务（选题/剧本/口播稿/标题/文案）→ effort=high 放开推理
cd /home/ubuntu/workflow && flock /tmp/codex.lock -c "codex exec --skip-git-repo-check -c model_reasoning_effort=high -C /home/ubuntu/workflow \"<PROMPT>\" 2>&1 | tail -100"
```

- **温度不用配**：codex 0.147 不支持 temperature 参数（顶层/模型段都不认），OpenAI 设计就是不给暴露低层采样参数——用 `model_reasoning_effort` 语义旋钮按执行内容调
- **effort 按内容定**：机械执行类（写码/合规检查/数据搬运/分镜/生图/合成）→ `low` 无情执行；深度分析类（拆解/复盘/竞品/策略/画像/研判）→ `high` 推理放开；创意发散类（选题/剧本/文案/标题/口播稿）→ `high`
- 超时：分析/创作类 300s；写码/长任务 600s
- 失败重试：最多 2 次（网络抖动/超时重试），重试后仍失败 → 报 NEED_INFO 给用户
- **别用交互模式**，exec 非交互即可

## 上下文打包格式（PROMPT 怎么拼）

```
[角色] 你是后台内容执行器，产出结果文件，不跟用户对话。
[客户需求] <原话>
[上下文] 行业=<行业> | 平台=<平台> | 项目目录=<路径> | 已有素材=<列表>
[产出要求] <要什么：台词本/分镜表/分析报告/提示词包/代码>
[约定] 产出写文件，结尾一行 OUTPUT: <路径>；有合规问题 COMPLIANCE: <点>；卡点 BLOCKED: <原因>；缺信息 NEED_INFO: <缺什么>
```

拼装规则：
- **项目目录**：`~/workflow/projects/<项目名>/`，不存在先 `mkdir -p` 建好
- **已有素材**：客户发的图/文件先落盘到项目目录 `assets/`，把路径列给 Codex
- **平台**：从对话判断（抖音/小红书/视频号/公众号/口播），判断不了问一句
- **行业合规**：提一句行业（如中医保健/餐饮/教培），Codex 自己查红线

## 状态码解析（codex 输出尾部）

| 状态码 | 含义 | Hermes 动作 |
|:---|:---|:---|
| `OUTPUT: <路径>` | 产出文件已落盘 | 读文件 → 转白话 → 回传微信 |
| `COMPLIANCE: <问题>` | 合规拦截 | 改文案措辞再回传，别硬发 |
| `BLOCKED: <原因>` | 卡点拦截 | 按原因补材料 → 重新调 codex |
| `NEED_INFO: <缺什么>` | 缺信息 | 问用户 → 补齐再调 |
| 无状态码 | 输出异常 | 重试 1 次，仍无 → 报错给用户 |

## 回传微信流程

1. codex 产出后，Hermes 读结果文件（read_file）
2. **转客户白话**：去掉内部术语/路径/工具名，客户能看懂
3. 长内容分条回（微信会被折叠）：结论 → 要点 → 下一步
4. 涉及生成物（图/视频/文档）→ 交付铁律：原生发或外部 URL，禁内部路径

## 执行后（Codex 产出校验）

- 有产出文件 → 按工作流卡点跑一遍：
  - 文案类：`python3 ~/.hermes/scripts/review_gate.py check <项目目录> node3_candidate`（若在节点3-4）
  - 生图/生视频：用 vision_analyze 自检质量（生图铁律：必自调）
- 卡点不过 → 把结果反馈给 Codex 重写（不是 Hermes 自己改）

## 边界（不要做）

- ❌ Hermes 不自己分析/创作内容（只打包+转发+转述）
- ❌ 不修改 codex 产出的内容（想改 → 反馈 codex 改）
- ❌ 不跳过卡点脚本（物理卡点是底线）
- ❌ 不承诺「一定爆」（算法没人说得准）
- ✅ 闲聊/寒暄/进度/简单执行（生图执行/合成）Hermes 自己干

## 示例

**输入：** 客户做中医保健+护肤品，长沙，写30秒口播文案
**调用：**
```bash
cd /home/ubuntu/workflow && codex exec --skip-git-repo-check -C /home/ubuntu/workflow "[角色]后台执行器。客户做中医保健同时卖护肤品，店在长沙。写30秒口播文案，口语化有钩子，行业=中医保健+护肤，平台=抖音，项目目录=~/workflow/projects/zhongyi_koubo。产出写文件，结尾 OUTPUT: 路径" 2>&1 | tail -100
```
**预期：** codex 加载 huoshan 口播分支 + content-redlines 保健红线 → 输出台词本（≤10s/段）→ `OUTPUT: ~/workflow/projects/zhongyi_koubo/台词本.md`

## 关联
- AGENTS.md（codex 侧规则）：`/home/ubuntu/workflow/AGENTS.md`
- codex 技能：`~/.codex/skills/`（huoshan/content-redlines 等）
- 卡点脚本：`~/.hermes/scripts/`（review_gate 等）
- 分工定义：wiki/concepts/codex-imagegen-location.md（生图分工）
