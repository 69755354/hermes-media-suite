# Response Formatting Rules — 2026-07-12

## Origin

User repeatedly complained that the bot output contained code blocks, JSON, terminal commands (ffprobe, ffmpeg, mkdir), and raw tool results. The bot was treating these as acceptable response content because the agent is designed to show tool output.

## The Problem

When a customer sends a message (text, image, or video), the bot:
1. Runs tools (web_search, vision_analyze, terminal commands)
2. Gets raw output back 
3. Often includes raw tool output in the response to the customer

This makes the bot look like a developer tool, not a customer service assistant.

## The Fix

SOUL.md must include explicit formatting rules with:
- **Allow list**: 纯文字描述, 表格, Emoji, 自然的段落
- **Block list**: 代码块, JSON, 命令行, 技术参数, 工具调用过程, 原始输出

## Key Rules Added

```
### 🚨 Response Formatting Rules

允许: 纯文字描述, 表格, Emoji, 自然的段落
禁止: 代码块(```), JSON, 命令行(ffprobe/ffmpeg/mkdir), 技术参数, 工具调用过程, 原始输出

核心原则：客户只需要看结论，不需要看过程。
```

## Media Analysis Rules

When customer sends images/videos:
1. Use vision_analyze directly — don't ask customer to describe
2. Only output the analysis result — NO tool calls, NO code blocks, NO JSON
3. If recognition fails, say "暂时识别不了" — don't show error details

## Verification

After adding these rules to SOUL.md:
1. Delete old session (SOUL.md changes don't apply to existing sessions)
2. Send a test message
3. Check that response has no ```, no JSON, no commands, no technical output
