# 任务书物理卡点设计（2026-08-23 codex 打包定案）

> 触发：派活前打包任务书、排查「Hermes 越权写任务书」「任务书作者无物理校验」。
> 关联：task-brief-gate「违反实录 + 物理卡点方向」节。

## 事故链（用户两次抓包）

1. 用户「让codex处理」C1/C2 修复 → Hermes 连写 B/C 两份详细任务书（背景分析、设计问题清单、硬约束全自己写）
2. 用户点破「你不是只负责传话吗？怎么任务书还是你写」
3. Hermes 承认「能违反，因为规则没有物理卡点」→ 用户「你还是能违反规则？」拍板物理化
4. 用户「跑」→ 派 codex 打包实施任务书；「广州的也要这么改 只传话」→ GZ 侧同款

根因：task_brief_gate/kb_gate 只校验任务书**内容格式**（TASK_TYPE/DATA_SOURCE/约束词），不校验**作者**——Hermes 自己写的和 codex 打包的在闸眼里一样。字符串标记零防御原则同样适用：光加「author=codex」标记没意义，执行器能伪造。

## SG 侧设计（TASK_BOOK.md，codex 打包自审 PASS）

### 校验位置
- `hermes_task_dispatch.py` 的 `run_gate()` 内、`issue_token()` **之前**——token 一旦签发控制面已放行，来源门必须卡在所有 target 共同入口
- 顺序固定：读任务书文件算 SHA-256 → task_brief_gate 格式检查 → 读 gate_config mode → 来源检查 → PASS/WARN 才解析 route → issue_token → 启动执行器
- 不得放到执行器 prompt 内、不得延后到 issue_token 之后、不得只在 codex_exec_gated.sh 内查
- task_brief_gate.py 保持格式职责，来源检查归 dispatcher（不把文件系统信任边界混入可接收纯文本的格式 gate）

### 任务书必须是文件
- `--brief` 必须解析为真实普通文件；symlink/目录/设备/FIFO/内联纯文本一律来源检查失败
- `resolve(strict=True)`；重算 SHA-256 读文件字节不重新编码
- 检查前后各取 stat：inode/size/mtime_ns 任一变化即失败（防检查期间换文件）
- 任务书必须位于 `--project` 解析出的项目目录内，`os.path.commonpath` 校验，禁裸字符串前缀比较

### 旁证查找与字段核验
- 旁证目录固定从项目目录推导 `<project>/guard/attest/`，任务书正文不得指定旁证路径
- 按任务书 basename + SHA-256 前 12 位缩小候选，但最终必须解析 JSON 逐项核验：
  - 普通文件、非 symlink
  - `artifact_sha256` == dispatcher 对任务书字节重算的完整 64 位 SHA-256（sha12 只缩小候选）
  - `channel` == codex、`role` == producer
  - `exit_code` 归一化后 == 0
  - `token_id` 匹配 32 位小写十六进制；token 文件存在、JSON 合法、`used=true`、`used_at` 落在 issued/expires 之间
  - artifact basename 与任务书 basename 一致；接受项目内移动同一字节文件，不接受跨项目旁证
  - 任一字段缺失/类型错/JSON 损坏/多候选冲突 = 失败

### 防伪造信任边界（切 BLOCK 前置条件）
1. `guard/attest/` 及其父目录对 Hermes 运行身份不可写（只读）
2. 旁证写入进程用独立 OS 身份（非 Hermes、非 Codex sandbox 内进程）
3. write_attest.sh / codex_exec_gated.sh / dispatcher 生产文件对 Hermes 不可写
4. 旁证 writer 调用权限不能让 Hermes 绕过真实 Codex 执行直接提交任意 artifact
5. 实测：id/namei/stat/getfacl 输出记录；Hermes 身份写伪旁证必须失败；Codex 壳真实打包必须成功

同 UID 无法防伪 → 只能 WARN，输出 `NEED_INFO: Hermes 与 attest writer 尚未形成写权限隔离，禁止切 BLOCK`。不得用 JSON 布尔字段/环境变量/prompt 字符串/普通 shell 命令冒充隔离。

### 灰度铁律
- mode WARN：来源失败写结构化审计，继续签 token 执行，不改现有退出码
- mode BLOCK：来源失败不调 issue_token，三种 target 全部不启动
- mode 缺失/不可读/非法值：按 WARN 运行 + 记 MODE_INVALID（防新功能灰度期意外硬拦）
- 切 BLOCK 只能人工改配置，实施脚本不得自动切

### 建议原因码
TASK_BOOK_NOT_FILE / TASK_BOOK_OUT_OF_PROJECT / TASK_BOOK_CHANGED_DURING_CHECK / ATTEST_NOT_FOUND / ATTEST_MALFORMED / ATTEST_HASH_MISMATCH / ATTEST_NOT_CODEX_PRODUCER / ATTEST_TOKEN_INVALID / ATTEST_TRUST_BOUNDARY_WEAK

