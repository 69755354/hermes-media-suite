---
name: physical-gate-debugging
description: bot行为偏差排查：不引用知识库/产出物类型错。先查物理卡点（guard加载+节点模板），禁往SOUL.md塞方法论。
---

# 物理卡点排查（Physical Gate Debugging）

## 何时用

- bot（小鹿/customer 或其他 agent）行为偏离预期：不引用知识库、产出物类型不对、不会写某类内容、跳过流程
- 用户说「它怎么不xxx」「它总是xxx」「让它做xxx它却yyy」

## 铁律（用户纠正 2026-08-06）

**物理约束 > 软规则。** 解决 bot 行为问题优先改物理卡点（guard 加载列表/节点模板/文件模板），**禁止往 SOUL.md 塞方法论**——SOUL.md 只放身份/铁律/极简行为规则，详细方法论在 skill/知识库/节点模板。

用户原话：「你什么都往soul里加？」——SOUL.md 是垃圾场思维的反面教材。

## 排查顺序（四步）

```
行为偏差
  ↓
① 查 guard 强制加载列表
   - workflow-execution-guard 的「内容生产强制加载」有没有包含工作流主 skill（如 huoshan）？
   - 缺主 skill = 分支方法论对模型不可见 → 裸奔
   - 案例：三件套（data-discipline/review-gate/thinking-config）缺 huoshan → 小鹿写剧情文案裸奔
  ↓
② 查节点模板设计
   - **模板第一列定义产出物类型！**
   - 节点4 模板第一列是「镜号」→ 模型照抄 → 产出分镜表而非文案（用户要文案却给分镜脚本）
   - 模板带什么字段，模型就产出什么结构——模板设计缺陷 ≠ 模型理解错
  ↓
③ 查 SOUL.md 速查表覆盖
   - 速查表只覆盖少数行业/内容类型时，模型对未覆盖类型「无库可引」
   - 修复：补知识库兜底规则（去读哪个文件），不是把内容搬进 SOUL.md
   - ⚠️ 2026-08-07 三合一根因（兜底已加仍漏）：①兜底是软规则无物理卡点 ②无「行业→文件名」映射
     （wiki/concepts 101 份文档命名多样，模型猜不到读哪个）③customer-facing-bot SKILL.md L437
     残留过时结论「bot has no read_file capability」——被加载=告诉模型读不了知识库
   - 修法=行业→文件映射表（物理路由）+ 卡点校验产出物确实读了知识库 + grep 清过时能力结论，不是继续塞提示词
  ↓
④ 查记忆文件残留旧规则（2026-08-07 新增，本会话实锤）
   - **customer profile 的 memories/USER.md、MEMORY.md 注入 system_prompt，优先级很高**
   - 残留旧规则会跟新技能/新 SPEC 直接打架，bot 遵守记忆 = 表面「违规」
   - 案例：USER.md 里「出片前必须输出分镜脚本(storyboard)审核」→ 小鹿节点4 出分镜表格，
     但 huoshan 新规则是「节点4 只出台词本、分镜归节点5」——文件矛盾，bot 遵守了更旧的记忆
   - 排查：grep memories/ 目录里跟工作流相关的旧表述，对照当前技能/SPEC 找矛盾
   - ⚠️ 读记忆文件坑：customer memories/USER.md 会被 read_file 误判为 binary（实际 UTF-8 文本、§ 分隔），
     用 `python3 -c "print(open('.../USER.md','rb').read().decode('utf-8'))"` 读
   - 修复：改记忆条目为新规则（保留原意图的安全阀）+ 清 system_prompts 缓存 + 删会话路由 + 重启 gateway
   - ⚠️ 这不是 bot 违纪，是「规则打架」——先分清 bot 是乱来还是在遵守另一条更老的规则
  ↓
⑤ 查物理卡点脚本检查的文件名 vs 流程实际产出文件名（2026-08-07 新增，本会话实锤）
   - review_gate.py / data_source_gate.py 等 gate 脚本硬编码检查的文件名 ≠ 流程实际产出文件名
     → 卡点形同虚设（查不到新产出物）或误杀（交付总闸拦正常项目）
   - 案例：改完节点4 产出=节点4_文案定稿.md（纯文本台词本）后，review_gate check_data_integrity 的
     body_candidates 还是旧名 节点4_正文定稿.md / 节点4_图文文案.md → 防编造闸永远扫不到实际文案
   - 排查：grep 脚本里硬编码的节点文件名，跟 SPEC/huoshan 当前【输出】定义逐一对表
   - 修复：脚本 body_candidates 加新文件名；改完跑 4 场景测试（缺文件/正常/不足/过短）验证
   - ⚠️ 每次改产出物文件名后，必须同步 grep 全部 gate 脚本（review_gate/data_source_gate/confirm_gate/semantic_review）——这是高频遗漏点
  ↓
⑥ 查废弃/过时文档残留（2026-08-07 新增）
   - skill references/ 里标注「已废弃/过时」的旧版文档，若仍被 guard/其他 skill 引用 = 模型加载旧规则
   - 案例：guard 引用 user-16node-workflow-analysis.md（双通道17节点旧版）→ 编号体系跟 18 节点打架；
     shuziren 引用 dual-branch-architecture.md（已废弃）当架构图
   - 排查：提取所有 `references/*.md` 引用 → 逐个查文件头部「已废弃」标注 → 分类执行引用（file_path=/skill_view(）
     vs 历史记录引用（翻车案例/审计记录）
   - 修复（先改引用再删本体）：①改危险执行引用 ②备份到 /tmp ③删文件 ④更新防再犯文档标注已删除
     ⑤主客同步 md5 + 清缓存 + 重启（详见 references/physical-gate-debugging-cases.md 案例5）
```

## 修复模式（物理层，按优先级）

1. **guard 强制加载列表**补主 skill（三件套→四件套→五件套）
2. **节点模板**改产出物边界（2026-08-07 最终形态：节点4=纯台词本【只有台词，禁说话人/语气/情绪/表格/镜号】；节点5=10列分镜表格【镜号/时间/景别/运镜/画面内容/台词/说话人/语气/情绪/音效/备注】——说话人/语气/情绪归节点5，不归节点4）
3. **知识库索引制**（2026-08-07 落地，替代「一行兜底规则」）：
   - 建 `wiki/concepts/industry-index.md`：行业关键词→文件路径映射表（覆盖抖音/小红书/快手/公众号/视频号全平台）
   - SOUL 兜底改为「先 read_file 索引查表 → 按表读对应文档」，禁止猜文件名
   - guard 五件套加第五步「read_file 索引」
   - 同时 grep 清过时能力结论（如 customer-facing-bot「no read_file」）——过时结论会反向告诉模型读不了库
4. **gate 脚本文件名对齐**：改产出物文件名后，grep 全部 gate 脚本（review_gate/data_source_gate 等）同步硬编码文件名

## 验证

改完重启对应 gateway 生效。行为复测：让 bot 实际跑一次目标任务，看产出物类型对不对。

## 相关案例

- references/physical-gate-debugging-cases.md — 小鹿案例：不引用知识库/写文案给分镜的完整排查记录
- references/memory-stale-rule-case-20260807.md — 小鹿案例：记忆文件（USER.md）残留旧规则 → 节点4 出分镜表格；含补跑评审脚本 node4_review_scorer.py 用法
- references/format-standard-audit-20260807.md — 本会话：文案/剧本/分镜行业标准（纯文本台词本 vs 8列分镜表格）+ 全工作流审计 P0 断点（gate 脚本查旧文件名/节点16 发布矛盾/口播段长铁律未落地）
