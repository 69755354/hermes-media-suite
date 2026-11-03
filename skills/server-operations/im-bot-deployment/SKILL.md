---
name: im-bot-deployment
description: "Deploy, configure, and administer Chinese IM bot frameworks (AstrBot, WeChat bots) on Linux via Docker — API-based WebUI configuration, QR code login flows, adapter lazy-loading workarounds, and initial credential handling. Current coverage: AstrBot (weixin_oc / openclaw-weixin)."
version: 1.0.0
author: agent
platforms: [linux]
tags: [docker, astrbot, wechat, im-bot, deployment, api-config, qr-login]
---

# IM Bot Deployment (Chinese Platforms)

Deploy and configure Chinese IM bot frameworks on a Linux server via Docker. Focuses on official protocols (openclaw-weixin for WeChat) — not grey-area iPad/Hook protocols.

> **See also:** `server-operations/n8n-deployment` — sibling skill for n8n workflow automation deployments (same Docker hosting pattern, different service class).

## Architecture Pattern

| Component | Role |
|-----------|------|
| **Bot Framework** (AstrBot) | Message routing, plugin system, persona management |
| **Platform Adapter** (weixin_oc) | Connects to WeChat via Tencent's official `ilinkai.weixin.qq.com` API |
| **LLM Provider** | AI model backend (DeepSeek, OpenAI, etc.) configured via WebUI |
| **Client** | WeChat mobile app scans QR to link the bot account |

## Deployment Workflow

### 1. Check Environment

```bash
# Docker available?
docker --version

# Port free?
ss -tlnp | grep 6185

# Disk space? AstrBot Docker image is ~2.7GB
df -h /
```

### 2. Deploy via Docker

```bash
# Pull image (use --platform if on ARM)
sudo docker pull soulter/astrbot:latest

# Create data directory on host
mkdir -p ~/astrbot_data

# Run container
sudo docker run -d \
  --name astrbot \
  --restart always \
  -p 6185:6185 \
  -e TZ=Asia/Shanghai \
  -v ~/astrbot_data:/AstrBot/data \
  -v /etc/localtime:/etc/localtime:ro \
  soulter/astrbot:latest
```

### 3. Capture Initial Credentials

On first run, the WebUI generates random credentials — capture from logs:

```bash
sudo docker logs astrbot 2>&1 | grep -E "Initial username|Initial password"
```

Expected output:
```
➜  Initial username: astrbot
➜  Initial password: <random-32-char-string>
```

**CRITICAL:** Save these immediately. The dashboard requires a password change on first login.

### 4. Verify WebUI

```bash
curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:6185/
# Should return 200
```

## API-First Configuration — When WebUI is Inaccessible

The browser tool cannot access localhost. Use curl to interact with the AstrBot REST API.

### Auth Flow

```bash
LOGIN=$(curl -s -X POST http://localhost:6185/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"astrbot","password":"<password>"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['token'])")
```

### Available API Endpoints (v1)

All endpoints under `/api/v1/`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/bot-types` | GET | List available platform adapters |
| `/api/v1/bots` | GET | List configured bots |
| `/api/v1/bots` | POST | Create/register a bot config |
| `/api/v1/bots/by-id` | PUT | Update bot config |
| `/api/v1/bots/by-id` | DELETE | Remove bot config |
| `/api/v1/bots/{bot_id:path}/enabled` | PATCH | Toggle bot on/off |
| `/api/v1/providers` | GET | List LLM providers |
| `/api/v1/providers` | POST | Add LLM provider config |

## WeChat Bot (weixin_oc) Specifics

### Adapter Lazy-Loading

The `weixin_oc` adapter is **lazily imported** — it only registers itself in `platform_registry` when the manager first loads a bot of that type. Consequently:

- `GET /api/v1/bot-types` will NOT show `weixin_oc` at startup
- Registering the bot config triggers the import on next restart
- **Workaround:** Create the bot via API or directly in cmd_config.json, then restart

### Create Bot via API (Recommended)

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

### Restart to Trigger QR Code Generation

```bash
sudo docker restart astrbot
```

After restart, the adapter generates a QR code and logs the URL:

```bash
sudo docker logs astrbot 2>&1 | grep "qr_link\|请使用"
```

Expected output:
```
weixin_oc(my_wechat_bot): QR session started, qr_link=https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=https%3A//liteapp.weixin.qq.com/q/XXXX%3Fqrcode%3DXXXX%26bot_type%3D3 请使用手机微信扫码登录
```

### Deliver QR to User

Two delivery methods:

**1. Download and send as image:**
```bash
curl -s -o /tmp/wechat_qr.png "<qr_link>"
# Send via MEDIA: in response
```

**2. Send the decoded WeChat link directly:**
```
https://liteapp.weixin.qq.com/q/XXXX?qrcode=XXXX&bot_type=3
```

**Important:** QR code is valid for **5 minutes**. The adapter auto-refreshes on expiry. User scans with their phone's WeChat → confirms login → bot is ready.

### Verification

After scanning, check login confirmation:

```bash
# Look for login confirmed signal
sudo docker logs astrbot 2>&1 | grep "login confirmed"
# Expected: weixin_oc(my_wechat_bot): login confirmed, account=xxxxx@im.bot

