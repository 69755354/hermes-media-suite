# feishu_send_gate 黑名单收窄 + 管理员豁免（2026-08-26）

## 背景

`feishu_send_gate.py` 是网关平台适配器 `base.py` 在发送前调用的物理闸。
广州 customer profile 的 `base.py` 配了 `_CUSTOMER_OUTBOUND_GATE_PLATFORMS = frozenset({"feishu", "weixin"})`，
所有出站消息都过闸。SG（主profile）是空集 `frozenset()`，不过闸。

## 问题：黑名单太死

旧版硬黑名单包含工具名（codex/hermes/ffmpeg等）、服务器标识（新加坡机/广州机等）、
路径片段（workflow/.hermes等）、文件后缀（.py/.json/.sh等）、过程词、报告结构。
小鹿回客户讲"codex跑完了"就被拦，变成完全哑巴——客户发什么都没回复。

## 改动

### 1. 收窄硬黑名单 — 只留凭证类

硬拦（命中直接block）：
- `api_key=xxx`、`app_secret=xxx`、`password=xxx` 等凭证赋值
- `-----BEGIN PRIVATE KEY-----` 私钥
- `Bearer xxx`、`sk-xxx`、`ark-xxx` 等 API key 模式
- 完整内部路径+文件后缀（如 `/home/ubuntu/.hermes/config.yaml`）
- `.env` 文件引用

不再拦（交给 SOUL.md 软规则管）：
- 工具名（codex、hermes、ffmpeg等）
- 服务器标识（新加坡机、广州机等）
- 路径片段（workflow/、.hermes等）
- 过程词、报告结构

### 2. 管理员白名单豁免

```python
ADMIN_WHITELIST = frozenset({
    "ou_9b793886207dc39cb0a8befbcac6065f",  # 天行者飞书user_id
})
```

`check_text(text, recipient_id)` 收到 recipient_id 在白名单中直接返回空（豁免）。
`send_message(chat_id, open_id, text)` 把 open_id 作为 recipient_id 传入。
`check` 命令不知道 recipient，不豁免（保守）。

### 3. 网关调用链

```
gateway/platforms/base.py
  → check_customer_outbound_text(platform, content)
    → subprocess feishu_send_gate.py check <content>
      → check_text() 命中 → rc=2 → 返回 BLOCK_MESSAGE
      → 未命中 → rc=0 stdout="OK" → 放行
```

SG `base.py`: `_CUSTOMER_OUTBOUND_GATE_PLATFORMS = frozenset()` → 不调闸
广州 `base.py`: `frozenset({"feishu", "weixin"})` → 调闸

注意：`base.py` 在 hermes-agent 核心代码里，不是 `feishu_send_gate.py`。
改闸规则只需改 `feishu_send_gate.py`，不需要动 `base.py`。

## 验证测试

```bash
# 凭证类应拦
python3 feishu_send_gate.py check "api_key=sk-xxxx1234567890abcdef"  # → BLOCKED rc=2
# 工具名不拦
python3 feishu_send_gate.py check "codex跑完了，hermes在跑"  # → OK rc=0
# 正常交付不拦
python3 feishu_send_gate.py check "做好了，视频在这"  # → OK rc=0
```

## 同步纪律

改完同步双机 + 刷hash基线 + 双机 ALL_OK 验证。
广州 `base.py` 的 `_CUSTOMER_OUTBOUND_GATE_PLATFORMS` 是改过的核心代码，
hermes update 会覆盖，需 git commit 保护。
