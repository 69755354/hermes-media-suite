# iLink QR Login Recovery & Session Expiry (2026-07-12)

## Session Expiry Symptoms

```
gateway.log:
ERROR gateway.platforms.weixin: [Weixin] Session expired; pausing for 10 minutes
```

- Gateway shows `weixin: connected` briefly, then logs session expired
- After 10-minute pause, retry fails again → infinite 10-minutes cycles
- `hermes pairing list` shows nothing
- Old saved token no longer works

## Recovery Flow

### Step 1: Direct QR Login (bypass setup wizard)

Run the `qr_login` function directly:

```bash
cd /home/ubuntu/.hermes/profiles/<profile>
HERMES_HOME=/home/ubuntu/.hermes/profiles/<profile> python3 -c "
import sys, asyncio
sys.path.insert(0, '/home/ubuntu/.hermes/hermes-agent')
from gateway.platforms.weixin import qr_login
creds = asyncio.run(qr_login('/home/ubuntu/.hermes/profiles/<profile>'))
if creds: print('OK:', creds['token'][:30])
else: print('FAIL')
"
```

This prints a QR code URL (e.g. `https://liteapp.weixin.qq.com/q/7GiQu1?qrcode=...`). The URL must be opened in **WeChat's in-app browser**.

### Step 2: Save New Credentials

After the QR scan confirms, `qr_login()` returns `credentials` dict with `token`, `base_url`, `user_id`. Save to the account file and update `.env`.

### ⚠️ Account ID Changes on Re-bind

The iLink **account ID changes** on re-bind — it's NOT the same as before (e.g. `f64a1fc401db@im.bot` → `2b8f99a5c0bd@im.bot`). All old pairing data, approved users, and session history are lost.

**Must update after re-binding:**
1. Account JSON filename → new account ID
2. `.env` → `WEIXIN_ACCOUNT_ID` + `WEIXIN_TOKEN`
3. systemd service unit if `Environment=` references account ID
4. `systemctl --user daemon-reload` + restart

### Step 3: Clean Restart

```bash
systemctl --user stop hermes-gateway-customer
sleep 2
rm -f /home/ubuntu/.hermes/profiles/<profile>/gateway.lock
rm -f /home/ubuntu/.hermes/profiles/<profile>/gateway_state.json
systemctl --user daemon-reload
systemctl --user start hermes-gateway-customer
sleep 15
# Verify weixin.state == connected
```

## Proactive Message Test

```bash
hermes --profile <profile> send -t "weixin:<user_id>@im.wechat" "测试消息"
```

- Admin receives it → iLink can send outbound ✅
- Admin replies and it arrives → iLink receives paired messages ✅
- Test account's reply doesn't arrive → iLink only forwards paired users ❌

## Debug Workflow (User-Provided)

When messages from other accounts don't reach the bot:

1. **Check gateway logs** — `grep "inbound\|from=" gateway.log`. No entry = iLink isn't forwarding.
2. **Logs absent** → iLink bridge not reporting DM events. Check login status, callback connections, DM event subscriptions.
3. **Logs present but ignored** → dm_policy filtering. Change to `open` or approve pairing code.
4. **Model called but can't send** → check send permissions, risk control, rate limits.
5. **Group-only / @mention-only** → confirm no restrictive trigger config.

### Common Causes (in priority)

- **Whitelist** — Most bots default to friend-whitelist. Non-whitelisted accounts' messages silently dropped.
- **Trigger rules** — Prefix/keyword/@mention blocking plain text.
- **Friend relationship** — Must be mutual friends (双向好友).
- **Bot offline / instance conflict** — Multi-device or logged-out account.
- **WeChat risk control** — New/unfamiliar accounts' messages delayed or filtered.

### Fast Self-Test

1. Message from the bot account itself → if it responds, bot/API is fine
2. Check logs for test account's message
3. Temporarily disable whitelist and prefix triggers, retry
