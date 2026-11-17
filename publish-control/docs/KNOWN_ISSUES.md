# 发布助手（publish-control / 火龙发布机器人）问题清单

更新：2026-11-17（对应 1.2.219 交付）。只列能复现、能指到文件的问题；每条给证据。

## 一、已修（1.2.216 → 1.2.219）

| 版本 | 问题 | 修法 |
|---|---|---|
| 1.2.217 | 发布浏览器卡死后被当成"标签复用"继续往下走，实际页面没起来 | `launch_environment` 加真实 CDP 握手判定（`alive_probe` 两次探测 + 退避），握手不通就杀进程重启；`reason` 不再报 `TAB_REUSED` |
| 1.2.218 | OTA 补丁不完整 → 客户「升级→起不来→回滚」死循环（1.2.188–1.2.191 报 `ModuleNotFoundError: winport.process_identity`） | 补丁补齐 1.2.188→目标版本所有改动文件（23→34 个），`min_version` 改为 1.2.192 重签上线；新增 `tools/patch_coverage_check.py` 与 `tools/ota_patch.py check/gate` |
| 1.2.219 | 非管理员客户机上旧计划任务删不掉 → 安装中断 | `bootstrap_py.py` 改 `schtasks /Change` 复用旧任务并直接拉起，接管是否成功交给 handover 判定（任务不存在但 HKCU Run 已注册 → WARNING 继续；旧任务确实接管失败 → 仍 FATAL） |

## 二、未解问题（按优先级）

### P0-1 远程协助通道默认开启
- 证据：`client/agent/winport/settings.py:15` → `"remote_channel": {"enabled": True}`；`panel.py:849` 面板复选框默认勾选。
- 后果：客户机装完即处于"可被远程执行命令"的状态，客户从未被告知。任何拿到服务端凭据的一侧都能在客户机跑任意命令。
- 建议：默认 `False`，只有在客户知情同意后由面板/授权文件显式打开；打开动作写进日志。**（这是原定下一项）**

### P0-2 Windows 上凭据文件没有 0600 等价保护
- 证据：`activation.py:85-98` 把 `control.json`（含 `customer_token`、`device_token`）写成 0600；`control_status.py:71-73` 同样。Windows 上 `os.chmod` 只能切只读位，实际权限仍是 `0666`。
- 证据：CI `windows (py3.11, informational)` 有 6 条测试红在 `assert 438 == 384`（0o666 vs 0o600），涉及 `test_control_bridge_1195/1196/1197`。
- 后果：同一台机器上任何本地账户都能读走接入凭据。
- 建议：Windows 分支改用 `icacls` 只授当前用户 + SYSTEM；测试按平台断言（Windows 校验 ACL 而非 st_mode）。

### P0-3 「卡死自愈」在 Windows 上没有一条真实验证
- 证据：CI `test_browser_cdp_handshake_1216.py::test_launch_environment_replaces_a_frozen_instance` 红在 `assert result["opened"] is True`（第 176 行）。
- 根因：`chrome.py:771-781` `survival_probe` 在非 Windows 直接返回 `NON_WINDOWS_SKIP`，Windows 上会真查进程表；测试注入的假 PID 999 在 Windows 上必然 `BROWSER_EXITED`。也就是说这条 Windows 分支至今没有任何测试覆盖，真机也没测过。
- 建议：让测试能注入 `alive=`，再补一次 Windows 真机（冻结一个 Chrome 实例 → 触发发布 → 看是否自动重启且页面真的打开）。

### P1-4 没有源码的版本无法证明 OTA 可用
- 证据：`python3 publish-control/client/tools/ota_patch.py gate --simulate` 输出 `WARN versions in range with no source in git: 1.2.193, 1.2.194, 1.2.195, 1.2.207–1.2.214`。
- 后果：这些版本的客户热更新路径证不了，只能走完整安装包；根因是历史上有非 main/tag 出包。
- 建议：这些客户一律改发完整安装包；以后出包只认 main 上的 tag（`release_guard.py` 已卡）。

### P1-5 旧版 supervisor / 接管逻辑不在升级范围
- 已发布 tag 里的 supervision 代码不会被补丁替换，回滚路径行为以旧版为准。1.2.188–1.2.191 客户尤其要按完整安装包处理，别指望 OTA 修好自启。

### P2-6 Windows CI 仍是信息位，7 条红不挡合并
- `linux (py3.11)` / `linux (py3.13)` 是必需检查，`windows (py3.11, informational)` 带 `continue-on-error`。要把它设为必需，先修上面 6+1 条。

### P2-7 客户面板自述「Windows 真机与真实账号尚未验收」
- `panel.py` 首页提示文字里就写着这句（本地测试完成、真机待验）。对外交付前应改成与实测状态一致的说法，或者补完真机验收再删。

## 三、复现命令

```bash
cd publish-control/client && python3 -m pytest tests -q          # 208 passed
cd publish-control && python3 -m pytest tests -q                 # 104 passed, 14 skipped
python3 tools/static_verify.py .                                 # 127/127
python3 tools/ota_patch.py gate --simulate                       # PASS + 上面那条 WARN
```
Windows 的 7 条红见 GitHub Actions `ci` 的 `windows (py3.11, informational)` 作业。
