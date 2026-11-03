# Customer Bot SOUL.md Structure — 2026-07-12 Production Pattern

A proven 3-layer architecture for customer-facing bot SOUL.md, built for the "小天" WeChat bot.

## Three-Layer Architecture

```
┌─ Layer 1: Identity + Permissions ────────────────┐
│  Permissions check rules, feature table,           │
│  daily quota tracking, welcome onboarding,         │
│  3-step interaction guides (progress -> work ->    │
│  output), dialogue style                           │
├─ Layer 2: Internal Thinking Tools ────────────────┤
│  Bot identity, core methodology (3-point method,   │
│  5-step analysis, empathy framework), core         │
│  beliefs (compliance, empathy, search-first)       │
├─ Layer 3: Locked Feature Workflows ───────────────┤
│  Gated behind permissions.json check               │
│  "Only trigger when video=true"                    │
│  Contains: full video production pipeline,         │
│  model config, scene composition rules             │
└────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Layer 2 is NOT gated — it stays active always
Methodology (3-point method, 5-step analysis, empathy framework) is safe to keep in the SOUL.md even when the corresponding features are locked. These are thinking tools the agent uses internally — customers never see them.

### 2. Layer 3 has a hard permission gate
The video production workflow includes a clear gate at the top:

```markdown
🚨 This section only activates when permissions.json has video: true
🚨 Current state: video: false → skip this section
```

This way, flipping the permission later makes the workflow instantly available without SOUL.md changes.

### 3. Interaction guides use "три-step" pattern
The guides were progressively simplified from 6-step detailed procedures to:

```
1. Tell customer what you're about to do ("I'm searching now...")
2. Do the work silently
3. Tell customer it's done, output the result
```

This hides internal workflow from customers while keeping them informed of progress.

### 4. Quota tracking uses a separate file
`quota_tracker.json` lives in the profile root alongside `permissions.json`:

```json
{}
```

The agent reads it before each task, checks `daily_quota` from permissions.json, compares used count, and increments after successful execution.

## Welcome Message Final Version

```
亲爱的朋友，我终于等到你了！我是你最贴心的助手小天，目前我能给你提供以下服务：

🔍 搜爆款 — 帮你搜同行的热门内容、选题
直接说：帮我搜一下[行业]的爆款

✍️ 写文案 — 帮你写短视频文案、口播稿
直接说：帮我写个[产品]的文案

📊 做分析 — 帮你分析行业趋势、竞品、账号
直接说：帮我分析一下[行业/账号]
我还能给你生成视频，自动发布等等，但是需要我老大批准哦

需要什么直接跟我说就行，先告诉我是做什么行业的～
```

Note: No indentation, no arrows, no verbose formatting. Clean and scannable.

## Permissions.json

```json
{
  "defaults": {
    "video": false,
    "trending_search": true,
    "copywriting": true,
    "analysis": true,
    "daily_quota": 3,
    "monthly_quota": 0
  },
  "users": {}
}
```

## Over-limit Response

When customer hits daily quota:
> 亲，你今天已经用了3次啦，每天最多使用3次哦～明天再来找我吧！😊

## Pairing Approval Pitfall (2026-07-12)

### The Code Display Bug

When `hermes --profile customer pairing list` shows:

```
Pending Pairing Requests (1):
  Platform     Code       User ID              Name
  --------     ----       -------              ----
  weixin       45b21617   o9cq807...@im.wechat o9cq807...@im.wechat
```

The `45b21617` is the **first 8 hex chars of the SHA-256 hash** — NOT the pairing code. The real code is a random 8-char string from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` sent to the user via WeChat.

**You CANNOT approve by typing the hash prefix.** You need the code the user received.

### If You Locked Out the Platform

Too many failed approve attempts lock out the platform for 3600s. To clear:

```bash
# Edit _rate_limits.json:
# Remove "_lockout:weixin" key
# Reset "_failures:weixin" to 0
```

### Clean Gateway Restart (When Connected but 0 Channels)

When `gateway_state.json` shows `weixin: {state: "connected"}` but no messages arrive:

```bash
systemctl --user stop hermes-gateway-customer
sleep 2
rm -f /home/ubuntu/.hermes/profiles/customer/gateway.lock
rm -f /home/ubuntu/.hermes/profiles/customer/gateway_state.json
systemctl --user start hermes-gateway-customer
sleep 10
# Verify: channels > 0
cat /home/ubuntu/.hermes/profiles/customer/gateway_state.json
```

### Connection Verification

Always verify TWO things, not just systemctl status:

1. `gateway_state.json` → `weixin.state == "connected"`
2. `channel_directory.json` → `weixin` has at least 1 channel entry
3. `hermes --profile customer pairing list` returns data (not "No pairing data found")
