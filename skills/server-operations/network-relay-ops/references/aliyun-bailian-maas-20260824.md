# 阿里云百炼（DashScope MaaS）OpenAI 兼容接入（2026-08-24 实测）

## 背景
新加坡机直连**阿里云百炼北京 region**（`*.maas.aliyuncs.com`）被网络墙挡——实测 TCP IPv4 connect timeout（DNS 解析正常，握手超时）。与火山 ARK 同病。**国内云服务（ARK/百炼/微信CDN）从新加坡直连全不通，必须走广州机中转。**

## Key / endpoint 语义（阿里百炼一条 key 三个地址，别搞混）
| 地址 | 用途 |
|:---|:---|
| `wss://<id>.cn-beijing.maas.aliyuncs.com` | API Host（websocket，一般不用） |
| `https://<id>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` | **OpenAI 兼容**（配 Hermes/codex 用这个） |
| `https://<id>.cn-beijing.maas.aliyuncs.com/api/v1` | DashScope 原生协议 |

key 格式 `sk-ws-...`，`maas.aliyuncs.com` = 阿里云，**别跟智谱（z.ai/open.bigmodel.cn）混**。

## ✅ 已落地：新加坡侧本地代理中转（2026-08-24 打通，无需改广州 relay）

**关键发现：`cdn_relay.py` 是 generic passthrough**——非 CDN 域名（ARK/阿里/任意 http(s)）一律原样透传（状态码+完整 body+Authorization）。所以**新接任何国内服务，广州 relay 那端不用改**，只需新加坡侧加一条本地代理指向它。

### 链路
```
新加坡应用 → 127.0.0.1:18890(glm_aliyun_proxy.py) → 127.0.0.1:8899(SSH反隧) → 广州 cdn_relay:8899 → 阿里 maas compatible-mode
```

### 落地步骤（三步）
**1. 复制 ARK 本地代理模板，改 ARK_BASE + 端口**
```bash
cp /home/ubuntu/.hermes/scripts/ark_local_proxy.py /home/ubuntu/.hermes/scripts/glm_aliyun_proxy.py
# 改 ARK_BASE = "https://<id>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
# 改默认 --port 18890（避开已用的 18888 ARK，本机代理端口编排：18888=ARK / 18890=阿里GLM）
# relay 仍指 http://127.0.0.1:8899
```
`ark_local_proxy.py` 本身就是**通用 OpenAI 兼容转发代理**（路径剥 `/api/v3|/v1|/v3` 前缀 → relay/upload?url= → 透传 Authorization/Content-Type），任何 OpenAI 兼容服务都能照抄。

**2. 起服务 + 实测**
```bash
(nohup python3 glm_aliyun_proxy.py --port 18890 --relay http://127.0.0.1:8899 > /tmp/glm_aliyun_proxy.log 2>&1 &)
# 实测走中转调真请求：
curl -s -m 60 -X POST "http://127.0.0.1:18890/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"glm-5.2","messages":[{"role":"user","content":"hi"}],"max_tokens":30}'
```

**3. 建 systemd 自启**（copy `ark-local-proxy.service` 模板，脚本名+端口换成 glm 的）
```bash
sudo tee /etc/systemd/system/glm-aliyun-proxy.service > /dev/null <<'EOF'
[Unit]
Description=Local GLM-Aliyun Proxy (relay to Guangzhou -> Aliyun MaaS)
After=network.target
[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/.hermes/scripts
ExecStart=/usr/bin/python3 /home/ubuntu/.hermes/scripts/glm_aliyun_proxy.py --port 18890
Restart=always
RestartSec=3
MemoryHigh=300M
MemoryMax=400M
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now glm-aliyun-proxy
```
⚠️ 写 `/etc/systemd/system/` 要 root，AI 无密码 → 把命令交给用户执行，或走用户终端。

## 🔑 config.yaml 安全敏感键（重要——write/patch 会被硬拒）
`providers.*` 的 api_key/base_url 是**安全敏感配置**，Hermes 的 write_file/patch 工具会拒绝（"Refusing to write to Hermes config file"）。必须走正式通道：
```bash
hermes config set providers.custom_glm.api_key '<key>'
hermes config set providers.custom_glm.base_url 'http://127.0.0.1:18890/v1'   # ⚠️ 填本地中转，不是直连国内
hermes config set providers.custom_glm.model 'glm-5.2'
hermes config set providers.custom_glm.api_mode 'chat_completions'
hermes config set providers.custom_glm.available_models_json '[{"id":"glm-5.2",...}]'
```
配置后 base_url 必须填**本地中转地址**（`http://127.0.0.1:18890/v1`）而非直连国内地址，否则新加坡仍连不通。删旧 provider 同理用 `hermes config unset`（别用 patch/sed 手改）。

