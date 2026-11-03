# OpenMontage 架构对比分析（2026-08-27）

> 来源：广州机 `/tmp/OpenMontage/` 完整 clone（2026-08-23）。GitHub trending #1。AGPLv3 开源。

## 一句话结论

OpenMontage 是纯视频生产链（idea→publish 7-8 阶段），我们比它强在全链路覆盖（19 节点到月结）、行业合规、执行器隔离；它比我们强在产物 Schema 校验、断点续跑、成本追踪、交付承诺分类器、幻灯片风险评分、Backlot 可视化看板。筛出 4 项值得搬，其余不搬。

## 架构对比

| 维度 | 我们 | OpenMontage |
|---|---|---|
| 范围 | 19节点全链路（立项→月结，含到店/成交/复购） | 7-8阶段纯视频生产（idea→publish） |
| 事实源 | WORKFLOW_REGISTRY.yaml + WORKFLOW_SPEC.yaml | pipeline_defs/*.yaml + tool_registry.py |
| 路由 | CREATIVE_ROUTE_TABLE 按内容类型(口播/探店/剧情) | pipeline manifest + selector tool 自动发现 |
| 执行器 | Hermes→GLM壳→物理门禁拦截 | AI coding agent(Claude Code/Cursor)直接当导演 |
| 产物校验 | .md 文件，人肉守格式 | JSON Schema，checkpoint 写入时自动 validate |
| 断点续跑 | 无（中断重跑） | checkpoint_<stage>.json，自动找断点恢复 |
| 成本追踪 | 成本模型(600积分/条)但无运行时追踪 | estimate→reserve→reconcile 三步，超阈值拦截 |
| 合规 | 8类行业红线 + 送客词禁令 + 知识库物理卡点 | 一句"宁可保守也不越线"，无行业分级 |
| 质量门 | content-review-gate 四维评审 + director-thinking 四层提示词 | reviewer meta skill，通用但不够深 |

## OpenMontage 设计模式速查

### 1. JSON Schema 产物校验
- `schemas/artifacts/` 下 20 个 schema（scene_plan/script/asset_manifest/edit_decisions/decision_log 等）
- checkpoint 写入时 `validate_artifact()` 自动校验，格式不对报 `CheckpointValidationError`
- scene_plan schema 含：id/type/description/start_seconds/end_seconds/shot_language(shot_size/camera_movement/lens_mm/lighting_key)/shot_intent/narrative_role/hero_moment

### 2. Checkpoint/Resume 断点续跑
- `lib/checkpoint.py`，每阶段完成后写 `checkpoint_<stage>.json`
- 含 status(completed/awaiting_human/in_progress) + artifacts + cost_snapshot
- 阶段前置依赖强制：`_enforce_stage_prerequisites()` 检查前驱阶段是否 completed
- 旧 checkpoint 归档到 `history/` 目录
- 重启时 `get_next_stage()` 自动找断点

### 3. 成本追踪器（cost_tracker.py）
- estimate → reserve → reconcile 三步
- 超阈值触发 `ApprovalRequiredError`（跟我们"说跑才跑"纪律吻合）
- 三种模式：observe(只记录) / warn(警告继续) / cap(硬停)
- 配置：total_usd / reserve_pct(10%) / single_action_approval_usd($0.50) / require_approval_for_new_paid_tool

### 4. 交付承诺分类器（delivery_promise.py）
- 8 类：motion_led(≥70%真运动镜头) / source_led / data_explainer / teacher_explainer / screen_demo / avatar_presenter / hybrid / localization
- proposal 阶段锁定，compose 前校验是否降级
- motion_led 的 still_fallback_allowed=False——静默降级被拦截
- **直接适用我们的复刻任务**：原片是"口播+剧情+App交替"但做成了纯口播拼接 = 静默降级

### 5. 幻灯片风险评分器（slideshow_risk.py）
- 6 维度 0-5 分：repetition / decorative_visuals / weak_motion / weak_shot_intent / typography_overreliance / unsupported_cinematic_claims
- 平均 ≥4.0 判 fail，不应进入 compose
- variation_checker.py：检测连续相同景别/静态镜头过用/通用废话词汇("modern"/"stunning"等)
- **场景限制**：针对"静图拼接冒充视频"问题，我们做口播/探店/复刻不是动画 explainer，场景不适配

### 6. 决策日志（decision_log）
- options_considered(≥2备选) + reason + confidence(0-1) + user_visible
- 追加写入不改旧记录，改了就追加新条目，旧的标 superseded
- confidence 全是 1.0 会被标记为不真实

### 7. Backlot 可视化看板
- 读项目目录自动派生：阶段进度/素材状态/成本/决策/审批门/事件流
- watchfiles 监听 + SSE 推送，无需 agent 额外操作
- 事件源：`events.jsonl`（BaseTool instrumentation 写的 start/finish/error）

### 8. 三层知识架构
- Layer 1: tool_registry.py（工具有什么能力/成本/状态）
- Layer 2: skills/（项目惯例：什么时候用什么工具）
- Layer 3: .agents/skills/（通用API规则：参数/约束/代码模式）
- 每个工具的 `agent_skills[]` 字段桥接 Layer 1 → Layer 3
- **我们缺 Layer 1**：没有统一声明工具能力/成本/状态的地方

### 9. 管道 manifest（pipeline_defs/*.yaml）
- 每条管道声明 stages/required_tools/required_skills/review_focus/success_criteria/human_approval_default
- 13 条管道：animated-explainer/cinematic/talking-head/screen-demo/avatar-spokesperson/clip-factory/podcast-repurpose/hybrid/animation/character-animation/localization-dub/framework-smoke
- orchestration mode: executive-producer（8阶段串行编排+质量门+跨阶段检查+send-back）

### 10. ToolContract（base_tool.py）
- 每个工具声明：capability/provider/tier/stability/runtime/cost/agent_skills/fallback_tools
- selector+provider 模式：tts_selector 自动发现所有 capability=tts 的工具
- ToolResult：success/data/artifacts/error/cost_usd/duration_seconds/seed/model

## 筛选结论

### 值得搬（4项，按优先级）

| 优先级 | 东西 | 解决什么痛点 | 改动量 |
|---|---|---|---|
| P0 | 交付承诺分类器(delivery_promise) | 复刻任务静默降级——原片是交替结构但做成纯口播拼接 | 搬概念+校验逻辑，加到 CREATIVE_BLUEPRINT 或 MEDIA_PRODUCTION 门禁 |
| P0 | 产物 JSON Schema | 分镜/提示词/文案格式偶尔出错只能人眼发现 | 写 4-5 个 schema 文件，gate 里加校验 |
| P1 | 视频分析工具链 | 复刻前看原片结构纯手动 | 搬 scene_detect+frame_sampler+transcriber，组装成分析流程 |
| P2 | Remotion 合成+组件库 | 合成全靠 ffmpeg 手搓，动态字幕/图表/产品展示做不了 | 需 Node.js 18+，装后用 17 个 React 组件 |

### 不搬（理由）

| 东西 | 理由 |
|---|---|
| 幻灯片风险评分器 | 场景不适配——我们做口播/探店/复刻不是动画 explainer |
| 决策日志 | 审计有用但不提升效率，方案选型靠 memory 和会话历史够用 |
| 工具注册表 | 我们工具就 5-6 个(Seedance/DashScope/婵镜/Seedream/wan3.0)，手能数过来 |
| selector 模式 | 工具太少没有选择困难 |
| Backlot 看板 | 投入产出比低，靠对话看进度够用 |
| pipeline manifest 替代 REGISTRY | 我们的 19 节点比它 7 阶段宽太多，替换会丢链路 |
| 审批门三档分级 | 我们就是"说跑才跑"一档 |
| 预算配置/事件流 | 不做看板就不需要 |

## 实施参考

- 交付承诺分类器源码：`/tmp/OpenMontage/lib/delivery_promise.py`
- JSON Schema 示例：`/tmp/OpenMontage/schemas/artifacts/scene_plan.schema.json`
- 视频分析工具：`/tmp/OpenMontage/tools/analysis/`（video_analyzer/scene_detect/frame_sampler/transcriber）
- Remotion 组件：`/tmp/OpenMontage/remotion-composer/src/components/`（TextCard/StatCard/CaptionOverlay/ComparisonCard 等 17 个）
- 成本追踪器：`/tmp/OpenMontage/tools/cost_tracker.py`
- 断点续跑：`/tmp/OpenMontage/lib/checkpoint.py`
