# 1.2.75+ 远程通道本地预置（踩坑记录）

从 1.2.75 起客户包内**不再包含任何私钥**，远程支持默认关闭，必须在客户机本地预置三个文件才启用：

目录：`%LOCALAPPDATA%\HuolongAgent\publish-worker\remote-channel\`

| 文件 | 内容要点 |
|---|---|
| `client_key` | 该客户专用的 OpenSSH 私钥（411B ed25519 起） |
| `known_hosts` | 中继主机公钥，非 22 端口要写 `[host]:port` |
| `relay.json` | **必须含 `"schema_version": 1`**，否则 `relay_config_invalid` |

`relay.json` 示例（key_sha256 = `sha256sum client_key`）：
```json
{"schema_version":1,"host":"<GZ_HOST>","user":"ubuntu","port":22,"key_sha256":"<64 hex>"}
```

## 校验与排障
- 缺任一文件 → 面板显示「远程支持未启用（本机尚未完成部署配置）」，日志 `logs\remote-channel.log` 记 `remote support not enabled: local provisioning missing`。
- 配置**每次启动时读取**，改完必须重启助手（托盘退出→双击图标），只补文件不重启不生效。
- 通道令牌在 `remote-channel\token`，本次升级后令牌会变，控制端 `.env` 的 `TUNNEL_TOKEN` 要同步替换，否则一律 401。
- 中继侧残留旧 sshd 监听会占端口，导致 `remote port forwarding failed`；清掉残留会话后助手会自增端口重连。
- 验证：`/info` 的 `version`、`program`、`python` 三个字段要指向新版本目录和 venv 的 `pythonw.exe`。

## 安装顺序坑
从旧版 `exec` 里直接 spawn bootstrap（含 scheduled task 方式）会被 Windows Job 一起收掉；正确顺序是：先把 bootstrap 的 stop_running 跳过跑完（复制一份 `bootstrap_py.py` 改写），再让用户托盘退出+双击图标起新版。

## 升级后控制端要同步
- `.env`：`CLI_ROOT`、`CLI_PY` 指向新版本目录；`TUNNEL_TOKEN` 换成新令牌。
- `login-check` 只按 cookie 数量和 HTTP 200 判定，**星图过期仍报 ONLINE**；真实判据是访问 `www.xingtu.cn/sup/creator` 是否被重定向到登录页。
