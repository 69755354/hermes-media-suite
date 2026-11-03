# 手机 SOCKS5 代理部署参考

> 2026-08-25 codex + claude 双执行器交叉评审定案，实测修正

## 方案对比

| 维度 | danted (Dante) | 3proxy | microsocks |
|:---|:---|:---|:---|
| 认证 | 系统用户名密码（要 useradd） | 配置文件内置用户名密码 | 命令行 -u -P（ps 可见） |
| UDP | 支持 | 支持 | 不支持（tun 客户端静默故障） |
| systemd | 支持 | 支持 | 需手写 |
| 安装 | apt install dante-server | apt 或编译 | 编译 |
| 安全 | 要开真实系统账号（攻击面） | 不用开系统账号 | 密码暴露在进程列表 |
| 推荐方 | codex | claude（最终推荐） | 不推荐 |

## 3proxy 关键坑（2026-08-25 实测，按踩坑顺序）

### 坑1：MD5 hash 里的 `$` 要加双引号

`users u383ec4:CR:$1$salt$hash/` → `$` 在 3proxy 配置里有"读取外部文件"的特殊含义。

报错：`Failed to open E5iHyHPsEgyq9wbgrmSaj/`

解法：用明文 `CL:` 格式（推荐），或给 CR hash 整体加双引号 `users "u383ec4:CR:$1$salt$hash/"`

### 坑2：proxy3 用户权限是死路 → 直接用 root 跑

用 `useradd -r` 建系统用户跑 3proxy → 日志目录权限反复修不好（`/var/log/3proxy/` Permission denied、`ls` 也 Permission denied）。

**最简方案：systemd 直接用 root 跑，日志走 journal（裸 `log` 无参数 = stdout）。** 不折腾降权，以后需要加固再单独处理。

### 坑3：配置文件是顺序执行的，log 必须在 socks 之前（claude 定因）

3proxy 配置不是声明式的，是**逐行执行**的脚本。`socks -pPORT` 一旦被解析就启动服务，后面的行不再生效。

**错误写法（会导致瞬退 exit 0，无报错无日志）：**
```
socks -p23125 -i0.0.0.0
log /dev/stdout    ← 在 socks 之后，不生效
```

**正确写法：**
```
log                 ← 裸 log 无参数 = stdout，systemd journal 接收
nserver 1.1.1.1
nserver 8.8.8.8
nscache 65536
timeouts 1 5 30 60 180 1800 15 60
maxconn 200
users u383ec4:CL:明文密码
auth strong
allow u383ec4
deny *
socks -p23125       ← 最后写
```

### 坑4：`log /dev/stdout` 写法不对

`/dev/stdout` 是 `/proc/self/fd/1` 的软链，3proxy 的 logger 自己 open/append 处理日志目标，这个路径过不去。报 `Permission denied`。

- 裸 `log`（无参数）= stdout（systemd journal 接收）✅
- `log @3proxy` = syslog
- `log /var/log/3proxy/3proxy.log D` = 文件日志（需确保目录权限）

### 坑5：systemd 瞬退排查法

systemd 启动 24ms 就退出、journalctl 无日志时：
```bash
# 用服务用户身份手动跑，暴露真实权限错误
sudo -u <user> /usr/local/bin/3proxy /etc/3proxy/3proxy.cfg
# root 跑也不退出但 systemd 退出 → 检查配置文件顺序（log 在 socks 之后=瞬退）
# 最小配置验证
printf 'nserver 1.1.1.1\nsocks -p23125\n' | sudo tee /tmp/min.cfg
sudo /usr/local/bin/3proxy /tmp/min.cfg
# 卡住不退出 = 3proxy 本身没问题，Ctrl+C 退出
```

## 最终可用配置（实测通过）

### 3proxy.cfg

```
log

nserver 1.1.1.1
nserver 8.8.8.8
nscache 65536
timeouts 1 5 30 60 180 1800 15 60
maxconn 200

users u383ec4:CL:密码明文
auth strong
allow u383ec4
deny *

socks -p23125
```

### systemd unit（用 root，不折腾降权）

