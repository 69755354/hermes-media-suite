# 工作流 v5.0 语义ID化（2026-08-10 重构）

## 背景

用户三次纠正后重构：打法必须前置（客户分析后、内容创作前）；工作流按客户交付物倒推（以终为始）；方案要有依据分级。codex 深度审计后产出重构方案（工作流按交付物重构方案.md）。

## 核心变更

1. **单一事实源**：`wiki/spec/WORKFLOW_REGISTRY.yaml`（19节点/95产物/19门禁）
2. **统一门禁**：`scripts/workflow_gate.py check <项目> <gate_id>`（旧 review_gate/confirm_gate/data_source_gate 降为底层适配器）
3. **语义ID替代数字编号**：节点用 PROJECT_CHARTER→MONTHLY_CLOSE；数字只做 display_order 排序
4. **三组交付物主链**：
   - 开局经营底座：PROJECT_CHARTER→BUSINESS_DIAGNOSIS→MARKET_INSIGHT→OFFER_PATH→GROWTH_STRATEGY→OPERATING_INFRA
   - 每周期内容包：CONTENT_CALENDAR→TOPIC_EXPERIMENT→COPY_PACKAGE→CREATIVE_BLUEPRINT→MEDIA_PREP→MEDIA_PRODUCTION→DELIVERY_PACKAGE
   - 持续运营结果包：PUBLISH_OPERATE→LEAD_OPERATION→CONVERSION_OPERATION→RETENTION_OPERATION→WEEKLY_REVIEW→MONTHLY_CLOSE
5. **内容分支按格式选路**（禁数字跳过表）：VIDEO_SHORT/IMAGE_POST/WECHAT_CONTENT/LONG_FORM
6. **精确回退矩阵**：按错误类型定向回退（scope_change→PROJECT_CHARTER，offer_change→OFFER_PATH，tech_issue→MEDIA_PRODUCTION 等 12 项）

## 使用要点

- 新项目：走语义ID + workflow_gate.py
- 存量项目（重构前）：旧门禁兼容（review_gate node4_review 等仍可用）
- 数字编号引用必须带工作流前缀（防三套编号混用）
- 打 codex 跑节点时：AGENTS.md 已更新 v5.0 说明，codex 会自己按语义ID校验

## 三轮检查教训（重构后必做）

1. **架构一致性**：REGISTRY vs SPEC 节点数一致；exit_gate/requires/produces 引用完整（produces 引用 71 个内部产物未注册→补全到 95）；无旧编号残留
2. **系统兼容**：文件存在/语法/门禁实测/存量兼容/双副本一致
3. **逻辑合理性**：依赖无环（抓到一个真环：WEEKLY_REVIEW 依赖 MONTHLY_CLOSE 产物→改 A_COST_LEDGER）；成本确认点/合规底线保留

验证命令：
```bash
python3 -c "import yaml; r=yaml.safe_load(open('wiki/spec/WORKFLOW_REGISTRY.yaml')); ..."  # 引用完整性
python3 scripts/workflow_gate.py check <项目> <gate_id>   # 统一门禁实测
```
