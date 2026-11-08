# 1.2.198 修复报告（1.2.197 复核残留 P0-4）

基线：`v1.2.197`（`8d5f1fa`）

分支：`fix/control-bridge-1.2.198`

范围：只改 `publish-control/client`；未改服务端、未改 license 校验、未新增依赖；未 tag、未打包、未上传。

## 必修 1：无凭据恢复路径（token 轮换/撤销后可恢复）

### 改法

- `agent/winport/activation.py`：`activate_with_code(layout, code, *, force=False)`。`force=True` 时跳过「已有正式授权 + control.json 合法」的早返回，必须执行一次 `exchange()`。
- `agent/winport/activation.py`：`refresh_control()` 固定走 force 路径；有码用码，无码明确提示输入 8 位激活码，不再因为 control.json 结构完整而空操作。
- `agent/winport/activation.py`：新增 `restart_after_control()`。只有本次确实写入了新 `control.json`（`control_written=True`）才触发 poller 重启；重启失败把 `接入服务重启失败：原因` 追加到客户可见结果，并写 `error` 状态。
- `agent/winport/main.py`：新增 `_restart_agentpoll()`，按 stop → start 重建 poller，使用共享锁避免面板重启与 30 秒复查线程同时创建两个 poller；旧 poller 停止失败时保留槽位并返回明确原因。
- `agent/winport/panel.py`：`/api/control-refresh` 通过 `PanelHandlers.control_refresh()` 调用 activation 并注入 poller 重启回调；`/api/activate-code` 与 `/api/activate` 写入了新 control 时也走同一重启路径。
- 重启 poller 时不再重复启动 remote-agent 线程；首次无 poller 的启动仍保持原行为。

### 回归

- `tests/test_control_bridge_1198.py::test_refresh_with_same_code_forces_exchange_and_restarts_poller`：合法 control + 失效 token + 同一激活码点刷新 → exchange 被调用、`control.json` token 从 `stale-secret` 变为 `fresh-secret`、重启回调被调用、状态从「接入凭据失效」变为 `pending`、面板显示「连接中…」且不是绿色。
- `tests/test_control_bridge_1198.py::test_refresh_restart_failure_is_visible_not_silent`：重启失败时结果包含 `接入服务重启失败` 与真实原因，状态保持 `pending`，不静默。
- `tests/test_control_bridge_1198.py::test_restart_agentpoll_stops_old_then_starts_new`：断言顺序为 `stop → start`，槽位替换为新 poller。
- `tests/test_control_bridge_1198.py::test_restart_agentpoll_failure_writes_visible_error`：启动失败写 `error`，面板不是 connected。

## 必修 2：状态文件统一到共享根

### 改法

- `agent/winport/control_status.py`：`_data_dir()` 固定优先取共享根：`Layout.data`；`CustomerLayout` 取 `base`，不再取租户 `root`。poller 与面板因此始终读写同一个 `<data>/control-status.json`。
- 保留原子替换、`0600`、不落 token 的写盘逻辑。

### 回归

- `tests/test_control_bridge_1198.py::test_historical_tenant_poller_writes_shared_status_visible_to_panel`：`single_root=False` 时 poller 租户根为 `<data>/customers/c_123`，401 后状态写到 `<data>/control-status.json`，租户目录不产生状态文件；面板读到 `error` +「接入凭据失效」，不是 connected。

## 必修 3：不许假绿

### 改法

- `agent/winport/control_status.py`：状态集合新增 `pending`。
- `agent/winport/activation.py`：`control.json` 写盘成功后写 `pending`（未验证），不再写 `connected`。
- `agent/winport/panel.py`：合法 `control.json` 只有在存在更新时间不早于其 mtime 的 `connected` 状态时才显示绿色；否则显示 warn 色「飞书接入：连接中…」。更新的 `error/disabled/missing` 仍优先显示「未连接（原因）」。
- `agent/winport/main.py`：启动期 `import_error/config_error/startup_error` 一律写 `error`，不再写可能被误读的 pending/disabled。

### 回归

- `tests/test_control_bridge_1198.py::test_control_write_is_pending_until_first_successful_poll`：写入 control 后状态为 `pending`、面板不是 connected；真实成功 poll 一次后变 `connected` 且 level 为 ok。
- `tests/test_control_bridge_1198.py::test_startup_config_error_writes_error_not_pending`：启动配置异常写 `error`，面板不是 connected。
- 既有 `test_control_bridge_1196.py` 与 `test_control_bridge_1197.py` 中「写 control 即 connected」的旧断言已改为 pending；旧失败状态早于新 control 时也保持 pending，不再回落绿色。

## 版本与文档

- `VERSION`：`1.2.197` → `1.2.198`。
- `VERIFY.md`：更新到 1.2.198，并记录本轮状态语义。
- `CUSTOMER_README.txt`：补充「连接中…」说明与「重新获取接入配置会重新换取凭据」；保持 UTF-8 BOM + CRLF。

## 测试输出

### 定向回归

```text
$ cd publish-control/client && python -m pytest tests/test_control_bridge_1195.py tests/test_control_bridge_1196.py tests/test_control_bridge_1197.py tests/test_control_bridge_1198.py -q
...........................................                              [100%]
43 passed in 0.69s
```

### 客户端全量

```text
$ cd publish-control/client && python -m pytest tests -q
........................................................................ [ 96%]
...                                                                      [100%]
75 passed, 4 warnings in 1.08s
```

### publish-control 全量

```text
$ cd publish-control && python -m pytest tests -q
........................................................................ [ 61%]
...............ssss................ssssssssss                            [100%]
103 passed, 14 skipped, 24 warnings in 8.35s
```

### 静态验收

```text
$ cd publish-control/client && python tools/static_verify.py
...
------------------------------------------------------------
STATIC VERIFY: 127/127 checks passed
------------------------------------------------------------
```

## 变更文件

- `publish-control/client/agent/winport/activation.py`
- `publish-control/client/agent/winport/control_status.py`
- `publish-control/client/agent/winport/main.py`
- `publish-control/client/agent/winport/panel.py`
- `publish-control/client/tests/test_control_bridge_1196.py`
- `publish-control/client/tests/test_control_bridge_1197.py`
- `publish-control/client/tests/test_control_bridge_1198.py`（新增）
- `publish-control/client/VERSION`
- `publish-control/client/VERIFY.md`
- `publish-control/client/CUSTOMER_README.txt`
- `review/FIX_REPORT_1.2.198.md`

## 未验证项

- 未在 Windows 实机执行真实服务端 exchange、token 轮换/撤销与飞书往返；本轮用本地 harness 验证调用链、落盘与面板状态。
- 未打包，因此未重算 `MANIFEST.json` / `SHA256SUMS.txt` / `PACKAGE_BINDING.json`。
- remote-agent 不随 poller 重启重复启动；其自身 token 刷新不在本轮 P0-4 范围。
