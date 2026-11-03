# 客户机只读契约 publish-materials/1（候选）

机器人经现有 `/api/remote/exec` 队列发送 `op=materials, args={"schema":"publish-materials/1"}`，customer_id 来自当前会话绑定。这里只规定只读 op 的语义，不表示队列无写入：生产调用仍会写控制面请求记录。本轮测试全部 mock，无真实调用。

客户端不支持、超时、版本/客户不符、残缺、截断、过期或未排序均显示“清单暂不可用”，不会回落 ls/exec 或固定路径。当前客户机未升级，正常情况下暂不可用是预期安全退路。本轮没有实现或部署客户机能力，也不要求当前客户机升级。

客户端将来实现时必须直接复用当前 `_publish_roots/_scan_inbox`、安全所有权校验，不得另造一套扫描规则。根为 inbox 和桌面发布素材，按根顺序扫描，排除链接、目录、隐藏临时名、零字节和非 mp4/mov；按规范路径、再按 (name.lower(), size) 去重，最终按 (mtime, name.lower()) 升序。当前实际去重规则不是“按内容哈希全局去重”，同名同大小内容不同也会合并；本轮保持该兼容行为。prepare 显式 files 使用同一根和相同排序。不可读取其他客户根。

完整返回示意（数字和摘要须取真实快照，示例不能投产）：

```json
{
  "ok": true, "schema": "publish-materials/1", "customer_id": "c_example",
  "snapshot_id": "opaque-customer-snapshot", "expires_at": 1790000000,
  "roots": {"inbox":"C:\\data\\inbox", "desktop":"C:\\Users\\example\\Desktop\\发布素材"},
  "complete": true, "truncated": false, "next_cursor": null, "total": 1,
  "materials": [{"material_id":"opaque-file-identity", "root":"inbox",
    "path":"C:\\data\\inbox\\a.mp4", "name":"a.mp4", "size":12, "mtime":1789999000,
    "sha256":"64位小写SHA256", "is_file":true, "is_symlink":false}]
}
```

snapshot_id 绑定客户、完整集合与顺序；material_id 绑定客户、规范路径、size、mtime、SHA256。快照最多有效 30 分钟。哈希读取前后复核文件 stat，文件变化须重取快照。必须返回全量，超 500 条不得沿用 ls 的静默截断；本版本不接受分页，未来分页需新增版本。

选择落盘 snapshot_id + material_id + path + SHA256，序号仅为当前快照 UI。准备 payload.files 为完整路径，附 material_ids/snapshot_id；旧 prepare 可忽略新增字段，因此机器人必须读回每条计划的 piece.sha256 并按 (name, sha256) 匹配快照，生成确认前再核对标题、话题。不匹配阻止确认。话题按素材 ID 存储，发 prepare 前按快照排序重建索引，不按客户输入顺序盲传。保留现有最终凭据和取消门禁。

素材总数不是可再发数。是否已发仍以账本门禁为准，清单不清账本、不生成计划、不 dry-run、不签 receipt、不发布。

设备协议：仅强绑定客户要求 agent 每次 poll/result/remote-poll/remote-result（含旧 /api/command 结果入口）提供 device_id 与整数 binding_epoch，并以该设备新 token 作 bearer；token_hash 仅在服务端存 SHA256。customer_id 必须显式提供。未启用时保留旧 token 和旧请求格式。新任务固定目标 device/epoch，旧未绑定任务不自动认领，过期 running 进入 needs_reconcile，旧设备/旧 epoch 结果不落库。暂停阻止新派发和认领，但允许当前设备回传结果。machine_code 仅为注册元数据，不是设备锁。
