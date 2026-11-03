---
name: singapore-guangzhou-relay
description: 新加坡经广州relay调ARK/微信CDN。触发:ARK直连不通/Seedream/微信发图失败。
---

# 新加坡↔广州 relay 通道（2026-08-09 搭建）

## 背景
新加坡机（<SG_HOST>）到国内网络服务直连不通：
- 火山 ARK（ark.cn-beijing.volces.com）：TCP 超时（DNS 正常）
- 微信 CDN（novac2c.cdn.weixin.qq.com）：TCP 超时 → MEDIA 发图失败
- 外网正常（httpbin 200），腾讯其他域名（mmbiz.qpic.cn）通

## 架构
```
新加坡机 → SSH反向隧道(广州机发起) → 广州机relay(8899) → 目标服务(ARK/微信CDN)
```
- 广州机主动 SSH 到新加坡（authorized_keys 有 key），`-R 8899:127.0.0.1:8899`
- 新加坡机访问 `http://127.0.0.1:8899/upload?url=<目标URL编码>` 即经广州机转发
- 微信发图：weixin.py 检测 WEIXIN_CDN_RELAY_URL=http://127.0.0.1:8899 → CDN 上传走 relay

## relay 分流逻辑（广州机维护）
- 微信 CDN 域名（novac2c/cdn.weixin/ilinkai）→ 原 x-encrypted-param 逻辑
- 其他域名（ARK/TOS 等）→ 纯透传：原状态码 + 完整 body

## 调用示例（新加坡机调 ARK 生图）
```bash
curl -sS -X POST "http://127.0.0.1:8899/upload?url=https%3A%2F%2Fark.cn-beijing.volces.com%2Fapi%2Fv3%2Fimages%2Fgenerations" \
  -H "Authorization: Bearer <ARK_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-seedream-5-0-260128","prompt":"...","size":"2560x1440","watermark":false}'
```

## 踩坑记录
1. relay 最初不透传 Authorization 头 → ARK 401（已修：透传 Authorization+Content-Type）
2. relay 曾强制要 x-encrypted-param 截断响应 → ARK URL 被吞（已修：域名分流）
3. ARK size 必须 ≥368万像素（2560x1440/1440x2560），2K/720x1280 被拒
4. ARK 根路径 /api/v3 404 正常，不是 AK 失效
5. 火山 TOS 图片下载只认 GET，relay 需支持 GET 转发（POST 会被 412 拒）
6. 广州机 SSH 隧道断了要广州机侧重连（autossh 更稳）

## 验证方法
- relay 存活：`curl http://127.0.0.1:8899/` → `cdn_relay alive`
- 隧道通：`curl -sS http://127.0.0.1:8899/upload?url=<任意URL>` 看透传响应
