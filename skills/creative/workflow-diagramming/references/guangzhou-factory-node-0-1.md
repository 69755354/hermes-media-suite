# 广州机工作流 Node 0/1 已核对定义（2026-08-19）

来源：workflow/wiki/spec/WORKFLOW_REGISTRY.yaml + WORKFLOW_SPEC.yaml + ssh 广州机 ai-video-factory 代码（orchestrator.py / gates.py / README.md）逐行核对。

## Node 0 · PROJECT_CHARTER（合作立项与资料建档）

- display_order: 0，阶段 S-A（仅此一节点）
- model: none（纯采集，不搜索不分析）；temperature 0.0；persona: persona-info-collector
- requires: []（第一个节点，无前置）
- produces（5 档案，创建项目时一次性生成）：
  - A_PROJECT_CHARTER 项目执行说明（项目名/内容类型/客户类型/线别/素材/服务范围）
  - A_STORE_FACTS 门店事实 rev1（门店行+报价行+行业+内容类型+分支事实）
  - A_ASSET_REGISTER 素材登记（按分支登记，归档到项目 assets）
  - A_RIGHTS_REGISTER 素材权属登记（客户逐项登记，等待内部核验）
  - A_AUTHORIZATION_REGISTER 授权登记（授权对象/用途/平台/有效期，等待内部核验）
- 入口条件：客户提交 BRIEF.json（余额 > 0 才能建项目），上传五类证据素材+授权 MP4
- 创建流程：写 5 档案 + BRIEF.json + workflow_state.json（active_node_id=PROJECT_CHARTER）→ set_node(PROJECT_CHARTER, INTERNAL_REVIEW)
- exit_gate: G_PROJECT_AUTHORIZED（项目授权门）
  - 检查：授权登记齐全（authorization_ids）、问题清单为空、O1 内部授权（README：O1 对项目授权执行「先检查依据」，5 分钟短效 token）
  - 未通过 → 打回 INTERNAL_REVIEW 补料；通过 → S-A 完成进 S-B

## Node 1 · BUSINESS_DIAGNOSIS（门店经营诊断）

- display_order: 1，阶段 S-B
- model: deepseek-v4-flash；temperature 0.1；reasoning low；persona: persona-user-analyst
- requires: [A_PROJECT_CHARTER, A_STORE_FACTS, A_AUTHORIZATION_REGISTER]
- input_deps (SPEC): [A_PROJECT_CHARTER, A_STORE_FACTS]
- note: 产品/价格/毛利/产能/营业时段/商圈/现有渠道/历史数据；无数据标「未测量」禁编造
- produces（produce_node 实际实现）：
  - A_BUSINESS_DIAGNOSIS 门店体检（门店名+已登记卖点；「历史咨询、到店和成交数据尚未提供时，不判断转化效率」）
  - A_BASELINE_LEDGER 基线台账
  - A_CAPACITY_PROFILE 容量画像
  - A_DATA_GAPS 数据缺口（需持续登记咨询/到店提及/成交，播放量不替代获客结果）
- exit_gate: G_BUSINESS_BASELINE_READY（经营基线就绪）→ 通过进 Node 2 MARKET_INSIGHT

## 通用流转状态

QUEUED → RUNNING → PRODUCED/INTERNAL_REVIEW →（exit_gate 通过）→ SIGNED_OFF → 下一节点。
advance() 主循环按 FREE_SEQUENCE 顺序推进；阶段分组 STAGE_NODE_IDS：
S-A=[PROJECT_CHARTER]；S-B=[BUSINESS_DIAGNOSIS, MARKET_INSIGHT, OFFER_PATH, GROWTH_STRATEGY, OPERATING_INFRA, CONTENT_CALENDAR]；S-C=[TOPIC_EXPERIMENT, COPY_PACKAGE, CREATIVE_BLUEPRINT]；S-D=[MEDIA_PREP, MEDIA_PRODUCTION]；S-E=[DELIVERY_PACKAGE]；S-F=[PUBLISH_OPERATE...MONTHLY_CLOSE]

## 关键代码位置（广州机 ai-video-factory）

- create_project / 5 档案生成：orchestrator.py 约 155-190 行
- produce_node 各节点 special 产出：orchestrator.py 438 行起
- 状态推进主循环：orchestrator.py advance() 793 行起
- 门禁 manifest 与 G_PROJECT_AUTHORIZED 检查：gates.py build_gate_manifest / _project_authorization_context
- 端到端业务路径：README.md「火锅店演示路径」12 步

## 整条业务链速查（第一版全流程图的内容）

客户侧（8090/access）：输入编号→余额>0→上传素材→C1确认→C2确认→下载ZIP
工厂（8090）：O1授权(5min token)→导入洞察≥3条→codex 生成打法+三版文案→冻结事实+红线四硬门→8列分镜(MEDIA_PREP 停在付费审批边界)→合成(MEDIA_PRODUCTION)→交付门 G_DELIVERY_READY→预生成ZIP→O9巡检+审计哈希链
账务（billing 8080，SQLite WAL 单库）：预占积分→任务执行→settle 扣 750（成片成功才扣，失败不扣）→ledger 流水（不可改只能冲正）→交付门禁校验（无凭证不交付）→对账
