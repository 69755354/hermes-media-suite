# 1.2.197 修复报告（1.2.196 复核残留 P0）

基线：`v1.2.196`（`e6dcc7045e04f95d303a31e92ea6130bca6c31c1`）

分支：`fix/control-bridge-1.2.197`

范围：只改 `publish-control/client`；未改服务端、license 校验；未新增依赖；未 tag、未打包、未上传。

## P0-1：历史分租户布局判定被 `ensure()` 破坏

### 改法

不再用“`<data>/customers/<id>` 存在且 `<data>/inbox` 不存在”判定历史布局。改为检查租户目录内的稳定产物：`config|run|inbox|out|system|accounts.json`（含 `config/accounts.json`）任一存在即视为历史租户布局，与共享根 `inbox` 是否存在无关。标准专用机仍走 `<data>` 单根。

- `agent/winport/main.py:33-44`：新增 `TENANT_LAYOUT_MARKERS`。
- `agent/winport/main.py:190-216`：`_single_root_for()` 改为按租户目录内标记判定；目录不存在或无标记时仍返回单根。

### 回归

- `tests/test_control_bridge_1197.py:94-107`：走真实 `main.run(["--data", ...])`，在 `Layout(...).ensure()` 之后断言标准布局 `--data == <data>`。
- `tests/test_control_bridge_1197.py:110-124`：同样走真实启动路径，先创建 `<data>/customers/c_123/run`，断言 `ensure()` 已创建 `<data>/inbox` 后，历史布局仍为 `single_root=False` 且 `--data == <data>/customers/c_123`。
- `tests/test_control_bridge_1196.py:100-114`：原历史布局回归改为使用租户内 `run` 标记，不再手工删除 `inbox`、不再绕过生产路径。

## P0-4：运行期接入失败仍显示“已连接”+ 状态行不刷新

### 1. 面板状态优先级

`control_banner()` 仍以合法 `control.json` 作为配置存在依据，但若 `control-status.json` 的状态为 `error/disabled` 且其 `updated >= control.json mtime`，则优先显示“未连接（原因）”，不再被合法 control 遮住。

- `agent/winport/panel.py:422-471`：读取首个有效 control 文件及其 mtime；较新的运行期 `error/disabled` 优先返回未连接状态。
- `agent/winport/panel.py:472-485`：只有没有更新失败状态时才按合法 control 显示“已连接”。

### 2. poller 运行期回写状态

- `agent/winport/agentpoll.py:1025-1048`：`auth_error/poll_error` 回写 `control-status.json`；401/403 等原因写入「接入凭据失效」，其余连接/超时写入「控制面连不上」。
- `agent/winport/agentpoll.py:1050-1062`：状态写入为 best-effort，捕获所有异常只记日志，不影响 poller 主循环；成功后写 `connected`。
- `agent/winport/agentpoll.py:1078-1086`：`run_once()` 首次/每次成功 poll 后写 `connected`。
- `agent/winport/agentpoll.py:1192`、`agent/winport/agentpoll.py:1266`：单通道/多通道路径均在成功 poll 后写 `connected`，失败路径经 `_note_error()` 写 `error`。
- `agent/winport/main.py:312-317`：启动 poller 线程后不再立即写 `connected`；`connected` 只由真实成功 poll 产生。
- `agent/winport/control_status.py:20-31`：状态路径同时接受 `Layout.data` 与 `CustomerLayout.root`；既有原子替换、`0600`、不落 token 的写盘逻辑保持不变（`control_status.py:41-72`）。

### 3. 面板前端原地刷新

激活成功、自动授权成功或点「重新获取接入配置」返回后，拉一次 `/api/control-status`，只更新 `#control-status-line` 的文本和 `st-ok/st-warn/st-bad` class（同时同步内部状态点），不整页刷新、不覆盖 `#license-result` 结果文本。

- `agent/winport/panel.py:1288-1311`：新增 `controlStatusClass()`、`applyControlStatus()`、`refreshControlStatusLine()`。
- `agent/winport/panel.py:1323`：自动授权成功后刷新状态行。
- `agent/winport/panel.py:1342`：激活码激活成功后刷新状态行。
- `agent/winport/panel.py:1361`：「重新获取接入配置」返回后刷新状态行。

### 回归

- `tests/test_control_bridge_1197.py:144-161`：合法 control + 更新的 `error/disabled`，断言面板不是 `connected`，并分别断言 `bad/warn` 级别与原因。
- `tests/test_control_bridge_1197.py:164-174`：旧失败状态早于新 control 文件时，不遮住新配置。
- `tests/test_control_bridge_1197.py:194-224`：合法 control + poller 401/403/网络超时，断言落盘为 `error`、原因为「接入凭据失效」或「控制面连不上」、面板不是 `connected`、状态文件 `0600` 且不含 token。
- `tests/test_control_bridge_1197.py:227-239`：首次成功 poll 写 `connected`。
- `tests/test_control_bridge_1197.py:242-256`：状态写盘失败不影响 poll 主循环。
- `tests/test_control_bridge_1197.py:259-450`：Node DOM 回归真实执行面板 JS，断言激活/重新获取后状态行文本与 class 原地更新、结果文本保留、页面不刷新（`location.reload` 被设为抛错）。

## 版本与文档

- `VERSION`：`1.2.196` → `1.2.197`。
- `VERIFY.md`：更新当前版本与本轮变更说明。

## 测试输出

### 定向回归

```text
$ cd publish-control/client && python -m pytest tests/test_control_bridge_1195.py tests/test_control_bridge_1196.py tests/test_control_bridge_1197.py -q
....................................                                     [100%]
36 passed in 0.61s
```

### 客户端全量

```text
$ cd publish-control/client && python -m pytest tests -q
....................................................................     [100%]
68 passed, 4 warnings in 1.01s
```

### publish-control 全量

```text
$ cd publish-control && python -m pytest tests -q
........................................................................ [ 61%]
...............ssss................ssssssssss                            [100%]
103 passed, 14 skipped, 24 warnings in 16.77s
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

- `publish-control/client/agent/winport/main.py`
- `publish-control/client/agent/winport/panel.py`
- `publish-control/client/agent/winport/agentpoll.py`
- `publish-control/client/agent/winport/control_status.py`
- `publish-control/client/tests/test_control_bridge_1196.py`
- `publish-control/client/tests/test_control_bridge_1197.py`（新增）
- `publish-control/client/VERSION`
- `publish-control/client/VERIFY.md`
- `review/FIX_REPORT_1.2.197.md`

## 未验证项

- Windows 实机上的真实控制面 401/403、DNS/超时、面板浏览器 DOM 表现仍需实机验收。
- 未打包，因此未重算 `MANIFEST.json` / `SHA256SUMS.txt` / `PACKAGE_BINDING.json`。
