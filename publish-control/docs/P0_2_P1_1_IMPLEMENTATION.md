# P0-2 / P1-1 隔离实施报告

已在指定隔离目录 `/tmp/publish-plan-validation/bot` 基于 P0-1 实施 P0-2、P1-1，交付相对未修改生产 bot.py 的累计补丁，包含 P0-1。专项 **190 passed**；全量 **7 failed, 263 passed, 3 skipped**。可交独立验收；全量未绿，不构成终审或部署授权。

## 交付与边界

- 累计补丁：`p0_2_p1_1_cumulative.patch`，以机器人目录为根 `patch -p1`；只修改 bot.py。
- 完整源码、61项新增测试、原测试与fixture、原始测试输出、退出码、哈希及补丁校验：`fix_evidence_p0_2_p1_1/`。
- 独立只读代码复核：`fix_evidence_p0_2_p1_1/INDEPENDENT_CODE_REVIEW.md`。实现与测试由同一owner完成，另有独立代码审查；无人代批人工门。

完整读取本轮任务书、方案4.2/4.3、P0-1报告、两个项目CONTEXT及相关源码/既有测试。只在隔离源码和本项目交付目录写文件；未部署、未重启服务、未操作客户机、未发布或重发、未发送飞书消息、未访问或修改生产数据库及账本。没有复制生产 .env、状态或密钥。客户机协议核对只读现存 `/tmp/plan_review_remote_ops_20261028.py` 快照，未通过 remote_pc/read 或实际远程API取数。

生产源码起止 SHA256 均为 `ee1bbf5e765633cd89fc61a81c59c02f6ec587c911d57db3257a466999452b31`；P0-1 基线为 `b13af83ea2cb2de31fb95c4c78d519101a2fbcf4786491e4552c025b1e377278`。最终源码与补丁完整哈希见 verification.json。

## 根因与实现位置

B 为生产 `feishu_publish_bot/bot.py`，I 为交付的 `fix_evidence_p0_2_p1_1/bot.py`。以下行号对应本次交付文件。

| 根因 | 生产位置 | 修复位置与结果 |
|---|---|---|
| 多客户提前路由；取消落不到持久化状态；暂停被解析为不支持的schedule | B:3507、5343、6336 | I:5578统一取消；I:3567、4490、4565保存/调度/投递读取消意图，优先执行取消，禁止走远程schedule指令 |
| 模糊确认、历史话题、隐式全部素材直接进入准备或确认 | B:5343、4720 | I:5726、5772、5819、4674：清单→选条→话题→标题确认→准备核对→最终卡→排期 |
| 排期/视频词命中宽泛分支，标题评价被当成标题 | B:5329、5343 | I:5863：确定性路由；仅显式标题设置语法；改期在查询之前 |
| 模型无客户上下文、两次90秒调用；异常仅写日志 | B:2286、5343、6502 | I:5657、5670、7047、7073、7097：客户隔离上下文、单次30秒预算、去重、有界队列、失败回复 |
| 已确认内容可在重建预览时漂移 | 旧调度/重建与确认契约未关联 | I:4490、4565：预览刷新前后及最终签发前核对内容摘要，变化即停止 |
| 长远程操作占批次锁，取消仅靠内存易在崩溃中丢失 | 旧取消/调度间缺独立持久化契约 | I:5567、5578：独立取消意图先fsync落盘，再归并批次；恢复时仍生效 |

## 实际行为

**取消与在途。** 文本「停/暂停/取消」对当前绑定客户本会话的未发批次生效；卡片仅取消其指定批次，过期、终态、旧客户卡不影响新批次。先独立原子写 `mt_batches/dialog/*.cancel.json`，再持批次锁把未开始条目置skipped并清凭据。在途dispatching/dispatched不杀进程、不撤回指令，只接收结果；needs_reconcile仍保留待核实。取消后晚到的发布结果可以更新本条事实，但不会恢复后续调度。最终取消检查与持久化dispatching占用共享锁；占用完成的单条视为在途，随后取消不杀该次投递。

旧状态写回不能抹掉取消；重启读取取消意图；重启中的在途条目转needs_reconcile。取消前已排队请求按截止时间拒绝；查询素材期间发生取消，旧请求也会因revision/status CAS失败而停止，不能用递增版本覆盖取消。

**选条、话题和标题。** 清单按客户和30分钟有效期保存，包含snapshot_id与基于素材路径/名称的material_id，选条保存原清单序号及snapshot_id。越界、重复、失效、跨客户选择拒绝；89只代表第89条，不拆成8和9。刷新清单清掉旧选择与话题回答。所选文件以显式files传递，准备结果必须与选中名称集合一致；最终内容摘要另绑定客户机提供的素材SHA及plan内容。

