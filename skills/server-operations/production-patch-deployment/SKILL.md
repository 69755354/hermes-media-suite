---
name: production-patch-deployment
title: 生产补丁部署纪律（多机/root/重启）
description: 部署经审查的补丁批次到生产机时用。先基线核对→备份→部署→MD5验证→冒烟→记录。
version: 1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [deployment, ops, patch, multi-machine, root]
    related_skills: [review-fix-verify-loop, ai-code-edit-safety, server-migration]
---

# 生产补丁部署纪律

## When to Use

- 把 codex/claude 产出、经独立终审（VERIFY_*.md 判定可部署）的补丁批次落到生产时
- 多机部署：新加坡（本机 <SG_HOST>，生产主力）+ 广州（<GZ_HOST>，`ssh -p 2222 ubuntu@127.0.0.1` 入口）
- 涉及 root 只读文件（`/opt/hermes/gates/*`）、服务重启、跨机同步
- 用户说「立即上的先搞完」「批X先跑」「部署」等指令时，按本流程走

## 核心流程（每批必走，顺序不可跳）

1. **基线核对**：`md5sum` 生产文件，对照交付清单（ANALYSIS/VERIFY 里的指纹表）。**任一不符即停**，先查漂移原因再决定，绝不强盖。
2. **备份**：所有将被覆盖的文件 + 哈希基线，带时间戳 `.bak-$TS`，放 `staging/<deploy>-*/backup/`。
3. **部署**：用 `install -m <mode>`（避免先 chmod 再写的中间可写窗口）；root 文件用 `sudo install -o root -g root -m 444`。
4. **MD5 验证**：部署后 md5sum 必须等于交付指纹。
5. **语法验证**：`bash -n` / `py_compile` / `yaml.safe_load`。
6. **功能冒烟**：真实场景测新行为（闸 BLOCK rc=2 / 干净 rc=0、attest 双 role 并存、curl 410 等）。
7. **记录**：部署清单、MD5、备份位置、验证输出。

## 本机门禁文件部署地图（2026-08-23 实测，SG 机）

| 文件 | 属主/权限 | 谁部署 | 备注 |
|---|---|---|---|
| `/home/ubuntu/workflow/scripts/workflow_gate.py` | root:root 0444 | root | 与 /opt 双副本独立 inode，md5 须一致（曾同为 9ba8da09…） |
| `/opt/hermes/gates/workflow_gate.py` | root:root 0444 | root | 同上；codex 容器环境可能看不到此路径，部署脚本里 test -f 核验 |
| `/home/ubuntu/workflow/scripts/director_review_scorer.py` | ubuntu:ubuntu 0755 | Hermes 可直打 | 备份→覆盖→`py_compile` 即可 |
| `/home/ubuntu/workflow/wiki/spec/CREATIVE_ROUTE_TABLE.yaml` | ubuntu:netdev 0644 | Hermes 可直打 | 与 `/home/ubuntu/wiki/spec/` **同一 inode（硬链接）**，改一份两路径同生效，备份一份即可 |

gate 常量指向的是 `/home/ubuntu/workflow/wiki/spec/CREATIVE_ROUTE_TABLE.yaml`（不是 /home/ubuntu/wiki/spec/），部署前 grep 常量确认真实路径。

## 陷阱（本类任务实测踩过）

