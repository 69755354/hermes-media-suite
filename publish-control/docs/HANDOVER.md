# 同客户换机清单（待独立复核，未执行）

本清单保留 customer_id 和会话绑定，只替换设备。脚本只读本地证据，不连接客户机，不修改服务或账本，不复制文件、不轮换凭据、不授予发布权限。

生成待填清单：

```bash
python3 scripts/handover_checklist.py template > /approved/offline/handover.json
```

人工维护窗口内按下列顺序执行并填写 steps 中的 operator、evidence、checked。脚本不会代填批准；路径仅为示例。本轮没有执行下述运维动作。

1. 人工批准维护窗口与同客户换机。完整导出该客户 commands、remote_ops、机器人 batches 和 items。普通 API 最近 50 条不是完整盘点；需要带一致性时点的全量只读导出。各 inventory 分区标明 complete，证据记录导出时点与摘要。
2. 暂停该客户新派发（dispatch_paused=1），停止旧机认领。轮换 token 不会撤回已经领取的任务。旧机不可达、网络分区或存在 running/dispatching/dispatched/needs_reconcile 时禁止放行；先隔离、核对平台和执行证据。queued/待发/暂停项也须逐条处置，保留审计，不批量迁给新设备。
3. 核实无在途并停止旧机执行后，制作一致性备份。保留 stage2-ledger.json、agentpoll-state.json、publish_holds.json，以及账本引用的成功证据、审计、关联素材。文件位于该客户真实数据根，不使用公共根替代。将所有关联文件补入 files 清单；发布签发私钥留在服务器，禁止加入迁移包。
4. 在批准的人工步骤中复制数据到新机。不得删改任何账本条目，不得覆盖分叉历史；发现分叉即冻结并取证。保留 key/content_hash/receipt_id/publish_confirmed。素材保持 SHA256 身份对应，独立记录旧新路径和旧新计划。新路径、新 nonce、新指纹不能使已发布素材变成未发布素材。
5. 两边导出只读本地副本，执行下列校验。每个文件比较完整字节 SHA256，JSON 再比较完整对象，不忽略保护状态。清单外的依赖仍须人工核实，脚本不声称自动发现全部依赖。
6. 新机仅做完整性、身份、许可、登录状态、账本与 dry-run 验证。未发布草稿重新建计划、重新确认并签新凭据；旧确认卡、旧 receipt 不挪用。验证同一已发布素材仍被账本阻止。客户机能力部署和验证是后续独立任务，本轮未做。
7. 在同一控制面事务中登记新设备 token_hash（SHA256，凭据需安全随机生成）、隔离旧设备、提升 binding_epoch、设置 active_device_id；首次满足客户端身份协议后才开启 device_binding_enabled。当前补丁不提供自动切换接口，需独立复核的运维流程。强校验开启后旧 customer token 不再用于 agent 身份。切换前处置未终态任务，不回填旧任务到新 epoch。
8. 验证新设备只用新凭据、旧凭据拒绝。旧机持续隔离。人确认切换后再解除暂停；脚本校验通过本身不批准解暂停或发布。

```bash
python3 scripts/handover_checklist.py verify \
  --source /approved/offline/old --target /approved/offline/new \
  --record /approved/offline/handover.json
```

缺证据、状态未核实、摘要不同返回 rc=3。checked 是外部人工记录，脚本仅检查完整性，不验证人的身份、不提供获批哈希。

人工恢复只允许：明确 customer/channel/目标记录 → 确认无在途且无 publish_confirmed → 人工批准并留证 → 用当前客户端 Stage2Ledger.recycle_zombie 的真实签名回收符合其年龄条件的 RESERVED。不得直接 pop，不得清 UNKNOWN/SUBMIT_INTENT/CONSUMED，不得自动清 holds 或重试。机器人自动恢复入口已禁用，未新增远程恢复工具。

回滚保留新表、字段、账本和成功事实。换机后不得关闭强校验退回匿名旧 token，也不得恢复旧 DB/旧 token；切回旧机必须隔离新机、重新核实账本，以更高 epoch 和全新凭据完成前向切换。
