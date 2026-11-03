# Customer Bot Profile Configuration Guide

## Overview

When deploying Hermes as a customer-facing bot (like "小鹿"), the profile configuration spans three layers:
1. **Gateway layer** — who gets through, what events fire
2. **Config layer** — session reset notifications, platform enable/disable
3. **SOUL.md layer** — identity, rules, analysis frameworks, group filtering

This guide captures patterns learned from configuring a Feishu/Weixin customer bot for new media operations.

---

## 1. Gateway Layer — Message Filtering

### Feishu `require_mention`

**Location:** Customer profile's `.env` file (`/home/ubuntu/.hermes/profiles/<profile>/.env`)

```ini
FEISHU_REQUIRE_MENTION=true   # Default. Drops non-@mentioned group messages at gateway level.
FEISHU_REQUIRE_MENTION=false  # All group messages reach the agent (SOUL.md handles filtering).
```

**How it works:**
- Set to `true`: Feishu adapter's `_admit()` method returns `group_policy_rejected` for non-@ messages — the agent never sees them.
- Set to `false`: All group messages pass through to the agent, which then applies SOUL.md rules to decide whether to respond.

**Key insight:** With `require_mention=true`, the SOUL.md rule "话题延续不用@" cannot work because follow-up messages don't have @ and are dropped at the gateway. These two approaches are mutually exclusive — pick one:
- **Strict @-only** → `require_mention=true`, SOUL.md says "每条消息都要@"
- **Smart topic tracking** → `require_mention=false`, SOUL.md handles filtering with topic continuity

### Weixin/lightclawbot Platform

**Location:** Customer profile's `config.yaml`

```yaml
platforms:
  lightclawbot:
    enabled: true
  weixin:
    enabled: false   # Set to false to disable WeChat platform
    extra:
        dm_policy: open
        allow_all_users: true
```

**Note:** Weixin platform is separate from Feishu platform. If the bot only operates on Feishu, disable Weixin to avoid interference.

---

## 2. Config Layer — Session Reset & Notifications

### Suppressing Session Reset Notifications

**Location:** `session_reset` block in `config.yaml`

```yaml
session_reset:
  mode: both              # both scheduled + idle timeout reset
  idle_minutes: 1440      # 24 hours — effectively never fires for idle
  at_hour: 4              # Reset daily at 4:00 AM
  notify: false            # ⬅️ ADD THIS: suppresses the "Session automatically reset" notification to users
```

Without `notify: false`, the session reset at 4:00 AM sends a system message to users like:
```
◐ Session automatically reset (daily schedule at 4:00). Conversation history cleared.
Use /resume to browse and restore a previous session.
```

This is confusing for end users who see it as a bot response. **Always set `notify: false` for customer-facing bots.**

### Feishu New Member Welcome (Adapter-Level)

**File modified:** `plugins/platforms/feishu/adapter.py` in the Hermes agent installation.

To send welcome messages when new users join a Feishu group:

1. **Register the event** in `_build_event_handler()`:
   ```python
   .register_p2_im_chat_member_user_added_v1(self._on_user_added_to_chat)
   ```

2. **Add handler method** that extracts `chat_id` and `users` from `P2ImChatMemberUserAddedV1Data`:
   ```python
   def _on_user_added_to_chat(self, data):
       event = getattr(data, "event", None)
       chat_id = str(getattr(event, "chat_id", "") or "")
       users = getattr(event, "users", []) or []
       names = [u.name for u in users if hasattr(u, "name") and u.name]
       name_list = "、".join(names)
       welcome = f"欢迎{name_list}加入！...自我介绍..."
       # Submit to async loop
       self._submit_on_loop(self._loop, self._send_welcome_message(chat_id, welcome))
   
   async def _send_welcome_message(self, chat_id, content):
       import json
       payload = json.dumps({"text": content}, ensure_ascii=False)
       await self._send_raw_message(chat_id=chat_id, msg_type="text", payload=payload, ...)
   ```

3. **Restart gateway** after modification.

