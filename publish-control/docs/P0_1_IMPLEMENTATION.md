# P0-1 实施报告

已在 `/tmp/publish-plan-validation/bot` 完成机器人发布结果层整改与隔离自测。产物可交独立复核，不能据此认定全量验收通过或获准部署：专项 129 项通过；全量仍有 9 项基线失败、3 项跳过。本报告由实现者提供，不是独立终审结论。

## 交付物

- `p0_1_result_contract.patch`：仅修改 `bot.py` 的 unified diff，以机器人目录为根用 `patch -p1` 应用。
- `fix_evidence_p0_1/tests/test_mt_result_contract.py`：新增专项测试；同目录附完整隔离测试及 fixture。
- `fix_evidence_p0_1/bot.py`：实际测试的完整源码；附两个原有签名辅助模块。
- `fix_evidence_p0_1/pytest-p0-final.txt`、`pytest-full-final.txt`、`pytest-baseline.txt`：原始测试输出。
- `fix_evidence_p0_1/test_exit_codes.json`、`baseline_exit.json`、`patch_check.json`、`verification.json`：退出码、补丁校验与源码哈希。

## 执行边界

完整读取 `BRIEF_p0_1_20261028.md`、方案 4.1、两项目 CONTEXT，并读取机器人源码及客户机 `remote_ops.py` 既有只读快照。只复制 Python 源码和测试到隔离目录，没有复制生产 `.env`、运行状态或密钥。

未部署、未重启服务、未发聊天消息、未发布或重发、未对客户机执行操作，未连接或修改生产数据库，未修改既有账本或删除记录。生产 `feishu_publish_bot/bot.py` 在交付时与初始快照逐字节相同。项目 CONTEXT 仅补充本轮可复用的隔离与结果契约约束，没有将补丁描述为已上线。

任务书给出的 `remote_pc.py ... read` 并非数据库无副作用操作：其 `enqueue()` 调用 `/api/remote/exec`，服务端会新增远程请求及结果记录。为服从“不动生产数据库”的明确边界，本轮未执行该命令，改读现存 `/tmp/plan_review_remote_ops_20261028.py`（2026-10-28 11:05 的本机副本）。其 SHA256 为 `77095dca4e67a7bf3b2cb4af496323ba97af438e9b99d6c3a7adef58379e0a19`。不能据此证明客户机代码此刻仍完全相同。

## 根因定位

以下 B 行号指未修改的生产源码 `/home/ubuntu/workflow/projects/feishu_publish_bot/bot.py`；R 指上述客户机快照。

| 位置 | 根因与后果 |
|---|---|
| B:4910–4922 | 用 `exit_code == 0` 与 `published` 做 OR，覆盖显式 false；成功消息先于批次状态落盘。 |
| B:3711–3749 | 账本 content_hash 使用 key 子串；receipt、plan_id、command_id 可互相替代；只认 publish_confirmed，漏掉 CONSUMED/create_v2。 |
| B:4956–4996 | 发送前先写内存 seen，发送错误可能被后续持久化；只读最近 50 条命令。 |
| B:2195–2220 | SDK 返回非成功仍正常返回，调用方无法把“已尝试”与“送达确认”区分。 |
| B:2141–2165 | 全局最近成功时间戳放行任意成功文案，不能绑定客户和命令。 |
| B:6567–6571 | import 即启动调度线程，普通测试导入不安全。 |
| R:533–545 | `bool(parsed.get("published"))` 会把字符串 `"false"` 当 true；空输出兼容受双开关约束。机器人必须同时检查原始嵌套/输出字段，不能再无条件扩大 exit=0 契约。 |

## 实现方式

