# FIX_REPORT 1.2.195 — 客户端 control 配置桥接

## 结论

- 分支：`fix/control-bridge-1.2.195`（基线 `v1.2.194`）
- 已完成：兑换响应中的 `control` 在授权安装成功后原子落盘；启动时 `agentpoll disabled` 会每 30 秒复查 `control.json`。
- 未执行：tag、打包、上传。
- 未改：license 校验/签名/试用逻辑、面板、依赖。
- token 不写日志；`control.json` 仅落盘，权限 0600。

## 变更摘要

### `agent/winport/activation.py`

- `exchange()` 现在返回完整响应对象（含 `license` 与可选 `control`），不再只返回 `license`。
- 新增 `is_valid_control()`：要求六个字段齐全；`control_url` 为 `https` 且有主机；`customer_id` / `device_id` 非空；`customer_token` / `device_token` 非空。
- 新增 `_write_control_config()`：写入 `<layout.data>/control.json`，使用同目录临时文件 + `fsync` + `os.replace`，并将文件权限设为 `0600`。
- 新增 `_install_with_control()`：先调用原有 `install_document()`；仅在其成功后尝试写 control。
  - 合法且有响应：`reason` 追加 `接入已配置`。
  - 缺失/非法：静默忽略，授权照常成功，`reason` 不宣称已接入。
  - 写盘失败：授权仍成功，`reason` 诚实提示 `接入配置保存失败`，不回滚授权。
- `activate()` 与 `activate_with_code()` 均改为从完整响应中取 `license`，并传入可选 `control`。

### `agent/winport/main.py`

- 新增 `CONTROL_RECHECK_INTERVAL = 30.0`。
- 新增 `_agentpoll_marker_state()`：读取 `run/agentpoll-status.json` 的启动状态。
- 新增 `_valid_control_file()`：按 `<data>/control.json`、`<program>/control.json` 顺序查找合法 control。
- 新增 `_control_recheck_once()` / `_control_recheck_loop()`：
  - 仅在启动结果为 `disabled` 时启动复查线程。
  - 使用 `stop_event.wait(30)`，无紧循环。
  - 合法文件出现后只尝试启动一次；成功或明确失败后停止复查。
  - 复查线程成功拿到 poller 后放入共享槽，主进程退出时统一 `stop()`。
- 初始 poller 正常运行时不会启动复查，不影响已有 poller。

### `tests/test_control_bridge_1195.py`（新增，10 个用例）

- 合法 control：文件写入、内容与响应一致、权限 0600、无临时文件残留。
- `activate()` 在线兑换路径同样写 control。
- 无 control / 缺字段 / http URL / 空 customer token / 空 device token：不写文件，授权仍成功。
- `exchange()` 返回完整响应。
- 主循环复查：`control.json` 出现后桩 `AgentPoller` 只启动一次，不联网。
- 复查循环在首次成功后退出。

## Diff 摘要

```text
 publish-control/client/agent/winport/activation.py | 71 +++++++++++++++--
 publish-control/client/agent/winport/main.py       | 88 +++++++++++++++++++++-
 tests/test_control_bridge_1195.py                  | 241 +++++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 391 insertions(+), 9 deletions(-)
```

## 测试输出

### `python3 -m pytest tests -q`

执行目录：`publish-control/client`

```text
..........................................                               [100%]
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
42 passed, 4 warnings in 0.60s
```

### `python3 tools/static_verify.py`

执行目录：`publish-control/client`

