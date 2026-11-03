# iLink Bot Identity ≠ WeChat Account — 2026-07-12

## Core Discovery

**iLink Bot (`xxx@im.bot`) is a SEPARATE identity from the WeChat account that scanned the QR code.** They are NOT the same recipient. Messages sent to the bound WeChat account go to the WeChat app — they are NOT forwarded to the iLink Bot.

```
个人微信号 A   → 发消息 → 个人微信号 B（闲置号）
                              ↓
                        普通微信会话，B的手机收到
                              ↓
                        ❌ iLink收不到，getupdates.msgs=[]

iLink Bot (3f33fddc85f4@im.bot) ← 只有A扫码获得了该Bot的专用入口
                              ↓
                        ✅ HOME_CHANNEL能通信
                        ❌ 其他好友发到B微信号的消息不会转投
```

## Why HOME_CHANNEL Works

`WEIXIN_HOME_CHANNEL` is the user who scanned the QR code. They got a **dedicated private chat entry** to the iLink Bot. That entry is what allows them to send messages that appear in `getupdates`. It is NOT "this WeChat account can read all messages sent to the bound phone."

## What Doesn't Work (exhaustively tested)

| Attempt | Result |
|:--------|:-------|
| WEIXIN_DM_POLICY=open + ALLOW_ALL_USERS=true | ❌ Only affects Hermes after message arrives. iLink never forwards. |
| Log out bound account from phone | ❌ iLink still doesn't forward stranger messages. |
| Re-bind with fresh QR (new account ID) | ❌ Three different IDs tested, same result. |
| _get_updates with empty buffer | ❌ Returns no msgs for non-HOME_CHANNEL users. |
| Pairing requests from non-HOME_CHANNEL users | ❌ No pairing requests created — iLink doesn't even send them. |

## What the Setup Wizard Actually Does

`hermes gateway setup` → Weixin → DM policy selection:

```
Select [1-4]:
  1) Use DM pairing approval (recommended)
  2) Allow all direct messages
  3) Only allow listed user IDs
  4) Disable direct messages
```

**This only writes to `.env`** — it calls `save_env_value("WEIXIN_DM_POLICY", "open")`. It does NOT call an iLink API to configure server-side message forwarding. The `.env` file change only affects Hermes' behavior AFTER a message arrives from iLink.

## The Correct Way for Others to Use the Bot

Other users need to access the **iLink Bot's dedicated entry/contact**, NOT message the bound WeChat account.

1. The QR-code scanner opens their chat with the iLink Bot
2. Look for a "share / recommend to friend / bot business card / invite" button in the chat UI
3. Share that Bot entry with the other user
4. The other user opens the shared entry and messages the Bot from THERE
5. `getupdates` should now show `from_user_id=xxx@im.wechat` for the new user
6. Hermes then applies dm_policy (pairing/open/allowlist) to decide whether to process the message

If there's no share button, the iLink/ClawBot account may only be open to the scanner.

## What We Can't Fix From Hermes

- iLink server-side message routing is opaque — no management API or web console
- No "close single-chat check" toggle exists in any accessible UI
- New bot accounts may have a 24h-7d cooling-off period with silent filtering
- The only viable multi-user setup is Telelgram, Feishu, Discord, or WeCom (Enterprise WeChat)

## HM Setup Wizard DM Policy Selection Not Enough

- The wizard selection only saves to `.env` (confirmed by code review of `hermes_cli/gateway.py` lines 5603-5614)
- It does NOT call an iLink API to configure server-side behavior
- Conclusion: `.env` values cannot expand iLink's delivery scope

## Quick Summary for Support Tickets

When contacting iLink service: explain that non-HOME_CHANNEL user messages don't appear in `getupdates.msgs` at all. This means iLink is not delivering them to Hermes. Ask:

1. Does iLink only deliver messages from the QR-code scanner's user?
2. Is there an API or config to enable "receive all messages" for a Bot account?
3. How do other users message an iLink Bot without being the scanner?
4. Is the new account in a risk-control observation period? How long?
