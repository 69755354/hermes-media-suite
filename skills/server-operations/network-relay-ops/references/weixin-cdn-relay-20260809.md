# 微信 CDN Relay 完整链路验证记录（2026-08-09）

跨机排查全记录。新加坡机（<SG_HOST>，海外）→ 微信 CDN/火山 ARK 被网络墙挡，广州机（<GZ_HOST>，国内）当中转。

## 故障时间线

1. 用户要求发 codex 生成的小鹿图 → MEDIA 发送失败，用户没收到
2. 日志 `[Weixin] send_document failed to=o9cq80-_:`（异常信息为空），失败间隔恒 ~120s
3. 追查 weixin.py 源码：`_upload_ciphertext` 的 `asyncio.wait_for(timeout=120)` 是超时点
4. 定位链路：iLink API（ilinkai.weixin.qq.com）通（HTTP 200）→ 但媒体上传必经微信 CDN（novac2c.cdn.weixin.qq.com）→ CDN TCP 超时
5. CDN 域名测试：IPv4/IPv6 全部 TCP 超时；同域其他微信域名（mmbiz.qpic.cn 400、res.wx.qq.com 404）通 → 特定 CDN 段被挡，非全墙
6. 火山 ARK（ark.cn-beijing.volces.com）同样 TCP 超时（DNS 正常、httpbin 200）

## 关键测试命令（可复现）

```bash
# 确认隧道
ss -tlnp | grep 8899
# 确认 relay 活着
curl http://127.0.0.1:8899/          # → cdn_relay alive
# 直连验证网络墙（DNS 正常 + 目标 TCP 超时）
curl --max-time 8 https://novac2c.cdn.weixin.qq.com/   # timeout
curl --max-time 8 https://ark.cn-beijing.volces.com/api/v3/models  # timeout
curl --max-time 8 https://httpbin.org/get              # 200（外网正常）
# 走 relay 转发（无凭证验证到达）
curl -sS --max-time 20 -X POST "http://127.0.0.1:8899/upload?url=https%3A%2F%2Fnovac2c.cdn.weixin.qq.com%2Fc2c%2Fupload%3Ftest%3D1" \
  -H "Content-Type: application/octet-stream" -d 'x'
# → relay error: HTTP Error 403: Forbidden（403 = 真实到达 CDN，CDN 拒绝无凭证）
# ARK 无鉴权头
curl -sS --max-time 20 -X POST "http://127.0.0.1:8899/upload?url=https%3A%2F%2Fark.cn-beijing.volces.com%2Fapi%2Fv3%2Fimages%2Fgenerations" \
  -H "Content-Type: application/json" -d '{"model":"x","prompt":"t","size":"2K"}'
# → relay error: HTTP Error 401: Unauthorized（头没透传）
```

## 落地配置

- 广州机公钥加入新加坡机 `~/.ssh/authorized_keys`（注释名如 `guangzhou-to-singapore`，原 `hk-to-gz` 保留）
- SSH 反向隧道：广州机 → 新加坡机，把广州机 relay 8899 映射到新加坡机 127.0.0.1:8899
- `.env` 加 `WEIXIN_CDN_RELAY_URL=http://127.0.0.1:8899`
- weixin.py `_send_file` 段：设 relay 时改写 upload_url → `relay/upload?url=<quote(upload_url)>`；relay 回传 `x-encrypted-param` 头后原流程继续
- relay 必须透传 `Authorization` + `Content-Type`（广州机侧 Python urllib 实现，读入站请求头拼到出站请求）
- 改完 gateway 重启生效（09:54 广州机侧重启验证过）

## ARK 401 → 404 演进记录

- 第一版 relay 不透传 Authorization → ARK 401
- 广州机改 relay 透传 Authorization + Content-Type → ARK 401 消失，变 404
- 404 排查：ARK 对无效/无权 AK 返回 404（不暴露接口存在性）；config.yaml 的 AK（<ARK_API_KEY>）只配了「豆包种子2.0 Mini 看图」模型，未必有 Seedream 权限 → 未完全解决，待查 AK 权限/换有效 AK

## 教训

- **异常信息为空的 send_document failed** = 大概率超时类异常（`str(exc)` 为空），别只看日志尾，去源码找 `wait_for` 超时
- 网络墙判断：DNS 能解析 ≠ 能连；外网通 ≠ 目标通；逐个域名测，别一刀切
- 隧道方向：两边防火墙互不可达时，由能出网的一侧（国内机）主动发起反向隧道
- relay 是通用 HTTP 转发，不只救微信 CDN——火山 ARK 也走同一通道
