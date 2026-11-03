# 微信 iLink MEDIA 发送失败诊断（2026-08-09 新加坡机实测）

## 症状
- 文字消息正常收发，图片/视频发送失败
- `~/.hermes/logs/gateway.log` 出现：
  ```
  ERROR gateway.platforms.weixin: [Weixin] send_document failed to=<id>:
  ERROR gateway.platforms.base: [Weixin] Failed to send image:
  ```
  注意：异常信息是**空的**（`logger.error(..., exc)` 里 `str(exc)` 为空）——别被误导去查异常对象，要看超时链路。

## 发送链路（weixin.py）
1. `send_document` → `_send_file(chat_id, path, caption)`
2. `_get_upload_url`：POST iLink `ilink/bot/getuploadurl`，`asyncio.wait_for(timeout=API_TIMEOUT_MS=15s)` —— iLink API 通则这一步成功
3. `_upload_ciphertext`：POST 加密文件到 CDN `novac2c.cdn.weixin.qq.com`，`asyncio.wait_for(timeout=120)` —— **挂在这步**
4. 拿到 `x-encrypted-param` → iLink sendmessage 带 media item 发出

## 根因（本次实测）
- `novac2c.cdn.weixin.qq.com`（微信 C2C CDN）在新加坡机 **TCP 全不通**：IPv4/IPv6 都超时，所有 A 记录 IP（180.102.x/180.111.x/58.217.x）逐个测全 000
- 但同机其他腾讯域名正常：`ilinkai.weixin.qq.com`（200）、`mmbiz.qpic.cn`（400）、`res.wx.qq.com`（404）、`speed.qq.com`（200）、`dldir1.qq.com`（401）——说明是**特定 CDN 段被网络策略挡**，不是腾讯全墙
- 失败间隔 ≈ 120s = `_upload_ciphertext` 的超时，不是 15s 的 API 超时

## 诊断顺序
```bash
# 1. 日志确认失败点
grep -E "send_document failed|Sending image" ~/.hermes/logs/gateway.log | tail -10

# 2. 测 iLink API（应通）
curl -sS --max-time 10 -o /dev/null -w "iLink: HTTP:%{http_code}\n" https://ilinkai.weixin.qq.com/

# 3. 测 CDN（应超时/000）
curl -sS --max-time 8 -o /dev/null -w "CDN: HTTP:%{http_code}\n" https://novac2c.cdn.weixin.qq.com/

# 4. 测同机其他腾讯域名（应通）→ 确认是 CDN 段问题
curl -sS --max-time 6 -o /dev/null -w "qpic: %{http_code}\n" https://mmbiz.qpic.cn/
```

## 根治方案：CDN 上传中转 relay（2026-08-09 已部署 ✅）

新加坡机 → 广州机反向 SSH 隧道（广州机主动连 22）→ 广州机 CDN relay 服务（8899）→ 微信 CDN：
1. 广州机起中转服务监听 8899，代传加密文件到真实 CDN，原样透传 `x-encrypted-param`
2. 广州机执行 `ssh -R 8899:127.0.0.1:8899 ubuntu@<SG_HOST>` 建反向隧道
3. weixin.py 增加 relay 逻辑（2184 附近）：`WEIXIN_CDN_RELAY_URL` 存在时把 upload_url 改成 `{relay_base}/upload?url=<原CDN地址>`
4. `.env` 配 `WEIXIN_CDN_RELAY_URL=http://127.0.0.1:8899`（`_wx_secret` 读取）
5. gateway 重启生效（从外部 shell 重启，进程内自重启被安全层挡）

验证：`curl -X POST "http://127.0.0.1:8899/upload?url=<编码后的CDN地址>"` → 期望 `502 + relay error: HTTP Error 403: Forbidden`（0.2s）——502 是中转机透传 CDN 的 403（无凭证被拒），证明请求真实到达 CDN。有真实凭证时 CDN 返回 200 + x-encrypted-param。

## 临时交付方案
- 图片/视频先传公网 URL → 发**纯文本链接**给用户（记忆铁律：交付只发链接禁 MEDIA；链接禁带标点）
- 不要反复重发 MEDIA（每次浪费 120s 超时）
- 等 CDN 网络恢复后 MEDIA 原生发送自动恢复

## 关联代码位置
- `~/.hermes/hermes-agent/gateway/platforms/weixin.py`
  - `_send_file`（2144 附近）、`_get_upload_url`（549）、`_upload_ciphertext`（581，120s 超时）
  - `WEIXIN_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"`（92 行），可用 `WEIXIN_CDN_BASE_URL` env 覆盖

## iLink token 过期（2026-08-09 实测补充）
- 手工调 iLink API 用磁盘 token（`~/.hermes/weixin/accounts/<account>@im.bot.json` 的 `token` 字段）会返回 `{"errcode": -14, "errmsg": "session timeout"}` —— 磁盘 token 会过期
- **gateway 进程内存里的活 token 才有效**（启动时恢复），手工测试拿不到
- 所以验证 getUploadUrl 返回哪个 CDN 域名：别指望手工 token；从 gateway.log 的失败间隔（120s 超时）推断卡在 `_upload_ciphertext` 就够定位
- 手动测试 getUploadUrl 需要带 header：`Authorization: ilink_bot_token <token>` + `AuthorizationType: ilink_bot_token`
