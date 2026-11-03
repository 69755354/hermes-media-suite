---
name: codex-workflow-deployment
description: 在新机器配codex、把Hermes工作流搬去codex、codex按SOUL干活时用。
---

# Codex 工作流部署（Hermes → Codex CLI 迁移）

## 触发条件
- 用户说「新机器（新加坡/香港/海外）上装了 codex，按现有工作流和 SOUL 配」
- 把 Hermes 的 skills / SPEC / gate 脚本搬到另一台跑 Codex CLI 的机器
- Codex 干活不遵守工作流规则（缺 AGENTS.md 或技能没同步到位）

## Codex 四层配置体系（映射表）

| 层 | Codex 位置 | 作用 | 对应 Hermes |
|:---|:---|:---|:---|
| 指令层 | 项目根 `AGENTS.md` 或 `~/.codex/AGENTS.md` | 项目规则、能做什么不能做什么 | SOUL.md（**转译版**） |
| 技能层 | `~/.codex/skills/<name>/SKILL.md` | 流程剧本，description 自动匹配触发 | skills/ |
| 偏好层 | `~/.codex/config.toml` | 模型、权限、MCP、sandbox | config.yaml |
| 权限层 | config.toml 内 approval_policy / sandbox_mode | 安全边界 | guard 脚本 |

## SOUL → AGENTS.md 转译（禁止直接拷）

- Hermes 用 `skill_view()` 工具加载技能；**Codex 没有这工具** → AGENTS.md 里写 `@技能名` 强制引用，靠 SKILL.md 的 description 自动匹配
- **description 写触发词、别精简**——Codex 靠它决定是否加载（截断也能匹配到）
- 保留全部方法论/信条/合规红线/说话风格，只改工具调用方式
- 模板见 `templates/codex-AGENTS.md`（可直接 scp 使用）

## 部署步骤

1. 目标机建目录：`mkdir -p ~/workflow/{wiki,skills,scripts,projects}`
2. rsync wiki 知识库（`--partial` 防中断，排除媒体大文件 mp3/png，分两批传）
3. rsync 核心技能到 `~/.codex/skills/<name>/`（video-production / huoshan / workflow-execution-guard / content-review-gate / content-data-review / content-redlines / monetization-first-analysis）
4. rsync gate 脚本到 `~/workflow/scripts/`
5. 推 AGENTS.md + config.toml（`approval_policy="on-request"`，**禁止 never**——但见下面 exec 模式坑）

## 🎭 人设分流：对话版 vs 执行器版（2026-08-09 用户定案）

**先问架构再定 AGENTS.md 人设——Codex 直接跟用户对话，还是被 Hermes 调用？**

| 架构 | AGENTS.md 人设 | 关键差异 |
|:---|:---|:---|
| **Codex 直连用户**（CLI/微信直接跟 codex 聊） | 对话人格版（`templates/codex-AGENTS.md`） | 保留长沙话/emoji/留钩子/称呼 |
| **Hermes 当前台 + Codex 后台执行器**（微信→Hermes→调 codex exec） | **执行器版**（`templates/codex-AGENTS-executor.md`） | **不寒暄不闲聊**、产出落盘文件、四种状态码协议 |

**执行器版必须改掉：**
- ❌ 删掉说话风格（长沙话/emoji/称呼「老爷」/留钩子/闲聊）——codex 不跟客户说话
- ❌ 删掉「跟用户对话」相关表述

**执行器版必须保留：**
- ✅ 五件套强制加载链 / 物理卡点 / 节点产出格式 / 合规红线 / 送客词禁令（干活规则全留）
- ✅ **决策机制（五智囊×六顶）**——见下面「干活规则别漏决策框架」

**执行器版必须新增（输入/输出协议）：**
- 输入：Hermes 打包（客户需求+上下文+指令），缺信息输出 `NEED_INFO: <缺什么>` 不瞎猜
- 输出：只认四种状态码，别的不许自创
  - `OUTPUT: <绝对路径>`（结果落盘）
  - `COMPLIANCE: <问题点>`
  - `BLOCKED: <原因>`
  - `NEED_INFO: <缺什么>`

## 🧠 干活规则别漏决策框架（2026-08-09 用户纠正）

**用户原话：**「干活规则不是还有什么5智囊团 6个帽子哪些吗」——初版 AGENTS.md 漏了 decision-framework，被当场纠正。