1. **统一归一化。** 新增 `_mt_normalize_result`（交付源码约 4822 行），同时检查外层、嵌套结果和 stdout JSON；严格接受布尔值与整数退出码。显式 false + exit=0、false + 强成功、true + 非零退出、命令身份不一致、UNKNOWN、提交开关冲突、作品号与账本冲突均归为 `needs_reconcile`，记录冲突字段来源。无冲突的 false/非零退出为失败；证据不足为待核实，不自动发布重试。
2. **保留空输出兼容。** 缺显式字段、空 stdout、exit=0，且命令是本客户有 ID 的 publish/confirm、payload 两开关严格为 true、receipt 为 approved_publish 并有 content_hash/receipt_id 时保留成功分支。未知协议版本、非空未解析输出或缺少这些前提不放行。没有修改客户机协议或发布执行链。
3. **账本精确绑定。** `_mt_match_evidence`（约 4795 行）按 customer + content_hash + receipt_id 匹配；不接受子串、旧 receipt 或 plan/command 替代匹配。支持 `publish_confirmed=true + success_toast` 与 `CONSUMED + publish_evidence.ok=true + create_v2`。存量账本不含 customer_id 时，客户身份由经过 chat 绑定校验的客户专属读取通道提供；若条目自身有 customer_id，必须一致。函数只读，不修整 SUBMIT_INTENT、CONSUMED 等状态。
4. **持久化先行。** `_mt_store_result` → `_mt_apply_result` → `_mt_prepare_notification`：结果先写入 `MT_RESULT_STATE.results`，flush/fsync、原子替换并 fsync 父目录，再更新批次并创建独立通知记录。重启可从已存结果补建通知，重试不再读取账本或执行发布。失败与冲突暂停剩余条目；已消费素材仅在明确失败分支保留原“确认重发”入口，冲突分支不创建重发候选。
5. **通知可靠性。** 通知键由 customer、command_id、chat_id、通知类型确定，并作为 SDK `uuid`。通知状态区分 pending/sending/uncertain/sent/binding_changed/needs_reconcile；只有明确 SDK 成功回执才置 sent 和 seen。发送前复核会话绑定。响应丢失保留 uncertain，后续只重发同一通知；首次发送超过本地一小时自动重试期限后转待核实，不盲目重复。该期限是本地保守限制，不构成端到端 exactly-once 保证。
6. **结果文案。** 缺作品号显示“已提交，平台作品号暂未返回”，不拿 video_id 代替；review_status 独立为 unknown/reviewing/approved/rejected，退出码不推导审核状态。进度显示待核实数量，不把其列为下一条待发。状态更新入口共用归一化结果。
7. **模型事实边界。** 删除成功文案校验对全局时间戳的依赖；多客户自由对话 fallback 使用确定性提示，发布事实由命令结果或绑定批次进度渲染。LLM 解析与文本输出边界继续过滤成功声明；全局时间戳不再授权文案。
8. **旧命令补查。** 当前服务端 `server.py:871`、`:1244` 的列表固定 50 条且忽略分页参数。未修改控制面；机器人对本地客户/会话批次内的 command_id 逐一 GET 补查，覆盖已跟踪发布被挤出最近 50 条的情况。未声称实现服务端分页。
9. **导入安全。** 将模块级调度线程启动移至 `main()` 的单实例锁之后。生产环境初始化方式不变；隔离测试不调用 main。

## 测试证据

在指定隔离目录运行，真实网络 connect/bind、线程 start 和生产文件读取由 conftest 拦截；签名使用临时合成种子；状态全部指向 pytest 临时目录。确认没有导入生产 bot/server 模块。已有两个 HTTP 集成用例改成控制面 mock，未启动测试 HTTP 服务；单个旧异步用例改用同步线程替身。计划构造用例仍执行临时素材上的本地 Python 子进程，不调用客户机。

专项命令：

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_mt_result_contract.py
129 passed in 0.42s
exit_code=0
```

任务书指定全量命令：

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/
9 failed, 200 passed, 3 skipped in 1.90s
exit_code=1
```