每次选条先问本批话题，支持默认、不填、原清单序号覆盖；默认值仅在本客户会话有效期内保留，不借用旧chat级跨客户默认值。待话题时不把无标记的普通问句当话题。显式「话题：…/把话题改为…」使旧卡失效并重新确认。客户机prepare会按mtime排序，因此逐条话题在结果返回后按素材名称重绑，再通过既有计划重建/dry-run取得匹配hash和新token；重建回读不一致时取消，禁止带错话题发布。实际远程重建只在获准运行代码时发生，本轮均mock。

标题保存draft_title/confirmed_title/max_length。只有「标题：xxx」「把标题改为xxx」设置值；评价和查询只展示当前草稿，不成为标题。超长仅尝试一次模型缩写候选，代码按Unicode字符计数；候选非法、仍超长或模型失败时保留原文，提示人工提供较短完整标题，不截断。可用候选仍需「确认标题」。默认整批标题，不做逐条标题产品化。已排期批次不被未确认的新标题草稿改写；重复准备仍在途/待发/待核实素材被拒绝。

**最终确认与改期。** 卡绑定customer/chat/batch/revision/snapshot及摘要；显示全部条目标题、话题、具体排期。只有唯一当前草稿可用明确文字确认；「可以/好/行」不授权。旧pending卡缺新契约时拒绝，需重新选择、回答话题和确认标题。准备响应必须匹配当前prepare_command_id和batch_id，取消或换草稿后的旧响应不能生成可用卡。

确认只置scheduled，由调度器统一下发；不在确认函数直接发布。保留prepare返回的排期，不再静默压成当前+3分钟；调度刷新preview使用原已确认时间，不擅自移到当前+90秒。整批改期先持久化editing、清旧token并使卡失效，完成重建后重新确认；部分失败置needs_reconcile，不恢复已取消/失败/待核实批次。当前明确拒绝逐条改期和绕过确认的立即发布。没有更改客户机发布内核、签名信任根或账本协议。

已确认摘要包含计划piece（含sha256）、账号、标题、话题、排期等；刷新preview或回读改变任何这些内容时，零新签名、零发布命令并停止本批。仅token刷新不改变授权内容。已部署前已scheduled的旧批次继续沿用已有授权与P0-1校验；不会批量重写历史文件。该兼容分支没有补造旧话题确认历史，部署前需人工盘点。

**上下文、队列与回复。** 会话文件按chat+customer哈希隔离，30分钟闲置后失效，含有限12轮历史、当前标题/限制、清单、绑定、真实批次错误。多客户不读旧tunnel/ONCE上下文。模型仅可提议清单、数量、进度和澄清，不能凭模型文本执行取消、确认、标题修改、删除或发布事实声明。

消息入口先原子记录message_id，再立即发接收回执，之后进入容量64的单工作线程队列（跨会话也串行，避免并行写状态）；取消走优先通道。队列等待超过30秒明确失败，不静默执行；message claims跨重启保留，未完成请求不自动重放。模型单次请求总预算30秒、无自动重试、响应体限256KiB；远程清单查询使用同一截止时间。异常和不支持动作返回确定性反馈，新诊断只记request_id/route/耗时/错误类，不记凭据URL。确认卡SDK失败会返回失败并提供重发卡片入口。

## 测试证据

原有测试文件未改断言、未新增xfail/skip。所有外部调用mock；conftest在导入前封锁真实网络connect/bind和Thread.start，封锁生产文件/密钥目录读取，状态路径指向pytest临时目录。签名种子为临时合成值；未启动bot.main或后台服务。旧计划脚本用例仅执行临时素材上的本地Python子进程。

实际命令与原始输出均在证据目录，退出码另存test_exit_codes.json：

| 运行 | 实际结果 | rc |
|---|---|---:|
| 放回P0-1源码，`pytest -q -p no:cacheprovider tests/ --ignore=tests/test_mt_dialog_contract.py` | 9 failed, 200 passed, 3 skipped in 1.88s | 1 |
| 最终源码，`pytest -q -p no:cacheprovider tests/test_mt_dialog_contract.py tests/test_mt_result_contract.py` | 190 passed in 3.62s | 0 |
| 最终源码，`pytest -q -p no:cacheprovider tests/` | 7 failed, 263 passed, 3 skipped in 5.13s | 1 |

190项由61项新增契约测试与P0-1全部129项组成。覆盖取消状态矩阵/重启/晚到结果/长调用锁前崩溃、在途一条不新增后续命令、卡取消作用域、清单取消竞态、快照失效/89/重复序号、话题必问与乱序覆盖、标题重启持久化/10字限制/中英标点emoji/超长候选、上下文改绑隔离、E6及指定日志原句、无key/超时/非法JSON/模型异常、队列超时/满额/message_id去重、旧卡/改期失效/部分失败、确认后标题/话题/素材hash漂移零签名零投递。关键判定断言prepare/confirm/receipt实际调用次数。

