---
name: dispatch-return
description: Operate the local durable dispatch_return queue, receipts, recovery and result notifications on SG or GZ; diagnose accepted jobs without bypassing execution or delivery gates.
metadata:
  legacy_id: dispatch_return
  runtime: /home/ubuntu/workflow/projects/dispatch_return/runtime/dispatch_return.py
---

# Local dispatch and return

## 派活必做两道（缺一即白等）
1. **brief 必须用 `/home/ubuntu/workflow/scripts/make_brief.py` 编译**（`--task-type <合法类型> --project <abs> --request-file <手写内容> --output <cbrief-*.md>`），submit 的 `--brief` 指向**编译产物**。手写 brief 直接 submit 会先返回“已受理”，再在 intake 静默失败：`{"state":"failed","error":"missing marker: USER_REQ="}`——三个单白排（已踩）。
2. **submit 后 ~25 秒查一次 `status <jobid>`**：`running` 才算真进执行；`failed` 立刻看 error、重编重派（复用同一 request_id 会报 `already used for a different task`，换新 id）。


Runtime: `/home/ubuntu/workflow/projects/dispatch_return/runtime/dispatch_return.py`.
Its adjacent `config.json` selects allowed profiles, local task dispatcher and gate environment; this is distinct from `.hermes/context/config.json`. State lives in adjacent `state/<32-hex-job-id>/`.

Use this for local queue operations. Cross-machine model execution must retain its original gated channel; this runtime does not provide a cross-machine receiver. Do not enable a dispatcher, change gate switches or restart gateways merely to make a task run.

## 失败告警看门狗（2026-10-04 用户当场要求「任务没发出去你都不检查的吗，隔个10分钟就去看一下」）

`scripts/failure_watchdog.py` + crontab `*/10`（flock `/tmp/dispatch_failure_watchdog.lock`）：扫 `runtime/state/*/status.json`，`failed|interrupted|send_unknown|blocked|error`、`accepted` 超 15 分钟未执行、`running` 超 3 小时，去账本 `/home/ubuntu/.hermes/state/dispatch_failure_alerted.json` 后 `hermes send` 推用户 DM。首次上线用 `--init` 登记存量再装 cron，否则会把历史失败全推给用户；`--dry-run` 只打印。

为什么必须有：gate 拒绝只写 `status.json`（`failure_to` 是运营通道，不通知派活人），提交回执只说 accepted —— 「任务根本没跑起来」在用户问之前不会有任何信号。历史存量 118 个作业里 42 个是 failed/interrupted，全是静默丢掉的。

## 执行器沙箱只看得到项目目录（2026-10-07 实测踩坑）

派 `task` 模式时执行器沙箱**只挂载项目目录**：项目外的共享包、上游项目、`/tmp` 一律不可见。实测后果——任务书让执行器读 `shared/huolong/`、另一个项目目录、`/tmp/数据包.md`，一条都读不到，直接写一份 BLOCKED 报告收工：**rc=0，但零产出**。

派活前把执行器要用的东西**全部拷进项目目录**，任务书里只写项目内相对路径：
- 复用包/脚本/模板（如 `shared/huolong/{render_final.py,rulings_source.py,plan_模板*.json}`）→ `<项目>/work/records/`
- 上游素材、台词分镜、角色场景图 → `<项目>/source/`、`<项目>/assets/`
- 需要的工具（ASR 脚本等）一并拷入；缺 ffprobe/tesseract 可让执行器自行补装并写进报告

`make_brief.py` 拒绝覆盖内容不同的 brief（`refusing to overwrite different brief`）→ 换一版就换输出文件名（`brief_..._r2.md`）。同 request-id 重提若报 `duplicate request_id ... will NOT run again`，按提示换新 id（`...-r2`）。

## 「跑完但零产出」必须报警（2026-10-07 用户当场骂「没成功也没发现」）

