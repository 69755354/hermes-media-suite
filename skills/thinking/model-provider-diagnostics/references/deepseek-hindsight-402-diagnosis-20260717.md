# DeepSeek + Hindsight 402 Diagnosis (2026-07-17)

## Scenario

User reported "The model provider failed after retries." Gateway hid raw provider details. Needed to check logs manually.

## Diagnostic Steps Executed

### 1. Locate the Logs

```bash
ls -lt ~/.hermes/logs/          # gateway.log, errors.log, agent.log
```

### 2. Check errors.log — found the root cause immediately

```bash
tail -80 ~/.hermes/logs/errors.log
```

Output showed:
```
hindsight_client_api.exceptions.ApiException: (402)
Reason: Payment Required
HTTP response body: {"detail":"Insufficient credits. Please add credits to continue."}

agent.conversation_loop: API call failed (attempt 1/3)
  provider=custom base_url=https://api.deepseek.com/v1 model=deepseek-v4-flash
  summary=HTTP 402: Insufficient Balance

agent.conversation_loop: Non-retryable client error:
  Error code: 402 - {'error': {'message': 'Insufficient Balance', ...}}
```

**Key insight:** Two separate 402 errors in the same log session:
1. **DeepSeek direct** — `api.deepseek.com/v1` → 402 Insufficient Balance (the model provider)
2. **Hindsight memory** — hindsight cloud API → 402 Payment Required (memory service, separate)

Both hit concurrently, which means both cloud accounts ran out around the same time.

### 3. Check gateway.log for retry pattern

```bash
tail -200 ~/.hermes/logs/gateway.log | grep -i -E 'error|fail|402|insufficient'
```

Confirmed the pattern:
```
attempt 1/3 → summary=HTTP 402: Insufficient Balance
→ Non-retryable client error: Error code: 402
```

### 4. Verify DeepSeek API after recharge

```bash
# Extract API key
KEY=$(grep -A10 'custom_custom' ~/.hermes/config.yaml | grep 'api_key' | head -1 | sed 's/.*api_key: *//')

# Test list models
curl -s -w '\nHTTP %{http_code}' https://api.deepseek.com/v1/models \
  -H "Authorization: Bearer $KEY"
# → 200 OK, returned deepseek-v4-flash + deepseek-v4-pro

# Test chat completion
curl -s -w '\nHTTP %{http_code}' https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'
# → 200 OK, valid response with choices[]
```

### 5. Locate Hindsight config

```bash
grep -r 'HINDSIGHT\|hindsight.*url\|hindsight.*base' ~/.hermes/.env*
# → HINDSIGHT_API_KEY=<REDACTED>
# → HINDSIGHT_MODE=cloud
```

## Commands Snapshot

| What | Command |
|------|---------|
| Error log tail | `tail -60 ~/.hermes/logs/errors.log \| grep -E '402\|Insufficient\|error'` |
| Gateway log tail | `tail -60 ~/.hermes/logs/gateway.log \| grep -i -E 'error\|fail\|provider\|402'` |
| DeepSeek key from config | `grep -A10 'custom_custom' ~/.hermes/config.yaml \| grep 'api_key' \| head -1 \| sed 's/.*api_key: *//'` |
| List DeepSeek models (health) | `curl -s https://api.deepseek.com/v1/models -H "Authorization: Bearer $KEY"` |
| Chat test | `curl -s https://api.deepseek.com/v1/chat/completions -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'` |
| Hindsight config | Found in `.env` — `HINDSIGHT_API_KEY`, `HINDSIGHT_MODE` |

## User Response Pattern

User said "已经充值了啊" (already recharged) — the correct response was to immediately verify with curl, confirm it's working, then address the separate Hindsight issue.

## Outcome

- DeepSeek: ✅ Fixed by user recharging at platform.deepseek.com
- Hindsight: ⏸ User asked "那个怎么处理" — options presented: recharge at hindsight.nousresearch.com, switch to local mode, or disable