## 🖥️ 跨机远程编配置：经 2222 反隧在**另一台机**上 `hermes config set`（2026-08-24 实测）

目标机不是本机时（本会话：广州机 `gz-customer-01` 的 `custom_glm` 用阿里 GLM，从新加坡经 2222 反隧去配），SSH 过去直接跑她的 hermes——**别在新加坡绕路配广州机，那是错的机器**。

```bash
timeout 20 ssh -p 2222 -o BatchMode=yes ubuntu@127.0.0.1 '
export PATH="/home/ubuntu/.local/bin:$PATH"   # 🔴 广州机 hermes 不在 PATH！手动指到 ~/.local/bin
hermes config set providers.custom_glm.api_key "<key>"
hermes config set providers.custom_glm.base_url "https://<id>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
hermes config set providers.custom_glm.model "glm-5.2"
'
```
**要点：**
- 目标机（广州）**直连阿里通** → 她不走本地代理中转，base_url 直接填**阿里真实地址**（区别于新加坡机填本地中转）。谁直连国内服务通，谁就填真实地址；被墙那台才填本地中转
- 目标机 `hermes` 不在 PATH（/usr/local/bin 无）→ 先 `export PATH="/home/ubuntu/.local/bin:$PATH"` 或直接用 `/home/ubuntu/.local/bin/hermes`。`which hermes` 无 = 不在环境变量，不是没装
- 配完**从目标机本地 curl 测真请求**验证（`ssh -p 2222 ... 'curl ...'`），别只信配置写入成功
- 同一模型在两台机角色不同（新加坡=被墙要中转、广州=直连通）时，**先确认目标机直连通不通**再决定 base_url——凭"这 key 给谁用"判断，别默认

## 实测验证（经广州机 2222 反隧，广州机直连阿里通）
```bash
ssh -p 2222 -o BatchMode=yes ubuntu@127.0.0.1 '
KEY="sk-ws-..."
curl -s -m 20 -X POST "https://<id>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"glm-5.2\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":20}"'
```

## 列可用模型（确认模型 ID 真实存在，别信口述）
```bash
curl -s -m 20 "https://<id>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/models" -H "Authorization: Bearer $KEY"
# 返回 data[].id 全列表——GLM 系(glm-4.7/5/5.1/5.2)、千问系(qwen3.*/qwen-image)、deepseek、kimi、minimax 等
```

## 坑：模型 ID 口述 ≠ 实际存在
用户说「能调 glm-5.2 和 happyhorse1.1」——实测 happyhorse1.1 返回 `model_not_found`（`Model not exist.`）。**必须 `/models` 拉真实列表核对**，不是用户说了就算。glm-5.2 调通（响应带 `reasoning_content` 字段，GLM 系正常）。

**处理（2026-08-24 实测）：** 用户确认「happyhorse1.1（OX 不稳定）」后，从 available_models_json 移除，只留实测稳定的 glm-5.2。**不存在的/口述的模型别硬配**——不存在的 ID 会污染 provider 列表，调用时报 `model_not_found` 卡壳。配置里只留 `/models` 核对过、实测调通的模型。

## 响应特征
GLM 系 OpenAI 兼容响应带 `choices[].message.reasoning_content`（思考链）——max_tokens 太小会被 reasoning 吃光导致 `content:""`，属正常，调大 max_tokens 或接受空 content + reasoning。

## 网络现状（2026-08-24）
- 广州机（<GZ_HOST>）：直连阿里百炼**通** ✓，直连火山 ARK 通 ✓（是国内云的正确出口）
- 新加坡机（<SG_HOST>）：直连阿里百炼/ARK/微信CDN 全被墙 ✗ → 一律经广州机中转
- 2222 反隧（新加坡 127.0.0.1:2222 → 广州机 SSH）是管理通道，可跑 curl/scp
- **✅ 阿里 maas 中转已落地**：新加坡 `glm_aliyun_proxy.py:18890` → relay:8899 → 广州 → 阿里，实测 GLM-5.2 调通
