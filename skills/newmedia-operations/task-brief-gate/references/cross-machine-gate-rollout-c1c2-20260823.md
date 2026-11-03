# 跨机 gate 部署后遗症修复实录（2026-08-23 C1/C2）

## 场景

SG R6 把 codex_exec_gated.sh 的 `TASK_GATE_ENABLED` 默认值 0→1（无 token 即 BLOCK rc=2）后，
广州 codex_remote.sh 远程通道全挂。同一轮部署还带出一个哈希基线过期误报（C2）。

用户指令链：拍板三选项时用户回「让codex处理」（=分析+出方案丢给 codex，不自己拍板）→
方案回来用户回「让他自己执行」（=按 codex 方案执行部署，不再逐项确认）。

## C1 根因链（两层缺陷）

1. **跨机接口不兼容**：广州 codex_remote.sh 的 `REMOTE_CMD="~/.hermes/scripts/codex_exec_gated.sh ..."`
   不带 `TASK_GATE_TOKEN`、不带豁免变量 → SG R6 默认开闸后全部 BLOCK rc=2。
   DEPLOY_RECORD 已记录「G4-e 未修（已知缺口）」，但部署时没做调用方侧前置。
2. **退出码接管 bug**（codex 同链抓出）：`if ! OUT=$(...); then RC=$?; fi` —— `!` 反转状态后
   then 分支 `$?` 恒为 0，远端失败被误报成功 rc=0，且执行 `record_producer "codex" false` 假记账。

## 方案三选项（codex 给出，Hermes 不自己拍板）

| 方案 | 内容 | 代价 | 状态 |
|---|---|---|---|
| A 临时豁免 | `TASK_GATE_ENABLED=0 SKIP_REASON=gz_brief_gate_passed_pending_task_token_20260823` + 修退出码 | 无一次性 token 防重放，依赖 GZ 本地两闸+SSH | **已部署（止血）** |
| B 透传 token | GZ fail-closed 要求 TASK_GATE_TOKEN 存在，透传 SG 原子消费 | 缺签发器接口/格式/TTL（NEED_INFO） | 待接口 |
| C SG dispatcher 端到端 | GZ 传任务书，SG 本机校验+签发+调用 | 缺 dispatcher 接口（NEED_INFO） | 优先目标态 |

关键判断：不能拿现有 `KB_GATE_TOKEN` 顶替——GZ 文件把它作为知识库闸 token 附加进 prompt；
SG R6 消费的是环境变量 `TASK_GATE_TOKEN`（`--task-gate`），用途和传输面不同。

## 部署清单要点（codex 出，Hermes 执行）

- C1（广州机）：先 md5sum 核对基线（2b65d893）→ 备份 .bak-c1-20260823 → git apply/scp 补丁 →
  bash -n → 复核新 MD5（f592f5e9）。不整文件重写，只改 156-163 行小段。
- C2（新加坡机）：只更新 `/home/ubuntu/.hermes/guard/hashes/execute_api.py.md5` 基线
  c97a3794→de78ce5d，**不回滚代码、不放宽校验脚本**；文件属主 ubuntu 无需 sudo（第一次用
  sudo 被密码挡，改普通权限版成功）。
- 探针验证（零付费）：
  1. 无 token 直调 gate → 期望 rc=2 BLOCKED（证明 R6 默认强制仍有效）
  2. 豁免+SKIP_REASON+非法 workdir → 期望 rc=1 且报 WORKDIR 不在白名单（证明豁免只到后置校验）
- 收尾：DEPLOY_RECORD.md 追加部署表（动作/结果/备份路径/遗留项）。

## 遗留

- 临时豁免到期条件 = task token 签发/dispatcher 接口完成（B/C NEED_INFO）。
- GZ `--search`/`--gen-img` 两条 shortcut 不走本闸（既有 R6 绕行入口），迁 dispatcher 时一并收口。
- DS 兜底链未动：GZ_codex_ds_fallback.sh 走 sg_ds_invoke.sh，不进 codex_exec_gated.sh；
  修复前 token BLOCK 文本不匹配 `usage limit|quota exceeded|rate limit`，所以不会触发 DS fallback。

## 后续（2026-08-23 同一会话）：用户拍板 B→C，C 方案出产（REPAIR_C1_C.md）

**用户指令链**：方案 A 部署后用户说「用b方案」→ Hermes 核实 B 的三个 NEED_INFO（签发接口=kb_token_issue.sh、白名单=^[0-9a-f]{32}$、注入方=广州自签）并发现双花冲突（见 gate-token-passthrough reference）→ 派 B 打包 → 用户问「bc.方案有什么区别」后拍板「那就c」→ 用户说「把b停下来」= 显式授权 kill 已提交的 B 任务（立即 kill + 残留检查）→ 派 C。**codex 明确判：B 与 C 不并存，B 会把 task token 再跨 SSH 交给广州，反向扩大凭据暴露面。**

**C 方案架构（三文件最小补丁，不能只改广州第 161 行）**：
1. **为什么不能只改广州**：dispatcher 的 codex 分支把 `--` 后第一个 argv 当 prompt；只改广州=在 SG shell 执行 `"$(cat brief)"` 会重引 shell/argv 边界 + ARG_MAX；且 SG 本地不存在广州 /tmp/projects/ 目录，SG 知识库闸读不到项目 guard/kb_checked.json——这是当初设计 KB 放行 token 的原因。
2. **广州侧**（GZ_codex_remote.sh 253→310 行）：保留 kb_gate_hard.py（SG 读不到广州目录，删了=KB 校验降成自我声明）+ gz_brief_gate_check.sh（发送前预检）→ 完整任务书写 0600 临时文件 scp 到 SG → SSH 调 SG dispatcher。**删除 147 行远程签 KB token 逻辑**（不再往 prompt 追加 token）。
3. **SG dispatcher**（hermes_task_dispatch.py 193→303 行）新增：`--prompt-file`（与 --brief 指向同一文件，防 gate 检查内容≠执行内容）、`--workdir`、白名单化 `--codex-arg=`、`--trusted-remote-kb-pass`（显式带 + target=codex + brief=prompt-file 同文件 + PROJECT_DIR basename 与 --project 一致 + brief 不含行首旧式 KB token 键才本机签 KB token）。
4. **SG codex gate**（codex_exec_gated.sh 163→225 行）：task token 与 KB token 都只经本机环境变量传递（TASK_GATE_TOKEN/KB_GATE_TOKEN + PROJECT 绑定），消费后 unset、成功不回显 token ID、失败输出 32 位 hex 脱敏。
5. **部署顺序铁律**：SG dispatcher → SG gate → SG 无付费探针 → 才部署 GZ。广州先上会因 dispatcher 不认识新参数失败；只上 SG 不启用 C。
6. **端到端验证**（会真调 codex）标注「仅 Hermes 获准后执行」，本次没碰；本地 11 项 mock/负例 PASS + 3 个非付费探针。
7. **确定遗留**：--search 仍直连 SG codex（不走 dispatcher）——不能谎称「所有 codex 调用已统一过闸」；--gen-img 入口契约 NEED_INFO。
8. **回滚分级**：首选仅回滚广州到方案 A（f592f5e9，SG 新接口向后兼容）；SG 成对回滚先 gate 后 dispatcher；回广州原基线 2b65d893 不能当恢复手段（无票+旧退出码 bug，R6 下必挂）。
