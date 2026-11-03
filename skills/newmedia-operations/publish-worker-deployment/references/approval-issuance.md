# 真发审批回执：控制面签发（一条命令）

真发（`operation_mode=approved_publish`）前必须由**控制面**签发绑定本次计划的审批回执；执行器只消费、**不许自签**（自签=自己批自己，执行器会拒绝并 BLOCKED）。

## 一条命令

```bash
cd /home/ubuntu/workflow/projects/publish-worker-deploy/stage2-exec
python3 tools/issue_approval.py \
  --fill-plan  /tmp/plan_cov_1_mac.json \
  --plan-out   /tmp/publish1/plan_publish_1.json \
  --receipt-out /tmp/publish1/approval_publish_1.json \
  --key-file   ~/.publish-control/approval.key \
  --approver-id tianxingzhe \
  --receipt-id  approval-<片子>-publish-<日期> \
  --ttl-hours 12
```

脚本自带硬规则：只改 `plan_id`/`operation_mode`；派生 `content_hash` 必须等于计划里 `compliance.content_hash`；`approver_id`/`receipt_id` 必须 ASCII 安全标识符；密钥 ≤0600 且只读不写（首次 `--init-key`）；落盘前用仓库自己的 `verify_receipt` 自校验；签发日志写 `~/.publish-control/issuance.jsonl`（不含密钥/签名值）。

## 踩过的坑（别再踩）

| 坑 | 现象 | 规矩 |
|:--|:--|:--|
| `approver_id` 写中文名 | 解析阶段 `PLAN_SCHEMA: approver_id has unsafe identifier syntax`（exit 5，浏览器都没开） | 只用 ASCII 标识符 |
| 拿旧 `plan_id` 签新回执 | 幂等键=hash(account, platform, content_hash, schedule_at)，同内容同时间=同一把键 → `IDEMPOTENCY_UNAVAILABLE` | 每条片子换 `plan_id`；同一条片子绝不重签重跑 |
| 想重跑一次拿回作品 ID | 幂等键已冻结（`UNKNOWN`/`RESERVED`） | 点过发布键就不许再跑；ID 用**只读**窗口补读 |
| 让执行器自签 | 执行器拒绝（不许自己批自己） | 签发永远在控制面 |

## Mac 侧执行（只会点一次发布键）

```bash
cd ~/stage2-exec
~/publish-worker/.venv/bin/python -m stage2_exec.cli publish \
  --plan ~/publish-worker/run/batch/plan_publish_1.json \
  --approval ~/publish-worker/run/batch/approval_publish_1.json \
  --hmac-key-file ~/publish-worker/config/approval.key \
  --canary-armed \
  --report ~/publish-worker/evidence/publish1-report.json \
  --evidence ~/publish-worker/evidence/publish1-evidence.json
```

账号记录里的 `allowed_actions` 必须含 `upload` 与 `publish`（改前备份 accounts.json）。