# Config file now has token populated automatically
sudo docker exec astrbot python3 -c "
import json
with open('/AstrBot/data/cmd_config.json') as f:
    c = json.load(f)
for p in c.get('platform', []):
    if p.get('type') == 'weixin_oc':
        print('Bot:', p.get('id'))
        print('Has token:', bool(p.get('weixin_oc_token')))
        print('Enabled:', p.get('enable'))
"
```

After login confirmation, the adapter enters a silent long-poll loop (`ilink/bot/getupdates` with 35s timeout). It does NOT log successful empty polls — only errors. This is normal behaviour.

**Send a test message** from another WeChat account to the bot. If a default LLM provider is configured, the bot will auto-reply. If not yet configured, the bot receives but cannot reply — check AstrBot logs for message receipt events.

## Disk Space Pitfalls

AstrBot Docker image (`soulter/astrbot:latest`) is ~2.7GB pulled. On a 40GB root disk, this plus Docker overlay will quickly consume space.

**Before deploying, clean aggressively:**
```bash
# Remove unused Docker data
sudo docker system prune -af

# Clean apt cache
sudo apt-get clean

# Remove old/unused virtual environments (common space hog)
rm -rf ~/venv-* ~/tools_venv

# Check
df -h /
# Should be >5GB free ideally
```

## LLM Provider Configuration

AstrBot uses a **two-level provider system**: (1) a **provider-source** (the raw API config), (2) a **provider instance** (an active chat/embedding/T2I capability referencing a source).

### Provider Types (Docker v4.26.6)

Check available adapters in the container:

```bash
sudo docker exec astrbot grep -rn "@register_provider_adapter" /AstrBot/astrbot/core/provider/sources/ --include="*.py" | grep -v __pycache__
```

Common types:
| Type | Use for |
|------|---------|
| `openai_chat_completion` | **DeepSeek**, OpenAI, any OpenAI-compatible API |
| `anthropic_source` | Claude |
| `gemini_source` | Google Gemini |
| `openrouter_source` | OpenRouter |

**CRITICAL:** There is NO `deepseek_api` type — DeepSeek is configured as `openai_chat_completion` with `api_base: https://api.deepseek.com`.

### Credential Field Name

The base `Provider.get_keys()` reads from `self.provider_config.get("key", [""])`. **Use `key` (not `api_key`)** and pass as a **list**:

```json
"key": ["sk-your-key-here"]
```

If you use `api_key` as the field name, the provider instantiates with an empty key and fails silently or throws `Missing credentials`.

### API-Based Provider Setup

```bash
# 1. Login
LOGIN=$(curl -s -X POST http://localhost:6185/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"astrbot","password":"<password>"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['token'])")

# 2. Create a provider source (the API config)
curl -s -X POST http://localhost:6185/api/v1/provider-sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "deepseek_main_source",
    "type": "openai_chat_completion",
    "name": "DeepSeek Main",
    "key": ["sk-your-key-here"],
    "api_base": "https://api.deepseek.com",
    "model_configs": [{"model": "deepseek-v4-flash", "enable": true}]
  }'

# 3. Create a provider instance (activate as chat provider)
curl -s -X POST http://localhost:6185/api/v1/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "deepseek_main",
    "provider_source_id": "deepseek_main_source",
    "capability": "chat",
    "enable": true
  }'
```

