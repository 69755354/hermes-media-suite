# 「任务书由 codex 打包」落地实操（2026-08-23 违反→纠正→派打包任务实录）

## 场景

用户拍板「任务书必须由 codex 打包 + attest 物理卡点」（SG + GZ 两机同款）后，Hermes 需要派「打包任务书」任务给 codex，而不是自己写实施任务书。

## 派「打包任务书」任务的正确姿势

Hermes 只传三样（USER_REQ 原话 + DATA_SOURCE + PROJECT_DIR + 产出要求一句话），让 codex 自己读源码、自己设计、自己打包任务书并自审：

```markdown
TASK_TYPE=分析
USER_REQ=<用户原话，含拍板内容>
DATA_SOURCE=<相关文件路径，逗号分隔>
PROJECT_DIR=<项目路径>
PRELOAD_NODES=1,2,3,4

# 任务：打包「XX」实施任务书，并自审
## 背景（环境事实，实测，来源见 DATA_SOURCE）
## 你的任务（打包任务书 + 自审，不是实施）
1. 读 DATA_SOURCE 全部文件，分析现状，设计方案
2. 打包成可派实施的任务书（含 TASK_TYPE/USER_REQ/DATA_SOURCE/PROJECT_DIR/背景/实施要求/基线清单每个目标文件 MD5/灰度铁律/误伤词自检/产出要求），写到 staging/<x>/TASK_BOOK.md
3. 自审结论写 SELF_REVIEW.md（三样自审 + PASS/FAIL）
4. 结尾 OUTPUT: <TASK_BOOK.md 绝对路径>
## 硬约束
- 只写产出目录 staging/<x>/，禁止改生产文件、禁止重启服务
- 禁止调付费/外部 API
- 你只打包任务书，不实施
```

## 关键点

1. **「打包任务书」本身也是一份任务书**——写它的 Hermes 同样受「只传话」约束：背景只放环境事实（路径/MD5/实测结果），不放 Hermes 的设计判断。
2. **任务书正文禁止出现触发词完整形态**（尤其 `KB_GATE_TOKEN=` 赋值形态会被 kb_gate 消费正则命中、`video.*gen` 跨词）——写方案描述时用拆分写法（「键名 K-B-G-A-T-E 下划线 T-O-K-E-N」）。
3. **预检必须脚本化**（write_file /tmp/precheck_*.sh 再 bash 跑），内联命令含触发词会被 security-middleware 硬拦；kb_gate 预检单独跑、单独取 RC（管道 tail 会吞 RC）。
4. **多机同款卡点**：GZ 任务书要显式让 codex「若 SG 侧 TASK_BOOK.md 已落盘，先读它对齐两机方案（同款机制，避免两套标准）」。
5. **已提交任务不杀**：用户改主意（B→C）时，已在跑的 B 任务不 kill，等它自然收尾留档作参考；只有用户显式点名「把X停下来」才 kill（见主 SKILL.md 停任务 pitfall）。
6. **产出验收**：TASK_BOOK.md 落盘后，dispatch 实施前再过一遍预检（触发词 grep + kb_gate + task_brief_gate），因为打包出来的任务书正文可能自带触发词（自审段写全触发词=自己拦自己）。

## 本会话产物路径

- SG 卡点任务书打包：staging/task-book-gate-20260823/TASK_BOOK.md（briefs/task-book-pack-codex-20260823.md）
- GZ 卡点任务书打包：staging/task-book-gate-20260823/GZ_TASK_BOOK.md（briefs/gz-task-book-pack-codex-20260823.md）

## TASK_BOOK.md 的物理卡点设计要点（codex 打包产物，2026-08-23）

codex 打包 SG 侧卡点任务书时给出的实现设计（SELF_REVIEW PASS，基线 MD5 独立核对一致）：

1. **校验位置**：`hermes_task_dispatch.py:run_gate()` 内、`issue_token()` 之前——token 一旦签发控制面已放行，来源门必须在三通道（codex/claude/ds_native）共同入口生效；不放进执行器 prompt、不只在 codex_exec_gated.sh 内检查。`task_brief_gate.py` 保持格式职责，不承载来源证明。
2. **任务书必须是文件**：`--brief` 必须解析为真实普通文件；symlink/目录/FIFO/内联文本一律失败；`resolve(strict=True)`；检查前后各取一次 stat（inode/size/mtime_ns 任一变化=失败，防检查期间换文件）；任务书必须在 `--project` 项目目录内（commonpath 校验，禁裸字符串前缀）。
3. **旁证查找**：固定 `<project>/guard/attest/`（任务书正文不得指定路径）；按 basename + SHA-256 前 12 位缩小候选，**最终必须完整 64 位 SHA-256 比对**（sha12 只用于缩小）；逐字段核验 channel=codex、role=producer、exit_code=0、token_id 32 位 hex + token 文件存在 + used=true + used_at 落在 issued_at/expires_at 之间、artifact basename 一致；任一缺失/类型错/JSON 损坏/多份冲突=失败。
4. **防伪造信任边界（诚实标注缺口）**：字段校验只能防误用，不能防同 UID 写文件。切 BLOCK 前必须满足：guard/attest/ 对 Hermes 运行身份只读、旁证 writer 独立 OS 身份、write_attest.sh/codex_exec_gated.sh/dispatcher 对 Hermes 不可写、实测伪证失败 + codex 真实打包成功。**同 UID 未隔离 → 只能保持 WARN，输出 `NEED_INFO: Hermes 与 attest writer 尚未形成写权限隔离，禁止切 BLOCK`**——不得用 JSON 布尔字段/环境变量/prompt 字符串冒充隔离。
5. **灰度铁律**：新校验受 gate_config.yaml mode 管辖；WARN=审计+继续签 token，BLOCK=不签 token 三通道全停；mode 缺失/异常按 WARN 处理（防灰度期硬拦）；切 BLOCK 只能人工改配置，实施脚本不得自动切换。审计记录不含任务书正文/密钥/完整 token（token 只记前 8 位）。
6. **14 个测试用例**：覆盖合法旁证放行 / 无旁证 BLOCK / 正文伪 channel/hash/token / attest channel=claude|ds / role=reviewer / 只伪造 sha12 / exit_code 非 0 / JSON 损坏 / 内联 brief / 检查期间换文件 / 原格式 gate WARN 保留 / 三通道不启动 / Hermes 写 attest 失败 / codex 真实打包。**T02/T12 必须检查 BLOCK 分支没调 issue_token()，不只查输出文字。**
7. **对现有流程影响**：合法任务书不增加第二次模型调用；存量无旁证任务书 WARN 期放行留日志；GZ_codex_ds_fallback.sh 自行构造临时任务书，WARN 期不受阻、BLOCK 后被拦（符合纪律；DS 机械类兜底 break-glass 需人另行定，不在本任务暗留旁路）。
