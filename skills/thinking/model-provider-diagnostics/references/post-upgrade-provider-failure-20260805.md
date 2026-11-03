# Post-Upgrade Provider Failure Diagnosis — 2026-08-05 (v0.19.1)

## Context

User reported "你刚刚升级到1.9版本挂了" (upgrade to 0.19.1 broke it) + system message
"The model provider failed after retries. I kept raw provider details out of chat; check
gateway logs for diagnostics."

## Symptom Trail Found in Logs

1. **errors.log 02:30** — the smoking gun:
   ```
   API call failed after 3 retries. [Errno 2] No such file or directory | provider=custom model=deepseek-v4-flash
   CA bundle path does not exist: /home/ubuntu/.hermes/hermes-agent/venv/lib/python3.11/site-packages/certifi/cacert.pem — falling back to default certificates
   ```
   FileNotFoundError on provider calls = local venv was mid-rebuild while gateway kept running.

2. **gateway-exit-diag.log** — 9+ `gateway.exit_nonzero` / `success: false` entries from
   2026-07-27 through 2026-08-04, clustered around upgrade events.

3. **venv rebuild artifacts**:
   - `venv/bin/python` symlink dated 02:52 (upgrade window) → `~/.local/share/uv/python/cpython-3.11-...`
   - BOTH `venv/` and `.venv/` present → duplicate environments after rebuild
   - certifi/cacert.pem EXISTS after restart but was missing during the 02:30 window

4. **hermes doctor** — `Config version outdated (v0 → v33)` ← the config schema drift.

5. **tools.registry spam** — `check_fn check_bfl_requirements returned False`,
   `_browser_cdp_check returned False`, `check_image_generation_requirements returned False`
   → npm deps missing after reinstall (agent-browser not installed).

6. **Red herrings** (not the cause):
   - composio MCP 401 Unauthorized on connect.composio.dev/mcp → expired consumer key in
     config.yaml `mcp_servers.composio.headers.x-consumer-api-key`, independent of upgrade
   - lightclaw 502 reconnect loop → platform-side, unrelated to provider

## Fix Sequence That Worked

```bash
# 1. Backup + migrate config schema
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak-$(date +%Y%m%d-%H%M%S)
cd ~/.hermes/hermes-agent && ./venv/bin/hermes config migrate
# → "Config version: 0 → 33" + 11 new optional keys, non-destructive

# 2. Restore npm deps for browser/image tools
cd ~/.hermes/hermes-agent && npm install --workspaces=false
# → "added 76 packages in 6s" incl. agent-browser ^0.26.0

# 3. Verify CURRENT health (not historical logs)
grep 'API call #' ~/.hermes/logs/agent.log | tail -5
# → API call #5-8 succeeded, cache=79-100% → provider healthy after restart
```

## Timing Insight

Upgrade events (02:30 failures, 02:52 venv rebuild, 03:06 restart) — the failure burst was
DURING the upgrade window, not after it. Current session API calls succeeded at 79-100%
cache hit. Lesson: correlate error timestamps against restart/upgrade timestamps before
declaring a persistent outage.

## Command Reference

- `hermes --version` — confirm the version bump
- `tail -60 ~/.hermes/logs/errors.log` — [Errno 2] + certifi warnings
- `tail -40 ~/.hermes/logs/gateway-exit-diag.log` — exit_nonzero pattern
- `ls ~/.hermes/hermes-agent/venv/lib/python3.11/site-packages/certifi/cacert.pem` — certifi NOW vs during upgrade
- `ls -la ~/.hermes/hermes-agent/.venv` — duplicate venv detection
- `cd ~/.hermes/hermes-agent && ./venv/bin/hermes doctor` — config version drift + missing deps
- `curl -s -o /dev/null -w '%{http_code}' https://connect.composio.dev/mcp` — composio key alive? (401 = dead)
