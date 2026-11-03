# Dual WeChat Bot Setup — 2026-07-12

## Goal

Set up a customer-facing WeChat bot (profile: `customer`) alongside the existing admin monitoring WeChat bot (profile: `default`). Customer bot has limited features (搜爆款/写文案/做分析 only, no video) and sends pairing approval requests to the admin's monitoring WeChat.

## Architecture

```
Hermes (Tencent Cloud)
├── Profile: default
│   ├── Gateway: hermes-gateway.service
│   ├── WeChat: 0ae3ec609fc7@im.bot  (admin monitoring)
│   └── lightclawbot: WebSocket
│
└── Profile: customer
    ├── Gateway: hermes-gateway-customer.service
    ├── WeChat: f64a1fc401db@im.bot  (customer-facing)
    ├── permissions.json              → feature gates
    └── SOUL.md                       → bot identity + onboarding
```

## Customer Bot Identity

- Name: 小天
- Welcome: "亲爱的朋友，我终于等到你了！我是你最贴心的助手小天"
- Style: 亲切温暖，普通话，不自称名字
- Features: 搜爆款 ✅ 写文案 ✅ 做分析 ✅ | 视频 ❌

## Progress Feedback Pattern

Customer bots MUST tell the user what they're doing before async operations. Silent processing makes the bot feel dead:

```
搜爆款 → 「好嘞，我现在开始搜[行业]的爆款内容...」→ 搜到 → 「搜到了！给你整理一下👇」
写文案 → 「好的，我现在开始帮你写[产品/店]的文案...」→ 写完 → 「写好了！你看看合不合适👇」
做分析 → 「收到，我现在开始分析[对象]...」→ 完成 → 「分析完了，给你说说结论👇」
```

## Layered SOUL.md Architecture

**Do NOT blindly strip the admin SOUL.md.** Use a layered approach:

```
Layer 1: Bot Identity + Permissions checks
Layer 2: General methodology (3-point, 5-step, empathy — always useful)
Layer 3: Advanced workflows (gated by permissions.json, skipped when false)
```

The admin's methodology (3-point, 5-step, empathy framework) is useful for customer bots too — keep it in Layer 2. Only production pipelines (video, ffmpeg, etc.) need gating behind permissions.

## Permissions Config

```json
{
  "defaults": {
    "video": false,
    "trending_search": true,
    "copywriting": true,
    "analysis": true,
    "daily_quota": 0,
    "monthly_quota": 0
  },
  "users": {}
}
```

## Pairing Monitoring

Cron job `customer-pairing-check` (every 2min, no_agent=true):
- Checks `hermes --profile customer pairing list`
- Silent when idle → delivers notification only when pending
- Deliver target: `weixin:o9cq80-_0LC4JqLptMI37QFgnC7o@im.wechat` (admin's monitoring bot)

## Key Commands

```bash
# Approve a pending pairing request
hermes --profile customer pairing approve weixin <code>

# Restart customer gateway
systemctl --user restart hermes-gateway-customer

# Check both gateways
systemctl --user status hermes-gateway
systemctl --user status hermes-gateway-customer
```

## Customer Account Credentials

- account_id: `f64a1fc401db@im.bot`
- token: `<REDACTED>`
- user_id: `o9cq807ARbXtrKK7TjDmH7LB6Mj0@im.wechat`
- base_url: `https://ilinkai.weixin.qq.com`

## Lessons Learned

1. **Welcome message formatting matters** — arrow `→` prefixes and extra indentation look like "乱码" to users. Keep clean plain text.
2. **Progress feedback is non-negotiable** — each async step needs a "before" and "after" message. Silent processing = dead bot.
3. **Admin methodology is useful for customer bots** — don't strip 3-point, 5-step, empathy framework. Only gate specific production workflows behind permissions.
