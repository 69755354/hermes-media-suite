# Feishu Setup on Customer Profile — 2026-07-12

## Context

Customer profile (`customer`) was already running with WeChat (iLink). Added Feishu/Lark as a second platform so customers could reach Xiao Tian without the iLink multi-user limitation.

## Setup Steps

1. Ran `hermes gateway setup` on the customer profile
2. Selected option 10 (飞书 / Lark)
3. Selected option 1 (Scan QR code to auto-create bot)
4. QR code displayed → user scanned with Feishu app
5. Wizard was interrupted before completion (terminal timeout)
6. **Fallback**: Created bot manually via Feishu developer console → got App ID + App Secret
7. Wrote credentials to `.env`:
   ```
   FEISHU_APP_ID=cli_aad9fec111389cdc
   FEISHU_APP_SECRET=<FEISHU_APP_SECRET>
   FEISHU_DOMAIN=feishu
   FEISHU_CONNECTION_MODE=websocket
   FEISHU_ALLOW_ALL_USERS=true
   ```

## 🚨 Critical: lark-oapi version

The Feishu adapter passes `extra_ua_tags` to `Client.__init__()`. This was added in **lark-oapi 1.6.0**. The installed version was 1.5.3, causing:

```
TypeError: Client.__init__() got an unexpected keyword argument 'extra_ua_tags'
```

**Fix:**
```bash
# In Hermes venv:
/home/ubuntu/.hermes/hermes-agent/venv/bin/pip3 install --upgrade lark-oapi
# 1.5.3 → 1.7.1
```

## Verification

After restart:
```json
{
  "gateway_state": "running",
  "platforms": {
    "weixin": {"state": "connected"},
    "feishu": {"state": "connected"}
  }
}
```

Both platforms active. Bot responds on both channels using the same SOUL.md personality and permissions.

## Results

- User opened Feishu → found the bot contact → messaged it
- Xiao Tian responded via Feishu ✅
- Customer now has a working channel (Feishu) that supports multiple users

## Architecture Notes

- Both platforms share same `customer` profile
- Same SOUL.md, permissions.json, quota_tracker.json
- No changes needed to the bot's personality or workflows
- Feishu supports DM + group chats natively (unlike iLink which is DM-only)
- WebSocket mode requires no public IP/URL

## 🚨 SOUL.md Changes Made for Feishu

### Welcome template — must NOT be in code blocks

Original format (markdown code block → bot didn't output verbatim):
```markdown
**新用户欢迎模板：**
```
亲爱的朋友...
```
```

Fixed format (plain text with explicit "output verbatim" instruction):
```markdown
**新用户欢迎模板（必须逐字输出，一字不差）：**
直接输出以下内容，不要加粗、不要改格式、不要增删任何字：

亲爱的朋友...
```

### Implicit needs recognition added

Before answering any customer question, bot must:
1. Identify surface needs (what the customer asked)
2. Uncover real needs (what they actually want)
3. Find blind spots (what they might be missing)

Then ask for confirmation in one sentence before proceeding.

Added as a general rule in SOUL.md under "客户提问统一规则" section.