失败看门狗只覆盖 `failed/interrupted/...`；`awaiting_review + rc=0` 却**没有任何产物**的作业会漏掉（执行器只写了 BLOCKED 报告也算零产出）。交付看门狗要补一条：完成态 + 没抓到产物 → 扫 `execution.log` 的 `BLOCKED`/`NEED_INFO` 行，把最后一行原因随告警一起 `hermes send` 给用户，**禁止静默标记为已处理**。参考实现：`projects/huolong-30set-20261001/work/watch_batch_deliver.py`（已支持多项目、成品一次性合并发送）。

## 产物自动交付（2026-09-30 用户要求「做完了自动发，不要每次都要我问」）

机制：`/home/ubuntu/workflow/projects/dispatch_return/scripts/auto_deliver.py` + 每 3 分钟 crontab。

- 扫 `runtime/state/*/status.json`，`state ∈ {awaiting_review, completed, done, success}` 且 `rc=0`；
- 从作业目录的 `spec.json`/`input.json`/`brief-generation.json` 读 `project`，扫其 `output/**`；
- 未登记过的产物（账本 `/home/ubuntu/.hermes/state/auto_deliver_sent.json`）自动 `hermes send` 到用户飞书 DM：`.md` 先 pandoc 转 `.docx`，>19MB 只发提示（需手动传云盘）；
- 新增产物自动发，已发过的绝不重发；`--init` 只登记不发送（首次建账用）。
- 因此派活后**不要蹲守、不要等**；用户问进度才 `status` 查一次。

## 无人值守 cron 的「已上报」必须回读 message_id（2026-10-18 实测）

cron job 的 `deliver` 可能是 `local`（示例 job `976d7bc17582`）：最终回复只落 `~/.hermes/cron/output/<job>/`，**不进用户 DM**。此时把待拍板事项写进最终回复＝没上报，项目日志里会出现「已上报」但飞书里根本没有这条。

规则：
- 判定通道：查 `~/.hermes/cron/jobs.json` 该 job 的 `deliver` 字段；`local` ⇒ 最终回复不算送达。
- **回读/扫 DM 的时间窗一律用本地 epoch 直取**：本机 TZ 就是 CST，`time.mktime(time.strptime('YYYY-mm-dd HH:MM:SS'))` 已经是正确 epoch，**不要再减 8 小时**（减了会得到 8 小时前的窗口，产生「消息全部缺失」的假否定，已踩：回读 0/11 而实际 11/11 在位）。同理旧扫 DM 脚本里的 `-8*3600` 是错的，窗口整体偏移 8 小时。
- 真送达＝`hermes send --to feishu:<chat_id> --file <txt> --json` 拿到 `message_id`，再用 `im/v1/messages/{id}` 只读回读确认 `code=0 / deleted=false / 正文一致`（只认回读，不认 send 成功自述）。
- 上报完写 `work/logs/REPORTED_<事项>_<时间戳>.md`（含 message_id + 回读结论 + 待选方案），并回写旧 REPORTED 文件头指向新文件——否则每 15 分钟一轮的 cron 会重复上报。
- 决策类上报只发一次、一次性给全 A/B/C 和推荐项；发完不重发、不自行按某一项施工（改闸/改口径/二次交付仍属禁自行）。

## 完成态核验还要比「交付件 vs 全机最新口径」（2026-10-11 实测）

判「完成」的四件证据（队列无非终态、产物哈希对账、飞书回读 N/N、成片闸 MEASURED_PASS）**都证明不了交付件仍符合最新口径**：闸读的是项目内 `source/` 口径副本，口径改定后副本与闸判据会一起停在旧口径，旧件照样满分过闸。实测：10 条成片 10-06 按「免费类风险提示 4 句」交付且全过闸，10-09 口径改定「三类一律 5 句」（星图按优矩 5 行审核、免费类缺「0.3 元」行被全部驳回）——全机比对才发现 10/10 交付件仍是 4 句件，其中 4 条连 5 句版都不存在。

规则：完成态每轮在队列/哈希/回读之外加一条**只读**比对——`find <workflow> <skills> -name 'current-rulings-*.md' -printf '%T@ %p\n' | sort -rn | head` 取全机最新口径，与本项目 `source/` 副本 diff；有实质差异就逐件核「交付件落在旧口径还是新口径」（读各件 gate_report 的证据字段，别采信日志自述），结论上报人工拍板。**补口径虽不产生 API 费用（改后期叠加层重合成即可），但仍属二次交付、且通常要动项目口径副本或闸判据 ⇒ 撞「禁改闸、禁改口径表」纪律，不得自行修**。派活侧同理：拿旧口径期间产出的任务书重派前，先对齐最新口径。