1. **补丁基线陷阱**：补丁的「期望基线 MD5」可能匹配**另一台机**的版本。部署前确认哪台机真的在跑这份代码（grep 调用方、看进程/service 状态、看隧道转发）。案例：codex 的 codex_gen_text.sh 补丁基线是广州版（55 行含 DS 兜底），新加坡那份是 40 行死代码（无调用方）——按 REPAIR 说明部署到新加坡会基线不符，正确目标是广州。
2. **先换文件再重启**：重启服务前必须确认新文件已落盘。先重启旧文件 = 白重启，验收仍显示旧行为（curl 200 而非 410）。部署说明里「此时文件已换但服务跑旧代码」的中间态是安全的，可以停。
3. **确认用户终端在目标机**：天行者从 Termux 操作，命令可能跑在手机本地而不是目标机。让用户先 `hostname -I` 确认（<SG_HOST>=SG，<GZ_HOST>=GZ）。Termux 出现 `pkg install` 提示 = 跑错机器，不是缺依赖。**跳板命令坑（2026-08-23）**：`ssh -J ubuntu@<GZ_HOST> ubuntu@<SG_HOST>` 会 `Permission denied (publickey)`——`-J` 模式下终点机（SG）认证用的是**发起端电脑的 key**，不是跳板机（GZ）的 key，而 SG 只认 GZ 的 key。正确姿势：两步走（先 `ssh ubuntu@<GZ_HOST>`，在广州机内再 `ssh ubuntu@<SG_HOST>`，GZ→SG 免密已验证通）。
4. **批次耦合不可拆**：终审验证过的「批内必须同时上」要遵守（如 GZ 批3：G6+G5+G4 三件齐才生效；只部署 G6 无效果，G6+G5 仍被吞码）。部署说明标注「成对」「必须同时上」的不能拆。
5. **成对文件**：`task_brief_gate.py` + `gate_config.yaml` 必须成对部署；新 gate + 旧 config 会静默退化为 WARN，不报错但失效。
6. **测试任务书构造**：测判断词闸时把判断词放 USER_REQ 行**外**——`sanitize_body` 会剔除 USER_REQ 行（那是天行者原话，允许判断词），拦截目标是正文里夹带的 Hermes 判断。
7. **风险评估先核运行时状态**：终审报告的 FAIL/风险要对照实际运行状态核实（service 是否活着、出片是否已迁走、调用方是否还在），跨机场景尤其重要。案例：F1「删 .hermes 副本打断广州出片」——核实后广州出片已迁新加坡（SSH 隧道 11889→1889）、execute-api.service 已停 13h，真实风险场景是「广州重启后自启」不是「当前」。
8. **YAML 新键可先打，py 解包不能拆**：旧代码用 `guard.get(...)` 读 YAML 时，新增配置键（如 exclude_path_prefixes）对旧代码无副作用，可先部署 YAML；但 py 侧的改动（如 scope 解包从二元变三元）必须和 YAML 一起上，否则旧代码解包直接 ValueError。判断依据：grep 被改函数是 `get()` 容错还是硬解包。
9. **辅助脚本读模型配置优先 `auxiliary.model.default`**：本机 config.yaml 顶层 `model.default` 是**主对话模型**（deepseek-v4-flash），`auxiliary.model.default` 才是**辅助任务专用**（deepseek-v4-pro，评审/质检类）。codex 补丁常把 `load_model()` 写成只读顶层 `model.default` → 导演评审会被降级成 flash。修复模式：优先 `cfg["auxiliary"]["model"]["default"]`，缺失回退顶层，再缺失回退 hardcode。部署任何读 config 的辅助脚本后，必须实测 `load_model()` 返回值。
10. **systemd auto-restart 循环 = 端口被手动健康进程占用**：execute-api.service 显示 `activating (auto-restart)` 且 journal 无日志时，查 `ss -tlnp` 找占端口进程——常是某天手动启动的 python 进程（PPID=1）健康服务中，systemd 新实例 bind 失败无限重启。服务其实正常（curl /health alive）。`systemctl stop` 也要 polkit 认证时留给用户 root；停 unit 不会杀 PPID=1 的旧进程，服务不中断。
11. **回归脚本调门禁函数要用正确签名**：`locate_creative_prompt_files(proj, reg=None)` 第二参是 **registry**（默认 load_registry()），不是 scope——scope 是函数内部自己 `creative_scope_config()` 读的。把 scope 当第二参传进去会 `AttributeError: 'tuple' object has no attribute 'get'`（artifact_path 里 reg.get 炸）。回归验证代码先 grep 函数定义确认签名再写，避免部署脚本第 4 步白报错。验证扫描数：`files = g.locate_creative_prompt_files(proj)` 后按 mtime 降序取前 3。
12. **git apply 在 git 仓库内会静默跳过且返回 0（部署假成功，2026-08-23 G07 验收 FAIL 核心）**：当部署目标目录本身就是 git 仓库（如 /home/ubuntu/workflow）且实施包在其子目录时，runbook 里的 `cd <子目录> && git apply --directory=/ <patch>` 会因为补丁路径已在仓库内而**静默跳过、返回 0**——预检脚本打印 PATCH_OK、部署脚本空转，走到最后一步才以「patched hash mismatch」报错，此时备份已建、模块已装、**零补丁生效**。防法：①部署验证**不能只信 `git apply` 退出码**，必须 apply 后用 `cmp`/md5 比对 patched 快照与实际文件 ②`verify_package.sh` 这类自检脚本要先在真实 cwd 下实测（文档写的 cwd 与真实执行 cwd 不一致 = 自检白过）③dry-run 与应用都要验证，不能 dry-run 走通就以为应用走通。
13. **部署脚本的 root 环境差异**：dispatcher/探针用 `Path.home()` 定位模块时，root 执行（部署步骤常见）与 ubuntu 执行 HOME 不同 → 模块级导入直接 ModuleNotFoundError。部署脚本必须显式设 HOME/绝对路径，或探针与部署同身份跑。**无 trap 的部署脚本 = 失败路径全静默**：中途失败不留 BACKUP_DIR 提示，而备份目录 0700 root 专属时非 root 连查都查不到。部署脚本必须 trap 打印备份位置，备份目录权限要考虑排障身份。

