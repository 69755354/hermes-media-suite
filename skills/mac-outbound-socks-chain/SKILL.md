---
name: mac-outbound-socks-chain
title: Mac 经广州-新加坡三层 SOCKS 出网看 YouTube/外网
description: 触发：Mac要翻墙看YouTube/外网但国内直连不通；电脑-广州-新加坡三层跳板SOCKS代理。
version: 1.0.0
---

# Mac 三层 SOCKS 出网（电脑→广州→新加坡）

## 触发场景（2026-08-24 定案）
- 用户在 Mac 上要看 YouTube / 境外网站，国内直连被墙
- 三层链：**Mac → 广州(<GZ_HOST>) → 新加坡(<SG_HOST>) → 出网**
- 关键：**广州自己出不了墙**（实测 YouTube/Google=000），只当中转跳板；
  真正能出墙的是**新加坡**（Google 实测 0.13s）。落地必须开在新加坡。

## 固定方案（就这么配，端口永远 1081）
```
# Mac 终端：三步跳到新加坡，落地在新加坡开 SOCKS，端口固定 1081
ssh -N -D 1081 -J ubuntu@<GZ_HOST> ubuntu@<SG_HOST>

# 浏览器/系统代理：SOCKS5 127.0.0.1:1081（设一次不改）
# 验证：https://ip.sb 应显示新加坡 IP（<SG_HOST>），不是广州
```

## 关键事实（别再踩坑）
- **三层链路各段连通性**：Mac→广州（通过，1081 在连）；广州→新加坡 22 通（实测 ssh 能落 sg-hermes-01）
- **新加坡 sshd hardening（99-hardening.conf 2026-08-09）里 `AllowTcpForwarding remote` 只在 `Match User relay-tunnel` 块内**，只限制广州 relay 专用用户。**ubuntu 用户没被禁 -D**，能正常开 SOCKS。别误以为 hardening 挡了 ubuntu 的代理。
- **开关机记住用户偏好**：用户要的是完整三层跳板，不是直连新加坡。直连新加坡那条 `ssh -N -D 1081 ubuntu@<SG_HOST>` 用户会嫌不对。

## 上次的坑
- 反复让对方在 Mac 上测试、来回猜链路，费了 2 小时——用户下午配好的，晚上问起我却翻记录找不到、反复实测。**这类已配好的方案早该固化成 skill 记下来**。
- 别反复测连通性（连通性本来就通），直接给固定命令让用户跑。

## 验证
```
curl -x socks5://127.0.0.1:1081 https://ip.sb
# 显示 <SG_HOST>（新加坡）= 成功；显示 <GZ_HOST>（广州）= 还停在中转
```
