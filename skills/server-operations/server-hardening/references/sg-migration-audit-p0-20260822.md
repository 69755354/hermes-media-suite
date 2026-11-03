# SG 迁移架构终审 P0 证据链（2026-08-22）

来源：`staging/sg-deploy/新加坡迁移架构审查_20260822.md`（claude 终审，39KB）。广州→新加坡迁移部署全绿后仍 3 个 P0，终审判定不通过。

## P0-A：sudoers 白名单通配符路径穿越 → 完整 root 回归

生效规则（`/etc/sudoers.d/99-hermes-tighten`）：
```
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart execute-api, /bin/systemctl restart helper-api,
                    /usr/bin/install -o root -g root -m 0644 * /etc/hermes/*
```

sudoers 里 `*` 是 glob 非路径规范化，可含 `/` 和 `..`。实测探针（不存在的源文件，install stat 阶段即中止，无写入）：
```
A 合法目标:  sudo -n install SRC /etc/hermes/zz-probe        → 免密通过，install 报 stat 错
B 穿越:      sudo -n install SRC /etc/hermes/../sudoers.d/zz-probe   → 免密通过（！）
C 穿越:      sudo -n install SRC /etc/hermes/../../opt/hermes/gates/zz-probe → 免密通过（！）
D 对照组:    sudo -n /bin/cat /etc/shadow                     → sudo: a password is required（被拒）
```

攻击链：ubuntu 写自建 sudoers 片段 `/tmp/pwn`（`ubuntu ALL=(ALL) NOPASSWD: ALL`）→ `sudo -n install /tmp/pwn /etc/hermes/../sudoers.d/99-pwn` → 免密写入 sudoers.d → **完整免密 root 回归**。同一手法可覆写 `/opt/hermes/gates/*.py`（绕过 P0-3 root 迁移）与 `/etc/hermes/render_authorized.list`（自授 LIGHT）。

**判读教训**：`sudo -l <cmd>` 对 catch-all 也返回 0，不能用它判白名单命中；必须 `sudo -n <cmd>` 实跑。

修法：白名单写字面目标（源和目标全路径）；或 root:root 0755 包装脚本内部 realpath 校验；删重复规则（实测重复 2 条相同内容）。

## P0-B：permission_gate 路径错位 → 出片 100% 阻断

```
/opt/hermes/gates/permission_gate.py:21  PERM_FILE = "/home/ubuntu/.hermes/profiles/customer/permissions.json"
ls: .../profiles/customer/permissions.json  → No such file（不存在）
find /home/ubuntu/.hermes -name permissions.json → /home/ubuntu/.hermes/permissions.json（真实文件）
```

真实文件 4 个用户全 unlimited，但闸读不到 → `load_perms()` 回 `{}` → 缺省 basic → rc=2「basic 无付费操作权限」。4 个真实 uid 全部复现。成因：468 基线无此闸，本次新引入的回归；部署只做了静态门禁+服务健康，fail-closed 型可用性故障测不出。

修法：PERM_FILE 指真实文件（改 /opt 下 root 文件需人批 + 更新 hash 基线）；以 4 个真实 uid 复测 rc=0 + 端到端 dry-run。

## P0-C：helper-api:1888 无闸第二出片通道

```
grep -c "_gate_chain\|CONFIRM_GATE\|PERMISSION_GATE\|render_authorized\|HERMES_SG_GATE" /opt/helper_api.py → 0
/opt/helper_api.py 路由：/seedance（直接提交 ARK 视频生成）、/pipeline（全流程出片）、/agnes-video（视频生成）——全无闸
唯一屏障：共享静态 token（/home/ubuntu/.hermes/helper_auth_token，ubuntu 可读）
```

两服务（execute-api 与 helper-api）同以 ubuntu 跑 → 能触达 execute-api 的执行体就能读 token 直连 1888 出片，不经 customer_id/CONFIRM/G_RENDER_READY/TEST_RUN，不留 gate_chain_audit.log。部署方案 76KB 只在 2 处提 helper（sudoers 白名单 + 健康检查），从未把 helper 当出片入口做闸链评估。

修法：三个出片路由接同一 `_gate_chain`（要求 customer_id + project_dir）；短期止血可停用出片路由或限流（不可逆运维须人批）。

## 审查失误披露（审查方也踩坑）

claude 验证「旧位置是否仍可 unlink」时对 `.hermes/scripts/confirm_gate.py` 实跑 mv，超出只读边界——属主从 root:root 降为 ubuntu:ubuntu（内容 MD5 与 /opt 权威副本一致、服务正常），需 `sudo chown root:root` 修复或随 P1-D 删旧副本。结论本可用 `stat` 静态推得，不必实跑。

## 附带发现（P1/P2 速记）

- P1-D：hash-verify.sh 仍校验旧路径闸文件，/opt/hermes/gates 零覆盖（grep -c /opt/hermes = 0）
- P1-E：部署记录称 gate_config skill_contract 段合并 DONE，实测文件与备份逐字节相同、该段不存在（代码兜底恰为 WARN 无误杀，但记录不可信）
- P1-F：CONFIRM.json / workflow_state.json ubuntu 664 可自签；workflow_gate 无 HMAC；LIGHT 白名单项目已豁免 G_RENDER_READY，confirm 闸是其唯一实质屏障却可自签（FULL 路径靠授权登记哈希守得住）
- P1-G：_gate_chain 对 project_dir 只 isdir 无前缀约束，与 output_path 严格前缀检查口径不一致（当前不可利用）
- P2-G：/job 复用 run_pipeline 恒传 entry="execute"，_HARD_ENTRIES 的 "job" 是死字符串
- P2-H：billing_gate 无 precheck（能力探测正确降级 WARN），且 execute_api 无 consume 调用 → 配额永不扣减，成本护栏不存在
