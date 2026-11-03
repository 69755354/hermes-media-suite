# Self-Diagnosis Rule: Check Server State First (2026-07-15)

## Signal

User asked "飞书现在配的是什么工作流" — a bot I had configured. Instead of checking the server, I searched memory and guessed. User had to guide me through the self-check process.

## Root Cause

Memory of past configuration is stale. The server state is the truth.

## Correct Workflow

When user asks about a bot/platform/service I deployed:

1. `gateway_state.json` → platform connected? state?
2. `config.yaml` → platform enabled? DM policy?
3. `SOUL.md` → workflow rules governing the bot
4. System services → execute-api, docker, etc.

## Current Server State (2026-07-15)

| Component | Status |
|:----------|:-------|
| Hermes Gateway (customer profile) | running, PID 2929363 |
| Feishu platform | **connected** (enabled: true) |
| WeChat platform (lightclawbot) | **connected** |
| execute-api (port 1889) | active, PID 2032515 |
| AstrBot (port 6185) | running (Docker) |
| n8n | not running (data dir exists, no container) |
| 飞书Bot identity | "小鹿", two-stage architecture |
| Gateway restart method | `systemd-run --user --scope /tmp/restart_gw.sh` |

## Lesson Embedded in SKILL.md

Added to `customer-facing-bot` SKILL.md as a new subsection under the pitfall section. Future sessions will see "Self-Diagnosis Rule: Check Server State Before Answering" and follow the 4-step workflow before answering config/state questions.