```text
== fingerprint ==
[PASS] fingerprint is deterministic
[PASS] fingerprint changes with a component
== licence (Ed25519, machine-bound) ==
[PASS] valid licence -> OK
[PASS] copied licence -> MACHINE_MISMATCH
[PASS] tampered licence -> SIGNATURE_INVALID
== manifest validation ==
[PASS] generated manifest is valid
[PASS] folder_key with space rejected
[PASS] bad sha256 rejected
== folder binding (exact whitelist) ==
[PASS] unknown folder -> UNKNOWN_FOLDER
== downlink: fetch -> verify -> bind -> ready ==
[PASS] two pieces downloaded  -- {"downloaded": 2, "folders": "READY"}
[PASS] folder bound READY
[PASS] re-run fetches nothing new
[PASS] ledger carries no secrets
== data collection (13 columns) ==
[PASS] 13 columns accepted
[PASS] column drift blocked
== report (xlsx that Excel/WPS can open) ==
[PASS] daily report xlsx written and valid  -- /tmp/winport-verify-gqs39hye/data/out/reports/日报_2026-11-08.xlsx
== publish gate ==
[PASS] fill mode also refuses a simulated driver without opt-in
[PASS] fill mode never publishes (harness, opt-in)
[PASS] approved mode needs canary
[PASS] approved mode needs a control-plane receipt
[PASS] simulated driver refused without opt-in (no auto-submit)
[PASS] harness: approved publish reads back a platform work id
[PASS] idempotency blocks a second publish
== redaction ==
[PASS] presigned/cookie/bearer redacted
== G1 vendor public key ==
[PASS] config/vendor_pubkey.hex ships
[PASS] vendor key is 32 bytes of hex
[PASS] vendor key is a usable Ed25519 point  -- on curve, not identity, not small order
[PASS] signature from another key is refused
== G2 launcher interpreter ==
[PASS] launcher.vbs prefers the venv pythonw
[PASS] launcher.vbs never falls back to the bundled runtime
[PASS] launcher.vbs sets PLAYWRIGHT_BROWSERS_PATH
[PASS] run-agent.vbs prefers the venv pythonw
[PASS] run-agent.vbs never falls back to the bundled runtime
[PASS] run-agent.vbs sets PLAYWRIGHT_BROWSERS_PATH
== G3 multi-platform login slots ==
[PASS] platform slot present: douyin
[PASS] platform slot present: xingtu
[PASS] platform slot present: shipinhao
[PASS] platform slot present: xiaohongshu
[PASS] platform slot present: gongzhonghao
[PASS] every slot owns a distinct profile dir
[PASS] every CDP slot owns a distinct debug port
[PASS] WebKit slot does not pretend to have a CDP port
[PASS] login check refuses to say OK without cookie evidence  -- douyin.com 下 0 条 cookie → 未登录或登录态已失效，请在该通道窗口里重新扫码
[PASS] login check reports cookie + backend as evidence  -- cookie 2 条（douyin.com）+ https://creator.douyin.com/ 可达（HTTP 200）
[PASS] panel renders a status card per platform
[PASS] panel offers one-click login and re-check
[PASS] panel /api/open routes to the slot opener
[PASS] panel refuses an unknown channel
== publish cadence (1.2.20) ==
[PASS] cadence default windows are the four natural time bands  -- [['07:00', '09:30'], ['11:00', '13:30'], ['17:00', '19:30'], ['20:00', '22:30']]
[PASS] cadence defaults leave the per-account daily cap unlimited
[PASS] cadence backoff doubles from 30 minutes and caps at six hours
[PASS] panel renders the publish-cadence controls
== real Chrome (source/extra-requirements-chrome.md) ==
[PASS] per-slot command carries --user-data-dir + --remote-debugging-port  -- /tmp/winport-verify-gqs39hye/Google/Chrome/Application/chrome.exe --user-data-dir=/tmp/winport-verify-gqs39hye/data/profiles/douyin --remote-debugging-port=9224 --no-first-run --no-default-browser-check --new-window --remote-allow-origins=http://127.0.0.1 --disable-gpu --disable-gpu-compositing --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --window-size=1440,900 --window-position=80,60 --disable-features=ExternalProtocolDialog,Translate,CalculateNativeWinOcclusion https://creator.douyin.com/
[PASS] no Chrome -> the caller gets the "需要 Google Chrome" sentence (official installer + official page)  -- 本程序需要 Google Chrome（只认官方正版 Chrome，不用 Microsoft Edge、Chromium 或其它浏览器顶替）。这台电脑上没检测到 Google Chrome。怎么装（二选一）：① 用随包附
[PASS] no in-package Chromium is consulted any more
[PASS] launch never uses the customer's default profile dir
[PASS] Chrome launch disables the native external-protocol dialog  -- C:/chrome.exe --user-data-dir=C:/prof/env_1 --remote-debugging-port=9224 --no-first-run --no-default-browser-check --new-window --remote-allow-origins=http://127.0.0.1 --disable-gpu --disable-gpu-compositing --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --window-size=1440,900 --window-position=80,60 --disable-features=ExternalProtocolDialog,Translate,CalculateNativeWinOcclusion https://creator.douyin.com/
[PASS] Chrome version floor is recorded
== environments (source/env-design.md) ==
[PASS] four phase-1 environments are registered  -- ['env_1', 'env_2', 'env_wechat', 'env_xhs']
[PASS] env ports are 9224..9227
[PASS] environments config validates clean
[PASS] every environment has a reserved (empty) proxy field
[PASS] each environment owns exactly one profile dir  -- {'env_1': {'/tmp/winport-verify-gqs39hye/data/profiles/env_1'}, 'env_2': {'/tmp/winport-verify-gqs39hye/data/profiles/env_2'}, 'env_wechat': {'/tmp/winport-verify-gqs39hye/data/profiles/env_wechat'}, 'env_xhs': {'/tmp/winport-verify-gqs39hye/data/profiles/env_xhs'}}
[PASS] panel renders one card per opened environment (抖音/星图 only)
[PASS] panel shows each platform light inside its environment card
[PASS] panel hides WeChat / Xiaohongshu instead of greying them out
[PASS] only the dropped platform is alerted
== G4.1 shortcut icon ==
[PASS] assets/app.ico ships
[PASS] app.ico is a valid multi-size ICO  -- 5 sizes, 302430 bytes
[PASS] make-shortcut.ps1 uses the icon and says so when it is missing
== per-account authorisation ==
[PASS] a seat that is not in the licence is refused
[PASS] a disabled seat does not affect its neighbours
[PASS] seats are counted per platform
== A dry-run / B evidence / C idempotency / D state / E expiry ==
[PASS] A dry-run passes a valid plan and mints a confirm token
[PASS] A dry-run blocks a plan with no title
[PASS] B failure evidence keeps png+html+index with env in the name
[PASS] B prune removes the evidence and the index row
[PASS] C idempotency key = material + env + window (stable in a window)
[PASS] D state machine: never logged in vs dropped vs rate-limited
[PASS] D alerts name only the affected environment
[PASS] E expiry notice fires the 7-day threshold
[PASS] E expired licence blocks publish but not collect/data
== 1.2.1 self-service install chain ==
[PASS] `winport machine-code` subcommand exists
[PASS] `winport license-import` subcommand exists
[PASS] 机器码 written to <logs>/机器码.txt
[PASS] 机器码 file carries the code + the 3 next steps
[PASS] licence import installs a valid, correctly-bound licence  -- 授权已导入并生效。
[PASS] licence import refuses another machine's licence
[PASS] licence import refuses a bad-signature licence
[PASS] show-machine-code.ps1 drives `winport`
[PASS] show-machine-code.ps1 drives `machine-code`
[PASS] import-license.ps1 drives `license-import`
[PASS] panel.ps1 drives `agent-ready.json`
[PASS] panel.ps1 drives `healthz`
[PASS] show-machine-code.vbs wrapper ships
[PASS] import-license.vbs wrapper ships
[PASS] import-license-shortcut.cmd ships for drag-and-drop
[PASS] bootstrap.ps1 shows + writes the machine code
[PASS] bootstrap.ps1 verifies every desktop entry and its target
[PASS] make-shortcut.ps1 creates only the single fixed shortcut
[PASS] make-shortcut.ps1 uses powershell.exe, not wscript/.vbs targets
[PASS] bootstrap.bat entry point ships
[PASS] show-machine-code.bat entry point ships
[PASS] import-license.bat entry point ships
[PASS] a license drop folder README ships
== browser: Google Chrome only (no Edge/Chromium fallback) ==
[PASS] Chrome present -> used (tier 1, engine=chrome)  -- engine=chrome tier=1 path=/tmp/winport-verify-gqs39hye/t1/localappdata/Google/Chrome/Application/chrome.exe
[PASS] no Chrome (Edge present) -> STOP, Edge is NEVER used  -- engine=None tier=None found=False
[PASS] Edge detected only as diagnostics ('不参与运行'), not as an engine  -- edge.present=True tiers=['chrome'] ENGINE_TIERS=('chrome',)
[PASS] no Chrome, no Edge -> same stop + official installer + official page  -- 本程序需要 Google Chrome（只认官方正版 Chrome，不用 Microsoft Edge、Chromium 或其它浏览器顶替）。这台电脑上没检测到 Google Chrome。怎么装（二选一）：① 用随包附带的官方离线安装包 chrome-offline\ChromeStandalon
[PASS] the stop message never offers Edge/Chromium as a substitute
[PASS] Chrome launch argv keeps isolation, no Edge-only flags
[PASS] build_launch_args REFUSES msedge.exe (no silent substitution)  -- ConfigError raised for msedge.exe
[PASS] engine identity helpers still name Edge, but only for detection
[PASS] CDP identity maps Edg/ -> edge and Chrome/ -> chrome (report only)
[PASS] the bundled official Chrome installer is declared in code
== 1.2.21 publish-driver guard ==
[PASS] publish selector policy has zero class / fuzzy-text candidates
[PASS] publish button uses exact semantic selectors only  -- ("button:text-is('立即发布')", "button:text-is('发布')", "[role='button'][aria-label='发布']", "[data-e2e='publish']")
[PASS] class and fuzzy negative selectors are rejected
[PASS] upload guard rejects preexisting title + missing request
[PASS] transcode guard rejects button-enabled-before-done
[PASS] work id binding accepts exactly one bound candidate
[PASS] work id binding rejects another account link
[PASS] humanize delay records carry sampled/realised and validate
[PASS] fault hold is persistent and not released by non-ONLINE
[PASS] ONLINE does not release a fault hold
[PASS] explicit manual resolution clears hold
[PASS] runtime literal forbidden-pattern scan (not variable-delay proof)  -- {
  "runtime_hits": [],
  "runtime_allowed": [
    {
      "file": "agent/winport/publish_exec.py",
      "line": 5022,
      "kind": "fixed_wait",
      "text": "time.sleep(0.8)",
      "marker": "wait-ok: poll"
    },
    {
      "file": "agent/winport/publish_exec.py",
      "line": 6893,
      "kind": "fixed_wait",
      "text": "time.sleep(0.4)",
      "marker": "wait-ok: poll"
    },
    {
      "file": "agent/winport/publish_exec.py",
      "line": 6945,
      "kind": "fixed_wait",
      
------------------------------------------------------------
STATIC VERIFY: 127/127 checks passed
------------------------------------------------------------
```