**Important:** This is a core-plugin modification. It will be overwritten on Hermes updates. Document the change.

---

## 3. SOUL.md Layer — Architecture Patterns

### Identity & Permissions (Layer 1)

```
🔴 Layer 1: Identity + Permissions (unconditional enforcement)

├─ 🆔 Forced Identity — Name, selfie path (MEDIA:/path), no self-API
├─ ⛔ Hard Rules — No pandering, no self-calling APIs
├─ 🚨 Permission Gate — Check permissions.json + quota_tracker.json per user
├─ ⛔ Hidden Needs Analysis — MUST analyze before answering (iron law)
└─ 💬 Speaking Style — Playful but not sycophantic, concise when working
```

### Analysis Framework (Layer 2)

```
🟡 Layer 2: Internal Thinking Tools

🧠 Analysis (for breaking down problems):
├─ First Principles — Decompose to fundamentals, rebuild logic
├─ Behavioral Psychology — Fear/herd/laziness/vanity/resonance
├─ Consumer Psychology — Need→Search→Evaluate→Decide→Post-purchase
├─ MECE + Issue Tree — Mutually exclusive, collectively exhaustive
├─ Empathy Depth — Scene→Behavior→Psychology→Emotion→Shame→Self-justification
└─ Underlying Anxiety — Identity/Death/Loneliness/Loss of control

🎯 Expression (for giving advice):
└─ Conclusion first, then process — "I suggest X, because: situation→problem→solution"
```

### Group Chat Filtering (Works with Gateway `require_mention`)

**With `require_mention=true` (strict):**
```
- @bot → Reply ✅
- No @ → Completely ignored, agent never sees it ❌
```

**With `require_mention=false` (smart, SOUL.md handles):**
```
- @start new topic → Reply ✅
- Previous reply was from bot, topic ongoing → Reply without @ ✅
- Topic ended / unrelated → Ignore ❌  
- Casual chat (weather/emojis) → Ignore ❌
```

### User Welcome Template

First interaction with a new user should include:
- Self-introduction ("I'm 小鹿")
- Available capabilities (search trends / write copy / do analysis / make videos)
- Reminder to @mention in group chats

---

## 4. Pitfalls & Lessons

| Pitfall | Lesson |
|:--------|:-------|
| Session reset sends system message to users | `notify: false` — always suppress for customer bots |
| Vague "话题延续不用@" doesn't work with `require_mention=true` | Gateway drops non-@ messages before SOUL.md can process them |
| New member join events not routed to agent | Must register `p2_im_chat_member_user_added_v1` at adapter level |
| Bot responds to every group message without @ | Check `FEISHU_REQUIRE_MENTION` in `.env` — set to `true` |
| Expression frameworks too many → bot confused | Keep it simple: one unified "先给结论，再给过程" |
| **SOUL.md update not taking effect** | **`prompt_caching.cache_ttl: 5m` — restart gateway or wait 5 min** |
| **Model not found in available_models** | **SOUL.md calls deepseek-v4-pro but available_models only has flash — add both** |
| **New user quota date stale** | **`quota_tracker.json` date doesn't auto-update — check before reading** |

---

## 5. File Reference

| File | Purpose |
|:-----|:--------|
| `/home/ubuntu/.hermes/profiles/<profile>/config.yaml` | Platform enable/disable, session reset, notify |
| `/home/ubuntu/.hermes/profiles/<profile>/.env` | `FEISHU_REQUIRE_MENTION`, API keys, env vars |
| `/home/ubuntu/.hermes/profiles/<profile>/SOUL.md` | Bot identity, rules, analysis framework, filtering |
| `/home/ubuntu/.hermes/hermes-agent/plugins/platforms/feishu/adapter.py` | Event handlers (new member welcome) |
| `/home/ubuntu/.hermes/profiles/<profile>/permissions.json` | Per-user feature gates + daily quotas |
| `/home/ubuntu/.hermes/profiles/<profile>/quota_tracker.json` | Daily usage tracking |
