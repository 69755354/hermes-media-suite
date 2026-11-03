# Local Infrastructure Reference

> Load this before starting ANY task. DO NOT ask the user what APIs exist — check here first.
> Last updated: 2026-07-10 | After Hermes update, re-scan before assuming what's available.

## API Services

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

### Background Services
- **Hindsight** `localhost:8888` — memory system via 火山ARK DeepSeek
- **n8n** `localhost:5678` — native node process (not Docker)
- **Caddy** `:80` — static file server
- **Image Server** `localhost:8899` — `/tmp/img_serve/` (store photos)
- **Chrome CDP** `ws://127.0.0.1:9222` — browser automation via chromium-browser
- **Hermes API Server** `:8642` — OpenAI-compatible API

### Key Tools
- **Edge TTS** — `~/.local/bin/edge-tts` (available but not used for Seedance channels)
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
| `seedance-prompt-template-library.md` | Node 8 (10 templates) |
| `seedance-2.0-prompt-formula.md` | Node 8 (9-module formula) |
| `compliance-checklist.md` | Node 9, 12 |
| `content-verification-protocol.md` | Node 12, 13 |
| `ffmpeg-synthesis-guide.md` | Node 11 |

### Script & Style Docs
| File | Content |
|:-----|:--------|
| `entity-store-30s-conversion-script-template.md` | 5 frameworks + 15 examples |
| `copywriting-spec.md` | Structure guide |
| `six-oral-styles.md` | Six oral delivery styles |
| `golden-3-seconds.md` | Hook techniques |
| `50-viral-hook-templates.md` | 50 ready-to-use hooks |
| `character-five-elements-design.md` | Character anchoring + 5 archetypes |

### Consumer Psychology (Node 1)
`consumer-decision-models-knowledge.md` / `behavioral-economics-marketing.md` / `china-consumer-sociology.md`

### Platform Publishing (Node 13)
`douyin-kuaishou-publishing-strategy.md` / `xiaohongshu-publishing-strategy.md` / `zhihu-wechat-video-publishing-strategy.md`

### BGM & Compliance
| File | Content |
|:-----|:--------|
| `bgm-library.md` | 17 SoundHelix tracks (Song-1~17), curl-friendly |
| `seven-pitfalls.md` | 7 common AI oral pitfalls |
| `liangtong-case-study.md` | Full case study reference |

### Deleted/Merged Docs (no longer reference)
- ❌ `seedance-omni-prompt-templates.md` / `omni-timestamps-9module-stack.md` — deleted (Omni deprecated)
- ❌ `30s-four-styles.md` / `five-part-structure.md` — merged into consolidated docs
- ❌ 根层 `compliance.md` / `final-fused-workflow.md` / `hermes-video-workflow.md` / `hermes-workflow-manual.md` — deleted

## Proactive Use Rules

1. **Before ANY task**, scan this reference
2. **Do NOT ask the user** what APIs exist — check here
3. BGM from `wiki/concepts/bgm-library.md`
4. **After Hermes update**, re-scan full infrastructure
5. Run `ss -tlnp | grep -E '1888|5678|8888|8899|9222'` to verify services
