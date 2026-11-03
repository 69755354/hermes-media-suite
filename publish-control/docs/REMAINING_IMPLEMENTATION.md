# 剩余项隔离实施报告

日期：2026-10-28。范围：P1-2、P1-3 的代码与流程、P2-2。身份：实现与测试 owner，未作独立终审。

已完整读取 BRIEF_remaining_20261028.md、方案 4.4/4.5/4.7、两个 CONTEXT，形成候选补丁、显式迁移及校验脚本、换机清单、只读能力契约和隔离测试证据。最新补丁从原始基线重建后测试 **185 passed in 1.60s**。这不是部署批准或真实客户端验收。

未部署、未重启服务、未连接或修改生产数据库、未对客户机执行任何操作、未发布/重发、未发飞书消息、未实际换机或轮换 token。业务代码只在 `/tmp/publish-remaining/bot`、`/tmp/publish-remaining/control` 修改；生产源码未改。两个 CONTEXT 按授权更新了文档。测试未复制 .env、生产状态或密钥。

## 交付文件

| 文件 | 用途 |
|---|---|
| remaining_bot.patch | 相对生产 bot.py 的补丁，路径 a/bot.py → b/bot.py |
| remaining_control.patch | 相对生产 server.py 的补丁，路径 a/server.py → b/server.py |
| migrations/20261028_device_binding.sql | 加法迁移；没有在生产执行 |
| scripts/verify_device_binding.py | 默认只读校验；显式 --apply 才执行幂等迁移，冲突回滚 |
| scripts/handover_checklist.py、HANDOVER.md | 离线换机清单模板、人工步骤、逐文件摘要与完整 JSON 比对 |
| MATERIALS_CONTRACT.md | 客户机只读素材能力与设备请求协议，明确当前客户端未实现 |
| scripts/reproduce_remaining.py | 校验基线 → 复制源码 → 隔离应用补丁 → 校验候选哈希 → 运行测试 |
| fix_evidence_remaining/ | 测试源码、合成 fixture、扫描函数参考、各轮输出、复现输出、哈希清单、CONTEXT 修改前后差异 |

## P1-2：素材清单和准备身份一致

根因：机器人固定使用某 Windows 用户桌面路径，ls 输出与 prepare 的扫描根、过滤、顺序和 500 条限制不同；同名素材仅按名字绑定话题与选择；进度混合了暂停、失败、已提交和待发。

改动：

- 去掉全局硬编码 Windows 用户路径。多客户清单只调用当前客户 `materials` 只读 op，接受 `publish-materials/1` 完整快照。旧客户端、不完整/截断数据、过期快照或错误客户均明确“清单暂不可用”，不回落其他目录或远程 exec。
- 契约复用客户端实际 `_publish_roots/_scan_inbox`：inbox + 桌面两根，非零常规 mp4/mov、所有权和链接校验、临时名排除、规范路径及 `(name.lower(), size)` 去重，最终 `(mtime, name.lower())` 升序。机器人验证返回契约，不自行扫描服务器文件。
- 明确保留现有客户端去重语义：同名同大小跨根会合并，即使内容不同；同名不同大小保留。没有擅自换成按 SHA 全局去重。客户端后续若调整规则必须同步版本化契约。
- 快照保留路径、mtime、size、SHA256、material_id，选择绑定 snapshot_id + material_id；序号只对当前清单有效。超过 500 条接受完整集合，拒绝截断，没有 500 条隐式上限。失败的清单刷新使旧选择失效。
- 准备发送绝对 files、snapshot_id/material_ids，并按 prepare 排序重建逐条话题。提高 max_items 到本次明确选择数量，避免旧 prepare 默认 50 条截断。
- 旧 prepare 不理解新增身份字段，因此在生成确认前读回计划的素材 SHA256，按 `(name, sha256)` 核对快照；材料变化拒绝确认。material_id、snapshot_id 和设备绑定纳入确认摘要，保留原最终凭据校验和取消门禁。
- 清单“素材总数”明确不等于“可再发数”。清单/进度统一展示待确认、待发、在途、已提交、失败、暂停、待核实、已取消；包含混合、失败、暂停和终态批次，按 item 实际状态计数。

边界：本轮没有改客户机发布内核，没有实现或要求升级客户端。当前旧客户端不支持 materials 时无法继续清单选材，属于明确的安全降级；不能声称生产清单已恢复。新版客户端能力须另行实施与验收。清单契约只读指客户机行为，现有远程队列依然会写控制面请求记录，因此本轮没有发真实只读请求。

旧单客户路径已移除用户专属默认值，若仍使用旧通道，维护者必须明确配置 CLI_PY/CLI_ROOT、WORKER_DATA_ROOT、LOCALAPPDATA、ONCE_SCRIPT/ONCE_PY、PUB_INBOX、EDIT_SCRIPT/DELETE_SCRIPT、LEGACY_PUBLISHED_ROOT 等实际需要的路径；不能依赖旧用户路径回退。本轮不验收旧隧道全部功能。