## 接待回合：派完就回客服位，禁「跟任务」（2026-10-14 用户当场点名「你要回客服位啊，你现在又开始去跟任务了」）

规则：接待回合里把活派出去（submit 拿到 OUTPUT 回执）或把长活交接给后台后，**立刻回客服位**——只回一句
「已安排／已完成，完成后通知你」，然后结束本回合，不看进度、不轮询。

被点名的高发形态（都算「跟任务」，别做）：
- 连续 ssh/查日志/看进程来「确认它跑起来了」；
- 同一件事拆成十几轮来回验证（开窗→查窗口→再查窗口→截图→再截图）；
- 隔几分钟回头「再确认一下」。

例外只有一个：**用户明确问进度**时，允许查一次状态并回一句。

手动远程操作（改机、开浏览器、拉文件）的节奏也是「一段动作 → 一次回报」：做完必须做的验证就收手，
别把验证本身拖成一串轮询。用户看到连续多轮查状态 = 事故信号。

## Submission contract

Run `python3 <runtime> submit` with:
- `--request-id`: original message ID plus operation suffix; reuse exactly for retries.
- `--profile`: configured absolute Hermes profile path.
- `--to`: explicit `feishu:oc_...` optionally followed by `:om_...`.
- `--kind dm|group`; groups also require original `--requester ou_...`.
- `--mode probe|local|task` and mode inputs below.

The destination and chat kind must exist in that profile's `sessions/sessions.json`. Destination and requester come from the authorized request, never guesses. Submission can cause eventual Feishu notifications; obtain sending authorization before submitting.

Modes:
- `probe --seconds 45`: duration 10–300 seconds, verifies a deterministic 1 MiB artifact.
- `local --command-file <json>`: JSON has exactly `argv` (nonempty string array) and `cwd`. CWD must resolve under `/home/ubuntu/workflow/projects`. Supported executables are `/usr/bin/python3`, `/bin/bash`, `/usr/bin/bash`, `/usr/bin/sha256sum`, `/usr/bin/stat`, `/usr/bin/find`, `/usr/bin/du`. Existing node-entry guard still applies. Model/cross-machine commands are rejected; do not disguise them in scripts to evade the check.
- `task --brief <file> --project <directory>`: local paths must resolve under workflow or clients. Requires a configured independent gated task dispatcher. The executor target is codex; retain KB, task-brief, workflow and human gates.

A durable receipt means accepted, not executed, reviewed or delivered. On successful submission, report acceptance and end the dispatch turn; background units handle execution and notification. The key hashes profile, destination and request ID. A changed spec under the same key is rejected. If submission reports services unavailable after queueing, retain the same request ID; do not duplicate the job.

Rejected-then-fixed is the one case where the ID must change. After a gate rejection, editing the brief and resubmitting under the SAME request ID is a no-op: the queue keys on the request ID, rejects the changed spec, and still prints the acceptance line (state dir keeps its old timestamps, nothing runs). Fix the brief, resubmit with a NEW request ID (`...-r2`), then confirm real execution by reading `status.json` for `state=running` with a fresh `started` timestamp. The acceptance line alone is never evidence that a job is running. Also copy `READ_SKILL` from a previously accepted brief of the same TASK_TYPE — `gate_config.yaml` pins the exact value per type, and a self-composed value fails as `marker conflicts with config`.

## Read-only diagnosis and recovery

`python3 <runtime> status <job-id>` reads status without executing work. Inspect `spec.json`, `receipt.json`, `status.json`, `gate.json`, `execution.log` and `delivery.json` as applicable; avoid exposing private request content.

`worker`, `send`, and `tick` are service entrypoints, not read-only diagnostic commands. `submit` and `tick` start per-job units. Do not invoke them when service actions or sending are outside authorization.