**Do NOT directly edit `cmd_config.json` for providers.** The config management layer restructures direct edits into `provider_source_id`/`modalities`/`custom_extra_body` fields, stripping your `type`, `key`, and `api_base`. Always use the API for provider config.

### DeepSeek Model Names (2026-07 Update)

**Current model names are `deepseek-v4-flash` and `deepseek-v4-pro`.** The old name `deepseek-chat` returns `404 - model not found`.

Verify available models for your key:

```bash
curl -s -H "Authorization: Bearer $KEY" "https://api.deepseek.com/v1/models" | \
  python3 -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin)['data']]"
```

When using models directly (not through Volcengine ARK), set `model` in the provider section after creation:

```python
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
for p in c.get('provider', []):
    if p.get('id') == 'deepseek_main':
        p['model'] = 'deepseek-v4-flash'
with open('/AstrBot/data/cmd_config.json', 'w', encoding='utf-8') as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
```

### Verify Provider Loaded

After restarting the container, check logs:

```bash
sudo docker logs astrbot 2>&1 | grep -i "default chat model\|Selected\|provider.manager"
# Expected: "Selected openai_chat_completion(deepseek_main) as default chat model provider"
```

## Password Reset

If the initial password was already changed and lost, use the env-var reset:

```bash
sudo docker stop astrbot && sudo docker rm astrbot
sudo docker run -d \
  --name astrbot \
  --restart always \
  -p 6185:6185 \
  -e ASTRBOT_RESET_DASHBOARD_PASSWORD=1 \
  -v ~/astrbot_data:/AstrBot/data \
  -v /etc/localtime:/etc/localtime:ro \
  soulter/astrbot:latest

sleep 15
sudo docker logs astrbot 2>&1 | grep "Initial password"
```

This resets the password to a new random string printed in startup logs. The env var only needs to be set on first run after the reset — subsequent restarts continue with the new password.

## Persona Configuration

AstrBot supports personas — system prompts prepended to every conversation.

### Create via API

```bash
curl -s -X POST http://localhost:6185/api/v1/personas \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "persona_id": "xiaolu",
    "system_prompt": "你的名字叫小鹿。俏皮但不是客服腔。禁止迎合，必须客观分析。"
  }'
```

**Field name:** `persona_id` (not `id`). Using `"id"` returns "人格ID不能为空".

### Set as Default