## P1-3：客户配置、设备约束与换机

根因：客户只有 machine_code 和共享 customer token；队列认领并不核对 machine_code。单次 SQLite 认领事务只保护某条任务，不证明物理设备唯一；租约过期可重投。新机缺旧机本地账本时不能保证幂等。标题和话题全局默认值会污染其他客户。

改动：

- customers 增 nullable default_title/default_topics/policy_version。管理 upsert/update 支持这些配置；default_topics 为 JSON 列表，null 表示未配置，[] 表示明确无话题。机器人草稿按 customer_id + chat_id 隔离，未配置标题或默认话题时询问，旧本地草稿首次使用新设置结构时不沿用全局默认标题。
- customers 新增 active_device_id/binding_epoch/dispatch_paused/device_binding_enabled；customer_devices 含 device_id/customer_id/token_hash/status/binding_epoch/last_seen，同客户 active 设备唯一。commands/remote_ops 增 nullable device_id/binding_epoch。last_seen 为预留字段，本轮不把它用作在线或无在途证明。
- 未迁移数据库继续兼容旧读写与 agent；新增设置写入会明确要求迁移。迁移后强校验默认关闭，未启用客户继续接受旧 agent 不带设备字段。没有自动登记设备、自动回填配置、自动启用强校验或自动迁移生产结构。
- 启用后 agent 必须提供当前 device_id、整数 epoch 和设备新 bearer token；服务端校验 SHA256 token_hash。旧 customer token、旧设备、旧 epoch 在 poll、result、remote-poll、remote-result 和旧 /api/command 结果入口均拒绝。
- 在同一认领/结果事务中重读绑定并核对任务目标，防止 HTTP 鉴权后换机的竞态。新命令固定设备/epoch，既有无绑定任务不自动收养；发布 payload 必须携带期望设备/epoch，避免检查后切换却投到新机。机器人另附 expected_customer_id，控制面拒绝会话改绑后的跨客户入队。
- 暂停阻止新任务入队和认领，但允许当前设备回传已领取任务结果。强绑定客户 running 超时转 needs_reconcile，不自动重投；合法当前设备的迟到结果仍可回传。旧模式保留原租约兼容行为。
- 机器人准备结果、改期、最终派发验证设备/epoch；旧设备草稿需重建并重新确认，不能在换机后复用。
- 换机脚本只生成清单、检查人工证据字段、检查全量盘点和逐项摘要，不做任何实际迁移、凭据更新、账本清理或批准。缺证据/不一致返回 rc=3。完整对象比对包含所有保护状态、publish_confirmed、receipt_id；不只比较条目数。

真实约束：一会话绑定一客户、一客户行一个会话；多个客户可各自绑定不同会话共用机器人。machine_code 仍是元数据，不能当设备锁。新强校验只对已启用且客户端已实现身份协议的客户有效；不能给当前旧 agent 直接开启。设备切换与暂停参数由经批准的运维事务管理，本轮没有增加对外自助换机 API，也没有执行切换。

路径 D 未实现。产品必须先决定：群内谁有权选客户、生成草稿、确认发布、取消、重发、切换客户和管理绑定；权限按飞书用户还是群角色；一个客户能否多群；授权变更时旧确认卡如何失效；结果回传到原授权会话还是当前会话。需独立用户授权模型和审计，不能删除 chat 唯一索引冒充支持多客户会话。

## P2-2：禁用自动恢复残留

根因：正常发布恢复已只执行一次，但无条件 pop RESERVED 的旧助手及自动清冻结调用仍留在源码；两个 CONTEXT 仍同时存在旧清理承诺与覆盖更正。

改动：_ledger_auto_clear_source 明确抛错，clear_client_ledger_blocks / auto_unblock_publish 返回禁用结果，既不远程执行也不清 holds、不重试；移除删除账本代码与过时失败话术。人工恢复没有新增远程执行入口，只在清单规定核实无在途、明确客户/通道/目标、无 publish_confirmed、留审计后走 Stage2Ledger.recycle_zombie。保护 UNKNOWN/SUBMIT_INTENT/CONSUMED/publish_confirmed，未读取或修改生产账本。

两个 CONTEXT 已移除矛盾的自动清理说明，收敛为唯一恢复口径；同时修正扫描两根、话题隔离、排期与静默维护的旧冲突。此前补丁是否已部署仅按本次任务书说明标注，不把本轮源码哈希当成运行进程证明。文档差异在证据目录可审。

## 测试与实际输出

复现命令：

```bash
python3 scripts/reproduce_remaining.py
```

