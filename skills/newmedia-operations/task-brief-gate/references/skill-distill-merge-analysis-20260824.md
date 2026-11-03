# 蒸馏能力融合分析派活 + 用户裁决流程（2026-08-24 实录）

reverse-video-prompt 蒸馏产物与现有复刻/反推体系融合分析。完整闭环：蒸馏产物落盘 → 派 codex 打包 claude 分析任务书 → claude 出 12 节融合报告 → 用户 11 条裁决 → P0 决策清单 → 派 claude 按裁决落地分析。

## 一、融合分析传话书结构（Hermes 只传话）

```
TASK_TYPE=分析
READ_SKILL=seedance-2-0-mini-workflow   # 必带：USER_REQ 含「出片」闭环词会触发 kb_gate（见 SKILL.md 对应 pitfall）
PROJECT_DIR=<项目>
PRELOAD_NODES=1,2,3,4
USER_REQ=<用户原话一字不差>
DATA_SOURCE=蒸馏产物（SKILL.md/prompt-framework/iteration-workflow/我方 v4.0）+ 现有 skill 清单（video-remake/video-reproduction/video-reverse-engineering/huoshan/seedance 系列）
产出要求=<一句话：能力矩阵对比→补缺映射→闭环落位→门禁影响→分阶段实施→风险>
```

- 任务书正文归 codex 打包（含 attest 自审），Hermes 只写传话书
- codex 容器无 claude 入口（缺 Bedrock key）是正常的——claude 走宿主机 `dispatch_claude_*.sh` 派

## 二、融合报告结构（claude 产出，12 节可复用模板）

1. 术语对照 + 路径校正（门禁术语 G_RENDER=G_RENDER_READY、路径 MISSING 记录）
2. 输入核验（第零步实测）
3. **分析 A：能力矩阵**（N 对象 × M 维度，每格 状态+证据摘要+行号；检出关键缺口）
4. **分析 B：补缺合并映射**（KEEP 保留 / ADD 补入 / BRIDGE 接缝 / CONFLICT 冲突 / DEFER 后置 / DEDUP 去重 六张总表）
5. 闭环链路落地到真实节点（不新占主链编号，用子节点 2.1/14.1/17.1 挂现有节点）
6. 门禁链影响（G_CREATIVE_READY 自动过 vs G_RENDER_READY manual 必人工批——迭代轮次=批准次数）
7. 分阶段实施（P0 只读裁决 → P1 补 reference → P2 流程落位 → P3 门禁硬化，每阶段独立回滚）
8. 风险表（每条 6 项）+ **待用户选择事项**（每项都有双侧来源证据，不是制造的选择题）

## 三、用户裁决流程（关键学习）

**用户口述编号 ≠ 报告 U 编号，歧义项不脑补、交执行器显式映射：**

- 用户说「我先把每个问题的答案告诉你」→ 11 条口述，编号 1-11 与报告 U1-U13 存在偏移（U3 已提前裁决不在本次 11 条内）
- 前 6 条明确对应 U1/U2/U4/U5/U6/U7，最后一条明确对应 U13（「沉淀规则肯定要落闸」= 硬化为 gate）
- 第 7-10 条编号歧义（「7a」「8配音直接sd生成」「9迭代a」「10 a」）→ **传话书写明「待 claude 按报告第 11.2 节原文 + 口述内容语义映射，映射结果必须在报告中显式列出，禁止静默假设」**
- 落盘 `staging/P0_DECISION_LOG_20260824.md`：原话照存 + 映射说明标注（Hermes 标注供执行器解析，不替执行器裁决）

**用户「你先全部整理完」= 13 项待裁决整理成一页选择清单，一次给全，不一项一项问：**
- `staging/P0_DECISION_LIST_20260824.md`：每项 = 编号 + 大白话问题 + 选项 A/B/C + 影响面
- 用户「大白话说出来」= 每项一句话解释 + 推荐项标注（「我标了推荐，但您说了算」）
- 用户回「编号+字母」（如「U3=B U8=B」）→ 严格执行所选，不扩展到相邻改动

**用户关键定案（2026-08-24）：经验反哺技能**
- 「优化的经验是要去反哺这个技能的」——沉淀终点 = 写回 skill 本体（reverse-video-prompt / video-remake），文档库只是中间过渡态
- 三层路径：项目内记录 → 候选规则 eval case → **反哺 skill 正文（第三层，人批准入）**
- 第三层必须过 Skill Change Gate 六问 + 人批，防单条片子经验污染全部项目

## 四、用户裁决全集（2026-08-24，reverse-video-prompt 融合）

| 项 | 裁决 | 含义 |
|---|---|---|
| U1 | 经验反哺技能 | 沉淀终点 = skill 本体，文档库只做中间态 |
| U2 | 按原视频镜数 | 复刻看原视频多少镜，不限定死镜数 |
| U3 | 复刻语速豁免（B） | 复刻类按原片节奏，不受 FAST_VOICE_RE 拦截；改 workflow_gate.py 归 P3 |
| U4 | 重跑人工确认 | 迭代重跑需人工确认，不自动循环 |
| U5 | 融合版为主 | 反推以融合后版本为主（7 要素 + 蒸馏补缺） |
| U6 | 字幕底部 | 主字幕底部居中（有实测） |
| U7 | 首尾帧肯定有用 | 首尾帧插值/接力锁脸判可用（需注意不混用 reference_image） |
| U13 | 沉淀落闸 | 沉淀规则肯定要硬化为 gate，「不然沉淀了干嘛」 |

歧义待映射：7a / 8 配音直接 SD 生成 / 9 迭代 a / 10 a。

## 五、配套流程

- P0 阶段只做裁决记录（零文件改动）；裁决齐 → P1 补 reference → P2 闭环落位 → P3 门禁硬化
- 用户裁决更新后重新派 claude 分析（pack-decision-analysis → CLAUDE_DECISION_ANALYSIS_TASK_BOOK）
- 火龙复刻重做挂在这条融合落地之后（用户「等复刻技能蒸馏好就去重新做火龙」）
