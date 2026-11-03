# ClawBot as the Actual Entry Point — 2026-07-12

## The Misconception

The common assumption is: "Bind a spare WeChat account → others message that account → iLink forwards to Hermes." This is WRONG.

The correct flow is:
```
User A (QR scanner) ←→ iLink Bot (xxx@im.bot) ←→ Hermes
                                              ↑
                                     This is the entry point.
                                     NOT the bound WeChat account.
```

## Finding the ClawBot Entry

After binding via QR scan, the entry point is a **ClawBot contact** in the scanner's WeChat. It can be found via:

1. **Chat list** — search for "ClawBot" or "微信ClawBot" or "小龙虾"
2. **Plugin center** — 我 → 设置 → 插件 → ClawBot
3. Sometimes it doesn't show up at all (known issue with some WeChat versions, documented in [这篇知乎文章](https://zhuanlan.zhihu.com/p/2019421545425027479))

## User Experience (2026-07-12)

The user had the ClawBot plugin page but:
- No "send message" button on the detail page
- No "share" or "recommend to friend" option
- Searching for "ClawBot" in chat list returned nothing
- The "开始扫一扫" button opened the camera (activation flow, not useful after binding)

**Result:** No way to access or share the ClawBot entry → iLink Bot is single-user only.

## Why This Happens

From external research (36kr article, majiabin blog):

- **ClawBot is a gray-test feature** — not fully rolled out to all WeChat users
- **ClawBot is an AI entry portal** — it's a contact that forwards messages to the bound OpenClaw/Hermes instance
- **Currently limited to the QR scanner only** — no official multi-user sharing mechanism exposed
- **WeChat's strategy is conservative** — safety > features, so sharing capabilities are deliberately limited

## What to Tell Users Who Can't Find ClawBot

If the user can't find the ClawBot contact after scanning:
1. Check WeChat version — needs to be up to date (`我 → 设置 → 关于微信 → 版本号`)
2. Check plugin list (`我 → 设置 → 插件`)
3. If plugin page shows ClawBot but no entry in chat list → the account type/region may not support full features
4. No known workaround for making the contact appear — this is a WeChat server-side limitation

## Platform Switch Recommendation

When ClawBot/iLink Bot is confirmed single-user, recommend:

| Platform | Pros | Cons | Setup Difficulty |
|:---------|:-----|:-----|:-----------------|
| **飞书 (Feishu/Lark)** | Native Hermes support, group chat, multi-user | Users need Feishu account | Easy — auto-create via QR |
| **企业微信 (WeCom)** | WeChat integration, no new app for customers | Need enterprise registration | Medium |
| **Telegram** | Easiest Hermes support, full-featured | Not commonly used in China | Very Easy |
| **Discord** | Full-featured bot APIs | Not commonly used in China | Medium |
