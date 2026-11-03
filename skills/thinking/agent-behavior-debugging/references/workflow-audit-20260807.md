# 全工作流审计断点清单（2026-08-07 红果漫剧项目后三轮审计）

> 触发：审计 huoshan 18节点工作流（或任何多文件工作流）时，对照本清单逐项排查。
> 本文件是 2026-08-07 三轮审计挖出的 10 个问题实录——**同一类问题会随工作流演进复发**，
> 每项都带「为什么是问题」和「怎么查」。

## 审计背景

- 目的：用户要求「看看整个工作流还有什么有问题的地方」，前两轮只做表层检查（文件存在/md5 一致）
  被用户纠正「每次说没问题，又出来一堆」；第三轮做内容级五方对照才挖出以下问题。
- 五方 = SPEC（权威定义）/ huoshan（执行手册）/ guard（调度器）/ gate 脚本（物理卡点硬编码）/ 记忆+SOUL（行为规则）

## P0 级（会实际卡死/跑错）

### 1. 文件接力目录树不完整
- **问题：** guard 的目录树只列到 `节点11_质检报告.md`，节点12-17（视频/合成/终检/交付/发布/复盘）文件名缺失
- **后果：** 接力铁律说「下一节点开工前必须先读上游文件，没读到卡死」——跑到节点12+ 时模型不知道接力文件叫什么名，要么乱起名要么跳过接力
- **查法：** grep guard 里 `├── 节点\d+_` 树，数到节点几截止

### 2. 两域分工三处矛盾
- **问题：** huoshan 内同时存在「Bot域0-5｜API域10-13」「Bot域0-5｜API域8-11」「Bot域0-5→API域8-11」三版，节点6/7/9 归属不明
- **后果：** 小鹿不知道生图/素材汇总该自己干还是丢 Execute API
- **查法：** grep `Bot域.*节点|API域.*节点` 全部表述，必须收敛到唯一版本

### 3. 口播分支节点路径逻辑断裂
- **问题：** L3504 说口播「跳过节点6/7/8/9/10，从节点5直接进节点11」——但节点11 是提示词质检不是婵镜出片；另一处写「口播跳过6-9,12-13」——两处互相矛盾。婵镜出片在整个 0-17 链路里没有对应节点，被硬塞进节点11
- **后果：** 口播走到节点11 时不知道该质检什么，出片环节无归属
- **查法：** 对每个分支（口播/小红书/剧情）逐段验证跳转落点节点职能是否匹配

### 4. guard 引用已废弃文档
- **问题：** guard L127-129 还在让模型读 `user-16node-workflow-analysis.md`（标注「已废弃，双通道17节点旧版」）——违反 guard 自己写的 References 过时铁律
- **后果：** 模型加载旧版编号体系，跟 18 节点现行规则打架
- **查法：** 提取 guard 所有 `references/*.md` 引用 → 逐个查文件头部有没有「已废弃」标注

## P1 级（内部打架）

### 5. 踩坑记录 vs 现行规则冲突
- **问题：** guard L132 新规则「不再问实体店还是自媒体」vs L568 踩坑记录「必须先问实体店还是自媒体再选工作流」——同文件新旧规则打架
- **查法：** 对每个「不再XX/改为XX」的新规则，grep 同关键词找旧表述；踩坑记录是历史，现行规则是权威

### 6. 节点并行/串行矛盾
- **问题：** 节点6 说「与节点5并行互不依赖」vs 节点8 说「两个节点是串行的——先出人设再生图」
- **查法：** grep `并行|串行|互不依赖` 全部表述

### 7. 防编造闸扫不到新格式文案
- **问题：** review_gate check_data_integrity 的 body_candidates 只扫 `节点4_正文定稿.md`/`节点4_图文文案.md` 旧文件名，流程产出 `节点4_文案定稿.md` → 检查永远扫不到实际文案（不报错但形同虚设）
- **查法：** grep gate 脚本硬编码 `节点N_XX.md`，与 SPEC【输出】对表

### 8. 节点16 发布方案矛盾
- **问题：** SPEC 说验证期不搞自动发布（封号风险+成本，客户手动发，产出发布指引+发布策略）vs huoshan 还写「调用各平台 API 自动发布」
- **查法：** 对每个「不XX」的新决策，grep 执行手册里旧做法的残留

### 9. 口播发音铁律没落地
- **问题：** 记忆里有硬教训「段长15s+语速略快=发音糊，改≤10s/段+语速适中吐字清晰」，但 huoshan 只写了「8s/10s 上限」，没写「语速适中/禁语速快」
- **查法：** 记忆里每一条「已改XX」的教训，grep skill 是否真的落地了

### 10. 三套节点编号体系共存
- **问题：** huoshan 18节点(0-17) vs shuziren 模式B 17节点(0-16) vs 模式A 4节点——「节点13」在 huoshan 是 ffmpeg，在 shuziren 是交付
- **查法：** 列出每个 skill 的节点体系，检查跨 skill 同编号是否同职能

## 审计执行模板（内容级五方对照）

```python
# ① 文件名差集
import re
def extract(text): return set(re.findall(r'节点\d+_[^\s`"\')）|,，。；;：:]+\.md', text))
spec_files = extract(open('SPEC').read())
huoshan_files = extract(open('huoshan').read())
print('huoshan有SPEC无:', huoshan_files - spec_files)
print('SPEC有huoshan无:', spec_files - huoshan_files)

# ② 逐节点 input_deps → post_checks 对照
# ③ 边界关键词全量 grep
# ④ 分支路径逐段验证
# ⑤ guard 目录树完整性（数到节点几）
# ⑥ gate 脚本硬编码文件名 vs 产出
# ⑦ 废弃文档引用检查
```

## 验证正常的项（防止下次重复审计浪费时间）

- gate 脚本全在（review_gate/confirm_gate/data_source_gate/semantic_review/onboarding_gate/permission_gate/info_gate/image_compliance_check/node4_review_scorer/update_state/security-middleware/project_init/render_lock）
- 关键路径全在（SPEC yaml/audit_v1.21.json/industry-index.md/platform-content-specs-v3/content-scoring-operation-manual/account-staged-operations-library/platform-local-traffic-templates/permissions.json）
- 7步链路 SOUL/huoshan 一致（平台选择在用户画像后、爆款拆解前）
- 三通道入口一致（探店/剧情/口播）
- node4 三版卡点有效（review_gate node4_review 实测 BLOCKED/ALLOWED）
- node15 终审门有效（终审 PASS ≥68 放行）
- 成本覆盖正常（Seedream 0.22元/张 每项目≤10张；Seedance ≈13-15元/条 ¥50 封顶；配额按客户级别）
- customer 记忆文件无旧规则残留
