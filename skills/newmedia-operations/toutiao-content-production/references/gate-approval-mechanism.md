# G_COPY_READY 审批机制拆解（2026-08-19 现场读代码核实）

用户问「审批机制主要是审什么」时现场核实的结论。头条图文对应语义节点 `COPY_PACKAGE` → 内容分支 `LONG_FORM`，出口门 `G_COPY_READY`。

## G_COPY_READY 关联三道底层检查（workflow_gate.py GATES 映射）

1. **review_gate.py node4_review（初稿评审门）**
   - 三版产出检查：项目目录必须有 `节点4_文案v1/v2/v3.md`（客户自备文案场景用 `_自备文案.flag` 豁免）
   - 评审报告检查：`节点4_评审报告.md` 存在且分数 ≥60（read_score 读 PASS/分数）
2. **review_gate.py node5_review（进节点5预读）**
   - 复用 node4 检查 + `codex_preload_manifest.check_node_preload(proj, "5")` 强制预读 huoshan 分镜方法论（主要针对视频链路）
3. **data_source_gate.py node4_body（正文编造统计+合规）**
   - 「研究表明/数据显示」+数字 必须带来源痕迹（BODY_FAKE_PAT + BODY_ALLOWED），无来源 = 编造统计 = BLOCKED
   - 极限词检测（广告法第九条 LIMIT_WORDS）
   - 高危特征词 WARN_WORDS：只告警不阻断
   - 玄学牟利组合：玄学词+牟利信号（无否定语境）→ BLOCKED；含否定词（辟谣）→ 放行
   - 封建迷信高危词组 METAPHYSICS_HIGH：直接熔断
   - 普通玄学名词：打 risk_metaphysics 标签强制评审
   - 送客词 SEND_AWAY_WORDS：默认 BLOCKED，客户明确要求 → `_豁免送客词.flag`
   - 知识库引用物理卡点（node4_kb 并入 node4_body）：必须存在 `_知识库引用.md`

## 人工 approve 通道（workflow_gate.py L689）

```
workflow_gate.py approve <项目目录> <gate_id> --by <审批人> --evidence <路径>
```
- `--by` 非空、`--evidence` 必须是存在的非空文件，否则 BLOCKED
- 审批锁定 produces 中每个产物的 **sha256**（禁止写入空哈希）——审批后任何人改文件，哈希对不上即失效（防篡改章）
- 记录 approval_by + approved_at；`approved_record_is_current` 只识别 approve 命令写入的记录
- AGENTS.md 铁律 7：人工门和不可逆操作只能由人批准，执行器和 Hermes 都不得代批

## 头条全自动产线的解法（天行者 2026-08-19 定案）

- **章 = AI 自审**：工具链定位成独立工具（方案甲），产出落 `projects/toutiao-shoufa-tools/runs/`，**不进 19 节点主链、不调 workflow_gate**，从而不触发铁律 7 的人工门。AI 自检闭环（评分器+数据源+合规全过）即章。
- 若未来要进主链交付（方案乙），只需在最后加「把文章复制到项目 artifacts 并等人 approve」一个动作，架构不用改。
