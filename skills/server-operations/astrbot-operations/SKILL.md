---
name: astrbot-operations
description: AstrBot 全生命周期运维 — 部署、配置、平台适配器、AI 提供商、排障。覆盖 Docker 部署、openclaw-weixin 微信接入、Volcengine ARK/DeepSeek 等 Provider 配置。
category: server-operations
---

# AstrBot 运维

## 触发条件

当用户提到 AstrBot、微信机器人、6185 端口、openclaw-weixin、iLink、ClawBot 时加载本技能。

---

## 1. 部署（Docker）

```yaml
# compose.yml
services:
  astrbot:
    image: soulter/astrbot:latest
    container_name: astrbot
    restart: always
    ports:
      - "6185:6185"
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ./data:/AstrBot/data
      - /etc/localtime:/etc/localtime:ro
```

```bash
docker compose up -d
# 或者直接跑
docker run -d --name astrbot --restart always \
  -p 6185:6185 \
  -e TZ=Asia/Shanghai \
  -v /path/to/data:/AstrBot/data \
  soulter/astrbot:latest
```

WebUI: `http://<IP>:6185`

### 密码

- **每次容器重启生成随机密码**（`password_change_required: true`）
- 查看密码：`docker logs astrbot 2>&1 | grep "Initial password"`
- 密码散落在启动日志中，找到 `Initial password: xxx` 那一行
- 如有 ASTRBOT_RESET_DASHBOARD_PASSWORD 环境变量则在启动时重置为随机强密码

---

## 2. WebUI API 认证

```bash
LOGIN=$(curl -s -X POST http://localhost:6185/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"astrbot","password":"<当前密码>"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['token'])")
```

API 前缀：`/api/v1`

---

## 3. 平台适配器 — 微信个人号（weixin_oc）

### 创建机器人（API）

```bash
curl -s -X POST http://localhost:6185/api/v1/bots \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "weixin_oc",
    "id": "my_wechat_bot",
    "enabled": true,
    "config": {
      "type": "weixin_oc",
      "id": "my_wechat_bot",
      "enable": true
    }
  }'
```

### 登录流程

1. 创建机器人后重启容器：`docker restart astrbot`
2. 适配器自动调用 `ilink/bot/get_bot_qrcode` 生成二维码
3. 从日志提取 QR 链接：
   ```bash
   docker logs astrbot 2>&1 | grep "qr_link" | tail -1
   ```
4. 提取实际微信链接（URL decode data 参数）发给用户扫码
5. 登录后日志显示 `login confirmed, account=xxx@im.bot`
6. 再次重启容器后适配器自动加载保存的 token，无需重复扫码

### 轮询机制

- 使用长轮询 `ilink/bot/getupdates`（默认 35 秒超时）
- 无新消息时静默，不输出日志
- 会话超时自动触发重新登录

---

## 4. AI Provider 配置（此部分坑最多）

### 架构

AstrBot 的 Provider 是**两层结构**：

1. **provider_sources** — 存放 API Key、endpoint、模型列表等实际凭证
2. **provider** — 引用 source_id，启用/禁用、选能力

### 字段映射（关键）

| 字段 | 说明 | 示例 |
|:---|:---|:---|
| `key` | **API Key（必须是列表 `list[str]`）** | `["sk-xxx"]` |
| `api_base` | API 地址 | `https://ark.cn-beijing.volces.com/api/v3` |
| `model` | **模型名，必须在最顶层** | `ep-20260710211910-f65h9` |
| `model_configs` | WebUI 展示用，不影响运行时模型选择 | `[{"model":"xxx","enable":true}]` |

⚠️ **关键踩坑**：
- Key 字段名是 `key`（不是 `api_key`），类型是 `list[str]`
- 模型名必须在 merge 后的 config 顶层有 `model` 字段，否则运行时会传 `"unknown"`（报错信息包含 `model or endpoint unknown`）
- `model_configs` **不影响运行时**，只是 UI 展示
- provider source 的 `model` 字段会被 `check_config_integrity()` **自动剥离** —— 必须写到 `provider` 节里
- 合并逻辑是 `{**provider_source, **provider}`，provider 的字段覆盖 source

