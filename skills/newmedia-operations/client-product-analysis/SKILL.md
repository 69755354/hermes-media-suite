---
name: client-product-analysis
description: Use when 客户给一个产品要用户分析+市场分析+打法。出三层客群+爆款+选题。
---

# 客户产品分析＋策略（小鹿那套接过来版）

用户给一个产品/品类 → 产出**用户分析 + 市场分析 + 平台打法 + 选题方向**。链路、人设、知识库全部沿用客户侧那一套，不另起炉灶。

## 触发
- 「我要推一个产品」/「给XX做用户分析、市场分析」/ 新客户首次需求诊断
- 品类举例：牙膏、汽车、智能家居、本地生活门店

## 三条不做什么
1. **不编数据** — 市场规模/竞品数字/爆款案例必须来自真实搜索并标来源与日期；查不到就写「查不到」，禁推算充数。
2. **不套模板凑字数** — 结构跟着数据走（同 `account-analysis` 输出约束）。
3. **不给编造目标** — 「7天涨粉500」这类不知道阈值的目标不写。

## 链路（串行，禁跳节点）

| 节点 | 干什么 | 人设（wiki/personas/） | 依赖 |
|:--|:--|:--|:--|
| 节点0 信息采集 | 问清产品/价格带/渠道/地域/预算/已有素材；自己推理客户类型，不问客户 | `persona-info-collector.md` | `huoshan/references/node-0-info-collection.md` |
| 节点1 用户分析 | 三层客群＋人性驱动力＋9维共情＋合规排雷，**每条溯源八大理论** | `persona-user-analyst.md` | `wiki/concepts/{consumer-decision-models-knowledge,emotion-psychology,empathy-9-dimensions,behavioral-economics-marketing,china-consumer-sociology}.md` |
| 平台选择 | 按画像选平台（抖音/小红书/快手/视频号/公众号），不听客户指定 | — | `huoshan/references/workflow-overview.md` 平台决策树 |
| 节点1.5 打法分析 | 该产品在该平台怎么打：内容形式/爆款逻辑/合规/账号与投放打法 | `persona-business-analyst.md` / `persona-growth-strategist.md` | `huoshan/references/industry-strategy-methodology.md`、`data-sourcing-strategy.md` |
| 节点2 爆款拆解 | 真搜同赛道近30天高赞≥3条，拆钩子/节奏/情绪曲线/评论区热词 | `persona-content-analyst.md` | `huoshan/references/node-2-trending-analysis.md` |
| 节点3 选题 | **只从爆款共性**推选题方向与理由；禁写镜头/机位参数 | `persona-strategy-editor.md` | `huoshan/references/node-3-topic-selection.md`、`wiki/concepts/50-viral-hook-templates.md` |

人设文件根目录：`/home/ubuntu/workflow/wiki/personas/`（`/home/ubuntu/wiki` 是它的软链）；知识库根目录：`/home/ubuntu/wiki/concepts/`。

## 输出契约（两份，缺一不可）

1. **内部版**（分文件，给下游节点/自己）：`01_信息采集.md` `02_用户分析.md` `03_市场分析.md` `04_平台打法.md` `05_选题方向.md`；每个结论标来源与可信度。
2. **客户版**（白话，禁术语/禁内部路径/禁过程）：产品是谁在用、为什么买、市场在发生什么、竞品在打什么、我们怎么打、第一批内容做什么。

## 交付纪律
- 结论无来源＝删掉；数字必须带来源 URL＋日期。
- 三个人工确认点：画像 / 打法 / 选题，客户确认后才进下一步。
- 先查 `content-redlines`（合规红线＋获客一致性红线）再出客户版。
- 分析不评判客户盈利性，只从运营角度给判断。

## 物理闸（本机实跑踩过）
- 写报告脚本（含"标题/正文/内容"等词）会被 `NEED_SKILL` 误判成头条内容生产而拦下：先 `skill_view(name='toutiao-content-production')` 放行即可，别改脚本绕词。
- KB 闸要求项目目录存在 `guard/kb_checked.json`（`{"checked":true,"read_files":[知识库绝对路径]}`）：先真读 `wiki/concepts/` 下的行业与合规文档，再写标记；不读直接写等于造假。

## 跑法
派 codex 执行（本机 `~/.hermes/scripts/codex_ds.sh exec`）：任务书只给**产品背景 + 上面这些源文件路径**，让它自己读、自己搜、自己产；不替它下结论。完成后抽查：有无编数据、有无无来源结论、选题是否真是从爆款共性推出来的。
