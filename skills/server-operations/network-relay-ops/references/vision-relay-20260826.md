# Hermes vision_analyze 走广州 relay 完整记录（2026-08-26）

## 故障时间线

1. 用户说"识图配置好了" → 测 vision_analyze 返回"没有接收到图像"
2. 抽帧到 `/tmp/vision_test_frame.jpg` → vision_analyze 仍看不到图
3. 查 config：`auxiliary.vision` 配了 ARK 端点 `ep-20260826131421-lllz8`
4. 从新加坡直连 `ark.cn-beijing.volces.com` → 30秒 TCP 超时（被墙）
5. 从广州机 curl 同端点 → 200 OK，但返回 `model: doubao-seed-2-0-lite-260428`（纯文本 lite 模型，最初无视觉能力）
6. 用户改了端点绑定后，广州机直接 curl 带图片 base64 → 成功识别画面内容
7. 新加坡 config `base_url` 指向 `http://<GZ_HOST>/vision/v1`（广州公网80）→ 超时不通（广州公网80未对外开放）
8. 改 `base_url` 为 `http://127.0.0.1:18890/v1`（以为是SSH隧道）→ 报 `invalid_api_key`
9. **根因发现**：18890 端口被 `glm_aliyun_proxy.py`（阿里云百炼代理）占着！不是 SSH 隧道。所有 curl 到 18890 的请求打到了 GLM 代理（指向 `maas.aliyuncs.com`），不认 ARK key
10. 换端口 18891 建新隧道 → 全链路通 → vision_analyze 准确识别画面

## 🔴 重大事故：改 vision base_url 撞了主模型通道（2026-08-26 实测）

**事故经过：** 建了 18891 SSH 隧道给 vision 用，改了 config 里 vision 的 base_url。但 **config.yaml 里主模型 glm-5.2 的 `model.base_url` 和 `providers.custom_glm.base_url` 也是 18891**（之前 sed 操作误改了主模型的 base_url）。Hermes gateway 重载 config 后，主对话的 glm-5.2 请求被发到 ARK 视觉端点——ARK 没有 glm-5.2 模型，返回 404 `InvalidEndpointOrModel.NotFound`。

**错误日志：**
```
provider=custom base_url=http://127.0.0.1:18891/v1 model=glm-5.2
HTTP 404: The model or endpoint glm-5.2 does not exist
```

**用户看到的现象：** `⚠️ The model provider failed after retries` — 不是看图卡了，是主对话通道断了。

**根因：** sed 批量替换 `base_url` 时没区分主模型段和 vision 段，把所有 `18890` 都改成了 `18891`，包括主模型的。

**✅ 防范（写死）：**
1. **改 config.yaml 前先 grep 全部 base_url 行**：`grep -n "base_url" config.yaml` — 看清楚每行属于哪个段（model./providers./auxiliary.）
2. **sed 只改指定行号**：`sed -i '38s|old|new|'` 而非全局 `sed -i 's|old|new|'`
3. **改完必须逐行验证**：确认主模型走 18890（glm_aliyun_proxy→阿里云百炼）、vision 走 18891（SSH隧道→广州relay→ARK）
4. **端口分配表（写死，不可混用）：**

| 端口 | 进程 | 用途 | config 段 |
|---|---|---|---|
| 18888 | ark_local_proxy.py | ARK 生图 relay（Seedream） | providers.custom_ark |
| 18890 | glm_aliyun_proxy.py | 阿里云百炼 GLM 代理（主对话） | model.base_url / providers.custom_glm |
| 18891 | SSH隧道→广州8890 | **vision relay（ARK视觉）** | auxiliary.vision |

## 最终架构

```
Hermes vision_analyze
  → 127.0.0.1:18891 (新加坡本地SSH隧道)
  → 127.0.0.1:8890 (广州机 vision_relay_gz.py)
  → https://ark.cn-beijing.volces.com/api/v3/chat/completions (ARK视觉端点)
  → doubao-seed-2-0-lite-260428 (实际跑的模型，有视觉能力)
```

## 关键配置

### 新加坡机 config.yaml（最终正确版）
```yaml
# 主模型 — 走 18890（glm_aliyun_proxy → 阿里云百炼）
model:
  base_url: http://127.0.0.1:18890/v1
  default: glm-5.2
  provider: custom_glm

# vision — 走 18891（SSH隧道 → 广州relay → ARK）
auxiliary:
  vision:
    api_key: <ARK_API_KEY>2
    base_url: http://127.0.0.1:18891/v1
    model: ep-20260826131421-lllz8
    provider: custom
    timeout: 120
```

### 广州机 vision_relay_gz.py（v2，修复版）

**v1 问题：** 原版 relay 透传上游 Authorization 头，但上游（新加坡）传的 ARK key 经过 GLM 代理时被改写或不认。原版 `load_vision_cfg()` 从 config 读 key 也有加载失败的情况。

**v2 修复要点：**
- **硬编码 BASE_URL 和 API_KEY**，不从 config 读（避免加载失败）
- **始终用本机 key**，不透传上游 Authorization（避免 key 被覆盖）
- 添加 stderr 请求日志便于排查