### Root Cause：`check_config_integrity` 机制

AstrBot 每次启动时调用 `AstrBotConfig.check_config_integrity()`，它：
1. 遍历 DEFAULT_CONFIG 的 key 结构
2. 移除用户配置中 DEFAULT_CONFIG **不存在的 key**（日志显示 "Config key removed"）
3. 按 DEFAULT_CONFIG 的顺序重排 key

这导致：
- `provider_sources` 中的 `model` 字段（不在默认配置中）被**自动删除**
- `default_personality` 被重置为 `"default"`（默认值覆盖）
- `prompt_prefix` 被重置为 `"{{prompt}}"`

**修复方法**：每次容器重启后，直写 `cmd_config.json` 再重启一次。

### Volcengine ARK 配置

```bash
# 创建 provider source
curl -s -X POST http://localhost:6185/api/v1/provider-sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "ark_main_source",
    "type": "openai_chat_completion",
    "name": "DeepSeek via Volcengine ARK",
    "key": ["<ARK_API_KEY>"],
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "model_configs": [{"model": "<endpoint_id>", "enable": true}]
  }'

# 创建 provider 引用 source
curl -s -X POST http://localhost:6185/api/v1/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "ark_main",
    "provider_source_id": "ark_main_source",
    "capability": "chat",
    "enable": true
  }'
```

**但 API 会自动剥离 `model` 字段！** 最稳的办法是直写 `cmd_config.json`：

```python
# 在 provider 节加 model 字段（不是 provider_sources）
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
for p in c.get('provider', []):
    if p.get('id') == 'ark_main':
        p['model'] = '<endpoint_id>'  # 坑：必须写在这里
json.dump(c, open('/AstrBot/data/cmd_config.json', 'w'), indent=2, ensure_ascii=False)
```

### 可用 Provider 类型

| 类型 | 说明 |
|:---|:---|
| `openai_chat_completion` | OpenAI 兼容 API（DeepSeek、Volcengine ARK、通义千问都走这个） |
| `anthropic` | Claude |
| `gemini` | Google Gemini |

---

## 5. 配置排障

### 编码问题

`cmd_config.json` 带 UTF-8 BOM，Python 读取需用 `encoding='utf-8-sig'`。

### 日志排障

```bash
# 看 provider 是否加载成功
docker logs astrbot 2>&1 | grep -E "Selected|error|ERRO|provider"

# 看微信适配器状态
docker logs astrbot 2>&1 | grep "weixin_oc"

# 看具体请求错误（401/404）
docker logs astrbot 2>&1 | grep "respond.stage"
```

### 常见错误

| 错误 | 原因 | 修复 |
|:---|:---|:---|
| `401 - Authentication Fails, Your api key: ****b41d is invalid` | key 无效或使用了旧 key | 更新 provider_sources 中的 key |
| `404 - model or endpoint unknown` | `model` 字段缺失（传了 "unknown"） | 在 provider 节加 `model` 字段 |
| `404 - InvalidEndpointOrModel.NotFound` | endpoint ID 错误或未授权 | 检查 ARK endpoint 是否可用 |
| `Missing credentials` | `key` 字段为空或格式不对 | `key` 必须是 `list[str]` |

---

## 6. 白名单与触发器

默认配置：
- `enable_id_white_list: true` + `id_whitelist: []` → 所有用户被白名单拦截
- `wake_prefix: ["/"]` → 用 `/` 唤醒
- `wl_ignore_admin_on_group: true` → 管理员在群里不受白名单限制

---

## 7. 环境变量

保存在 `/home/ubuntu/.hermes/.env`：
- `ARK_API_KEY` — 火山引擎 API Key
- `ARK_ENDPOINT` — 火山引擎 Endpoint ID

---

## 8. 人格/人设配置