### 审计记录
UTC 时间、project、任务书真实路径、完整 SHA-256、attest 候选路径、结果、原因码、mode、是否签 token。不得记录任务书正文/密钥/token 完整内容（token 只记前 8 位）。

### 测试用例（14 项）
T01 合法旁证放行 / T02 无旁证 WARN 记日志 BLOCK / T03 正文伪 channel/hash/token 文本但无旁证 / T04 channel 为 claude/ds / T05 role 为 reviewer / T06 只伪造文件名 sha12 / T07 exit_code 非 0、token 格式错、未用/双花 / T08 JSON 损坏、symlink、目录穿越 / T09 --brief 内联文本/FIFO/symlink / T10 检查期间任务书变化 / T11 原格式 gate WARN 保留原 WARN / T12 来源失败三 target 均不启动 / T13 Hermes 身份写 attest / T14 Codex 壳真实打包。T02/T12 必须检查 BLOCK 分支没调 issue_token，不只查输出文字。

## GZ 侧设计（GZ_TASK_BOOK.md，codex 打包自审 PASS）

### 权威校验点
放 SG dispatcher（codex/claude/ds_native 共同签票点），广州本地只做非权威可用性预检。**禁止在 GZ shell 用 grep/jq/文件名规则复刻简化 validator**（第二套规则=维护噩梦+不一致）。

### 独立 packager 入口（防启动闭环）
- 新增 SG 受限入口 `codex_task_book_packager.py`（NEW）
- 只接受传输信封：USER_REQ / DATA_SOURCE / OUTPUT_REQUIREMENTS / PROJECT_BINDING / REQUEST_ID
- 固定动作：拒绝内联 prompt/symlink/FIFO/越界路径 → 信封作为数据交固定系统提示的 Codex 打包任务（小鹿不得追加分析/方案/步骤/gate 声明）→ Codex 只能向固定请求目录写一个 TASK_BOOK.md（输出路径不能由信封指定）→ 壳外 writer 写 producer attest（writer 失败=打包失败）→ 只返回结构化结果+任务书路径，不返回 token
- 建议 spool：`/home/ubuntu/workflow/task_book_spool/gz/<project>/<request_id>/{envelope.json,TASK_BOOK.md,guard/attest/}`
- 收窄入口而非 TASK_GATE_ENABLED=0：固定程序/系统提示/输出文件名/可写目录；禁止 --search/--gen-img/任意 -C/任意执行器参数/任意输出路径；packager 身份不能写 dispatcher/gate/writer/token/attest 目录

### 与 SG 同款 attest 一致
广州任务书不定义第二种 JSON；必须调用 SG 同款 validator 逐项核验（完整 SHA-256、channel=codex、role=producer、成功退出、basename/项目/token/时序、非 symlink、检查前后 stat 一致、实际交付已校验字节快照）。

### 广州 wrapper 接线
```
解析用户传话信封 → 广州 kb_gate_hard.py（保留）→ 上传信封至 SG packager 受控 inbox
→ 调 SG packager → 取得 SG 内 TASK_BOOK.md 路径
→ 调 SG hermes_task_dispatch.py --brief <该路径>
→ SG attest gate PASS/WARN 后签票并执行
```
- 不得继续把小鹿拼出的完整 prompt 当任务书上传
- gz_brief_gate_check.sh 可 WARN 期保留作兼容对账，但其输入改为 Codex 产出的任务书，返回不能覆盖 SG 的 BLOCK
- --search/--gen-img 是已核实旁路：BLOCK 前二选一（纳入统一链 or 广州 wrapper 明确拒绝+给迁移入口），只修 generic 不收 shortcut 不得切 BLOCK
- DS 兜底：GZ_codex_ds_fallback.sh 不再自行 cat 生成任务书；只接受已由 Codex 打包并通过 SG attest 的任务书引用；codex 额度失败允许白名单机械类复用同一任务书走 ds_native；打包阶段 codex 不可用=无合法任务书，DS 不得代打包；producer 记账只在 DS 真成功后写

## C 方案衔接（广州改走 SG dispatcher，REPAIR_C1_C.md）

三文件最小补丁：GZ_codex_remote.sh（删方案 A 豁免）+ SG_hermes_task_dispatch.py（新增 --prompt-file/--workdir/--codex-arg=/--trusted-remote-kb-pass）+ SG_codex_exec_gated.sh（双 token 本机环境消费，成功不回显、失败 32 位 hex 脱敏、进 sandbox 前 unset）。部署顺序铁律：SG dispatcher → SG gate → 无付费探针 → GZ。B 方案与 C 不并存（B 把 task token 跨 SSH 交给广州，反向扩大凭据暴露面）。

## 部署前补采（codex 标记 NEED_INFO，不能拿 staging 冒充）
- 生产 task_brief_gate.py / write_attest.sh / gate_config.yaml 的 MD5、owner、mode、ACL
- 切 BLOCK 前权限隔离实测
- --search/--gen-img 收口决策
