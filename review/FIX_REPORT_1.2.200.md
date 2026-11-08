# 1.2.200 修复报告（1.2.199 复核客户端 P1/P2）

基线：`v1.2.199`（`1a1c0ad`）

分支：`fix/control-bridge-1.2.200`

范围：只改 `publish-control/client`（本报告文件按交付要求放在 `review/`）；未改服务端、未新增依赖、未 tag、未打包、未上传。

## 1. control_error 优先与 rotated 兼容（P1-2）

### 改法

- `agent/winport/activation.py`：`_bridge_control()` 现在先处理 `control_error`，不再先比较三项凭据。
- `control_unreachable` / `control_timeout` → 「控制面连不上，稍后再点『重新获取接入配置』」。
- `control_admin_rejected` / `control_auth_rejected` → 「服务商侧授权配置异常，请联系服务商」。
- 未知 `control_error` 原样显示，保留 1.2.196 的既有可观测性。
- 只有服务端明确 `rotated=false`（或 `rotate_skipped=true`）且三项凭据全同，才提示「服务端明确未签发新凭据（未轮换）；同一激活码可重兑并换发新凭据，请稍后再点『重新获取接入配置』；仍提示未签发新凭据时再向服务商索取新的 8 位激活码」。
- 缺少 `rotated` 字段按未知处理：返回「服务端未确认已换发新凭据，请稍后再点『重新获取接入配置』」，不误报成未轮换/需新码。
- 兼容顶层与 `control` 内的 `rotated`，兼容布尔、`"true"/"false"`、`1/0`。

## 2. epoch 单调与 exchange+写盘同锁（P1-3）

- 写 `control.json` 前读取盘上 `binding_epoch`；新值小于盘上已有值即丢弃本次结果，返回「已获取更新的接入配置，无需覆盖」，不改写文件、不重启 poller。
- 盘上 `binding_epoch` 从文件中直接解析，不要求整份旧 control 仍然结构合法。
- `activate_with_code()` 把 exchange 与最终写盘放在同一把 `_LOCK` 内，两个标签页用同一激活码并发时不会再出现旧响应后写覆盖新凭据。
- 写盘继续使用临时文件 `fsync` + `os.replace` + `0600`，状态文件不落 token。

## 3. poller 停止/退出不写假状态（P1-4）

- `agent/winport/agentpoll.py`：`stop_event` 已置位时，在途 401/网络失败只更新 agentpoll 自身状态，不写 `control-status.json` 的 `error`。
- 连续 2 次 poll 失败才写 `error`；首次失败只记日志。
- 任意一次成功 poll 立即写 `connected`，并清零失败计数，覆盖旧错误。
- poller 正常退出写 `disabled` +「接入服务已停止」；异常退出写 `error` +「接入服务异常退出：类型: 原因」。
- 写控制面状态前对 device token 做脱敏，避免异常文本把 token 带进状态文件。

## 4. 面板刷新与超时文案（P1-6/P2-7）

- `agent/winport/panel.py`：「用激活码激活」失败时也立即拉取一次 `/api/control-status` 刷新状态行，与「重新获取接入配置」入口一致；结果文本仍保留在 `#license-result`，不互相覆盖。
- 60 秒轮询超时时：若状态为 `disabled`，显示「飞书接入：接入服务已停止，请重启面板」；否则维持「连接中…（可稍后刷新页面）」。

## 5. 文档语义（P2-5）

- `CUSTOMER_README.txt`：改为「同一激活码可以重兑并换发新凭据，未连接先点『重新获取接入配置』；只有明确提示未签发新凭据/需要新的激活码时，才向服务商索取新的 8 位激活码」。
- `VERIFY.md`：版本更新到 1.2.200，新增本轮变更记录，并注明 1.2.199 的旧 README 语义已纠正。
- `VERSION`：`1.2.199` → `1.2.200`。

## 6. 包内静态自检降级（P2-8）

