---
name: phone-outbound-proxy
title: 手机全局走服务器出网（SOCKS5 常驻代理）
description: 触发：手机要翻墙看外网/安卓全局代理/手机连服务器出网。装3proxy常驻SOCKS5，手机填IP+端口+密码直连。
version: 1.0.0
author: Hermes curator
license: MIT
metadata:
  hermes:
    tags: [socks5, 3proxy, phone-proxy, outbound, android]
    category: server-operations
    related_skills: [mac-outbound-socks-chain, user-terminal-collab]
---

# 手机全局走服务器出网

## When to Use

手机（安卓无 root）要全局走新加坡服务器出网访问外网。SSH -D 隧道只有 Termux 内能用，安卓 App 走不了。tun2socks 要 root。不想装 WireGuard。触发词：手机翻墙/手机连外网/安卓全局代理/SOCKS5 常驻。

## 触发场景

- 手机（安卓无 root）要全局走新加坡服务器(<SG_HOST>)出网访问外网
- SSH -D 隧道只有 Termux 内能用，安卓 App 走不了 Termux 的 SOCKS5
- tun2socks 要 root，手机没 root
- 不想装 WireGuard

## 方案选型（已定案）

**用 3proxy，不用 danted/microsocks。**

| | danted | 3proxy | microsocks |
|---|---|---|---|
| 认证 | 强制建真实系统账号（安全风险） | 内置用户名密码 | 密码暴露在 ps aux |
| UDP | 支持 | 支持 | 不支持（tun 客户端静默故障） |
| systemd | 支持 | 支持 | 需手写 |

codex 推荐 danted，claude 推荐 3proxy。**claude 正确**：danted 强制开系统账号不安全，microsocks 没 UDP 会出怪问题，3proxy 内置认证+UDP+systemd 最均衡。

## 关键约束

- **Hermes 无 sudo 权限**——所有安装命令必须给用户在 Termux/Mac 上 SSH 进新加坡机手动跑
- **手机直连新加坡不通**——必须先 `ssh ubuntu@<GZ_HOST>` 进广州，再 `ssh ubuntu@<SG_HOST>` 跳新加坡
- **配置顺序铁律**：`users` → `auth strong` → `allow` → `socks`。`socks` 必须在最后，写反了变开放代理
- **两层防火墙**：ufw + 云控制台安全组都要放行，缺一个外网连不上

## 完整部署步骤

详见 `references/phone-socks5-3proxy-deployment.md`——含编译安装、配置生成、systemd、防火墙、验证、手机 NekoBox 配置全流程。

## 安全边界

- 裸 SOCKS5 是明文协议，账号密码和流量不加密
- 公网裸开端口会被持续扫描，用高位随机端口+20位以上随机密码
- 家网用没问题，公共 WiFi 有被窃听风险
- 如果目的是穿透审查/隐私保护，应上 VLESS+TLS/Reality 或 WireGuard，不要裸 SOCKS5

## 3proxy 配置铁律（2026-08-25 实测踩坑，2小时排查）

### 1. `log` 必须在 `socks` 之前

3proxy 配置是**逐行顺序执行的脚本**，不是声明式配置。`socks -p端口` 一旦被解析就启动服务，它后面的行不再生效。`log` 在 `socks` 之后 = 日志配置无效。

### 2. `log /dev/stdout` 不工作

3proxy logger 对 `/dev/stdout`（`/proc/self/fd/1` 符号链接）做 open/append/rotate 时失败。正确写法：**裸 `log`**（无参数）= stdout，systemd journal 接收。

### 3. MD5 hash 里的 `$` 要加双引号

`users u123:CR:$1$salt$hash/` 里的 `$` 有特殊含义（读取外部文件）。报错：`Failed to open <hash片段>/`。正确：`users "u123:CR:$1$salt$hash/"` 或用明文 `CL:` 格式。

### 4. 用 root 跑，别折腾降权

proxy3 用户权限链（/var/log/3proxy 目录、日志文件、配置文件）容易断，排查耗时。最简方案：systemd `User=root`、`StandardOutput=journal`，配置里不写 `setuid`/`setgid`/`daemon`。安全加固以后再做。

### 5. 秒退诊断

3proxy systemd 启动后秒退（inactive 6-24ms，exit 0）= 配置问题。先用最小配置确认二进制没问题：
```bash
printf 'nserver 1.1.1.1\nsocks -p23125\n' | sudo tee /tmp/min.cfg
sudo /usr/local/bin/3proxy /tmp/min.cfg   # 卡住=正常
```

### 6. 最终可用配置模板

```
log

nserver 1.1.1.1
nserver 8.8.8.8
nscache 65536
timeouts 1 5 30 60 180 1800 15 60
maxconn 200

users UUSER:CL:UPASS
auth strong
allow UUSER
deny *

socks -pPORT
```

## 踩坑（部署过程）

- **Termux ≠ 新加坡机**：用户在 Termux 本地跑 sudo，报 "sudo is not installed"。必须先 SSH 进广州再跳新加坡
- **make 成功但 install 漏跑**：用户跑完 make 没跑 install 就验证，报 No such file。分步确认每条命令执行了
- **mkdir 没跑成功**：后续 tee 写配置报 No such file or directory。先 `ls /etc/3proxy/` 确认目录在
- **命令挤一行**：用户复制多条命令粘贴时换行丢了，命令连一起报错。给用户的命令尽量单条发，或提醒分开粘贴
- **Termux 终端卡死**：SSH 会话卡住。Ctrl+C 打断，关掉 Termux 重开，重新 SSH 进去
- **用户掉回 Termux 本地**：操作着操作着不在新加坡机上了。跑 `hostname` 确认在 `sg-hermes-01` 再继续

## 华为手机装 NekoBox APK（2026-08-25 实测）

- **国内应用商店搜不到** NekoBox/v2rayNG
- **GitHub 下载 APK**：手机浏览器打开 https://github.com/MatsuriDayo/NekoBoxForAndroid/releases 下载最新 APK
- **华为纯净模式拦截**：提示"未备案"不让装。去 **设置 → 安全 → 纯净模式** 关掉，或 **设置 → 安全 → 更多设置 → 外部来源应用** → 允许下载用的浏览器安装未知应用
- 关掉纯净模式后用**文件管理器**找到下载的 APK 点击安装

## 关联

- Mac 出网走 SSH -D 三层跳板，见 skill `mac-outbound-socks-chain`
- 用户终端协作与跨机通道，见 skill `user-terminal-collab`
