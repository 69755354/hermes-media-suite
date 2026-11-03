# 手机 SOCKS5 代理部署（3proxy 常驻服务）

> 2026-08-25 实测定稿。之前 proxy3 降权方案踩坑2小时，最终用 root + journal 方案跑通。

## 完整安装步骤（用户在新加坡机上跑，Hermes 无 sudo 权限）

### 0. 前置：SSH 进新加坡机

手机直连新加坡不通，必须两步跳：

```bash
# Termux 或 Mac 上
ssh ubuntu@<GZ_HOST>    # 进广州
ssh ubuntu@<SG_HOST>     # 跳新加坡
```

提示符变成 `ubuntu@sg-hermes-01` 才是在新加坡机上。

### 1. 编译装 3proxy

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

### 2. 建目录和配置（用 root 跑，不折腾 proxy3 降权）

```bash
sudo mkdir -p /etc/3proxy
ls /etc/3proxy/  # 确认目录在
```

生成端口和密码（Hermes 跑这段，把值给用户）：

```bash
PORT=$(shuf -i 20000-32000 -n1)
PUSER=u$(openssl rand -hex 3)
PPASS=$(openssl rand -base64 18 | tr -d '/+=')
echo "PORT=$PORT USER=$PUSER PASS=$PPASS"
```

写配置（把 UUSER/UPASS/PORT 替换成上面生成的值）：

```bash
sudo tee /etc/3proxy/3proxy.cfg >/dev/null <<'EOF'
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
EOF
```

**配置顺序铁律：** `log` → `nserver` → `users` → `auth strong` → `allow` → `deny` → `socks`（最后）。

### 3. systemd 常驻（用 root 跑）

```bash
sudo tee /etc/systemd/system/3proxy.service >/dev/null <<'EOF'
[Unit]
Description=3proxy proxy server
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

预期：`Active: active (running)`。

### 4. 防火墙

```bash
PORT=$(grep -oP '(?<=-p)\d+' /etc/3proxy/3proxy.cfg)
sudo ufw allow 22/tcp
sudo ufw allow "$PORT"/tcp
sudo ufw --force enable
sudo ufw status
```

**云控制台安全组也要放行同一 TCP 端口**——ufw 通了但安全组没开，外网照样连不上。

### 5. 验证

```bash
PORT=$(grep -oP '(?<=-p)\d+' /etc/3proxy/3proxy.cfg)
PUSER=$(grep -oP '(?<=users )\w+' /etc/3proxy/3proxy.cfg)
PPASS=$(grep -oP "(?<=$PUSER:CL:)\w+" /etc/3proxy/3proxy.cfg)

# 端口在听
sudo ss -lntp | grep ":$PORT"

# 正例：应返回服务器出口 IP
curl -sS --max-time 15 -x "socks5h://$PUSER:$PPASS@127.0.0.1:$PORT" https://api.ipify.org; echo

# 反例：错密码必须失败
curl -sS --max-time 10 -x "socks5h://$PUSER:wrongpass@127.0.0.1:$PORT" https://api.ipify.org; echo "exit=$?"

# 无认证也必须失败
curl -sS --max-time 10 -x "socks5h://127.0.0.1:$PORT" https://api.ipify.org; echo "exit=$?"
```

### 6. 手机 NekoBox 配置

| 字段 | 填什么 |
|---|---|
| 类型 | SOCKS |
| 服务器 | <SG_HOST> |
| 端口 | 生成的端口 |
| SOCKS 版本 | 5 |
| 用户名 | 生成的 PUSER |
| 密码 | 生成的 PPASS |
| TLS | 关 |
| Remote DNS | 开（防 DNS 泄漏） |

保存 → 长按测延迟 → 启动 → 手机浏览器开 `https://api.ipify.org` 应显示服务器 IP。

## 改密码

```bash
# 直接改配置文件里的 CL: 后面的密码
sudo nano /etc/3proxy/3proxy.cfg
# 改 users 行里的密码
sudo systemctl restart 3proxy
```

## 踩坑记录

- **Termux ≠ 新加坡机**：用户在 Termux 本地跑 sudo，报 "sudo is not installed"。必须先 SSH 进广州再跳新加坡
- **make 成功但 install 漏跑**：用户跑完 make 没跑 install 就验证，报 No such file
- **mkdir 没跑成功**：后续 tee 写配置报 No such file or directory。先 `ls /etc/3proxy/` 确认目录在
- **命令挤一行**：Termux 复制多条命令粘贴时换行丢了。给用户的命令尽量单条发
- **Termux 终端卡死**：SSH 会话卡住。Ctrl+C 打断，关掉 Termux 重开，重新 SSH 进去
- **用户掉回 Termux 本地**：跑 `hostname` 确认在 `sg-hermes-01` 再继续
- **proxy3 降权方案废弃**：权限链断裂数次（/var/log/3proxy 目录权限、日志文件权限），最终改用 root 跑 + journal 日志，一步到位
- **log /dev/stdout 不工作**：3proxy logger 对符号链接做 open/rotate 时失败。用裸 `log`（无参数）
- **MD5 hash $ 特殊字符**：`$` 在 3proxy 配置中有"读取外部文件"含义。用 `CL:` 明文格式或加双引号
