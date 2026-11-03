# G07 Attest Gate 两机部署审计与修复（2026-08-29）

## 背景

G07 attest 闸在新加坡机（SG）和广州机（GZ）部署后，派 Codex 做独立审计。审计结论：**FAIL**——两机均未达到「完整、一致、无绕过、strong」标准。

完整审计报告：`projects/g07-attest-audit/G07_ATTEST_DEPLOYMENT_AUDIT_2026-08-29.md`（297 行）

## 审计方法论

1. **收集证据**：两机 gate_config、attest_writer 用户信息、所有相关脚本（taskbook_attest_gate.py / dispatcher_g07_adapter.py / attest_verify.py / 各 wrapper / dispatch 脚本）全 cp 进项目 `inputs/` 目录
2. **脚本一致性**：三个核心 Python 脚本 diff 逐字节比对（全一致）
3. **写结构化审计 brief**：8 项检查清单（config 一致性 / 脚本一致性 / SG 接线完整性 / GZ 接线完整性 / 信任边界 / 审计日志 / 绕过路径 / 遗漏项）
4. **kb_gate 预检 + task_brief_gate 预检** 通过后 dispatch
5. **G07 悖论**：BLOCK 模式拦住了审计任务书自身（无 codex producer attest）→ 临时切 WARN 派审计 → 跑完切回 BLOCK

## P0 问题清单（6 项）

### P0-1: GZ 运行时 config 为空
- **现象**：`gz_brief_gate_check.sh` L56-68 调 `run_g07_before_issue_token` 时传 `config={}` + `trust_boundary_strong=False`
- **后果**：validator `resolve_mode()` 对空 config 回落 WARN，BLOCK 形同未部署
- **根因**：调用方没加载 YAML 配置文件传给 adapter

### P0-2: GZ prompt 写 /tmp 随机文件
- **现象**：`gz_brief_gate_check.sh` L39-44 把 prompt 写到 `/tmp/gz_brief_gate.XXXXXX`
- **后果**：validator 要求 brief 在 project dir 内（L228-233），即使 config 修对也会全量误拦 `TASK_BOOK_OUT_OF_PROJECT`

### P0-3: GZ OX/DS/Claude 通道吞 BLOCK 退出码
- **现象**：`gz_ox_shell.sh` L100-113 自签 token 直调 `ox_native_invoke.py` 无闸；`ds_fallback.sh` L40-44 和 `claude_remote_wrapper.sh` L63-67 用 `| grep ... || true` 吞掉 BLOCK exit code
- **后果**：BLOCK 被拦截但下游继续执行

### P0-4: SG ds_fallback.sh 未接 G07
- **现象**：`ds_fallback.sh` L74-119 直接执行 `claude -p` / `codex exec`，无 TASK_GATE 或 dispatcher 调用
- **后果**：DS 通道完全绕过 attest 闸

### P0-5: GZ write_attest.sh 权限
- **现象**：`write_attest.sh` 是 ubuntu 所有 rwx（700）
- **后果**：attest_writer 读不了 → 信任边界不满足 → `dispatcher_gate_and_writer_not_writable_by_hermes` promotion requirement 失败
- **修法**：`sudo chown attest_writer:ubuntu write_attest.sh && sudo chmod 750 write_attest.sh`（root 命令）

### P0-6: Token 无签名无独立信任链
- **现象**：Token 是同 UID 可写 unsigned JSON，validator 不检查 token 文件 owner/mode/signature
- **后果**：Hermes 可伪造 token（同 UID 写文件）

## P1 问题清单（7 项，摘要）

1. SG Claude wrapper `TASK_GATE_ENABLED=0` 可绕过（只检查等不等于 1）
2. SG codex_exec_gated.sh L100 `unset TASK_GATE_PROJECT` 在 L102 check 前 → bypass token 无项目绑定
3. GZ `--search`/`--gen-img` 旁路完全绕过闸（直接 SSH exit 0）
4. 知识库豁免标记纯字符串旁路（DS 脚本无 G07）
5. `attest_verify.py` 两机零生产调用
6. Config 缺失/损坏 fail-open 到 WARN（应 fail-closed）
7. SG 74 条审计日志存在但质量未验；GZ 零日志

## PASS 项

- 三个核心 Python 脚本逐字节一致（SHA-256 全匹配）
- SG dispatcher 主链正确（import L58-60 → call L208 → BLOCK 分支 L215-218 返回）
- attest_writer 独立 OS UID（SG uid=993, GZ uid=995）
- attest 目录 attest_writer:ubuntu 750（group r-x, no w）

## 修复流程

1. 收集全部源文件进项目 inputs/
2. 写 fix_brief.md（列出全部 P0/P1 + 期望修复产出）
3. kb_gate 预检 fix_brief（注意：brief 正文不能出现 `SKIP_KB_GATE=1` 等触发词原文）
4. 临时切 WARN → dispatch codex 生成修复补丁 → 切回 BLOCK
5. 部署 SG 侧补丁
6. 穿隧道部署 GZ 侧补丁
7. GZ root 命令列给用户手动跑（write_attest.sh 权限）
8. 两机切回 BLOCK + 冒烟验证

## 部署踩坑（2026-08-29 实测）

### GZ claude_remote_wrapper.sh 路径与 SG 不同

SG 侧 `~/.hermes/scripts/claude_remote_wrapper.sh` 是软链 → `workflow/scripts/claude_remote_wrapper.sh`。**GZ 侧没有软链**，文件直接在 `~/workflow/scripts/claude_remote_wrapper.sh`，`~/.hermes/scripts/` 下不存在。

部署脚本（codex 产出）把 GZ claude_wrapper 的 verify + deploy 目标写成 `~/.hermes/scripts/claude_remote_wrapper.sh`——文件不存在 → `verify_baseline` 直接 `exit 3` → 部署中途退出，后续文件（g07_brief_gate_check.py / write_attest.sh 迁移 / gate_config.yaml 落盘）全部没执行。

**修法**：部署脚本 GZ 侧 claude_wrapper 路径改写为 `/home/ubuntu/workflow/scripts/claude_remote_wrapper.sh`。验证探针同理。

**通用教训**：两机脚本布局不对称——SG 用 `~/.hermes/scripts/` 软链指向 `workflow/scripts/`，GZ 部分脚本在 `workflow/scripts/`、部分在 `~/.hermes/scripts/`。部署脚本逐文件写死路径时，必须 SSH 实测目标机文件真实位置，不能假设两机布局一致。诊断指纹：部署脚本 `exit 3` + `BLOCKED: target missing` = 路径写错。

### setfacl 未安装

`acl` 包没装 → `setfacl` 不存在 → 部署脚本 `command -v setfacl` 检查直接 `exit 3`。`sudo apt install -y acl` 后重跑即可。SG 侧实测需要装。

## 关键教训

1. **YAML 声明≠运行时**：审计必须查调用方传参，不查 YAML 值
2. **闸检自身悖论**：BLOCK 拦检查者 = 闸在工作；临时降级是唯一出路
3. **通道全覆盖才算接好**：漏一个通道（ds_fallback / ox_shell / --search）= 闸有后门
4. **权限链要闭环**：attest_writer 不只建用户，write_attest.sh 等脚本也要 chown
5. **Token 要有独立信任链**：同 UID 可写 = 可伪造 = 信任边界不成立
6. **两机脚本布局不对称**：部署脚本逐文件写死路径前必须 SSH 实测目标机真实位置，不能假设两机一致（SG 软链 vs GZ 直放）
