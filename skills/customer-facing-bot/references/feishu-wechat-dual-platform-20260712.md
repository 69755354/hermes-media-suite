# Feishu + WeChat Dual Platform Setup (2026-07-12)

## Context
After iLink Bot was confirmed to only serve the QR scanner (HOME_CHANNEL), this session added a Feishu (飞书) bot as a second platform on the same customer profile. Feishu supports multiple users and groups natively.

## Architecture
Both platforms share the same `customer` profile, same SOUL.md, same permissions/quotas:
```
Gateway running: customer profile
├── weixin: connected    ← iLink (扫码者本人用，仅单人)
└── feishu: connected    ← Lark (客户加机器人，支持多人)
```

## Feishu Setup Steps
1. Run `hermes --profile customer gateway setup`, select 飞书 (option 10)
2. Choose option 1 (Scan QR to auto-create bot)
3. User scans with Feishu app → credentials saved automatically
4. If auto-create fails, create bot manually at https://open.feishu.cn/app and set env vars:
   - `FEISHU_APP_ID=cli_xxxxxxxx`
   - `FEISHU_APP_SECRET=secret_xxxxxxxx`
   - `FEISHU_DOMAIN=feishu`
   - `FEISHU_CONNECTION_MODE=websocket`

## 🚨 lark-oapi Version Fix
Feishu adapter passes `extra_ua_tags` kwarg to `Client.__init__()`. Requires `lark-oapi>=1.6.0`. The Hermes venv may have 1.5.3 → upgrade:
```bash
/home/ubuntu/.hermes/hermes-agent/venv/bin/pip install --upgrade lark-oapi
```

## Feishu DM Policy
Set in `.env` or config.yaml:
```
FEISHU_DM_POLICY=pairing     # New users trigger pairing approval
FEISHU_ALLOW_ALL_USERS=false # Don't allow everyone
```
Pairing flow identical to WeChat: user messages bot → bot replies with code → admin runs `hermes --profile customer pairing approve feishu <CODE>`.

## Welcome Template Fix
**Don't** put the welcome template inside markdown code blocks (```). When wrapped in a code block, the bot treats it as a code example, not output instructions. 
**Fix:** Write the template as plain text with a "must output verbatim" directive:
```markdown
**新用户欢迎模板（必须逐字输出，一字不差）：**
直接输出以下内容，不要加粗、不要改格式、不要增删任何字：

亲爱的朋友，我终于等到你了！...
```
Not:
```markdown
**新用户欢迎模板：**
```
亲爱的朋友...
```
```