v2 脚本已部署到广州机 `/home/ubuntu/.hermes/scripts/vision_relay_gz.py`（覆盖了原版）。

### 广州机 systemd 服务（持久化）

广州机用户级 systemd 服务 `vision-relay.service`：
```ini
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

**注意：** 不能加 `User=ubuntu` / `Group=ubuntu`，会报 `status=216/GROUP`（`Failed to determine supplementary groups: Operation not permitted`）——用户级 systemd 服务不需要指定 User/Group。

广州机 linger 已开（`loginctl show-user ubuntu | grep Linger=yes`），重启后服务自动恢复。

### 新加坡机隧道持久化

- 脚本：`~/.hermes/scripts/vision_tunnel.sh`
- crontab：`@reboot` + `*/5 * * * *`（检查 18891 端口存活，断了自动重建）
- 隧道命令：`ssh -f -N -p 2222 -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:18891:127.0.0.1:8890 ubuntu@127.0.0.1`

## 🔴 端口冲突陷阱（头号坑）

**建 SSH 隧道前必须 `ss -tlnp | grep <端口>` 确认端口没被占。** `Address already in use` 不是隧道建成功了，是端口被别的进程占着。

本次 18890 被 `glm_aliyun_proxy.py` 占着，导致所有 vision 请求打到了 GLM 代理而非 ARK relay。排查时看 `ss -tlnp` 的 `users:((...))` 字段——是 `ssh` 就是隧道，是 `python3` 就是别的代理。

## 🔴 广州机 relay 常见故障

1. **relay 没启动**：`ss -tlnp | grep 8890` 无输出 → `systemctl --user start vision-relay`（广州机）
2. **relay 读不到 key**：原版 `vision_relay_gz.py` 从 config 读 key 有时失败 → v2 已硬编码
3. **relay 透传了错误的 Authorization**：v1 透传上游 key 被 ARK 拒 → v2 始终用本机 key
4. **relay BrokenPipe**：上游超时后客户端断开，relay 写响应时 BrokenPipe → 不影响功能，只是日志噪音

## 🔴 nohup 经 SSH 挂死 session + setsid 解法

**症状：** 在广州机通过 `ssh -p 2222 ... "nohup python3 ... &"` 启动 relay，SSH session 永不返回（foreground timeout 180s）。

**根因：** nohup 仍持有 stderr/stdout 管道连到 SSH session，SSH 等 EOF 不断。

**✅ 解法：**
```bash
ssh -p 2222 ubuntu@127.0.0.1 "setsid python3 /path/to/script.py >> /tmp/log 2>&1 < /dev/null & disown; echo started"
```
- `setsid`：脱离控制终端
- `>> /tmp/log 2>&1`：重定向 stdout+stderr
- `< /dev/null`：断开 stdin
- `& disown`：后台+脱离 job table

**更优方案：** systemd user service（见 SKILL.md 「免 root 托管」段），持久化 + 崩溃自愈。

## 排查顺序（vision_analyze 看不到图时）

### 第0步：8890 本地直连可用吗？（2026-08-28 新增，最高优先）

**先 `ss -tlnp | grep 8890`——如果 8890 本地有监听，直接 `hermes config set auxiliary.vision.base_url "http://127.0.0.1:8890/v1"` 跳过整个 SSH 隧道。**

8890 是 vision relay 的实际服务端口，18891 只是"经 SSH 隧道到广州 8890"的间接路径。当 8890 直接在本机 LISTEN 时（relay 服务已部署在本地或已迁移到本机），多一跳 SSH 隧道纯属多余且增加单点故障（2222 断 = vision 全挂）。

验证 8890 可用：`curl -X POST http://127.0.0.1:8890/v1/chat/completions -H "Authorization: Bearer <key>" -H "Content-Type: application/json" -d '{"model":"<endpoint>","messages":[{"role":"user","content":"ping"}],"max_tokens":10}'` — 正常返回 JSON = 可用。

### 原排查顺序（18891 隧道路径）

1. `ss -tlnp | grep <config里的端口>` — 确认是 SSH 隧道（ssh 进程）还是别的代理占着
2. 纯文本 curl 测链路：`curl -s -X POST http://127.0.0.1:<port>/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"<endpoint_id>","messages":[{"role":"user","content":[{"type":"text","text":"ping"}]}]}'`
3. 如果返回 GLM/百炼错误 → 端口打错了，换端口
4. 如果返回 ARK 正常回复 → 链路通，再测带图片的请求
5. 图片太大（base64 超 50KB）可能超时 — `ffmpeg -vf scale=480:-1 -q:v 5` 压缩后再传
6. **改 config 后必须验证主模型通道没被破坏**：`grep -n "base_url" config.yaml` 逐行核对

## ARK 端点绑定模型

- curl 返回的 JSON 里 `model` 字段显示实际跑的模型
- `doubao-seed-2-0-lite-260428` 虽然名字带 lite，但有视觉能力，能处理 image_url
- 如果端点绑的模型完全没视觉能力，会报 `InvalidParameter`
- 到火山引擎 ARK 控制台确认端点绑的模型
