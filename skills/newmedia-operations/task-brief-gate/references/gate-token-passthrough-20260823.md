# Gate 一次性 token 透传架构与 C1/C2 修复实录（2026-08-23）

背景：R6 部署后广州 codex 通道被 SG 默认强制 token 拦死（C1），SG hash-verify 基线过期误报（C2）。天行者拍板先方案 A（临时豁免）止血、后方案 B（透传一次性 task token）落地。本文是 B 方案设计必须的 token 架构事实 + 两处修复的可复用配方。

## 一次性 token 双路径消费（双花冲突）

kb_gate_sg.py `consume_gate_token()`：token_id 白名单 `^[0-9a-f]{32}$`（uuid4().hex，fullmatch），O_EXCL `.consumed` 标记原子消费，消费后永久保留（禁止双花），失败则删标记允许重试。

**两条独立消费路径：**
1. `TASK_GATE_TOKEN`（环境变量）→ codex_exec_gated.sh R6 校验 → `kb_gate_sg.py --consume-token <id> --task-gate`
2. prompt 内知识库放行 token（键名 KB_GATE_TOKEN）→ kb_gate_sg.py `-f` 时 KB_GATE:REMOTE_PASS 路径（425-451 行正则 `KB_GATE_TOKEN\s*=\s*([^\s]+)`）

**同一 token_id 被两条路径各消费一次 → 第二次 O_EXCL 已存在 → `token 已使用（一次性）` BLOCK。** 方案 B（广州透传 task token）必须**签两个 token**：一个 kb_gate（附 prompt 走知识库闸）、一个 task_gate（环境变量走 R6 闸），task_type 区分，先后签发、分别透传。不能用现有 KB 放行 token 顶替。

## 广州→SG token 签发接口（B 方案复用现成机制）

- 广州 codex_remote.sh:147 已有：`bash ~/.hermes/scripts/kb_token_issue.sh <project> <task_type> <ttl>` SSH 到 SG 执行，stdout `tail -1` 拿 token_id
- SG kb_token_issue.sh：uuid4().hex，payload `{project, task_type, issued_at, expires_at, used:False}`，落 `/home/ubuntu/workflow/gate_tokens/<id>.json`（0600），目录 0700
- TOKEN_DIR 单一来源 env `GATE_TOKEN_DIR`，四处一致：kb_gate_sg.py / kb_token_issue.sh / codex_exec_gated.sh / hermes_task_dispatch.py
- hermes_task_dispatch.py `issue_token()`：TOKEN_TTL=600，payload 额外带 brief_hash/route；广州不用此路径，走 kb_token_issue.sh

## 退出码接管 bug（wrapper 误报成功 + 假记账）

广州 codex_remote.sh 原写法：
```bash
if ! OUT=$(echo "$PROMPT" | "${SG_SSH[@]}" "$REMOTE_CMD" 2>&1); then
    RC=$?    # 此处为 0：`!` 已反转状态，then 分支 $? 不是远端退出码
fi
```
`!` 反转命令状态后，then 分支里的 `$?` 是 0 不是远端 rc —— SG 的 rc=2 BLOCK 被误报 rc=0，还触发 `record_producer "codex" false` 假记账。正确写法：
```bash
OUT=$(echo "$PROMPT" | "${SG_SSH[@]}" "$REMOTE_CMD" 2>&1) || RC=$?
```

## C2 哈希基线修复（不是回滚代码）

hash-verify.sh 报 SECURITY_BREACH 但生产 execute_api.py 是已验证部署的正确版本 → 修复 = 更新 stored 基线 `/home/ubuntu/.hermes/guard/hashes/execute_api.py.md5` 到实际 MD5，**不改校验脚本、不回滚代码、不清空 security_alerts.log（历史审计记录保留）**。

部署硬前置：生产文件 MD5 = 已验收值 且 stored = 旧值，任一不符 fail-closed。备份 `.bak-c2-<ts>` → mktemp+mv 原子替换 → chown/chmod --reference 继承 → 重跑 hash-verify 期望 15 项 OK + ALL_OK + rc=0。
注意：基线文件属主是 ubuntu（rw-rw-r--）时**无需 sudo**（sudo 在无密码终端会卡「a terminal is required to read the password」）。

## 非计费探针（验证 gate 部署，不调用 codex）

探针设计原则：在调用 codex_sandbox.sh 之前失败 → 零模型/API 消耗。

- 探针1（默认开闸保留）：无 token 直调 `codex_exec_gated.sh --skip-git-repo-check -C /definitely-not-allowed` → 期望 rc=2 + `BLOCKED: 缺少 TASK_GATE_TOKEN`
- 探针2（豁免生效）：`TASK_GATE_ENABLED=0 SKIP_REASON=c1_nonbillable_probe ...` → 期望 rc=1 + `ERROR: WORKDIR 不在白名单`（在 workdir 校验处停下，未调 codex）
- 端到端真实验证会真正进 codex（花钱），必须由获准测试任务执行，不能当普通探针

## 部署纪律复现（本次实录）

基线 MD5 核对 → 备份 `.bak-c1-<ts>` → 本地按 diff 打补丁并验证 MD5 = codex 给的 EXPECTED_NEW → scp → 远端 md5sum + bash -n + 关键行 grep → 跑探针 → 更新 DEPLOY_RECORD.md。本次：GZ codex_remote.sh 2b65d893 → f592f5e9（方案 A）；C2 基线 c97a3794 → de78ce5d。

## 方案 A → B 的替换注意

- 方案 A 是临时豁免（`TASK_GATE_ENABLED=0 SKIP_REASON=gz_brief_gate_passed_pending_task_token_20260823`），B 落地后撤销，运行日志不应再出现该 SKIP_REASON
- --search / --gen-img 两条 shortcut（GZ codex_remote.sh 39-55 行）直连远端 codex，不走 codex_exec_gated.sh，是既有 R6 绕行入口，最终迁 dispatcher 时一并收口，不能用临时豁免把它包装成已过任务书闸
- DS 兜底链（GZ_codex_ds_fallback.sh）走 sg_ds_invoke.sh，不进 codex_exec_gated.sh，无需改动
