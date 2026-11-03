# Mac 经广州跳板代理访问国外网站（2026-08-24 OpenRouter 注册实测）

## 场景

用户 Mac（上海，`<MAC_USER>@<MAC_HOST>`）不能直连新加坡机（<SG_HOST>）——网络不通/无授权，必须经广州机（<GZ_HOST>）中转。本次目标：注册 OpenRouter 用 ox-alpha 模型。

## 网络拓扑（实测确认）

```
Mac(上海) ──SSH──> 广州机(<GZ_HOST>) ──SSH──> 新加坡机(<SG_HOST>)
```

- **Mac → 广州机**：SSH 通（公钥已加广州 authorized_keys，免密）
- **广州机 → 新加坡机**：SSH 通（反向隧道 2222/8899 常驻）
- **Mac → 新加坡机直连**：❌ 不通，必须跳板
- **新加坡机 → OpenRouter**：直连 0.05-0.14s（快）
- **广州机 → OpenRouter**：直连 1.76s（通但波动）
- **广州机 → GitHub**：经新加坡 SOCKS 0.6s，直连也通

## 关键结论（实测）

1. **代理链路越短越好**：Mac → 广州直连出口（`ssh -N -D 1081 ubuntu@<GZ_HOST>`）比 Mac → 广州 → 新加坡三段跳快 5 倍。广州机直连 OpenRouter 就能用，**不必绕新加坡**。
2. **`-J` 跳板命令的坑**：`ssh -N -D 1080 -J ubuntu@<GZ_HOST> ubuntu@<SG_HOST>` 要求 **Mac 公钥同时被广州机和新加坡机接受**。只加了广州没加新加坡 → `Permission denied (publickey)` 卡最后一跳。加完两边公钥才通。
3. **`-J` 模式不稳定**：广州 → 新加坡新连接容易 `channel open failed: connect failed: Connection timed out`（网络波动或连接数限制）。能免密直连广州时，优先「Mac 单段 -D 到广州」而不是 -J 跳板。
4. **代理设置后所有网站走代理**：ERR_PROXY_CONNECTION_FAILED = 代理开着但背后隧道没建（SSH 没跑/断了）——不是网站问题。验证隧道：`lsof -i :1080` 有输出 = 端口在监听。
5. **端口占用**：`bind [127.0.0.1]:1080: Address already in use` = 旧隧道没停干净，换端口（1081/1082）即可。
6. **隧道会掉**：SSH 窗口关了/网络断了隧道就没了（`ss -tlnp` 查 1080 监听 + `ps aux | grep 'ssh .*-D'`）。掉了重跑。

## 推荐命令（Mac 终端）

```bash
# 1. 广州出口（最快，推荐）
ssh -N -D 1081 ubuntu@<GZ_HOST>
# 窗口停住 = 隧道建好，别关；浏览器 SOCKS 代理 127.0.0.1:1081

# 2. 新加坡出口（要跳板才通）
ssh -N -D 1082 -J ubuntu@<GZ_HOST> ubuntu@<SG_HOST>
# 前提：Mac 公钥在两家 authorized_keys 都授权

# 验证出口 IP
# 浏览器开 https://ip.sb （显示当前出口 IP）

# 关代理（Mac）
networksetup -setsocksfirewallproxyloopback Wi-Fi off

# 查隧道是否活着
lsof -i :1080
```

## 授权 Mac 公钥到广州机（新加坡机经反向隧道代操作）

广州机 authorized_keys 里曾有过旧 Mac key（指纹不同）导致免密失败——加新 key 前先看现状：

```bash
# 从新加坡机经 2222 反向隧道查广州机 authorized_keys
timeout 20 ssh -p 2222 -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@127.0.0.1 \
  "wc -l ~/.ssh/authorized_keys; grep -n '<用户名>' ~/.ssh/authorized_keys"

# 备份 + 追加
timeout 20 ssh -p 2222 -o BatchMode=yes ubuntu@127.0.0.1 \
  "cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak-\$(date +%Y%m%d-%H%M) && echo '<公钥行>' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

广州机 sshd 允许密码登录（`PasswordAuthentication yes`）+ 公钥登录（`PubkeyAuthentication yes`）——密码输不对时优先加公钥免密，别让用户死磕密码。

## 远程操作广州机（新加坡机侧）

```bash
# 经 2222 反向隧道执行命令（广州 autossh 反隧常驻）
timeout 20 ssh -p 2222 -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@127.0.0.1 "<命令>"
# 例：查广州到新加坡连通性
# ssh -p 2222 ubuntu@127.0.0.1 "timeout 8 bash -c 'echo > /dev/tcp/<SG_HOST>/22' && echo 通 || echo 不通"
```

## 注册国外网站（OpenRouter）踩坑

- 注册页能开但提交转圈：网络慢（国内→国外 10-30s 正常），多等/刷新；分不清时先查链路（curl 测试）。
- GitHub OAuth 授权页国内直连不稳，走代理后能开。
- 邮箱验证邮件链接：**可以转发给新加坡机 Hermes，用服务器 curl 秒开**（0.14s）——比用户浏览器点快得多。
- 国内 IP 注册可能被风控，GitHub OAuth 绕过邮箱注册更稳。
- 免费模型（ox-alpha，`stealth/ox-alpha`）挂在 OpenRouter，`OPENROUTER_API_KEY` 配到 `~/.hermes/.env` 后 Hermes 内置 openrouter provider 可直接用。
