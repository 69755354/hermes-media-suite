# Full Deployment Session — 2026-07-14

## Summary

Complete end-to-end AstrBot v4.26.6 deployment with openclaw-weixin WeChat bot on a Linux server via Docker. All major pitfalls encountered and resolved.

## Timeline

1. **Deployment**: Docker pull + run on port 6185
2. **Bot creation**: weixin_oc adapter via API, QR code login with WeChat
3. **Provider setup**: DeepSeek -> Volcengine ARK pivot (key format, model field strip)
4. **Persona**: Created "小鹿" personality via API
5. **Group config**: Whitelist disabled, @mention + /prefix trigger

## Key Error Resolution Chain

| Error | Root Cause | Fix |
|-------|-----------|-----|
| "Missing credentials" | Used `api_key` field instead of `key` | Use `key: ["value"]` (list format) |
| "401 - key ****b41d invalid" | Was using DeepSeek key, not ARK key | Switch to `ark-xxx` key format |
| "404 - unknown endpoint" | `model` field missing from merged config | Add `model: "ep-xxx"` to `provider` section (not `source`) |
| "404 - InvalidEndpointOrModel" | Endpoint ID wrong | Use `ep-20260710211910-f65h9` |
| "人格ID不能为空" | Used `"id"` instead of `"persona_id"` | Use `"persona_id"` field name |
| "未找到任何对话模型" | No default provider configured | Add provider source + instance, set default |

## API Endpoints Used

- `POST /api/auth/login` — auth
- `GET/POST /api/v1/bot-types, /bots` — bot management
- `GET/POST/PUT /api/v1/provider-sources, /providers` — LLM config
- `GET/POST/PUT /api/v1/personas` — personality
- `docker exec -it astrbot python3 -c "..."` — direct config manipulation

## Direct Config Edits (cmd_config.json)

The API works for creation but certain fields must be set via direct config editing:
- `model` in `provider` section (gets stripped from `provider_sources`)
- `default_personality` in `provider_settings`
- Group chat settings (`reply_with_mention`, `enable_id_white_list`, etc.)
