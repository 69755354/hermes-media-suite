---
name: toutiao-content-production
description: 今日头条图文内容生产合规与成本。触发：头条发文/AI内容标注/头条限流/头条首发/图文项目。
version: 1.0.0
author: hermes-curator
license: internal
metadata:
  hermes:
    tags: [toutiao, 头条, content, ai-labeling, compliance, cost]
---


# 今日头条内容生产：任务路由

## 触发
写头条文章、图文/首发项目、选题与标题、爆款拆解、审核/AI标注、账号诊断、配图、生产成本与产线维护时使用。按下列任务读取对应参考，勿默认加载全部历史。

## 核心规则与原文优先级
- 禁编造数据、事件、政策；区分官方原文、客户方法论、行业经验和外部分析。政策事实须核对官方原文。
- 写稿必须深度改写、共情、大白话；2026-09-07已明确废弃周式风格。每篇按9月8日五层写法及7项约束执行。
- 标题先搜真实爆款并验证目标格式热度，≤30字；9月8日由codex选最佳，覆盖9月7日“让用户选”。选题看近2天、社保范文近5天，避免连续同领域。
- 默认codex写稿，任务书明确真实来源、范围与字数；不能绕过产线质检。交付前读verdict.json，FAIL修复重验；rc=3须人工审核。人工门不得代批。
- 质检包括AI味、格式、编造、行业红线与逐图视觉检查；检测分数不代替全文审阅。编号/加粗冲突按原文9月7日豁免规则显式记录，不静默跳过。
- 交付正文纯文本，长文用.txt附件；产出文件AI标注与平台发布声明按合规参考区分，发布操作由人工处理。
- 各参考原文逐字保留，含旧规则和修复记录。原文已明确废弃/覆盖的条款不因拆分恢复；日期不能脱离赛道、任务与显式定案范围使用。未裁决冲突不得自行改业务或放宽门禁。
- “头条+中年职场停止”原文与旧职场方案均保留，先核对用户当前范围，不因读取历史方案恢复停掉的方向。字数按适用定案核对配置，不把历史数值当通用默认。

## 按任务读参考（路径均相对本skill根目录）
- 写稿必读：[文风](references/writing-style-ruling.md)、[五层写法](references/writing-five-layer-method.md)、[写作与交付](references/writing-workflow-and-delivery.md)、[门禁与审阅](references/quality-gates-and-editorial-review.md)、[交付判定](references/delivery-verdict-and-quality.md)。
- 合规/发布必读：[审核、红线与AI标注](references/compliance-and-ai-labeling.md)、[事实核验与故障处置](references/fact-check-and-pipeline-troubleshooting.md)；成本/首发另读[first-publish-and-cost-history](references/first-publish-and-cost-history.md)。
- 选题/标题/拆文：[近期选题与指标抓取](references/topic-title-and-article-research.md)、[来源与写作派发](references/topic-sourcing-and-writer-dispatch.md)、[来源归属](references/source-attribution-and-reporting.md)。
- 账号诊断/赛道：[账号与赛道沿革](references/account-diagnosis-and-track-history.md)、[选题校准](references/topic-selection-calibration-history.md)、[选题池与规划沿革](references/topic-pool-and-planning-history.md)、[旧热点职场方案](references/hot-topic-career-strategy-history.md)。
- 配图：[尺寸与生产标准](references/illustration-production-standards.md)、[AI图中转与视觉检查](references/ai-illustration-relay-and-vision.md)。
- 产线维护/历史复盘：[架构](references/pipeline-architecture-history.md)、[里程碑验收](references/milestone-and-acceptance-history.md)、[搜索与回炉补丁](references/search-and-rewrite-patches.md)、[校准与修复](references/quality-calibration-and-repair-history.md)、[检测盲区与漂移](references/detector-and-config-drift.md)、[模型实测](references/model-comparison-history.md)。
- 更多既有专题与原文来源：[原参考索引](references/existing-reference-index.md)、[原元数据与触发](references/original-metadata-and-triggers.md)。参考中旧的 references/、scripts/、_staging/ 路径仍以本skill根目录为基准；“上/下节”通过本路由对应专题定位。
