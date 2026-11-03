# 闸活性可观测性实施报告（2026-08-26）

> 来源：claude 诊断方案 `/tmp/claude_gate_analysis.md` + codex 实施 P0-1/P0-4/P0-5

## 诊断结论（人话）

1. **三闸联防从来没有"联防"过，是一条串联单链。** 闸二（票据）、闸三（哈希）的拦截力全挂在闸一（hook）上。闸一文件没了，闸二退化成"自愿执行的命令行工具"，闸三退化成"往没人看的日志里追加告警"。证据：`guard/tickets/` 自 8-15 建立至今为空，全机没有任何 `ticket_ledger.jsonl`——闸二从上线到现在开过 0 张票。

2. **真正致命的不是"闸掉了"，是"闸掉了 11 天没人知道"。** 系统里没有任何东西检查"闸还活着吗"。哈希闸本该尖叫，结果有人把尖叫的两行从清单里删了——广州版 `FILES` 数组已摘掉 `node-entry-guard.py` 和 `feishu_send_gate.py`。这不是修故障，是关警报。

3. **设计文档自己预测到了这个死法，然后在缓解措施上留了刚好等于致命文件的豁口。** R10 风险条写"新增文件全部落 Git 内；`.hermes/` 侧只放 `node-entry-guard.py`"——全套七八个文件都进了 Git，唯一例外就是最核心的闸，无备份、不可回滚。

4. **角色分工目前是 0 机器约束的纯文档规则。** 08-23 G01-G14 审计已独立确认（G11/G12「纯软规则无卡点」）。

5. **修复第一优先级不是重建闸，是先装"闸的活性探针"。** 否则重建完下一次静默失效仍然是 11 天后才发现。探针 30 行代码，比闸本身便宜两个数量级。

## 根因分析

### R1 闸的存活依赖于一份可被编辑的清单，而编辑清单不需要任何人批准
哈希闸的检测范围写在自己的 `FILES` bash 数组里。文件没了→天天报 `FILE_MISSING`→把那两行删掉，报警消失，故障留下。自指闭环：闸三监控闸一，但没人监控闸三的清单。

### R2 三闸是串联，不是联防
改造方案 4.4 的十行"攻破方式→被谁拦"表里，六行答案是闸一。闸二的不可绕性由闸一提供。闸一一死：闸二没人强制开票→11 天 0 票；闸三只会写日志不会阻断。

### R3 没有活性探针，静默失效不可观测
"闸在跑"和"闸不在跑"对外表现完全一样：都没有 BLOCK 输出，都不报错，工具调用都成功。闸的正常工作方式就是沉默，因此沉默不能作为健康信号。

### R4-R7 放大器
- R4: hook 挂载是一次性手工配置，无幂等/无自检/无版本控制
- R5: 影子模式没有毕业判据，"临时"变成永久
- R6: 验收标准是"报告说通过"，不是"探针现在还通过"（一次性快照）
- R7: 同 UID——被闸的人对闸文件有写权限（ubuntu 可写全部 guard 文件，无 ACL）

## 已落地修复

### P0-1 活性探针 `guard/gate_liveness.py`
- 5 分钟 systemd timer
- 三问：挂载在不在 / 必拦 payload 是否真被拦 / 真流量是否过闸
- 三问任一失败→`GATE_DOWN` 告警推人
- **关键设计**：②是唯一有价值的一问——实际构造一次必拦动作验证真的被拦

### P0-4 声明式清单 `guard/hash_manifest.yaml`
- `common`/`gz_only`/`sg_only` + `expected_count` 断言
- 人批退役墓碑式（`retired_by` 含 `approval_by`+`approved_at`+`evidence`+`evidence_sha256`）
- 删条目→`MANIFEST_TAMPERED`→rc=2
- 封死"删清单消警"的第三条路

### P0-5 告警管线 `guard/alert_pipeline.py`
- P0 立即推人：`GATE_DOWN`/`MANIFEST_TAMPERED`/`GUARD_BYPASSED`/`PROTECTED*`
- 24h 去重，5 分钟未确认重推
- 每日 `ALERT_PIPELINE_OK` 心跳（当天收不到=链路死亡）
- P1 日报，P2 静默（仅已退役的 `FILE_MISSING`）

### P0-2 重建 node-entry-guard.py
- 实现放 `workflow/guard/node-entry-guard.py`（Git 内可回滚）
- `.hermes/guard/` 放运行副本/符号链接
- 补内容穿透检查（重定向/heredoc 写盘按 PRODUCE 处理；解释器间接执行读被执行文件递归分类）
- PROTECTED 写保护清单化（命中即 BLOCK，不看票据不看模式，observe 期也拦）
- INTELLECT_GEN 内容闸：检测写入内容含模型ID+≥2参数键=智力活→block要求codex旁证

### 闸文件落位铁律
- 关键闸实现必须放 Git 内 `workflow/guard/`
- `.hermes/` 只放符号链接或运行副本
- `.gitignore` 的 `.hermes/` 一刀切排除整个运行时——闸文件住在 `.hermes/guard/` 天然不可回滚
- 修法：闸实现放 `workflow/guard/`，hook command 直接指向 workflow 路径

## 两套闸体系

| | 框架层三闸（8-15设计） | 应用层 G01-G14（8-23审计） |
|---|---|---|
| 拦什么 | Hermes 自己的工具调用 | 派给执行器的任务书与通道票据 |
| 入口 | config.yaml pre_tool_call hook | hermes_task_dispatch.py |
| 票据 | guard/tickets/*.json（TTL 2h） | gate_tokens/（TTL 600s） |
| 现状 | 整条链死 | 部分在跑 |

两套票据、两套 guard 目录、两套审计日志，互不校验。小鹿绕分工正好走在两者缝里。后续治理要合并。

## 快速复核命令

```bash
# 活性探针
python3 ~/.hermes/guard/bin/gate_liveness.py \
  --config ~/.hermes/config.yaml \
  --guard-dir ~/.hermes/guard \
  --alert-pipeline ~/.hermes/guard/bin/alert_pipeline.py \
  --alert-config ~/.hermes/guard/alert_pipeline.json \
  --status-file ~/.hermes/guard/gate_liveness_status.json

# hash清单校验
python3 /home/ubuntu/workflow/guard/hash_verify.py \
  --manifest /home/ubuntu/workflow/guard/hash_manifest.yaml \
  --machine sg --validate-only

# 广州远程复核
ssh -p 2222 ubuntu@127.0.0.1 \
  'systemctl --user list-timers --all | grep -E "gate-(liveness|alert-pipeline|hash-verify)"; \
   cat ~/.hermes/guard/gate_liveness_status.json; \
   tail -20 ~/.hermes/guard/alert_events.jsonl'
```

## 待人工审批项

- MISMATCH 人工定性：SG 6 项 + 广州 1 项需对照 Git/批准记录判定每次变化是否授权
- 人的 Feishu 收件确认：程序只证明发送接口成功，不能伪造"人已看到"
- B6/B7 摘闸演练：mv 走 guard 和注释 hooks 的演练，以人的 Feishu 收件为验收终点
