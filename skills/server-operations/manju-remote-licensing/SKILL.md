---
name: manju-remote-licensing
description: 远程给客户机取机器码并下发 license 授权。
---

# 漫剧发布助手 远程授权

客户装好面板后，授权可以全远程做：取机器码 → 本地签发 → 回写 license.json。客户只需装好并打开「允许远程诊断」。

## 前置：拿到通道令牌

重装/重启后令牌会重新生成，旧的会 401。让客户在 PowerShell 跑：

```
cmd /c type "%LOCALAPPDATA%\HuolongAgent\publish-worker\remote-channel\token"
```

隧道落在服务器 `127.0.0.1:12226`，客户本地转发端口是助手进程的监听端口（`netstat -ano` 找，通常 `49980`，不是 `8000`）。

## 一条命令

```bash
cd /home/ubuntu/workflow/projects/win-agent-package-20261015/output/control-plane
EXEC_TOKEN=<令牌> python3 remote_license.py --customer-id <客户代号> --days 365
```

默认**只读 + 本地签发**（输出 `/tmp/license-remote.json`，不动客户机）。核对无误后加 `--apply` 才写入，写入前自动备份 `license.json.bak-<时间>`。

其他参数：`--plan`、`--accounts douyin:default:365`、`--expires 2027-10-23`、`--client-py`。

## 边界

- 签发私钥 `/home/ubuntu/secure/vendor.key`，先 `--check-key` 核对与包内公钥一致（MATCH）再签。
- 扫码登录不能远程代做，必须客户本人手机扫。
- 写完刷新面板；不生效点「重试自动授权」，仍不行重启助手。
- 别拿真实客户机器做 `--apply` 测试，先 dry-run。
