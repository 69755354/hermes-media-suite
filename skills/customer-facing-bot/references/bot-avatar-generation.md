# Bot Avatar Generation via Seedream API

2026-07-12 session: created 小鹿's character portraits using the helper_api Seedream endpoint.

## Workflow

1. **Describe the character** — white square-collar cami, floral skirt, brown wavy shoulder-length hair, gold necklace/earrings. Keep consistent across versions.

2. **Generate base portrait** (full body / half body for vibe):
   ```json
   POST /seedream
   {"prompt": "治愈系小姐姐自拍，白色方领吊带...居家温馨氛围"}
   ```

3. **Generate close-up** (for avatar/profile pic, chest-up framing):
   ```json
   {"prompt": "治愈系小姐姐大头特写自拍，胸部以上构图，奶油虚化背景..."}
   ```

4. **Iterate on background/mood** — keep character description identical, change only the scene keywords (e.g. "暖光窗边绿植" → "奶油虚化暖白调").

## Prompt Tips

- **Front-load character description** (all physical traits first)
- **Specify framing** (大头特写/胸部以上/肩部以上) for avatar shots
- **Avoid real-person reference** unless explicitly using the person's image as base64 reference. Pure text prompts generate original faces.
- **Use scene keywords** for mood: 暖光/奶油虚化/居家/自然光侧照

## Key Learnings

- Don't use real person's photo as reference for bot avatar unless that person IS the bot
- Generate multiple crops (full body + close-up) for different use cases
- Save all versions with consistent naming: `<botname>_portrait.jpg`, `<botname>_closeup.jpg`, `<botname>_warm.jpg`
- When renaming bot, rename asset files too: `mv xiaotian_*.jpg xiaolu_*.jpg`