Queued work is recovered by the timer. Worker locks prevent simultaneous execution; running or finished work is never automatically replayed. A lost worker becomes `interrupted`. Successful local/task execution becomes `awaiting_review`; only a successful probe becomes `completed`. Neither substitutes for independent review. A downstream rc=3 is recorded as failed with rc=3: preserve its manual-review meaning; do not claim approval.

Local commands are snapshotted and compared before execution; task briefs are hashed and rechecked. Changed inputs require a new authorized request ID. Never edit queue evidence to force acceptance.

Notification requires the existing send gate, correct profile and group requester mention. Delivery is confirmed only with success plus a message ID. `sending` left by an interrupted sender becomes `send_unknown`; inspect receipts before any retry. Never reset uncertain delivery state or blindly resend. Keep execution, review and delivery statuses distinct.

## Deterministic dispatch briefs (2026-09-14)

The local queue worker compiles every task input through `/home/ubuntu/workflow/scripts/make_brief.py` before handing it to the executor. The existing `--brief` input is an envelope: `TASK_TYPE=`, `USER_REQ=`, project binding, asset/data references and optional instructions. Missing or duplicate type/request fields fail explicitly. A TASK_TYPE that conflicts with the original request under the shared intent classifier is invalid compiler input and is rejected; this is not a change to skill_contract gate mode. Mandatory markers, constraints and preload declarations come from `gate_config.yaml`; applicable skill contract constraints come from the live skill registry. The template is `/home/ubuntu/workflow/scripts/templates/task_brief.md.tmpl`.

For raw requests, use:
```bash
python3 /home/ubuntu/workflow/scripts/make_brief.py --task-type 分析 --project /absolute/project --asset-ref '客户提供的记录' --request-file /absolute/request.txt --output /absolute/project/brief.md
```
`USER_REQ` is a JSON string so multiline original text survives without creating additional marker lines. The compiler decodes it on re-entry. `PROJECT_DIR` is the KB gate's binding marker; `guard/kb_checked.json` must already satisfy the real KB gate. The compiler never marks the KB read, invents attestations, consumes bypass tokens or changes gate modes. A blocked gate prevents publication; diagnostic output names missing markers or the blocking gate. WARN results remain WARN and are included in the returned gate report.

Self-check uses the real format gate at `/home/ubuntu/workflow/task_brief_gate.py`, `kb_gate_sg.py`, `skill_contract.py`, the dispatch package validator, and the same G07 adapter/trust boundary as `hermes_task_dispatch.py`. The separate `scripts/g07_brief_gate_check.py` additionally requires configured BLOCK mode; its WARN-configuration refusal is not proof that the live dispatch adapter blocks. No mode is automatically promoted. A compiled brief is a preflight result, not approval or proof of execution; downstream gates still run.

Preflight a task envelope before submitting: call `from_envelope` + `generate(..., output=<project-local temp>.brief.md)` from `scripts/make_brief.py` and require no exception. This runs the same format/KB/skill-contract/G07 gates the worker will run, so an intake failure is caught while the reception turn is still open. `READ_SKILL` is not free text: `gate_config.yaml` pins an exact value per `TASK_TYPE` (e.g. `出片` requires `READ_SKILL=seedance-2-0-mini-workflow,hyperframes`); any other value fails as `marker conflicts with config: READ_SKILL=...` one second after acceptance, and that failure is delivered only to `failure_to` (the operator channel), never to the requester channel. Copy the marker line from a previously accepted brief of the same task type instead of composing it from the skills you think the executor needs.

The worker snapshots the source hash, opens its `dispatch_<job_id>` ticket with `workflow_ticket.py open T-ORCHESTRA.INTAKE --project ... --session ...`, compiles to a project-local brief and then evaluates the original entry guard. Existing tickets are validated and never renewed or replaced to evade expiry or dependencies. The child inherits `HERMES_SESSION_ID`. Job state contains `ticket.json`, `brief-generation.json`, `gate.json` and `execution.log`; ticket/generation failure records a failed state and returns a nonzero worker exit. INTAKE does not close or approve any content node. Independent review remains required.
