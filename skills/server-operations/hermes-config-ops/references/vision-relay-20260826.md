# Vision Relay 配置全流程（2026-08-26 实测定案）

## 背景

新加坡机 GLM-5.2 无视觉能力，vision_analyze 需走 ARK 视觉模型。但新加坡直连 ARK 超时（被墙），需经广州机中转。

## 架构

```
新加坡 vision_analyze
  → config auxiliary.vision.base_url = http://127.0.0.1:18891/v1
  → SSH隧道 (18891→广州8890)
  → 广州机 vision_relay_gz.py (systemd: vision-relay.service)
  → ARK视觉端点 (ark.cn-beijing.volces.com/api/v3)
  → 返回视觉分析结果
```

## 端口分配表（写死，不可混用）

| 端口 | 进程/服务 | 用途 | config 段 |
|---|---|---|---|
| 18888 | ark_local_proxy.py (systemd) | ARK 生图（Seedream） | providers.custom_ark |
| 18890 | glm_aliyun_proxy.py | 阿里云百炼 GLM-5.2（主对话） | model.base_url / providers.custom_glm |
| 18891 | SSH隧道→广州8890 | **vision（ARK视觉）** | auxiliary.vision |
| 8899 | SSH反向隧道（广州→新加坡） | 微信CDN/ARK通用relay | (singapore-guangzhou-relay) |

## 广州机 relay 脚本（vision_relay_gz.py）

装在广州机 `~/.hermes/scripts/vision_relay_gz.py`，systemd user service `vision-relay.service` 持久化。

**关键设计决策：**
- **硬编码 ARK key 和 base_url**，不透传上游 Authorization（透传会导致 ARK 报 invalid key，因为新加坡传的 key 和广州 config 里的可能不一致）
- 读广州机 `~/.hermes/config.yaml` 或 `profiles/customer/config.yaml` 里的 vision 段
- `ThreadingHTTPServer` 支持并发
- 监听 `0.0.0.0:8890`

**v1 坑：** 原版 relay 透传 Authorization 头，但新加坡传的 key 跟广州 config 不一致时 ARK 报 invalid key。v2 改成始终用本机 key，不透传。

**v2 脚本核心逻辑：**
```python
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
API_KEY = "<ARK_API_KEY>"  # 硬编码或从config读

auth = 'Bearer ' + API_KEY  # 始终用本机key
req = urllib.request.Request(target, data=body, method='POST', headers={
    'Content-Type': 'application/json',
    'Authorization': auth,
})
```

## 新加坡机持久化隧道

脚本：`~/.hermes/scripts/vision_tunnel.sh`
```bash
#!/bin/bash
TUNNEL_CMD="ssh -f -N -p 2222 -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18891:127.0.0.1:8890 ubuntu@127.0.0.1"
if ss -tlnp | grep -q "127.0.0.1:18891"; then exit 0; fi
$TUNNEL_CMD 2>/dev/null
```

crontab 持久化：
```cron
@reboot /home/ubuntu/.hermes/scripts/vision_tunnel.sh
*/5 * * * * /home/ubuntu/.hermes/scripts/vision_tunnel.sh
```

## config.yaml 最终配置

```yaml
auxiliary:
  vision:
    api_key: <ARK_API_KEY>2
    base_url: http://127.0.0.1:18891/v1   # 走隧道到广州relay
    model: ep-20260826131421-lllz8        # ARK端点ID
    provider: custom
    timeout: 120
```

主模型段**必须保持 18890**，不能改：
```yaml
model:
  base_url: http://127.0.0.1:18890/v1    # glm_aliyun_proxy → 阿里云百炼
  default: glm-5.2
  provider: custom_glm
```

## 验证全链路

```bash
# 1. 隧道存活
ss -tlnp | grep 18891   # 应显示 ssh 进程

# 2. relay存活（广州机）
ssh -p 2222 ubuntu@127.0.0.1 "systemctl --user status vision-relay --no-pager | head -5"

# 3. 纯文本测试
curl -s --max-time 15 -X POST http://127.0.0.1:18891/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"ep-20260826131421-lllz8","messages":[{"role":"user","content":[{"type":"text","text":"ping"}]}]}'

# 4. 视觉测试（本地图片base64）
IMG_B64=$(base64 -w0 /tmp/some_small.jpg)
curl -s --max-time 30 -X POST http://127.0.0.1:18891/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"ep-20260826131421-lllz8\",\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"image_url\",\"image_url\":{\"url\":\"data:image/jpeg;base64,${IMG_B64}\"}},{\"type\":\"text\",\"text\":\"一句话描述\"}]}]}"

# 5. Hermes vision_analyze 工具直接测试
# 用 vision_analyze 工具传一张本地图片路径，看返回是否包含真实画面描述
```

## 广州机 systemd 服务

```ini
# ~/.config/systemd/user/vision-relay.service
[Unit]
Description=Vision Relay (ARK proxy for Singapore)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/ubuntu/.hermes/scripts/vision_relay_gz.py
Restart=always
RestartSec=3
MemoryHigh=200M
MemoryMax=300M

[Install]
WantedBy=default.target
```

注意：去掉 `User=ubuntu` 和 `Group=ubuntu` 行，否则报 `status=216/GROUP: Failed to determine supplementary groups: Operation not permitted`。systemd user service 不需要指定 User/Group。

需 `loginctl show-user ubuntu | grep Linger=yes` 确认 linger 开启（服务能在用户登出后持续运行）。

## 踩坑记录

### 坑1：18890 vs 18891 端口冲突
18890 端口被 `glm_aliyun_proxy.py`（阿里云百炼代理）占着。最初建 SSH 隧道用 18890 端口时报 `Address already in use`。改用 18891 端口解决。

### 坑2：sed 全局替换撞主模型通道
用 `sed -i 's|18890|18891|'` 全局替换，把 `model.base_url` 和 `providers.custom_glm.base_url` 也改了 → 主对话 glm-5.2 请求被发到 ARK 视觉端点 → ARK 没有 glm-5.2 → 404 → 用户看到 `⚠️ The model provider failed after retries`。

**防范：** `sed -i '38s|old|new|'`（指定行号），改完 `grep -n "base_url" config.yaml` 逐行验证。

### 坑3：nohup 挂住 SSH session
在广州机用 `ssh ... "nohup python3 script.py &"` 启动后台进程，SSH session 挂住不返回。改用 `setsid`：
```bash
ssh -p 2222 ubuntu@127.0.0.1 "setsid python3 /tmp/script.py >> /tmp/log 2>&1 < /dev/null & disown; echo started"
```

### 坑4：relay 透传 Authorization 导致 ARK 报 invalid key
relay v1 透传上游 Authorization 头，但新加坡传的 key 跟广州 config 里的 key 可能不一致。v2 改成始终用本机硬编码 key，不透传。

### 坑5：ARK 端点绑的模型不对
用户创建 ARK 端点 `ep-20260826131421-lllz8`，绑的是 `doubao-seed-2-0-lite-260428`（纯文本 lite 模型），不是视觉模型。返回正常文本但看不到图。需要去 ARK 控制台把端点绑的模型换成视觉模型。

### 坑6：gateway 不能从内部重启
`hermes gateway restart` 和 `systemctl --user restart hermes-gateway` 都会被拦截：`Blocked: command or referenced script cannot restart or stop the gateway from inside the gateway process`。必须从外部 shell 重启。
