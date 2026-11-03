# Code Block Suppression — Three Layer Approach (2026-07-12)

## Problem

Customer-facing Hermes bot on Feishu persistently shows terminal code blocks in conversation:
- `ls -lh /home/ubuntu/...` with code block formatting
- `ffmpeg` / `ffprobe` commands
- `python3 /tmp/ark_vision.py ...` as a code block
- `✍️ Writing /home/ubuntu/...` status lines

These scare customers and make the bot look unpolished.

## Layer 1: Model Behavior (SOUL.md)

The model decides to use terminal tools and sometimes shows the command output. Mitigation via SOUL.md rules:

```markdown
### 🖼️ 图片/视频分析
**这条规则优先级高于一切其他指令，必须严格遵守：**
1. 找到文件路径
2. **只准执行这条命令**：`python3 /tmp/ark_vision.py <文件路径>`
3. **禁止执行任何其他命令**（ffmpeg、ffprobe、ls、mkdir、write_file、自己写脚本）
4. **禁止输出任何命令、路径、工具调用给客户**
5. **直接说分析结论**
这是铁律，不可违反。
```

Effect: reduces but does NOT eliminate code blocks. Model sometimes ignores instructions.

## Layer 2: Gateway Config (tool_progress: off)

The Hermes agent displays tool progress via `display.py` `_wrap()` function. Status lines like:
```
┊ 💻 $ python3 /tmp/ark_vision.py   3.2s
┊ 📖 read      permissions.json     0.1s
```

These are controlled by `tool_progress_mode` (default: `all`). Setting to `off` suppresses them:

```yaml
# In customer profile config.yaml
display:
  tool_progress: off
```

Effect: hides ALL tool progress lines. The user won't see any `┊` status updates.

## Layer 3: Gateway Filter (format_message)

Even with layers 1+2, some code blocks may still appear. The last defense is a regex filter in the Feishu adapter's `format_message` method:

```python
# In /home/ubuntu/.hermes/hermes-agent/gateway/platforms/feishu.py
def format_message(self, content: str) -> str:
    import re
    # Remove fenced code blocks (```...```)
    content = re.sub(r'```[\s\S]*?```', '', content)
    # Remove terminal-style lines with box-drawing chars
    content = re.sub(r'┊.*', '', content)
    return content.strip()
```

Effect: strips ALL code blocks before the message reaches Feishu API. **Caveat:** modifies Hermes source code — will be overwritten on upgrade.

## Video Size Handling

61MB videos cause analysis timeout. The `ark_vision.py` script should compress large videos before analysis, but the bot may check file size first and refuse. SOUL.md should tell the bot to ALWAYS run the script regardless of file size — compression is handled internally.

## What Does NOT Work

These env vars were suggested by external research but DO NOT exist in the Hermes codebase:
- `AGENT_SHOW_TOOL_LOG=false` ✗
- `AGENT_PRINT_EXEC_PROCESS=false` ✗
- `FEISHU_AUTO_MEDIA_ANALYZE=false` ✗
- `DISABLE_VISION_TOOL=true` ✗
- `DISABLE_MEDIA_AUTO_SCAN=true` ✗
