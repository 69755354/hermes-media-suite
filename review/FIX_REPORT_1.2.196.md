# FIX_REPORT 1.2.196 — 接入闭环 P0 修复

## 结论

- 分支：`fix/control-bridge-1.2.196`（基线 tag `v1.2.195`，commit `e411885`）
- 范围：只改 `publish-control/client`
- 已修：P0-1、P0-2、P0-3、P0-4，以及 P1-1、P1-2；顺手修 P1-3 状态路径与 P2-1/P2-2 健壮性
- 未执行：tag、打包、上传
- 未改：license 签名/校验/试用规则、服务端、依赖
- 新增写盘：`control.json` / `control-status.json` 均为同目录临时文件 + `fsync` + `os.replace`，权限 `0600`；状态文件不含 token

## P0-1 poller 的 `--data` 必须等于 worker 数据根

**改法**

- `main._single_root_for()`：默认 `single_root=True`；仅当 `normalize_customer_id(customer_id)` 非 `default`、`<data>/customers/<id>` 存在且 `<data>/inbox` 不存在时返回 `False`。
- `_start_agentpoll()` 把该判定传给 `AgentConfig.from_env(..., single_root=single_root)`；因此 `build_argv()` 的 `--data` 和 `_worker_env()` 的 `WINPORT_DATA` 都指向 worker/面板同一个数据根。
- 同时显式把 agentpoll 的 `status_file` 固定到 `<data>/run/agentpoll-status.json`，消除 P1-3 的主进程/poller 状态路径分叉。

**证据**

- `publish-control/client/agent/winport/main.py:177-192`：`_single_root_for()` 判定规则
- `publish-control/client/agent/winport/main.py:240-250`：传入 `single_root` 与统一 `status_file`
- `publish-control/client/tests/test_control_bridge_1196.py:94-118`：标准布局 `--data == layout.data`；历史租户布局 `--data == <data>/customers/<id>`
- `publish-control/client/tests/test_control_bridge_1196.py:120-142`：无效 `data/control.json` 不再阻断 `program/control.json`

## P0-2 已有正式授权时也要能补接入

**改法**

- `activate_with_code()` / `activate()` 的早返回改为：只有“正式授权有效 **且** `control.json` 合法”才直接返回；`control.json` 缺失/无效时继续走一次 exchange。
- 补接入时不再要求重新安装授权：已有正式授权只更新 control，不覆盖已有 license；exchange 返回的 license 不会回退已有授权。
- 新增 `_bridge_control()` 统一处理 `control` / `control_error`；`_complete_existing_control()` 返回授权成功但接入可能未完成的结果。
- 提示文案改为「授权已生效，接入已补齐」/「授权已生效，但接入未完成：<原因>」。
- 新增 `refresh_control(layout, code=None)` 供面板「重新获取接入配置」按钮调用；无激活码时提示客户输入。

**证据**

- `publish-control/client/agent/winport/activation.py:113-125`：`_has_valid_control()` 同时检查 `<data>/control.json` 与 `program/control.json`
- `publish-control/client/agent/winport/activation.py:128-167`：`_bridge_control()`、`_install_with_control()`、`_complete_existing_control()`
- `publish-control/client/agent/winport/activation.py:216-239`：有正式授权且无 control 时仍执行 exchange
- `publish-control/client/agent/winport/activation.py:300-350`：`activate()` 同样补接入
- `publish-control/client/agent/winport/activation.py:373-397`：`refresh_control()`
- `publish-control/client/tests/test_control_bridge_1196.py:150-177`：有效正式授权 + 无 control -> exchange 1 次、control 生成、license 不被覆盖
- `publish-control/client/tests/test_control_bridge_1196.py:179-208`：`control_error` -> 授权不变、提示含原因
- `publish-control/client/tests/test_control_bridge_1196.py:210-228`：exchange 超时 -> 授权仍有效、状态为 error

## P0-3 / P0-4 接入状态要能被客户看见

**改法**

- 新增 `control_status.py`：原子写 `<data>/control-status.json`（`0600`），字段固定为 `state` / `reason` / `updated` / `customer_id` / `device_id`，状态取 `connected|missing|error|disabled`，不写 token。
- 写 control 成功 -> `connected`；exchange 返回 `control_error` -> `error` + 原因；无 control -> `missing`；poller 启动失败/缺 token/配置错误 -> `disabled` + 原因。
- 面板 `control_banner()` 以磁盘上的合法 `control.json` 为真相来源，状态文件只补充原因；授权区块常驻一行「飞书接入：已连接 / 未连接（原因）」。
- 面板新增「重新获取接入配置」按钮，调用 `/api/control-refresh`；输入框为空时提示输入 8 位激活码，输入后走一次 exchange。
- 激活结果不再依赖 900ms 临时消息：结果写入 `control-status.json`，页面刷新后仍由状态行常驻显示；激活成功后不再自动 `location.reload()` 冲掉结果。

**证据**