原始 bot 源码放回同一隔离目录、保留相同安全测试适配后对照（最后已恢复整改源码）：

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/ --ignore=tests/test_mt_result_contract.py
9 failed, 71 passed, 3 skipped in 1.36s
exit_code=1
```

两轮 9 个失败 node ID 一致：5 项计划脚本 `NameError: title_from_file is not defined`；2 项旧单客户取消状态预期失败；2 项旧话题交互预期不符，其中数字“1”已走其他队列入口并被隔离网络拦截。均未扩展修复到 P0-2/旧单客户工作流，也未通过修改断言、xfail 或跳过这些失败让全量变绿。

3 项跳过为：客户端 `winport` 源码路径不存在导致两份签名/客户端契约测试模块无法收集；旧 ledger helper 用例也因客户端源码缺失跳过。没有使用生产私钥或换用未经核验的客户端版本填补缺口。

专项覆盖包括：90 组 true/false/缺失 × exit 0/2/缺失 × 精确匹配/错 receipt/错客户/错 hash/无账本 × 两类成功信号；非布尔值；嵌套和多行 JSON 冲突；空输出兼容边界；缺作品号与审核状态；HTTP/SDK 明确失败和响应丢失；结果落盘后中断、磁盘失败；通知 UUID 稳定；会话改绑；本地重试时限；超过 50 条的已跟踪命令；跨客户成功时间戳。另以现存五条账本的脱敏结构 fixture 回放三条 SUBMIT_INTENT/success_toast 和两条 CONSUMED/create_v2，未改动原账本。

`test_dispatch_once_then_notification_retry` 实际调用隔离 bot 的 `_dispatch_mt_item`，只 mock 发布投递及凭据依赖；投递调用恰好一次，通知失败后批次已 published，排期器不再投递，恢复通知后调用数仍为一次。SDK builder 使用本地安装版本实测 uuid 字段，消息接口完全 mock。

补丁已在 `/tmp/publish-plan-validation/apply-check` 的原始源码副本完成：正向 dry-run、实际应用、反向 dry-run，三者 exit=0；应用后的源码与测试源码逐字节一致，并通过 compile。生产源码 SHA256：`ee1bbf5e765633cd89fc61a81c59c02f6ec587c911d57db3257a466999452b31`。完整哈希见 `verification.json`。

## 未覆盖边界与复核事项

- 全量非绿及上述客户端签名测试缺口仍未关闭，不能宣布全量验收通过。
- 没有飞书真实 HTTP/SDK 联调、长期宕机恢复或平台去重时效实测；SDK 成功仅表示服务端接收确认，不证明用户已阅读。超过本地重试时限需要人工核对消息送达情况。
- 本次持久化 outbox 覆盖 **publish/confirm 终态结果通知**。准备确认卡和其他指令仍沿用原工作流，只改善 SDK 明确失败传播；不宣称这些通知都已具备持久化 outbox。
- 补查保证本地批次已记录的发布命令不被 50 条列表上限饿死。没有本地批次记录、且已滑出列表的历史命令仍需要后续控制面分页/游标接口；本轮没有修改 server.py 或数据库结构。历史 seen 也不会被强行清空重播。
- 客户机 remote_ops 协议版本/evidence_source 字段未改；机器人以可选字段兼容。客户机字符串布尔转换风险由机器人检查嵌套原始字段兜底，客户端自身修复仍需另行补丁与批准。
- 结果与通知目前保存在同一原子 JSON 文件的不同字典中，未做长期归档/分片；大量历史状态的体积与 fsync 开销未压测。文件损坏会失败关闭，不自动重置或重发。
- 旧单客户发布判定和无调用的危险恢复 helper 不在本次整改范围；不得因本补丁绕过既有人工恢复限制。
- 未做独立终审。复核重点：客户专属 ledger namespace、缺字段兼容前提、原有重发确认入口、通知不确定状态、控制面分页缺口及原有基线失败的处置。

## 部署步骤（仅供批准后执行，本轮未执行）

1. 独立复核 patch、专项证据及基线差异；人工决定是否接受已列边界并批准维护窗口。确认无在途发布，盘点待发送通知及批次。
2. 在另一个隔离目录以待部署版本做 `patch --dry-run -p1 -i .../p0_1_result_contract.patch`；生产 bot 若不再符合上述哈希，先重新评估差异，不强制套用补丁。
3. 批准后备份机器人源码及机器人自身结果/批次文件，保持签名密钥原位；不备份恢复式覆盖 control.db 或任何客户账本。
4. 由获授权运维在批准窗口应用补丁并通过既有单实例服务流程切换。禁止另起手工后台 bot。本报告不授权停止、重启、发布或客户机操作。
5. 核对既有 pending/uncertain 通知、客户绑定及人工待核实项。观察经另行授权的正常业务结果；不得为验收重发历史五条素材或删除账本。

回滚：只在人工批准、无在途任务且评估状态兼容后恢复原 bot.py；反向 patch 已在临时副本 dry-run 成功。保留 results、notifications、seen 和批次状态，不删除不确定记录，不恢复旧数据库/账本。旧代码不理解新增通知状态时应暂停相关批次、人工核对并前向修复，不让旧误判继续运行；通知恢复不能转成发布任务重跑。

OUTPUT: /home/ubuntu/workflow/projects/publish_control/P0_1_IMPLEMENTATION.md