- `tools/static_verify.py`：`devsign` / `receipt_fixture` 改为可选导入。
- 包内缺少这些开发/测试模块时打印 `[SKIP]`，跳过依赖它们的检查并以 0 退出，不再抛 `ModuleNotFoundError`。
- 源码树内依赖齐全时仍执行全部 127 项检查；包内模拟缺模块时执行 114 项、跳过 10 项。

## 7. 回归用例

- `tests/test_control_bridge_1199.py`：新增 control_error 优先、rotated 缺失兼容、旧 epoch 丢弃、同码 exchange 串行、激活失败刷新状态行、停止后超时文案。
- `tests/test_control_bridge_1200.py`：新增首次 poll 失败不写 error、第二次写 error、成功覆盖 error、停止中不写 error、正常退出 disabled、异常退出 error + 脱敏原因。
- `tests/test_control_bridge_1197.py` / `tests/test_control_bridge_1198.py`：原「一次失败即 error」用例按 2 次失败去抖语义更新。

## 测试输出

### 客户端全量

```text
$ cd publish-control/client && python -m pytest tests -q
........................................................................ [ 76%]
......................                                                   [100%]
94 passed, 4 warnings in 1.62s
```

### publish-control 全量

```text
$ cd publish-control && python -m pytest tests -q
........................................................................ [ 61%]
...............ssss................ssssssssss                            [100%]
103 passed, 14 skipped, 24 warnings in 8.58s
```

### 静态验收（源码树）

```text
$ cd publish-control/client && python tools/static_verify.py
------------------------------------------------------------
STATIC VERIFY: 127/127 checks passed, 0 skipped
------------------------------------------------------------
```

### 静态验收（模拟客户包缺 devsign/receipt_fixture）

```text
[SKIP] licence (Ed25519, machine-bound)  -- devsign unavailable in this package
[SKIP] approved mode needs a control-plane receipt  -- devsign/receipt_fixture unavailable in this package
[SKIP] simulated driver refused without opt-in (no auto-submit)  -- devsign/receipt_fixture unavailable in this package
[SKIP] harness: approved publish reads back a platform work id  -- devsign/receipt_fixture unavailable in this package
[SKIP] idempotency blocks a second publish  -- devsign/receipt_fixture unavailable in this package
[SKIP] signature from another key is refused  -- devsign unavailable in this package
[SKIP] E licence expiry notices  -- devsign unavailable in this package
[SKIP] licence import installs a valid, correctly-bound licence  -- devsign unavailable in this package
[SKIP] licence import refuses another machine's licence  -- devsign unavailable in this package
[SKIP] licence import refuses a bad-signature licence  -- devsign unavailable in this package
STATIC VERIFY: 114/114 checks passed, 10 skipped
```

### 文件编码

```text
$ cd publish-control/client && python tools/check_encodings.py --root .
RESULT: OK -- every .ps1/.bat/.cmd/.vbs and every project text file obeys the policy
```

## 变更文件

- `publish-control/client/agent/winport/activation.py`
- `publish-control/client/agent/winport/agentpoll.py`
- `publish-control/client/agent/winport/panel.py`
- `publish-control/client/tools/static_verify.py`
- `publish-control/client/tests/test_control_bridge_1197.py`
- `publish-control/client/tests/test_control_bridge_1198.py`
- `publish-control/client/tests/test_control_bridge_1199.py`
- `publish-control/client/tests/test_control_bridge_1200.py`
- `publish-control/client/CUSTOMER_README.txt`
- `publish-control/client/VERIFY.md`
- `publish-control/client/VERSION`
- `review/FIX_REPORT_1.2.200.md`

## 未验证项

- 未在 Windows 实机验证面板点击、真实服务端 rotate、飞书往返与真实发布/抓数。
- 未打包，因此未重算 `MANIFEST.json` / `SHA256SUMS.txt` / `PACKAGE_BINDING.json`。
- 1.2.199 复核中的 P0「飞书会话预绑定」属于服务端/运营流程，不在本客户端分支范围。
