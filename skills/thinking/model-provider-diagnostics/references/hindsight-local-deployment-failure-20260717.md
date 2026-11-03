# Hindsight Local Deployment Failure (2026-07-17)

## Scenario

DeepSeek API recovered after recharge. Hindsight cloud still 402. Tried to switch Hindsight to local mode to avoid paying for another cloud service.

## What Was Tried

1. **Found existing installation:** `hindsight-api-slim` v0.8.3 already installed in the Hermes venv, along with `hindsight-client` v0.6.1
2. **Found launch scripts:** `start_hindsight.sh` (uses ARK endpoint + key) and `start_hindsight.py` (reads DeepSeek key from config.yaml)
3. **Updated model name:** Changed `HINDSIGHT_API_LLM_MODEL` from `ep-20260629192533-hwgdb` (old ARK endpoint) to `deepseek-v4-flash` in both scripts
4. **Tried to start:** `bash ~/start_hindsight.sh`

## Root Cause of Failure

The server started but crashed during `MemoryEngine.__init__`:

```
ValueError: Unknown embeddings provider: none.
Supported: 'local', 'onnx', 'tei', 'openai', 'openai-codex',
'openrouter', 'cohere', 'google', 'zeroentropy', 'litellm', 'litellm-sdk'
```

The config had `HINDSIGHT_API_EMBEDDINGS_PROVIDER=none` — which works for the **cloud** Hindsight service (which has its own embeddings pipeline) but is **not supported by the local `hindsight-api-slim` package** (v0.8.3). The local server requires a valid embeddings provider.

## Options to Fix

| Option | Effort | Trade-off |
|--------|--------|-----------|
| Install `sentence-transformers` | 300+ MB, slow first run | Works fully offline, but heavy |
| Use `openai` embeddings with DeepSeek key | Zero deps, ~10-20ms/embed | Makes API calls per embed, small cost |
| Use `tei` (Text Embeddings Inference) | Needs Docker | Dedicated embed server, overkill |
| Accept cloud 402, keep using built-in memory | Nothing to do | Loses semantic search, but MEMORY/USER PROFILE still work |

## Resolution

Chose option 4: accepted the cloud 402 for now. The built-in `memory` tool (which stores MEMORY and USER PROFILE at the top of each conversation) is unaffected. Hindsight cloud failure only costs `hindsight_recall`/`hindsight_reflect` semantic search.

## Key Takeaway

**hindsight-api-slim does NOT support embeddings_provider=none.** The cloud service and local server have different configuration constraints. Any migration from cloud to local must provide a valid embeddings provider upfront.
