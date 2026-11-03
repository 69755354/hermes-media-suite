# 广州 relay 隧道运维补充（2026-08-09 实测）

> 原 `singapore-guangzhou-relay` skill 是用户自有（curator 无法改），此文件补充其生命周期细节。

## 隧道守护（P0-5 定案，两侧分工）

**广州机（隧道发起方）**：
- 服务：`tunnel-sg.service`（autossh + systemd）
- 命令：`autossh -M 0 -N -i <绝对key路径> -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -R 8899:127.0.0.1:8899 ubuntu@<SG_HOST>`
- ⚠️ **坑：systemd 里 `~` 是 profile home**（如 `/home/ubuntu/.hermes/profiles/customer/home/.ssh/`），不是 `/home/ubuntu/.ssh/`——key 路径写错会 Permission denied 疯狂重连。必须写绝对路径。

**新加坡机（隧道接收方）**：
- 服务：`tunnel-watchdog.service`，脚本 `~/.hermes/scripts/tunnel_watchdog.py`
- 每 60s TCP 探测 8899，连续 3 次失败写 `/tmp/tunnel_degraded`（DEGRADED_MEDIA 标记），恢复自动清除

## relay GET 转发（2026-08-09 下午上线）

- relay 的 GET **带 url 参数** → 转发（ARK 图片下载、微信 CDN 下载）
- GET **不带参数** → 返回健康检查 `cdn_relay alive`
- 所以下载火山 TOS 图片：`curl -o out.jpg "http://127.0.0.1:8899/upload?url=<编码后的完整TOS URL>"` 即可
- TOS 只认 GET（POST 会 412 Precondition），relay 早先只转发 POST → 图片 URL 拿到了但下载不了，后来才加 GET 转发

## 鉴权与安全现状

- relay 是「域名分流 + 纯透传」，不携带本地凭据；ARK 的 AK 由新加坡机请求头带（`Authorization: Bearer`）
- 最初 relay 不透传 Authorization → ARK 401；广州机改成透传 Authorization+Content-Type 后正常
- 已知残余风险（P2-1 未做）：relay 是开放代理（任意 URL 转发）→ SSRF 风险；因为已绑 127.0.0.1 + UFW 挡住公网，风险降级为纵深防御项，优先级低

## 断链行为

- 隧道断：文字链路不受影响（iLink 直连），媒体/ARK 全挂
- autossh 3s 自动重连，watchdog 标记 DEGRADED_MEDIA
- media outbox（`~/.hermes/scripts/media_outbox.py`）把发送失败媒体入队，隧道恢复自动补发
