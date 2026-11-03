# 国内机经海外机 CONNECT 代理访问 OpenAI/Bedrock（2026-08-14 实测）

## 场景

国内服务器（广州机）访问不了 `api.openai.com` / AWS Bedrock（被墙，实测 `curl api.openai.com` 返回 000），codex/claude 这类重活天生只能待在海外机。但海外机内存小（2GB 时代），国内大内存机想跑 codex 又连不上 API。**方案：海外机（新加坡 <SG_HOST>）搭 HTTP CONNECT 代理，国内机 codex 通过代理访问 OpenAI——codex 执行在国内大内存机，网络绕道海外机中转。**

## 新加坡机（海外）搭代理

```bash
# 1. 代理脚本 ~/.hermes/scripts/http_proxy.py（支持 CONNECT HTTPS 隧道，双向转发）
# 2. 启动（长驻后台，别用 nohup&，用 hermes 后台进程）
python3 ~/.hermes/scripts/http_proxy.py 3128
# 3. 验证本地隧道：返回 401 = 网络通（401 是未授权，说明隧道建立成功）
curl -s -x http://127.0.0.1:3128 -o /dev/null -w '%{http_code}' https://api.openai.com/v1/models   # → 401
```

**安全（防开放代理被滥用）：** UFW 只放行国内机 IP，别开 0.0.0.0/0：
```bash
sudo ufw allow from <国内机IP> to any port 3128 proto tcp
sudo ufw status | grep 3128   # 只看到目标 IP 的 ALLOW 行
```
本次放行的是广州机出口 IP：`<US_HOST>`、`<GZ_HOST>`（从 `ss -tn | grep :22` 看谁连着新加坡机 SSH 端口获得）。

**两层防火墙都要放：** 服务器 UFW 放行只是第一层，**腾讯云安全组**还要在控制台给 3128 端口放行（用户操作），否则外部访问不到。

## 国内机（广州）配置 codex 走代理

```bash
export HTTPS_PROXY=http://<SG_HOST>:3128
export HTTP_PROXY=http://<SG_HOST>:3128
codex exec ...   # 正常跑，网络经代理
```
（codex 支持标准 HTTPS_PROXY 环境变量；claude 走 Bedrock 同理配代理。）

## 验证联通（注意反隧方向）

- 新加坡机本地：`curl -x http://127.0.0.1:3128 https://api.openai.com/v1/models` → 401 通
- 广州机经代理：`curl -x http://<SG_HOST>:3128 https://api.openai.com/v1/models` → 401 通
- **坑：升级/重启后广州机到新加坡的反隧（`ssh -p 2222 ubuntu@127.0.0.1`）会断**（`Connection refused`），此时从新加坡机访问不了广州机；但广州机 `codex_remote.sh`（正向 SSH 到新加坡）不受影响，广州机还能连新加坡。跨机测试走哪条通道先确认方向。

## 与 codex_remote.sh 的关系

现在广州机小鹿调 codex 是 `codex_remote.sh` **SSH 到新加坡机跑**（占新加坡内存）。配好代理 + 广州机装本地 codex 后，可以反过来：**广州机本地跑 codex，网络经新加坡代理**——小鹿的重活不再挤新加坡机内存，这才是根治（比单纯升内存更治本：重活不挤 gateway）。