## 手工验证命令

以下命令在客户端目录（Windows 安装目录或源码 `publish-control/client`）执行。不要打印或粘贴 token 值。

### 1. 复跑自动化验收

```bash
cd publish-control/client
python3 -m pytest tests -q
python3 tools/static_verify.py
```

### 2. 激活后检查 control.json（不输出 token）

Linux/macOS：

```bash
python3 - <<'PY'
import json, os, stat
from pathlib import Path
p = Path(os.environ["WINPORT_DATA"]) / "control.json"
data = json.loads(p.read_text(encoding="utf-8"))
print("fields:", sorted(data))
print("mode:", oct(stat.S_IMODE(p.stat().st_mode)))
print("https:", data["control_url"].startswith("https://"))
print("ids_present:", bool(data["customer_id"]), bool(data["device_id"]))
print("tokens_present:", bool(data["customer_token"]), bool(data["device_token"]))
PY
```

Windows PowerShell：

```powershell
$data = Join-Path $env:LOCALAPPDATA 'HuolongAgent\publish-worker'
$control = Join-Path $data 'control.json'
Test-Path $control
(Get-Content $control -Raw | ConvertFrom-Json).PSObject.Properties.Name
icacls $control
```

预期：六个字段存在；`control_url` 为 `https`；token 非空；日志与终端均不出现 token 明文。