AGENTS.md 方法论必须包含（转译自 thinking/decision-framework skill）：
- **分轨判据**：决定错了是「重写一次文案」还是「全链路返工」→ 前者决策卡片，后者完整版
- **完整版（策略/决策/分析类）**：第一轮五智囊对抗（反驳者/本质追问者/机会发现者/外行人/无情执行者）→ 第二轮六顶查漏（白/黄/绿/红帽）→ 第三轮主席综合+行动收尾
- **决策卡片（文案创作类）**：9 项速评，≤一页纸
- ⚠️ 策略类不能用卡片糊弄，创作类不能用完整版（太重被弃用）；分析完必须给「行动」

## ⚠️ 核心坑：gate 脚本硬编码源机路径（必踩）

`review_gate.py` / `data_source_gate.py` 里有硬编码绝对路径：
- `GUARD_LOG = "/home/ubuntu/.hermes/guard/security_alerts.log"`
- 绝对路径调兄弟脚本：`python3 /home/ubuntu/.hermes/scripts/data_source_gate.py`
- `update_state.py`、`node4_review_scorer.py` 读 `/home/ubuntu/.hermes/config.yaml` 的 `model.api_key`

症状：`FileNotFoundError: [Errno 2] .../guard/security_alerts.log`

修法（**别改脚本源码，保持字节一致不漂移**）：
1. 目标机建同构目录：`mkdir -p ~/.hermes/guard ~/.hermes/scripts`
2. 推齐依赖脚本（data_source_gate.py + update_state.py）到 `~/.hermes/scripts/`
3. 生成精简 config.yaml（只含 model 段 + api_key，**别把整个 Hermes config 推过去**——含飞书/微信/网关敏感配置）

## 零成本验证清单（不烧 token）

- `review_gate.py check /tmp/nonexist node3_candidate` → 退出码=1（BLOCKED 拦截生效）
- `~/.hermes/guard/security_alerts.log` 有写入
- `data_source_gate.py` / `update_state.py` 帮助正常输出
- 技能 SKILL.md frontmatter（`name:` 行）完整
- **真跑 LLM 测试（codex exec 实际生成）前必须问用户**——烧 token 属付费操作

## 坑清单

1. **权限别开 `approval_policy="never"`** —— 物理卡点脚本的意义就是拦截，never 直接绕开确认闸，违背「客户说跳过才跳过」规则
2. **无 Helper API 中间层**：源机流水线有本地 Helper API（retry+合规统一入口），Codex 直调火山 API 要自己处理重试——AGENTS.md 注明「失败重试≤3 次」
3. **AGENTS.md 放项目根**，Codex 按启动目录加载——所有任务在 `~/workflow/` 下跑，换目录就加载不到
4. **查「远程机」信息前先验证本机身份**：`hostname` + `curl ifconfig.me`。血泪案例：把 SSH 自己公网 IP 当「另一台机器」，两边文件当然一模一样，白折腾半天还差点编出迁移方案
5. rsync 大目录中途断：`--partial` 续传 + 排除媒体文件分批传
6. **TOML 表陷阱（2026-08-09 实测）：顶层键必须写在所有 `[...]` 表之前**。config.toml 里 `model`/`approval_policy`/`sandbox_mode` 写在 `[projects."..."]` 之后会被 TOML 归进该表，导致配置不生效（`codex exec --strict-config` 报 `unknown configuration field projects....model`）。修法：顶层键放文件最顶部，`[表]` 全放后面
7. **codex exec 非交互模式强制 `approval=never`（2026-08-09 实测）**：即使 config.toml 写了 `on-request`，exec 模式（无终端弹确认框）运行也显示 never——这是设计使然，靠 `sandbox_mode="workspace-write"` 兜底（只能写工作区）。**交互模式**（直接敲 `codex`）才真正生效 on-request。别把 exec 显示的 never 当配置失效去反复改
8. **别自作主张改目标机模型（2026-08-09 用户纠正）**：配 config.toml 时用目标机默认模型，别因为「知道更好的」就写 `model = "xxx"` 降级/改掉。用户原话：「他用的就是5.6 你配置5.5干嘛」。**模型选择权在用户/目标机，不在配置者**——除非用户明确要求换模型，否则 config.toml 不写 model 字段（用默认）

## 相关文件

- `templates/codex-AGENTS.md` — 对话人格版模板（Codex 直连用户场景，SOUL 转译版，可直接 scp）
- `templates/codex-AGENTS-executor.md` — **执行器版模板（Hermes 当前台 + Codex 后台执行器场景，2026-08-09 用户定案）**：不寒暄、落盘产出、四种状态码协议、含五智囊×六顶决策机制
- 完整部署方案文档：源机 `~/deliverables/codex-sg-deploy.md`
