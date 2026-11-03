# AstrBot Provider Setup — Session Log (2026-07-14)

**Scenario:** Deploy AstrBot via Docker → configure weixin_oc WeChat adapter → add DeepSeek as LLM provider → end-to-end verification.

## Key Discovery: Provider Field Name

**Problem:** `openai_chat_completion` provider failed with "Missing credentials."
**Root cause:** The base `Provider.get_keys()` reads `self.provider_config.get("key", [""])`. The field must be `key` (a list), NOT `api_key`.

The error `openai.OpenAIError: Missing credentials. Please pass an api_key` is misleading — the AstrBot config layer correctly passes the key list, but the wrong field name means the list is empty.

**Fix:** Use `"key": ["sk-xxxx"]` in provider config, never `"api_key": "sk-xxxx"`.

## Two-Level Provider System

AstrBot v4.26.6 separates provider configuration into:

1. **Provider Source** (`POST /api/v1/provider-sources`): Contains the raw API endpoint config — type, key, api_base, model_configs.
2. **Provider Instance** (`POST /api/v1/providers`): An active provider that references a source, with capability (chat/embedding etc.) and enable flag.

**Direct editing of cmd_config.json for providers is UNRELIABLE.** The config management layer restructures provider entries on load — adding `provider_source_id`, `modalities`, `custom_extra_body` fields and stripping `type`, `key`, `api_base`. Always use the API.

## DeepSeek as openai_chat_completion

There is no `deepseek_api` adapter in AstrBot's Docker image. DeepSeek exposes an OpenAI-compatible API, so use:

- **type:** `openai_chat_completion`
- **api_base:** `https://api.deepseek.com`
- **model:** `deepseek-v4-flash` (NOT `deepseek-chat` — the old name returns 404)
- **model_configs:** `[{"model": "deepseek-v4-flash", "enable": true}]`

**2026-07-15 update:** DeepSeek changed model names. `deepseek-chat` no longer exists. Current models are `deepseek-v4-flash` and `deepseek-v4-pro`. Verify with `GET https://api.deepseek.com/v1/models`.

## Provider Source Creation Command

```bash
curl -s -X POST http://localhost:6185/api/v1/provider-sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "deepseek_main_source",
    "type": "openai_chat_completion",
    "name": "DeepSeek Main",
    "key": ["sk-your-key-here"],
    "api_base": "https://api.deepseek.com",
    "model_configs": [{"model": "deepseek-chat", "enable": true}]
  }'
```

Then create the provider:
```bash
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

## Password Reset with Env Var

When the initial dashboard password was changed and lost:

```bash
sudo docker stop astrbot && sudo docker rm astrbot
sudo docker run -d \
  --name astrbot \
  --restart always \
  -p 6185:6185 \
  -e ASTRBOT_RESET_DASHBOARD_PASSWORD=1 \
  -v /home/ubuntu/AstrBot/data:/AstrBot/data \
  -v /etc/localtime:/etc/localtime:ro \
  soulter/astrbot:latest
```

The env var triggers a new random password on startup. Capture it from logs.

## Verification Checklist

1. **Login confirmed:** `sudo docker logs astrbot 2>&1 | grep "login confirmed"`
2. **Provider loaded as default:** `sudo docker logs astrbot 2>&1 | grep "Selected.*default chat model"`
3. **Message received:** `sudo docker logs astrbot 2>&1 | grep "core.event_bus"`
4. **No provider error:** Check there's no "未找到任何对话模型" in logs after message receipt