### 3. 验证“晚到 control.json”复查

1. 先恢复/制造启动时 `disabled` 状态（例如暂时移走 `control.json`），启动 agent。
2. 在 `logs/agent.out` 中看到：

```text
agentpoll disabled at startup; rechecking control.json every 30s
```

3. 放入合法 `control.json`，等待不超过约 30 秒，日志应出现：

```text
control.json ready at ...; retrying agentpoll startup
agentpoll started customer=... control=https://...
```

4. 检查 `run/agentpoll-status.json` 中 `state` 进入 `polling`（或后续正常状态）。

```powershell
$data = Join-Path $env:LOCALAPPDATA 'HuolongAgent\publish-worker'
Get-Content (Join-Path $data 'logs\agent.out') -Tail 100 | Select-String 'agentpoll|control.json'
Get-Content (Join-Path $data 'run\agentpoll-status.json') -Raw
```

### 4. 验证失败不影响授权

- 使用缺少字段、`http://` URL 或空 token 的 control 响应激活。
- 预期：授权成功、`control.json` 不生成、激活提示不包含“接入已配置”。
- 若 control 写盘失败（磁盘满/权限不足），预期：授权仍成功，提示“接入配置保存失败”，不会回滚 license。

## 边界与安全说明

- `control.json` 内含 `customer_token` / `device_token`，属于敏感文件；实现只在内存与 0600 文件中处理，不写日志。
- 复查只读取本机 `<data>` 与 `<program>` 下的固定文件名，不访问网络；真正的网络轮询仍由 `AgentPoller` 负责。
- 复查线程是 daemon，并受统一 stop event 控制；主进程退出时会对晚启动的 poller 调用 `stop()`。
- 初始 `import_error` / `config_error` 不进入复查，避免对坏安装/坏配置做无意义重试。