AstrBot 支持 persona（人格），作为 system prompt 注入每次对话。

### 方法 A：Persona 系统（受 `check_config_integrity` 影响）

```bash
curl -s -X POST http://localhost:6185/api/v1/personas \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "xiaolu",
    "system_prompt": "你的名字叫小鹿。俏皮但不是客服腔。禁止迎合，必须客观分析。"
  }'
```

**字段名是 `persona_id` 不是 `id`**，否则报「人格ID不能为空」。

**设为默认（每次重启后执行）：**
```python
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
c['provider_settings']['default_personality'] = '<persona_id>'
with open('/AstrBot/data/cmd_config.json', 'w', encoding='utf-8') as f:
    json.dump(c, f)
```
重启后验证：`docker logs astrbot 2>&1 | grep "persona_mgr"` → "Loaded N personas."

**为什么重启后人设不生效？** `PersonaManager.__init__` 从 `acm.default_conf`（硬编码 `{"default_personality": "default"}`）读取默认值，`check_config_integrity` 在启动时覆盖用户配置。每次重启后需重设。

### 方法 B：`prompt_prefix`（更可靠，但仍需重启后重设）

`prompt_prefix` 被添加到每条用户消息前。它不走 persona 系统，绕开了 `default_personality` 回退问题。

```python
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
c['provider_settings']['prompt_prefix'] = '你的名字叫小鹿。俏皮亲切的AI助手。说中文。禁止迎合必须客观。'
with open('/AstrBot/data/cmd_config.json', 'w', encoding='utf-8') as f:
    json.dump(c, f)
```

注意：`prompt_prefix` 也会在重启时被重置为 `"{{prompt}}"`，同样需要每次重启后重写。

---

## 9. 多用户接入

### 添加好友

Bot 号是一个**真实微信个人号**（通过 ClawBot 扫码登录）。其他人要跟它聊天，必须先加它为好友：
1. 别人搜 bot 号的微信号/手机号添加好友即可
2. 加上好友之后就能直接私聊
3. 也能拉 bot 号进群——先把 bot 号加为好友，然后像拉任何好友一样拉进群

### 群聊触发

群里用 `@小鹿` 或唤醒前缀 `/` 触发：
- 不 @ 不 / 的消息 bot 完全忽略
- 私聊不需要任何前缀，直接发消息就行

### 权限配置（首次部署必调）

默认配置 `enable_id_white_list: true` + 空白名单 = 任何人发消息 bot 都不回。

```python
c['platform_settings']['enable_id_white_list'] = False      # 关白名单
c['platform_settings']['reply_with_mention'] = True          # 开@唤醒
c['platform_settings']['friend_message_needs_wake_prefix'] = False  # 私聊无需前缀
```

---

## 10. `default_personality` 回退问题

**现象：** 每次容器重启后 `default_personality` 会被重置为 `"default"`，人设不生效。

**原因：** AstrBot v4.26.6 的 config 初始化逻辑在启动时覆盖了该字段（`default.py` 硬编码 `\"default_personality\": \"default\"`）。

**修复（每次容器重启后都需要执行）：**

```python
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
c['provider_settings']['default_personality'] = 'xiaolu'
with open('/AstrBot/data/cmd_config.json', 'w', encoding='utf-8') as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
```

然后重启容器。已知 AstrBot v4.26.6 行为，非配置错误。

---

## 11. ^ 群聊配置

| 配置 | 推荐值 | 效果 |
|:---|:---:|:---|
| `wake_prefix` | `["/"]` | `/命令` 触发 |
| `enable_id_white_list` | `false` | 关白名单（或加群 ID） |
| `reply_with_mention` | `true` | @小鹿 触发 |
| `friend_message_needs_wake_prefix` | `false` | 私聊直接聊 |

---

## 10. 用户交互风格

这个用户极度直接，不接受啰嗦：
- 直接配，不要问「要不要搞」
- 说「搞」「跑吧」立刻执行
- 犯错直接认，不说「疏忽」「忘了」
