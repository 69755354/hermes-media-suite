# 查 Codex 剩余额度（ChatGPT 计划，非 API key）

用户问「codex 额度还剩多少」「还能用多久」时用。**不要猜、不要看 token 计数**——Codex 是按 ChatGPT 计划的滚动窗口限流的。

## 方法一（推荐）：直接查官方用量接口

`~/.codex/auth.json` 的 `auth_mode: chatgpt` = 走计划额度（不是 API key 计费）。用里面的 access_token 查：

```python
import json, urllib.request
a = json.load(open('/home/ubuntu/.codex/auth.json'))
tok = a['tokens']['access_token']; acc = a['tokens'].get('account_id')
hdr = {"Authorization": "Bearer "+tok, "chatgpt-account-id": acc,
       "User-Agent": "codex_cli_rs/0.154.0", "originator": "codex_cli_rs", "Accept": "application/json"}
for u in ["https://chatgpt.com/backend-api/wham/usage",
          "https://chatgpt.com/backend-api/codex/usage"]:
    try:
        print(urllib.request.urlopen(urllib.request.Request(u, headers=hdr), timeout=30).read().decode())
        break
    except Exception as e:
        print('fail', u, e)
```

**两个 URL 等价**（实测 2026-09-15 都返回 200、同一份 JSON，2120 字节）。端点是从原生二进制 strings 里挖的（`/wham/usage`、`/api/codex/usage`），别去猜别的路径（`/wham/token-usage` 之类实测 404）。

## 返回字段怎么读

| 字段 | 含义 |
|:--|:--|
| `plan_type` | 计划档位（pro / plus…） |
| `rate_limit.primary_window.used_percent` | **主力额度已用百分比**（这是关键数字） |
| `rate_limit.primary_window.limit_window_seconds` | 窗口长度，604800 = **7 天滚动**，18000 = 5 小时 |
| `rate_limit.primary_window.reset_at` | 重置的 Unix 时间戳（本地时区换算后告诉用户） |
| `rate_limit.allowed` / `limit_reached` | 现在还能不能用 |
| `additional_rate_limits[]` | 其他额度池（如 GPT-5.3-Codex-Spark / gpt-reserve）；**不一定管主力模型**，别拿它们的 0% 报喜 |
| `model_usage.<model>.available` | 目标模型（如 `gpt-6-astra`）当前可用性 |
| `credits.balance` | 额外积分余额，0 = 没有加量包，只能等重置 |
| `rate_limit_reset_credits.available_count` | 「重置券」数量；`applicable_available_count` = 当前窗口可用的，0 就是现在用不上 |

## 方法二：读原生二进制找端点（接口变了时）

```bash
F=/home/ubuntu/.npm-global/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex
strings -n 8 "$F" | grep -n -B4 -A4 "api/codex/usage"
# 找 path 常量；base = https://chatgpt.com/backend-api
```

## 踩坑

- **`codex exec --json` 不含额度信息**：事件只有 `thread.started / turn.started / item.completed / turn.completed`，`turn.completed.usage` 是**这次调用的 token 数**，不是剩余额度；`turn.completed` 里也没有 rate_limits 字段（0.154.0 实测）。
- **`codex app-server proxy` 连不上**：需要 managed standalone 安装（`~/.codex/packages/standalone/current/codex`），npm 装的没有 → `codex app-server daemon start` 直接报错。协议里虽有 `account/rateLimits/read` / `account/usage/read`，没 daemon 时走不通 → 用上面的 HTTP 方法。
- **`codex --help` 没有 usage/status 子命令**（0.154.0）：额度只在**交互式 TUI 的 `/status`** 里显示。用户要数字时用 HTTP 查询，别让他自己翻。
- token 只在请求头里用，**不要把 access_token 打印到聊天/日志**；返回体本身无敏感字段，可以整段贴给用户看重点。