```ini
[Unit]
Description=3proxy tiny proxy server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/3proxy /etc/3proxy/3proxy.cfg
Restart=on-failure
RestartSec=2
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## 完整安装步骤

### 1. 编译安装 3proxy

```bash
sudo apt update
sudo apt install -y build-essential git openssl
cd /usr/local/src
sudo git clone --depth 1 -b 0.9.5 https://github.com/3proxy/3proxy.git
cd 3proxy
sudo make -f Makefile.Linux
sudo install -m 0755 bin/3proxy /usr/local/bin/3proxy
/usr/local/bin/3proxy --help 2>&1 | head -3
```

> 如果 `-b 0.9.5` 报 tag 不存在，先 `git ls-remote --tags https://github.com/3proxy/3proxy.git | tail -5` 查最新 tag。

### 2. 生成凭据

```bash
PORT=$(shuf -i 20000-32000 -n1)
PUSER=u$(openssl rand -hex 3)
PPASS=$(openssl rand -base64 18 | tr -d '/+=')
echo "PORT=$PORT USER=$PUSER PASS=$PPASS"
```

### 3. 写配置（顺序很重要！log 在前，socks 在最后）

```bash
sudo mkdir -p /etc/3proxy
sudo tee /etc/3proxy/3proxy.cfg >/dev/null <<EOF
log

nserver 1.1.1.1
nserver 8.8.8.8
nscache 65536
timeouts 1 5 30 60 180 1800 15 60
maxconn 200

users ${PUSER}:CL:${PPASS}
auth strong
allow ${PUSER}
deny *

socks -p${PORT}
EOF
sudo chmod 600 /etc/3proxy/3proxy.cfg
```

### 4. systemd 服务（用 root，不折腾降权）

```bash
sudo tee /etc/systemd/system/3proxy.service >/dev/null <<'EOF'
[Unit]
Description=3proxy tiny proxy server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/3proxy /etc/3proxy/3proxy.cfg
Restart=on-failure
RestartSec=2
LimitNOFILE=65536
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now 3proxy
sudo systemctl status 3proxy --no-pager
```

### 5. 开防火墙（两层缺一不可）

```bash
# 系统防火墙
sudo ufw allow ${PORT}/tcp
# 腾讯云控制台安全组也要加：TCP 端口 ALLOW
```

### 6. 验证

```bash
# 端口在听
sudo ss -lntp | grep $PORT
# 正例：返回服务器 IP
curl -sS --max-time 15 -x "socks5h://$PUSER:$PPASS@127.0.0.1:$PORT" http://httpbin.org/ip
# 反例：无密码必须失败
curl -sS --max-time 10 -x "socks5h://127.0.0.1:$PORT" http://httpbin.org/ip
```

### 7. 手机端 NekoBox

1. GitHub Releases 下载 NekoBox for Android APK（国内应用商店搜不到）
2. 华为手机关纯净模式才能装第三方 APK（设置→安全→纯净模式）
3. 新建 SOCKS 节点：地址=<SG_HOST> 端口=PORT 用户名=PUSER 密码=PPASS
4. 开 Remote DNS 防泄漏
5. 启动 → 浏览器开 https://api.ipify.org 验证

## 未解决问题（截至 2026-08-25）

- 手机直连新加坡 SOCKS5 端口超时——已开 UFW + 腾讯云安全组仍不通
- 尝试改 443 端口绕运营商封锁（未验证结果）
- SOCKS5 代理不像 SSH 能跳板，手机不能经广州中转连新加坡 SOCKS5
- 可能需要换 WireGuard（全隧道，不受端口封锁影响）

## 安全边界

- SOCKS5 是明文协议：用户名密码网络上明文传，只有 HTTPS 内容受 TLS 保护
- 公网裸开端口会被持续扫描：用高位随机端口 + 20 位以上随机密码
- 必须 verify「无密码/错密码都连不上」（防 open relay 被滥用）
- 手机端用 NekoBox VPN 模式（不是 Wi-Fi 代理框），开 Remote DNS 防泄漏
- 建议加 fail2ban 防爆破
- 如需加密/抗审查：上 Xray VLESS+TLS/REALITY 或 WireGuard（安卓官方 App 不要 root）
