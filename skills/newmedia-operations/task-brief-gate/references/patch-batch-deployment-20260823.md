# 补丁批次部署执行配方（2026-08-23 unified-fix 全量部署实录）

适用：终审「有条件 PASS」后的补丁集按批次部署到两机（SG 本机 + GZ 隧道机 ssh -p 2222 ubuntu@127.0.0.1）。
前置链：实现（codex/claude）→ 独立终审（见 independent-verify-dispatch.md）→ 本配方部署。

## 每批固定五步（缺一不可）

1. **基线 MD5 核对**：`md5sum` 目标机生产文件，对照 ANALYSIS/终审指纹表（第五节交付件指纹）；任一不符 → **停**，先查漂移原因（可能是补丁基线对应错机器，见 task-brief-gate pitfall）。跨机先 ssh 目标机 md5sum 再动。
2. **备份**：SG 侧 `staging/<deploy>/backup/` 或目标机同目录 `.bak-<日期>`；`cp -a` 保留权限。三副本同批换，只换一份会出现「改了但生效的是另一份」。
3. **部署**：`install -m <权限>` 落盘（root 件用 `sudo install -o root -g root -m 444`，避免先 chmod 再写的中间可写窗口）。跨机：`scp -P 2222` 到 /tmp 验证 MD5 + 语法后再 install，装完清临时文件。
4. **部署后 MD5 核对**：全部等于 ANALYSIS 指纹才继续。
5. **功能冒烟**：每批配针对性最小验证（见下），不是只跑 py_compile/bash -n。

## 本批功能冒烟清单（各批次对应的验证）

- **R2/G6 分级闸**：干净任务书 PASS rc=0；夹带判断词 BLOCK rc=2。**判断词必须写在 USER_REQ 行外**——sanitize_body 剔除 USER_REQ 行（那是天行者原话），写在行内测不出来（本次实测假阴性）。
- **R3/G2 attest**：producer/reviewer 同 sha 两条并存不覆盖；非法 role rc=2；DS 签 reviewer rc=2。
- **G7 attest_verify**：缺终审 rc=3 MANUAL_REVIEW_REQUIRED；自审（同通道双签）rc=2 BLOCKED。
- **R6 本体**：无 token 直调 rc=2 BLOCKED；豁免路径（TASK_GATE_ENABLED=0 + SKIP_REASON）进执行器。
- **批3 耦合（G4+G5+G6 三件齐）**：夹带 rc=2 透传 rc=2；只部署 G6 无效（G5 exit 0）、G6+G5 仍被吞（G4 管道抹平）——必须三件同批。
- **R7 棘轮**：confirm 带产物 → check 不带产物 rc=2；篡改产物 rc=2；宽限期内活跃项目 check rc=0。
- **R1**：POST /execute 与 /job 返回 410。

## F1 软链模式（替代「删除副本」，2026-08-23 批5 落地）

问题：删除某文件会打断绝对路径调用方（广州 execute_api.py:423 绝对路径调 `.hermes/scripts/workflow_gate.py`，删了出片全拦 fail-closed）。
方案：保留入口名，`ln -sfn <权威件> <入口>`，不动调用方、不重启。
要点：
- 先备份两份（cp -a），再覆盖权威件（install），再 ln -sfn
- 校验：`test -L <入口>` + `readlink -f <入口>` = 权威件 + md5sum 两路径一致
- 同步 hash 基线（`guard/hashes/<文件>.md5`）+ `hash-verify.sh`
- **旧 `rm -f` 命令必须从部署说明删除**（软链后执行会删掉兼容入口，复现 F1）
- 部署后验收：两条调用路径（入口/权威件）rc 与输出完全一致，无 `can't open file`
- 回滚：rm 软链 → 恢复 .bak（两份 + hash 基线）

## 批次顺序（终审给出，部署遵守）