脚本仅复制源码到 `/tmp/publish-remaining` 并在副本应用补丁；若生产源码与记录基线不符立即退出，不猜测重放。pytest 的 conftest 在导入 bot 前禁止真实 socket connect/bind 和 Thread.start，并阻止测试打开 workflow 生产路径及签发私钥目录。客户机、飞书、模型、队列交互全部 mock，控制面使用临时 SQLite。

最新实际输出（fix_evidence_remaining/reproduction.txt）：

```text
patching file bot.py
patching file server.py
........................................................................ [ 38%]
........................................................................ [ 77%]
.........................................                                [100%]
185 passed in 1.60s
```

测试覆盖：

- 同名异路径、两根同名同大小去重、零字节、.mp4 目录、符号链接、mtime 与名字排序不一致、504 个扫描文件、604 项完整快照、截断拒绝、跨客户拒绝、过期与 NaN 元数据拒绝。
- 从既有客户机只读源码提取实际 `_scan_inbox/_pick_files`，在临时目录和所有权 fixture 下验证扫描/显式准备排序一致。真实 Windows secure_stat、文件所有权、网络、界面未实测；这不是客户端集成验收。
- 序号逆序选择后完整路径和逐条话题正确；计划素材摘要变化阻止确认；同名不同摘要分别绑定；8 类状态展示。
- 旧 schema/迁移 schema 下旧 agent 兼容；客户互斥、设备唯一约束、旧设备/epoch/token 拒绝、旧未绑定任务拒绝、暂停和结果回传、租约过期不重投、HTTP 当前与旧入口、入队绑定竞态。
- 临时数据库重复迁移保持所有旧列/旧行和结果不变；字段类型冲突事务回滚；错误唯一索引检测；客户默认值隔离。
- 各保护状态和新旧 RESERVED 在禁用恢复后字节不变；失败发布只调用一次；换机完整 JSON/摘要一致和不一致拒绝。
- 保留的结果归一化矩阵、通知可靠性、最终确认与派发凭据回归。五种历史成功形状用合成 hash/receipt/work_id 表示，未复制真实账本。

过程输出保留：首轮 34 passed/1 failed（测试误将既有空结果 {} 断言为 null，修正断言）；首次扩展回归 179 passed/2 failed（隔离根路径旧断言与缺失 fixture，修正测试路径并补合成 fixture）；随后迭代最终全部通过。没有隐藏失败，未宣称跑完旧单客户整套测试。py_compile 通过。没有启动并发线程；设备互斥由事务、唯一索引及多身份请求测试验证，真实并发与网络分区仍需后续集成测试。

## 建议部署顺序与回滚（本轮未执行）

1. 由独立审查者审核两个补丁、迁移、契约、清单和测试；人批准维护窗口。当前代码和测试 owner 不自行终审。
2. 备份并只读校验目标 DB；在获批窗口显式运行 `verify_device_binding.py <db> --apply`。原 SQL 单独执行不具备重复 ALTER 处理，必须使用 runner；默认不带 --apply 为只读检查。加法字段留空/默认关闭，旧命令与结果不重写。
3. 部署经审查的控制面与机器人，再逐客户填写本人确认的默认配置。部署和重启需另行授权；不能未经评估就发布会使当前旧客户端清单暂不可用的机器人版本。
4. 客户机材料只读能力、身份协议由后续独立任务实现与验收；满足契约后才开放清单，准备与发布门禁不放宽。没有客户端能力时保持明确不可用。
5. 按 HANDOVER.md 盘点、暂停、隔离、无在途核实、一致性备份、迁移账本/holds/证据、逐项校验，新机只 dry-run，重新建草稿/确认，最后人批准切换新设备/更高 epoch/新凭据并恢复派发。旧设备持续隔离。

回滚保留新表/字段和成功事实，不 drop、不回滚整个 DB/账本、不删除记录、不恢复撤销凭据。未启用设备强校验的客户可评估应用回滚；已启用客户不得直接回滚到不校验设备的旧服务或关闭强校验降级，须暂停并前向修复。切回旧机器也需更高 epoch 和新凭据。自动恢复禁用必须保留。回滚机器人需保留新对话/快照/确认字段；旧代码不能理解时冻结相关草稿重新确认，不能当作新授权。

## 基线完整性

结束时复核与起始一致：

```text
bot.py     6e1399d0e47db7063cf5ea3f8ecc4fff2754b18cd791f4099a83110cc6ed0efe
server.py  1a5b97d8bf5f2ab4fead9b912abd0ef72913012f24f2cfaa4326f35d272063de
```

补丁 SHA256：

```text
remaining_bot.patch      b3361deef438f2fcbd0b0466ddf251f2290cde617f0bd6b54e3463e0ed4c9b45
remaining_control.patch  d192ba31e199515447af416525cfd65203b56fd0d7255fc9c7bcbdfec01c5703
```

业务代码补丁与新增脚本均为待独立复核候选；实际执行和授权状态没有改变。