新增on_message测试证明mock环境下首个回执在2秒内、先于查询/模型/执行；不能把它解释为真实飞书网络送达SLA。真实SDK延迟、远程长dry-run等待、真实模型质量与压测均未执行，不能用stub结果替代。

## 全量7项失败与3项跳过

本轮修复了基线4项交互失败：两个cancel文本测试，以及`test_handle_asks_then_publishes_with_topics`、`test_handle_skip_topics_and_expired_pending`。其余失败完整保留：

1. `test_batch_publish.py::test_plan_maker_expands_all_inbox_items`
2. `test_topics.py::test_bt_topics_injected_into_plan_and_hash`
3. `test_topics.py::test_bt_topics_empty_keeps_topics_empty`
4. `test_xingtu_flow.py::test_plan_maker_writes_order_id_and_topics_as_description`
5. `test_xingtu_flow.py::test_plan_maker_keeps_task_name_without_order_id`

以上五项均在嵌入PLAN_MAKER脚本第70行报`NameError: title_from_file is not defined`。其中两项名称含话题，但在执行话题断言前就被同一旧标题helper缺失阻断；本轮按任务边界保留该旧脚本问题，没有宣称这两项已通过。任务书对旧9项的口头归类与实测不同，此处以基线原始输出为准。

另外两项原来通过、现在失败，原因是旧期望与新强制门冲突，未修改断言掩盖：

- `test_republish_and_mt.py::test_mt_prepare_is_stored_and_confirm_enqueues_remote_confirm`：直接store旧结果、没有话题/标题/摘要，调用旧两参数confirm，要求立刻enqueue；现在必须拒绝。新测试覆盖完整草稿到排期和调度实际执行。
- `test_republish_and_mt.py::test_two_chats_route_to_their_own_customer_queues`：要求仅说「发布」立即enqueue publish；现在应先显示清单并问话题/标题。该旧测试也把「状态」预期为远程status命令，新路由从当前绑定批次渲染进度。新增跨客户与改绑测试验证新的隔离契约。

三项跳过仍为缺失客户端winport源码所致（两份签名/客户端契约模块、旧ledger helper），没有为变绿添加跳过。

## 复核结论与实际限制

独立只读审查发现的取消竞态、快照残留、跨客户展示、卡作用域、确认内容漂移及SDK失败问题已修复并增加测试。复核者未独立跑测试，最后结论是其检查范围内未见新增重大阻断项；这不代替人工终审。

仍需在任何部署决定前评估：全量非绿；未做真实飞书/客户机联调；老scheduled兼容批次无新增话题证明；本地message claims未归档、永久去重且崩溃丢失队列不自动重放；单工作线程会让其他会话等待长改期任务，过期请求失败关闭；长计划重建沿用原远程超时，取消先持久化但数量汇总会等锁；标题候选仅做结构/长度验证，未测真实模型语义质量。首次清单material_id是路径身份，不宣称扫描时已计算视频字节hash；正式确认绑定准备后的SHA。

## 补丁校验、部署与回滚（仅说明，未执行）

在 `/tmp/publish-plan-validation/apply-check-p0-2-p1-1` 的生产源码副本完成正向dry-run、实际应用、反向dry-run，三者rc=0；应用后逐字节等于受测源码，compile通过。patch_check.json记录原始输出。原有测试逐文件比较无变动；生产源码哈希不变。

若后续另行批准部署：

1. 先由独立终审与人工确认是否接受全量失败、客户端测试缺口与兼容边界；盘点在途、scheduled、pending、needs_reconcile及通知状态。当前报告不提供批准哈希。
2. 核对生产bot.py仍为上述基线哈希；有变化则重新合并和验收，禁止强制套补丁。先在新的隔离副本应用累计补丁并复跑，不叠加P0-1补丁两次。
3. 获授权运维备份机器人源码及机器人自己的批次/结果/对话状态，保留取消意图、message claims、结果outbox；不以数据库或客户账本恢复来回退。
4. 仅由获授权运维按既有单实例服务流程部署与切换；本轮没有执行任何服务命令。旧pending卡不得继续授权，需完整新草稿；旧scheduled批次单独人工盘点，不能为验收重发历史素材。
5. 核对取消项保持停、在途只回读结果、needs_reconcile不自动重试、确认卡展示内容与调度契约一致；真实联调须另获授权。

回滚同样须另行人工批准，且先确认无在途动作、评估旧代码不理解新取消意图/草稿/通知状态的风险。源码可按临时副本验证过的反向patch恢复，但不能删dialog/取消意图/claims/结果/通知，也不能恢复旧数据库账本或自动重放队列。存在新取消意图或待核实项时，不让旧调度器直接接管；应维持停止并前向修复，由人工决定后续处置。

OUTPUT: /home/ubuntu/workflow/projects/publish_control/P0_2_P1_1_IMPLEMENTATION.md
