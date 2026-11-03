# Volcengine ARK Session — 2026-07-14

## Environment
- AstrBot v4.26.6 (Docker, soulter/astrbot:latest)
- Provider type: `openai_chat_completion`
- API base: `https://ark.cn-beijing.volces.com/api/v3`
- API Key: `<ARK_API_KEY>2` (from .env: `ARK_API_KEY`)
- Endpoint ID: `ep-20260710211910-f65h9` (from .env: `ARK_ENDPOINT`)
- Underlying model: Doubao/豆包 (ByteDance)

## Error Progression

| Step | Error | Root Cause |
|------|-------|------------|
| 1 | `401 - Authentication Fails ... ****b41d` | Used DeepSeek key (`sk-...b41d`) against ARK endpoint |
| 2 | `401 - same error` | Key still wrong even after switching api_base to ark.cn-beijing |
| 3 | `404 - model or endpoint unknown` | `model` field missing from provider config → defaults to "unknown" |
| 4 | `404 - model or endpoint unknown` (still) | `model` field was in `provider_sources` (got stripped on restart) |
| 5 | `404 - InvalidEndpointOrModel.NotFound` | `model` added to `provider` section but not persisted through restart |

## Key Discoveries

### Provider Key Field
- Field name is `key` (NOT `api_key`)
- Must be `list[str]`, e.g. `["ark-xxx"]`
- Base class `Provider.get_keys()` reads `self.provider_config.get("key", [""])`

### Model Field Persistence
- `provider_sources` fields are validated against default config schema
- Unrecognized fields (including `model`) are stripped by `check_config_integrity()`
- `model` MUST be in `provider` section, which overrides source via `{**source, **provider}` merge
- `model_configs` is UI-only — does NOT set runtime model name

### Config Auto-Restoration
Values reset on every restart:
- `default_personality` → `"default"`
- `prompt_prefix` → `"{{prompt}}"`
`model` and other non-schema fields → stripped

### Persona Fallback Chain
1. `get_persona_v3_by_id(default_personality)` → if "default", returns `DEFAULT_PERSONALITY`
2. `DEFAULT_PERSONALITY.prompt` = `"You are a helpful and friendly assistant."` (English)
3. ARK model (Doubao) defaults to 豆包 identity when no strong Chinese persona prompt is set

## Working Config (cmd_config.json snippets)

```json
// provider_sources (key and endpoint only, no model field)
{
  "id": "deepseek_main_source",
  "type": "openai_chat_completion",
  "name": "DeepSeek via Volcengine Ark",
  "key": ["<ARK_API_KEY>2"],
  "api_base": "https://ark.cn-beijing.volces.com/api/v3",
  "model_configs": [{"model": "ep-20260710211910-f65h9", "enable": true}]
}

// provider (model field here is critical)
{
  "id": "deepseek_main",
  "enable": true,
  "provider_source_id": "deepseek_main_source",
  "model": "ep-20260710211910-f65h9",
  "modalities": [],
  "custom_extra_body": {}
}
```

## Start-Up Sequence (Required After Each Restart)

```python
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
# 1. Add model field to provider section
for p in c.get('provider', []):
    if p.get('id') == 'deepseek_main':
        p['model'] = 'ep-20260710211910-f65h9'
# 2. Set personality
c['provider_settings']['default_personality'] = 'xiaolu'
c['provider_settings']['prompt_prefix'] = '你的名字叫小鹿...'
with open('/AstrBot/data/cmd_config.json', 'w', encoding='utf-8') as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
# Then restart: docker restart astrbot
```