14. **验收 PASS ≠ 部署授权：PASS 只打开「下一个 root 变更窗口」，先只读预检再部署（2026-08-23 G07 复验 PASS 实测）**：claude 复验 `REVIEW_RESULT=PASS` 后，报告明示 `WARN_DEPLOY_ENTRY=READY` 仅表示允许进入下一个 root 变更窗口，且保留 NEED_INFO 清单——必须先补采再谈部署。三类典型 NEED_INFO 及判据：① **N1 sudo 语义**（部署探针 root 身份下的 HOME）——`sudo grep -E 'always_set_home|env_reset|env_keep' /etc/sudoers /etc/sudoers.d/*` + `sudo printenv HOME`，在**目标机**上跑（见 pitfall 15）；② **N2 root 级 ACL/owner 留证**——只读预检脚本 `sudo bash staging/scripts/deployment_preflight.sh`；③ **N4 现存调用面**（如内联 `--brief` 调用）——`grep -rn "hermes_task_dispatch.py" <项目>/work/*.sh` 逐条看 `--brief` 后跟的是文件变量还是内联文本，全文件形态 = 无内联，兼容性结论成立。**放行边界：PASS + 预检齐 + 人工批准 = 才执行部署脚本；PASS 不代表已部署、不代表可切 BLOCK（BLOCK 晋级要另开变更单）**。用户说「跑」仅授权只读预检步骤，部署脚本执行仍需单独拍板。
15. **确认用户终端在目标机：MacBook 本机跑 sudo = 结果无效（2026-08-23 G07 N1 预检实测）**：pitfall 3 的 Mac 变体——天行者从 MacBook 终端跑 `sudo grep /etc/sudoers`，返回的是 **MacBook 本机**的 sudoers（`env_keep += "HOME MAIL"`），不是新加坡机（<SG_HOST>）的。部署判据（N1 类）必须在部署目标机跑，MacBook 的 sudo 语义跟新加坡机无关。识别特征：输出里 `Last login ... on console` / `<MAC_HOST>` / `/Users/xxx` 路径 = 本地机结果。正确通道：两步走 SSH（MacBook → 广州 <GZ_HOST> → 新加坡 <SG_HOST>，`-J` 跳板被拒因 SG 只认 GZ key），命令分开发回报防粘错。
16. **用户质疑「为什么改动要这么大」时，把 FAIL 清单按「同根因/补测试/真修复」三分解释改动量（2026-08-23 G07 F01-F06 实测）**：claude 验收 6 条 FAIL 全是交付脚本层问题、核心闸零改动——但用户看到 FAIL_COUNT=6 会以为是大改。正确解释框架：① **同根因合并**（F01/F02 是一个 git apply cwd bug 的两个表现，实际一处修复）；② **补测试≠改逻辑**（F06 四类行为 claude 实测全对，缺的是回归护栏，补的是用例不是代码）；③ **真修复最小化**（F03 改一行、F04 加 trap 几行）；真正危险只有 F01/F05 两条（假成功部署/装闸但恒不校验）。**汇报验收 FAIL 时先按根因聚类再报数量，别让 6 条 FAIL 吓到用户以为要重写系统**。
17. **验收/复验进程「日志空≠卡死」：claude -p 是干完活一次性落盘，中间零输出是正常形态，判活看 CPU 时间增长（2026-08-23 G07 复验实测，用户「验收这么慢」）**：claude -p 验收长任务日志往往只有一行 `[claude-wrapper] 开始`，跑 18+ 分钟零输出——**不是卡死**，claude -p 模式把中间过程吞掉、最后一次性写报告。误判卡死 → 杀进程 = 白等一场。判活三板斧：① `ps -o pid,etime,pcpu,stat -p <pid>` 看进程活着；② **CPU 时间对比**——`cat /proc/<pid>/stat | awk '{print $14+$15}'` 隔 5 秒跑两次，数值在涨 = 在推理（本次 2633→2650）；③ fd 更新时间——`ls -lt /proc/<pid>/fd` 有 22:37 这类新时间戳 = 有读写活动。三样都在 = 正常慢，报预计剩余时间继续等，不杀进程（已提交不杀纪律）。