- `publish-control/client/agent/winport/control_status.py:16-57`：状态枚举、字段、原子写、`0600`
- `publish-control/client/agent/winport/activation.py:139-145`：connected / error / missing 写入点
- `publish-control/client/agent/winport/main.py:211-212,230-232,256-257,263-265,271-274,283-293`：disabled / missing / connected 写入点
- `publish-control/client/agent/winport/panel.py:422-460`：`control_banner()`
- `publish-control/client/agent/winport/panel.py:1217-1226`：状态行与「重新获取接入配置」按钮
- `publish-control/client/agent/winport/panel.py:1297-1317`：`refreshControl()` 调用 `/api/control-refresh`
- `publish-control/client/agent/winport/panel.py:1624-1630`：`/api/control-refresh`、`/api/control-status`
- `publish-control/client/tests/test_control_bridge_1196.py:231-258`：面板显示 error 原因、刷新按钮、connected 状态；无激活码提示输入

## P1-1 README / VERIFY 口径

- `CUSTOMER_README.txt:11,13,32,38,42`：明确「试用期内飞书发布/抓取不可用，需要激活后自动接入」，并说明「飞书接入：已连接」才算开通完成；删除了“试用期可直接在飞书发布”的说法。
- `VERIFY.md:1,3,5,17-23`：标题与当前版本更新到 1.2.196，并补充本轮 P0 变更说明。
- `VERSION`：更新为 `1.2.196`。

## P1-2 复查线程

**改法**

- 新增 `CONTROL_RECHECK_MAX_SECONDS = 24 * 60 * 60`。
- `_is_auth_failure()` 只把 `auth_error`、401/403、authentication/unauthorized/forbidden、鉴权/认证失败视为显式失败。
- `_control_recheck_loop()`：显式鉴权失败立即停；其他启动/连接/超时失败返回 `retry`，继续按 30 秒重试；超过 24 小时预算后停止。

**证据**

- `publish-control/client/agent/winport/main.py:30-31`：30 秒与 24 小时常量
- `publish-control/client/agent/winport/main.py:317-326`：鉴权失败分类
- `publish-control/client/agent/winport/main.py:345-387`：复查单次结果与循环预算
- `publish-control/client/tests/test_control_bridge_1196.py:261-319`：401 停止、瞬时失败继续、24 小时预算退出

## 附带修复

- P1-3：`status_file` 固定到 `<data>/run/agentpoll-status.json`（`main.py:248`），主进程与 poller 读同一个 marker。
- P2-1：`_start_agentpoll()` 改用 `_valid_control_file()`，空/无效 `data/control.json` 不再阻断 `program/control.json` 回退（`main.py:214-232,329-342`）。
- P2-2：control 字段读取改为 `if key in control_data and control_data[key] is not None`，数字 `0` 不再被 `or ""` 丢弃（`main.py:225-228`）。

## 测试输出

### `cd publish-control/client && python3 -m pytest tests -q`

```text
.......................................................                  [100%]
=============================== warnings summary ===============================
tests/test_customer_onboarding_1192.py::test_bootstrap_trial_failure_is_explicit_in_console_and_install_log
tests/test_customer_onboarding_1192.py::test_bootstrap_trial_success_passes_handover
  /home/ubuntu/build/hermes-media-suite/publish-control/client/scripts/bootstrap_py.py:433: DeprecationWarning: invalid escape sequence '\p'
    """Resolve every historical Run-key launcher form to its product root.

tests/test_customer_onboarding_1192.py::test_bootstrap_trial_failure_is_explicit_in_console_and_install_log
tests/test_customer_onboarding_1192.py::test_bootstrap_trial_success_passes_handover
  /home/ubuntu/build/hermes-media-suite/publish-control/client/scripts/bootstrap_py.py:1274: DeprecationWarning: invalid escape sequence '\L'
    """Stop old supervisors/agents BEFORE anything writes into the venv.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
55 passed, 4 warnings in 1.39s
```

### `cd publish-control && python3 -m pytest tests -q`

```text
........................................................................ [ 61%]
...............ssss................ssssssssss                            [100%]
=============================== warnings summary ===============================
tests/test_bootstrap_purge.py: 12 warnings
  /home/ubuntu/build/hermes-media-suite/publish-control/client/scripts/bootstrap_py.py:433: DeprecationWarning: invalid escape sequence '\p'
    """Resolve every historical Run-key launcher form to its product root.

tests/test_bootstrap_purge.py: 12 warnings
  /home/ubuntu/build/hermes-media-suite/publish-control/client/scripts/bootstrap_py.py:1274: DeprecationWarning: invalid escape sequence '\L'
    """Stop old supervisors/agents BEFORE anything writes into the venv.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
103 passed, 14 skipped, 24 warnings in 13.44s
```

### `cd publish-control/client && python3 tools/static_verify.py`

```text
------------------------------------------------------------
STATIC VERIFY: 127/127 checks passed
------------------------------------------------------------
```

## 未覆盖

- 未在 Windows 实机执行安装、真实 Chrome 登录、真实抖音发布、Task Scheduler/VBS 路径。
- 未对生产控制面做在线联调；P0-1/P0-2/P0-3/P0-4 的回归均使用本地最小 harness。
