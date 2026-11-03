---
name: hermes-memory-management
description: "Manage Hermes built-in memory (MEMORY.md + USER.md) — read usage, consolidate when full, prune stale entries. Covers the memory tool workflow and in-place consolidation pattern."
version: 1.0.0
author: agent
platforms: [linux]
tags: [hermes, memory, maintenance, consolidation, cleanup]
---

# Hermes Memory Management

Manage Hermes's built-in memory — the `memory` tool that stores facts across sessions. These appear as `MEMORY` and `USER PROFILE` at the top of every conversation.

## Trigger Conditions

- User asks "你还有多少内存" / "记忆容量" / "memory"
- Memory approaches 80%+ of its char limit (2,200 for MEMORY, 1,375 for USER)
- User corrects how you manage memory content
- You need to save a new fact but memory is nearly full

## Architecture

Memory has **two stores:**
- **MEMORY (memory_char_limit: 2,200 chars):** Agent's personal notes — environment facts, project conventions, tool quirks, server configs, pricing data
- **USER (user_char_limit: 1,375 chars):** What you know about the user — preferences, communication style, workflow habits, corrections

On-disk locations: `~/.hermes/memories/MEMORY.md` and `~/.hermes/memories/USER.md`

**Memory vs Skills:**
- Memory = "who the user is and what the current situation is" — facts that change over time
- Skills = "how to do this class of task for this user" — durable procedures

## Consolidation Workflow

When memory is >80% full, consolidate rather than moving content elsewhere.

### Step 1: Read Current Entries

There's no direct read tool. Instead, note what's currently in memory from the conversation header, or check file sizes:

```bash
wc -c ~/.hermes/memories/MEMORY.md ~/.hermes/memories/USER.md
```

### Step 2: Categorize Each Entry

Classify entries into three buckets:

| Category | Action | Examples |
|----------|--------|---------|
| **SOUL.md/skill-redundant** | DELETE | Rules already hardcoded in SOUL.md or a skill (safety rules, core identity, framework definitions) |
| **One-time task (done)** | DELETE | "安全铁律已加固", "知识库已重构" — the work is done, the fact is documented in the file |
| **Duplicate across stores** | MERGE | Same fact about the user in both MEMORY and USER → keep in USER only |
| **Related topics** | MERGE | 3 entries about "小程序商城" → 1 entry. 2 entries about "Seedream pricing" → 1 entry |
| **Unique current facts** | KEEP (compress) | Server configs, API keys, project status, user preferences not in SOUL.md |

### Step 3: User Preference — In-Place Consolidation

**Critical rule (user-corrected 2026-07-17):** Do NOT move memory content to skills or files. The user explicitly rejected this with "搬出去那不是没用了" (moving it out makes it useless). Memory is the only thing injected into every conversation.

**Correct approach:** Remove the old entries and add back compressed versions in the same batch. Use the `memory` tool with `operations` array.

### Step 4: Execute via memory Tool

Use batch operations with the `memory` tool. The tool accepts an `operations` array with `{action, content?, old_text?}` items. The char budget check runs on the **final** state, so you can remove 20 entries and add 6 in one call.

**REMOVE entries** — use old_text as a short unique substring:

```json
{"action": "remove", "old_text": "huoshan技能不能摘"}
```

**REPLACE entry** — matches on old_text substring:

```json
{"action": "replace", "content": "§ consolidated content", "old_text": "PLACEHOLDER"}
```

**ADD entries** — appends to the current store:

```json
{"action": "add", "content": "§ new entry content"}
```

**Batch size:** Max ~25 operations per call. For larger consolidations, do multiple calls.

### Step 5: Verify

Check the tool response for:
- `usage: "28% — 636/2,200 chars"` — verify target utilization
- `entry_count: 6` — verify appropriate number of entries
- If over limit, the tool returns `char limit exceeded` — split into more aggressive removal

## Consolidation Example (from 2026-07-17)

**Before:** MEMORY at 90% (2,123 chars, 21 entries) + USER at 93% (1,291 chars, 17 entries)

**Cleaned by:**
- Removed 17 old entries from MEMORY (duplicates, SOUL.md-redundant, one-time tasks)
- Removed 15 old entries from USER (duplicates, merged into single pref summary)
- Kept only 6 MEMORY entries + 5 USER entries

**Key merges:**
- 3 separate "小程序商城" entries → 1
- 2 "Seedream pricing" entries → 1
- 2 "Gewechat/AstrBot port" entries → 1
- 5 user preference entries → 1 tight summary
- Deleted SOUL.md security rules (already in SOUL.md)
- Deleted completed task entries (知识库已重构 etc.)

**After:** MEMORY at 28% (636 chars) + USER at 26% (368 chars)

## Pitfalls

- **Don't move content to skills/files.** The user corrected this: memory must stay in memory or it won't be injected.
- **Don't just delete old entries without replacing them.** You must preserve all factual content — just compress it. Disappearing facts break the user's trust in your memory.
- **Batch operations check the FINAL char budget.** You can massively overshoot temporarily during the operation — the tool only validates the result after all operations apply.
- **USER profile is especially tight (1,375 chars).** User preferences tend to accumulate faster than environment facts. Check it first.
- **Timeline of last consolidation matters.** Note the date so future consolidations know what's old vs new.
- **Rapid refill warning (2026-07-18):** Memory went from 28% (636 chars) back to 99% (2,189 chars) in ~1 day after consolidation. Active development can add 1,500+ chars/day. Check capacity at the START of every long session — if >75% full, consolidate before starting complex multi-step tasks.
- **Pre-check before complex tasks:** Before a task that will generate new memory entries (project configs, pricing, user prefs, customer info), check capacity. A single session adding 5+ entries can push from 60% to 95%. Consolidate first, work second.