批1'（SG R2/R3，可立即）→ 批2（SG R7+R1 root+重启，**须人批准 + 用户终端跑**，注意时间窗如 24h TTL）→ 批3+4（GZ 5 文件一次上，含成对的 G6 两文件）→ 批6（G7 零风险）→ R6 前置+本体（先前置豁免再本体默认开闸）→ 批5（G3 权威件同步 + F1 软链，删除动作暂缓）。

**部署执行人分工**：非 root SG 文件 Hermes 直接部署；root 件（/opt、重启）给用户终端分段跑（见 user-terminal-collab「给用户终端命令的交付纪律」：分开发 + 先 hostname 确认机器 + 用户说做了≠完成要 md5 复核）；GZ 生产文件走 ssh 隧道，非 root 可 Hermes 直接 install。

## 第 6 步：部署后独立检查（全部批次落地后必跑，2026-08-23 CHECK 实例）

全部批次部署完 ≠ 收工。派一个**独立 claude 会话**做部署后全量检查（不采信部署记录/终审任何自述，16 指纹自跑 md5sum、出片链路自发 curl、闸功能自建隔离夹具），四类检查：

1. **SG/GZ 文件指纹**：md5sum + wc -l 对照部署记录，行数还要对照终审交付件行数（一致=部署件与终审过的交付件同一份，无中途替换）
2. **出片链路**：ping / seedance-exact/job POST / job/status GET / execute+job 410 / confirm check rc
3. **功能抽查**：闸夹带 BLOCK、G7 rc=3/rc=2、R3 双签、N1 DS 拦死（隔离夹具 + 生产 audit md5 前后一致防污染）
4. **部署遗漏**：对照终审批次清单逐批核对、备份件三处、hash-verify、遗留项是否已失效

**部署后检查才抓得到的坑（2026-08-23 C1/C2/C3 实录）：**

- **C1「当前安全」结论有有效期——改默认值/开强制后必须重查跨机依赖（紧急 P0 实例）**：终审写「G4-e 当前安全（SG 默认未强制）」是在 R6 部署**前**；R6 把 `TASK_GATE_ENABLED` 默认 0→1 后，GZ `codex_remote.sh` 远程调 SG 的 REMOTE_CMD **不带 TASK_GATE_TOKEN**（且 sshd AcceptEnv 只收 LANG LC_*，SendEnv 传不过去；GZ 现有 KB_GATE_TOKEN 塞 prompt 正文 ≠ 环境变量 TASK_GATE_TOKEN，codex_exec_gated.sh 全文无 KB_GATE_TOKEN 引用；DS 兜底条件只匹配额度关键词，`缺少 TASK_GATE_TOKEN` 不触发）→ 广州所有 codex 远程任务 rc=2 全挂。**规则：任何「把自愿闸变默认开/加强制」的补丁，部署后必须立即实测所有跨机调用方路径（ssh 模拟非交互 env -i 复现），不能沿用部署前的「当前安全」结论；紧急修法 = 给调用方 REMOTE_CMD 前缀加 `env TASK_GATE_ENABLED=0 SKIP_REASON=<原因>`（与 codex_task.sh 同一手法，留审计痕迹），正解 = GZ 签 task_gate token 透传后删豁免。**
- **C2 部署 execute_api.py / confirm_gate 后必须同步 `guard/hashes/<文件>.md5` 基线**：只换文件不更新 hash 基线 → hash-verify.sh 报 `SECURITY_BREACH` rc=1，把真部署当篡改。批2 部署说明里写了同步 confirm_gate hash，但 execute_api 的 hash 基线也要同步——部署记录要显式列出所有「需同步 hash 基线」的文件。
- **C3 部署记录 md5 不手抄，用部署后 md5sum 实际输出**：本次记录写 `49d5b2dd`，实际 `md5sum` 是 `0dca299d`（记录值无对应实物）——每部署完一个文件，把当次 `md5sum` 输出直接抄进记录，不靠记忆/中间输出。

**部署后检查产出**：`staging/<deploy-check>/CHECK_DEPLOY_<日期>.md`，顶部整体结论（健康可收工 / 有问题需处理），FAIL 分紧急 P0 / 遗漏 P1 / 口径 P2 三级。
