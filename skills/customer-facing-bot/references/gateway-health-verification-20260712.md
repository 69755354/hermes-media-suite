# Gateway Health Verification — 2026-07-12

## The Problem

You've set everything up:
- Gateway shows `active (running)` 
- `weixin: {state: "connected"}` in gateway_state.json
- But no messages are coming through
- Users report the bot isn't replying

How do you tell if the gateway is **actually** receiving/polling for messages, vs just showing a stale "connected" state?

## Solution: sync.json Buffer Change Test

The iLink platform uses long-polling. Each poll request carries a `get_updates_buf` that changes when the poll cycle completes. By watching this buffer, you can verify the gateway is actively polling:

```bash
# Check current buffer
cat /home/ubuntu/.hermes/profiles/<profile>/weixin/accounts/<account_id>.sync.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
buf = d.get('get_updates_buf','')
print(f'Buffer: {len(buf)} bytes')
"

# Wait 10 seconds and check again
sleep 10
cat /home/ubuntu/.hermes/profiles/<profile>/weixin/accounts/<account_id>.sync.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
buf = d.get('get_updates_buf','')
print(f'Buffer: {len(buf)} bytes')
"
```

**Interpretation:**
- **Buffer CHANGED** (different size or content) → ✅ Gateway is actively polling. The iLink connection is alive and receiving.
- **Buffer STAYED THE SAME** after 10+ seconds → ⚠️ Gateway isn't polling. Either long-poll hung or the process is stuck.

## Root Causes for "Connected but Not Receiving"

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Buffer changes, no messages | Wrong dm_policy (pairing blocking non-approved users) | Set `dm_policy: open` + `allow_all_users: true` in config.yaml |
| Buffer changes, messages from paired users work | Gateway is fine, only issue with new/unpaired users | Check `_is_dm_intake_allowed()` and `_is_dm_allowed()` in weixin adapter |
| Buffer stuck, gateway shows running | Stale state from previous crashed instance | Clean restart (remove gateway.lock + gateway_state.json, restart) |
| Buffer stuck, gateway shows disconnected | iLink connection failed | Check token validity, may need to re-bind |

## Other Health Checks

### 1. Channel Directory

```bash
cat /home/ubuntu/.hermes/profiles/<profile>/channel_directory.json
```

If `weixin: []` (empty array), no conversations have been established. Even in `open` mode, this should show active channels after someone messages the bot.

### 2. Pairing List (if dm_policy=pairing)

```bash
hermes --profile <profile> pairing list
```

Messages from unpaired users appear as pending pairing requests here. If no requests appear even though users report sending messages, the gateway isn't receiving them.

### 3. Environment Variable Check

```bash
cat /proc/<gateway_PID>/environ | tr '\0' '\n' | grep WEIXIN
```

If `WEIXIN_DM_POLICY` and `WEIXIN_ALLOW_ALL_USERS` aren't in the output, the `.env` isn't being loaded — use config.yaml instead.