18. **改全局闸前先查工作区脏状态：git 脏了就不能当差异/回滚基线，改用文件快照（2026-08-24 评审递归修复实测）**：修 `workflow_gate.py` 时发现相对 HEAD 已有 **377 insertions / 27 deletions 未提交**（整个导演意图闸特性 `locate_creative_prompt_files`/`check_director_intent` 在 HEAD 里根本不存在），`CREATIVE_ROUTE_TABLE.yaml` 状态 `??` 从未进 git。后果：① `git diff` 会混入 406 行无关预存改动，无法证明「只改了几处」；② `git checkout --` 回滚会连带丢掉整个未提交特性。正确姿势：**改前 `git status --short` 查脏 + `git show HEAD:<file> | grep -c <关键函数>` 确认预存特性在不在 HEAD**；差异核验用改前文件快照逐字比对（`cp <file> /tmp/baseline_<ts>/` + `diff -u` 数 hunk），回滚用 `cp` 还原副本；**预存改动的提交口径（何时提交/提交信息）是人的决策，执行器不整理、不提交、不回退，只在其上加补丁并如实上报**。判定「预存 vs 本次」：`git diff --stat` 改前记录 + 任务开始时的基线 SHA。

## MISMATCH 定性与基线刷新（2026-08-26 实战）

当 hash-verify 报 SECURITY_BREACH（MISMATCH），不要慌：

1. **逐文件查 git log + 修改时间**：`git log --oneline --all -- <file>` + `stat --format='%y' <file>`
2. **对照时间线**：修改时间是否对应某次授权的 codex/claude 执行（P0/P1 执行报告里有时间戳）
3. **双机当前哈希对比**：两机当前哈希一致 = 同版本，基线不同只是建立时间不同
4. **全部可追溯 = 授权变更**→ 刷新基线（备份旧 `.md5` → 写新 MD5 → 跑 hash-verify 确认 ALL_OK）
5. **有任何一项无法追溯 = 疑似篡改** → 不可刷新，人工调查

8月26日实测：SG 7项 + 广州2项 MISMATCH，全部追溯到 codex P0/P1 执行（git commit bda1b04/784ba4d/98287bc 等），刷新后双机 ALL_OK。

详见 `references/hash-verify-baseline-refresh.md` — 完整刷新脚本（Python + SSH）、manifest 结构、定性方法。

## 受保护路径上线（`~/.hermes/scripts/` 等）实操

1. **AI 写不进受保护路径**：guard 拦 `PROTECTED_PATH_WRITE`；即使通过 SSH 打到远端、命令里用相对路径，也会被解析成绝对路径拦掉。正路两条＝管理员带外放解锁文件 `~/.hermes/guard/unlocks/<name>.json`（字段 `pattern` 正则匹配命令、`expires_at` ISO 或 epoch、`one_shot`、`used`、`created_by`），或用户本人在目标机直接执行 cp。禁自建解锁文件、禁绕闸。
2. **部署判定以哈希为准，不信脚本退出码**：分发脚本可能备份成功、打印了重启命令，却在写文件前抛错（如 `'str' object has no attribute 'parent'`）；落盘后必须 `sha256sum` 比对「基线哈希＝改动前线上值」与「候选哈希＝包内 APPLIED_SHA256」，改完再比一次。
3. **root shell 里不能用 `systemctl --user`**（`Failed to connect to bus: Operation not permitted`）：用 `su - ubuntu -c 'export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user restart <unit>'`。
4. **磁盘改完必须重启才生效**（进程仍载旧代码）；重启后再核 hash、MainPID、启动时间、平台连接日志（如 `[Lark] connected`）。

## 参考文件

- `references/r7-confirm-gate-deploy.md` — R7（confirm_gate 三副本 + execute_api + 重启）完整部署命令与验收，root 操作须天行者终端执行
- `references/hash-verify-baseline-refresh.md` — Hash-Verify 基线刷新流程（MISMATCH 定性 + 双机刷新脚本 + 验证）
