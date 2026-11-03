# Local Infrastructure Reference

> Load this before starting ANY task. DO NOT ask the user what APIs exist — check here first.
> Last updated: 2026-07-10 | After Hermes update, re-scan before assuming what's available.

## API Services

### Execute API (`localhost:1889`)
systemd service `execute-api.service` at `/home/ubuntu/execute_api.py`. 段2后半段（节点5→13），接收文案+照片→成品视频。

| Endpoint | Purpose | Timeout |
|:---------|:--------|:-------:|
| `POST /execute` | 完整段2流程图（分镜→生图→出提示词→Seedance→ffmpeg→出片） | 300s |

### Helper API (`localhost:1888`)
systemd service at `/opt/helper_api.py`. Zero LLM, pure tool dispatch.

| Endpoint | Purpose | Timeout |
|:---------|:--------|:-------:|
| `POST /pipeline` | Full video pipeline (Seedance→TTS→ffmpeg→compliance) | 300s |
| `POST /seedance` | Video generation only | 300s |
| `POST /seedream` | Image generation (Seedream) | 30s |
| `POST /tts` | Edge TTS only | 30s |
| `POST /compose` | ffmpeg compose only | 120s |
| `POST /compliance` | Compliance check only | 5s |
| `POST /agnes-pipeline` | Agnes video pipeline (full) | 300s |
| `POST /agnes-video` | Agnes video gen only | 300s |
| `POST /agnes-image` | Agnes image gen | 60s |
| `POST /agnes-compose` | Agnes compose | 120s |

### DeepSeek API (`https://api.deepseek.com/v1`)
Custom provider. deepseek-v4-flash (execution, temp 0.1) / deepseek-v4-pro (creative, temp 0.2-0.8).

### Vision API
- **看图 endpoint:** `ep-20260710211910-f65h9` -> model `doubao-seed-2-0-mini-260215`（多模态看图专用）
- **来源:** 火山引擎方舟控制台，配置在 .hermes/.env 中
- **注意:** endpoint 会过期（约2周），过期需在方舟控制台重建
- **ARK_API_KEY:** 存在 .hermes/.env 中

### Background Services
- **Hindsight** `localhost:8888` — memory system via 火山ARK DeepSeek
- **n8n** `localhost:5678` — native node process (not Docker)
- **Caddy** `:80` — static file server
- **Image Server** `localhost:8899` — `/tmp/img_serve/` (store photos)
- **Chrome CDP** `ws://127.0.0.1:9222` — browser automation via chromium-browser
  
  **验证：** `curl -s http://localhost:9222/json/version | python3 -c "import sys,json; print(json.load(sys.stdin)['webSocketDebuggerUrl'])"`
  
  **常见故障：** config.yaml中的 `browser.cdp_url` 端口与实际chromium启动参数 `--remote-debugging-port` 不一致。修复：`hermes config set browser.cdp_url "ws://127.0.0.1:9222"`
  
  **检查配置：** `grep 'cdp_url' ~/.hermes/config.yaml` 应输出 `browser.cdp_url: ws://127.0.0.1:9222`
- **Hermes API Server** `:8642` — OpenAI-compatible API

### Key Tools
- **Edge TTS** — `~/.local/bin/edge-tts` (both channels use Seedance自带人声, not TTS, but available for other uses)
- **ffmpeg** — video/audio composition
- **chromium-browser** — at `/usr/bin/chromium-browser`
- **WeChat Gateway** — lightclawbot configured
- **Tavily** — web search backend

## Knowledge Base

**Path:** `/home/ubuntu/wiki/concepts/` (21 active docs + comparisons + raw articles)

### Core Workflow Docs (loaded per node)
| File | Used By |
|:-----|:--------|
| `seedance-director-prompt-dual-system.md` | Node 8 (both channels) |
| `seedance-prompt-template-library.md` | Node 8 (10 templates, main prompt source) |
| `seedance-2.0-prompt-formula.md` | Node 8 (9-module formula) |
| `compliance-checklist.md` | Node 9, 12 (forbidden words + industry red lines) |
| `content-verification-protocol.md` | Node 12, 13 (auto checks + rollback) |
| `ffmpeg-synthesis-guide.md` | Node 11 (concat, BGM, subtitle commands) |

### Script & Style Docs (loaded per need)
| File | Content |
|:-----|:--------|
| `entity-store-30s-conversion-script-template.md` | 5 frameworks + 15 examples (merged from old `30s-four-styles.md`) |
| `copywriting-spec.md` | Structure guide (merged from old `five-part-structure.md`) |
| `six-oral-styles.md` | Six oral delivery styles |
| `golden-3-seconds.md` | Hook techniques |
| `50-viral-hook-templates.md` | 50 ready-to-use hooks |
| `character-five-elements-design.md` | Character anchoring + 5 archetypes + scene fusion |

### Consumer Psychology Docs (Node 1)
| File | Content |
|:-----|:--------|
| `consumer-decision-models-knowledge.md` | 5-stage + S-O-R + 6 behavioral econ concepts |
| `behavioral-economics-marketing.md` | 8-concept + existential 4 elements + 4 industry cases |
| `china-consumer-sociology.md` | Tier 3+ city consumption |

### Platform Publishing Docs (Node 13)
| File | Content |
|:-----|:--------|
| `douyin-kuaishou-publishing-strategy.md` | Algorithm + publish time + tags |
| `xiaohongshu-publishing-strategy.md` | CES algo + store acquisition + cold start |
| `zhihu-wechat-video-publishing-strategy.md` | 3-platform diff + private domain loop |

### BGM & Compliance
| File | Content |
|:-----|:--------|
| `bgm-library.md` | 17 SoundHelix tracks (Song-1~17), curl-friendly, no attribution |
| `seven-pitfalls.md` | 7 common pitfalls for AI-generated oral content |
| `liangtong-case-study.md` | Full production case study reference |

### Deleted/Merged Docs (no longer reference)
- ❌ `seedance-omni-prompt-templates.md` — deleted (Omni no longer used)
- ❌ `omni-timestamps-9module-stack.md` — deleted (Omni no longer used)
- ❌ `30s-four-styles.md` — merged into `entity-store-30s-conversion-script-template.md`
- ❌ `five-part-structure.md` — merged into `copywriting-spec.md`
- ❌ 根层 `compliance.md` — merged into `wiki/concepts/compliance-checklist.md`
- ❌ `final-fused-workflow.md` / `hermes-video-workflow.md` / `hermes-workflow-manual.md` — deleted (superseded by huoshan/shuziren skills)
- ❌ `shop-info.md` / `customer-analysis.md` / `script-v11.md` / `storyboard-v11.md` / `published.md` — deleted (亮瞳 project-specific, cleaned)

## Proactive Use Rules (derived from user feedback)

1. **Before ANY task**, scan this reference to confirm what's available
2. **Do NOT ask the user** if an API exists — check here first
3. **Do NOT assume** memory is complete — this file is the single source of truth
4. BGM tracks from `wiki/concepts/bgm-library.md` — always check there
5. **After any Hermes update**, re-scan full infrastructure before assuming anything
6. Run `ss -tlnp | grep -E '1888|1889|5678|8888|8899|9222'` to verify services are alive
