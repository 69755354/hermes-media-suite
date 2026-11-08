# 1.2.199 修复报告（1.2.198 复核必修 A/B）

基线：`v1.2.198`（`8fb0805`）

分支：`fix/control-bridge-1.2.199`

范围：只改 `publish-control/client`；未改服务端、未改 license 校验、未新增依赖；未 tag、未打包、未上传。

## 必修 A：面板接入状态自动刷新

### 改法

- `agent/winport/panel.py`：激活、重试自动授权或「重新获取接入配置」成功后启动状态轮询。
- 轮询立即拉取一次 `/api/control-status`，随后每 2 秒一次，最多 60 秒。
- 命中 `connected` 或 `error` 立即停止；为兼容只返回 `level` 的状态视图，`level=ok/bad` 也视为终态。
- 超时停在「飞书接入：连接中…（可稍后刷新页面）」。
- 只原地更新 `#control-status-line` 的文本和 `st-ok/st-warn/st-bad` class，不整页刷新、不覆盖 `#license-result`。
- 重复点击会递增轮询 token 并清理旧定时器，避免旧请求回写覆盖新结果。

### 回归

`tests/test_control_bridge_1199.py`：

- `test_pending_then_connected_updates_in_place`：首次 `pending`，2 秒后 `connected`；状态行变绿、结果文本保持「授权已生效，接入已补齐」，只发 2 次状态请求且无残留定时器。
- `test_pending_then_error_stops_polling_and_shows_reason`：`pending → error`；状态行变红并显示「未连接（接入凭据失效）」，结果文本保持「已重新获取接入配置」。
- `test_pending_timeout_stops_after_sixty_seconds`：持续 `pending` 时，在 60 秒（31 次请求、30 个 2 秒定时器）后停止并显示「连接中…（可稍后刷新页面）」。

## 必修 B：同码未换凭据时诚实报错

### 改法

- `agent/winport/activation.py`：`_bridge_control()` 写盘前读取现有合法 `control.json`，比较 `customer_token`、`device_token`、`binding_epoch`。
- 三者全部未变时：
  - 不覆盖 `control.json`；
  - 返回 `ok=False`；
  - 原因写「服务端没有签发新的接入凭据，请向服务商索取新的 8 位激活码后再试」；
  - 状态写 `error` + 同一原因。
- `_install_with_control()` / `_complete_existing_control()` 不再把该情况包装成「接入已补齐」，`control_written=False`，因此也不会触发 poller 重启。
- 仅三项全部相同时拒绝；任一项变化仍正常写入并显示 `pending`。
- 写盘仍沿用原子替换、`0600`、状态文件不落 token。

### 回归

`tests/test_control_bridge_1199.py`：

- `test_same_code_same_credentials_is_not_reported_as_repaired`：exchange 返回与旧 control 完全相同的字典 → `control.json` 字节与 mtime 均未变、结果 `ok=False`、原因完全一致、状态 `error`、未触发 poller 重启、状态文件不含 token。
- `test_any_changed_credential_field_is_really_written`：分别只改 `customer_token` / `device_token` / `binding_epoch` → 均正常写入新 control、结果 `ok=True`、状态 `pending`、触发重启。

## 文档与版本

- `CUSTOMER_README.txt`：删除「输入同一激活码可恢复」的旧说法，改为未连接时向服务商索取新的 8 位激活码；保留 UTF-8 BOM + CRLF。
- `VERSION`：`1.2.198` → `1.2.199`。
- `VERIFY.md`：更新到 1.2.199，记录本轮轮询与同码兜底语义。

## 测试输出

### 定向回归

```text
$ cd publish-control/client && python -m pytest tests/test_control_bridge_1199.py -q
.......                                                                  [100%]
7 passed in 0.29s
```

### 客户端全量

```text
$ cd publish-control/client && python -m pytest tests -q
........................................................................ [ 87%]
..........                                                               [100%]
82 passed, 4 warnings in 1.79s
```

### publish-control 全量

```text
$ cd publish-control && python -m pytest tests -q
........................................................................ [ 61%]
...............ssss................ssssssssss                            [100%]
103 passed, 14 skipped, 24 warnings in 10.22s
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
- `publish-control/client/agent/winport/panel.py`
- `publish-control/client/tests/test_control_bridge_1199.py`（新增）
- `publish-control/client/CUSTOMER_README.txt`
- `publish-control/client/VERSION`
- `publish-control/client/VERIFY.md`
- `review/FIX_REPORT_1.2.199.md`

## 未验证项

- 未在 Windows 实机执行真实服务端同码重兑、token 轮换与飞书往返；本轮用本地 harness 验证客户端拒绝逻辑、落盘不变和面板轮询状态机。
- 未打包，因此未重算 `MANIFEST.json` / `SHA256SUMS.txt` / `PACKAGE_BINDING.json`。
- 服务端是否会对新激活码真正 rotate token 不在本分支范围；客户端已能在同码返回旧凭据时明确失败并提示索取新码。