Direct config edit (API doesn't have a reliable set-default endpoint):

```python
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
c['provider_settings']['default_personality'] = '<persona_id>'
with open('/AstrBot/data/cmd_config.json', 'w', encoding='utf-8') as f:
    json.dump(c, f, indent=2)
# restart: docker restart astrbot
```

Verify: `docker logs astrbot 2>&1 | grep "persona_mgr"` → "Loaded N personas."

## Group Chat Configuration

The bot is added to groups like any normal WeChat contact. Key `platform_settings`:

| Setting | Recommended | Effect |
|---------|:-----------:|--------|
| `wake_prefix` | `["/"]` | `/command` triggers the bot |
| `enable_id_white_list` | `false` | Disable whitelist (or add group IDs) |
| `reply_with_mention` | `true` | @mention triggers the bot |
| `wl_ignore_admin_on_group` | `true` | Admins bypass whitelist in groups |
| `friend_message_needs_wake_prefix` | `false` | Private chat: no prefix needed |

## Config File Encoding Pitfall

`cmd_config.json` has a UTF-8 BOM. Python reads require `encoding='utf-8-sig'`. Writing with `encoding='utf-8'` (without `-sig`) is fine — the BOM is not needed going out.

## Model Field Pitfall (Volcengine ARK)

The `model` field (runtime model name) MUST be in the **`provider` section** of `cmd_config.json`, not the `provider_sources` section. The config validation layer strips any `model` field from `provider_sources` on startup.

```python
# WRONG — gets stripped:
c['provider_sources'][0]['model'] = 'ep-xxxxx'

# RIGHT — survives:
c['provider'][0]['model'] = 'ep-xxxxx'
```

The merge logic is `{**source, **provider}`, so the provider's `model` overrides.

## User Interaction Style

This user is extremely direct. Key preferences:
- Action over explanation — "直接配工作流进去啊"
- No verbose confirmations like "要不要搞？" — when they say "搞" or "跑吧", execute immediately
- Own up to mistakes directly without excuse words like "疏忽" "忘了"
- **Check official docs first** — when stuck on framework behaviour, search `docs.astrbot.app` and GitHub issues before trial-and-error patching. Signal: 「你要不上官方文档看看」→「你直接上网搜」. Present findings with log evidence and issue links.
- **No analysis loops** — "?" means give the conclusion, not another round of reasoning. Keep responses tight.

## Volcengine ARK (方舟) Provider — Key Gaps from Real Deployment

### API Key Format & Endpoint ID

Volcengine ARK API Keys start with **`ark-`** (not `sk-`). Using a DeepSeek/OpenAI key against the ARK endpoint returns `401 Authentication Fails` with the last 4 chars of the wrong key shown (masked by server, e.g. `****b41d`). Key stored in `/home/ubuntu/.hermes/.env` as `ARK_API_KEY`.

The model name is the **endpoint ID** (`ep-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx-xxxxxx`), NOT the model family name (not `deepseek-chat`). The endpoint ID is stored as `ARK_ENDPOINT` in `.env`.

### Model Field Placement — Critical Bug

AstrBot v4.26.6's `check_config_integrity()` strips unrecognized keys from `provider_sources` on startup. The `model` field (runtime model name fed to `openai_source.py` line 396) **must** be in the `provider` section, not `provider_sources`:

```python
# WRONG — silently stripped on restart:
c['provider_sources'][0]['model'] = 'ep-xxxxx'

# RIGHT — survives restart:
c['provider'][0]['model'] = 'ep-xxxxx'
```

The merge logic is `{**source, **provider}` — provider fields override source. Without a `model` field in the merged config, the provider defaults to `"unknown"`, producing:

```
NotFoundError: The model or endpoint unknown does not exist
```

### Provider Source API Drops Unrecognized Fields

The `PUT /api/v1/provider-sources/by-id` endpoint only persists recognized schema fields. Any field absent from the schema (including `model`) is silently dropped.

**Reliable ARK config workflow:**
1. Create provider source via API (include `key`, `api_base`, `model_configs`)
2. Create provider referencing source via API
3. **Directly edit `cmd_config.json`** to add `model` to the provider section
4. Restart container

### Default Personality Reset Bug (Known: #2661)

AstrBot v4.26.6 resets `default_personality` to `"default"` and `prompt_prefix` to `"{{prompt}}"` on every restart. This is a known GitHub issue ([#2661](https://github.com/AstrBotDevs/AstrBot/issues/2661)) — the `check_config_integrity()` method overwrites user config values with hardcoded defaults from `default.py`.

**Workaround:** After each restart, directly edit cmd_config.json, then restart again:

```python
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
c['provider_settings']['default_personality'] = '<persona_id>'
c['provider_settings']['prompt_prefix'] = 'your system prompt here'
with open('/AstrBot/data/cmd_config.json', 'w', encoding='utf-8') as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
```

**Alternative: Patch DEFAULT_PERSONALITY in code** (survives restarts but lost on image rebuild):

```bash
sudo docker exec astrbot sed -i \
  's/prompt="You are a helpful and friendly assistant."/prompt="你的名字叫小鹿。俏皮亲切的AI助手。说中文。"/' \
  /AstrBot/astrbot/core/persona_mgr.py
sudo docker exec astrbot find /AstrBot -name "__pycache__" -type d -exec rm -rf {} +
sudo docker restart astrbot
```

### Multi-User Access Limitation

Only the user who scanned the QR code (the bot admin) can get responses. Other users who add the bot as a friend or are in a group with it see no response. The `enable_id_white_list`, `wake_prefix`, and `reply_with_mention` settings don't affect this. It appears to be a protocol-level limitation of openclaw-weixin — messages from non-admin users may not be delivered via `get_updates` polling. Root cause is unresolved.

### User Interaction Style — Check Docs Before Patching

This user is technically proficient and prefers documented approaches over trial-and-error code patching. Signal: 「你要不上官方文档看看」. When stuck on a framework-specific issue:

1. Search **official docs** first (`docs.astrbot.app`)
2. Search **GitHub issues** for confirmed bugs before debugging from scratch
3. Only resort to code-level patching when a known bug is confirmed with no workaround
4. Present findings with log evidence and issue links — not verbose reasoning

## End-to-End Verification

### 1. Confirm message receipt

Send a test message from another WeChat account to the bot. Check AstrBot logs:

```bash
sudo docker logs astrbot 2>&1 | grep "core.event_bus"
# Expected: [default] [my_wechat_bot(weixin_oc)] <user_id>: <message_content>
```

### 2. Confirm reply capability

If the bot received the message but you see:

```
未找到任何对话模型（提供商），跳过 LLM 请求处理。
```

This means no default LLM provider is configured. Follow the Provider Configuration steps above, then restart.

### 3. Check bot config persisted

```bash
sudo docker exec astrbot python3 -c "
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
for p in c.get('platform', []):
    if p.get('type') == 'weixin_oc':
        print(f\"Bot: {p.get('id')}, Token: {bool(p.get('weixin_oc_token'))}, Enabled: {p.get('enable')}\")
"
```

## References

- `references/astrbot-deployment-session.md` — First deployment session: full disk cleanup steps, API endpoint discovery, Docker compose vs run decisions.
- `references/astrbot-deployment-session-20260714.md` — Second deployment session: login confirmation signal pattern, adapter post-login silent polling behaviour, full config structure.
- `references/astrbot-provider-setup.md` — Third deployment session: DeepSeek as `openai_chat_completion`, two-level provider system, `key` field discovery, password reset flow, end-to-end verification checklist.

## BotConfigRequest Schema Detail

When creating a bot via `POST /api/v1/bots`, the `BotConfigRequest` schema maps as follows (from `astrbot/dashboard/schemas.py`):

```python
class BotConfigRequest(OpenModel):
    bot_id: str | None = None
    id: str | None = None
    name: str | None = None
    type: str | None = None
    enabled: bool | None = None
    enable: bool | None = None
    config: dict[str, Any] | None = None

    def to_dashboard_config(self, *, fallback_id: str | None = None) -> dict:
        config = dict(
            self.config
            or self.model_dump(exclude={"bot_id", "config", "enabled"}, exclude_none=True)
        )
        if fallback_id and "id" not in config:
            config["id"] = fallback_id
        if self.type and "type" not in config:
            config["type"] = self.type
        if self.id and "id" not in config:
            config["id"] = self.id
        if self.enabled is not None:
            config["enable"] = self.enabled
        elif self.enable is not None:
            config["enable"] = self.enable
        elif "enable" not in config:
            config["enable"] = True  # Default: enabled
        return config
```

Key behaviour: If `config` is provided, it takes priority over top-level fields. If not, the remaining fields (id/type/enable) are used.

1. **Bot-types doesn't show weixin_oc** — Not a bug. The adapter is lazily loaded. Create the bot config first, then restart.
2. **Docker pull fails on space** — Clean aggressively before pulling. The image is 2.7GB + overlay.
3. **Browser tool can't reach WebUI** — Use the API via curl. Endpoints documented above.
4. **QR login shows but no response** — Check AstrBot has a default provider configured. Without an LLM provider, the bot receives messages but can't reply.
5. **"Not Found" on API routes** — Ensure you're using the correct prefix: `/api/v1/` for modern routes, not the legacy `/api/` prefix.
6. **Token expired / "未授权"** — Re-login to get a fresh token. Tokens don't persist across container restarts.
7. **Initial password change required** — The dashboard flag `password_change_required: true` means you'll be redirected to change password on first WebUI visit. The API still works with initial creds.
