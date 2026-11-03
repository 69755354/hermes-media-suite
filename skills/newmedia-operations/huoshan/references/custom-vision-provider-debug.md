# Hermes 自定义 Vision Provider 配置与调试

## 场景

给 Hermes 配一个非内置的 vision provider（如火山引擎 ARK 的豆包种子看图模型），通过 `custom_ark` 自定义 provider 接入。

## 配置文件结构

```yaml
# config.yaml

# 1. 在 providers 下定义自定义 provider
providers:
  custom_ark:
    base_url: https://ark.cn-beijing.volces.com/api/v3   # 不要带 /chat/completions
    model: doubao-seed-2-0-mini-260428                    # vision 模型名
    api_key: ark-xxxx-xxxx-xxxx                           # ARK API Key
    api_mode: ""                                          # 关键！设为空字符串，不设 chat_completions
    model_display_name: 豆包种子2.0 Mini 看图
    available_models_json: '[{"id":"doubao-seed-2-0-mini-260428","name":"豆包种子2.0 Mini 看图"}]'

# 2. auxiliary.vision 引用该 provider
auxiliary:
  vision:
    provider: custom_ark
    model: doubao-seed-2-0-mini-260428
    base_url: https://ark.cn-beijing.volces.com/api/v3   # ⚠️ 必须！防止缓存穿透导致 client 创建走错分支
    api_key: ark-xxxx-xxxx-xxxx                           # ⚠️ 同上理由
```

## 解析链路（Debug 路径）

当 `vision_analyze` 工具被调用时，请求经过的代码路径：

```
vision_analyze_tool()                          # tools/vision_tools.py
  → async_call_llm(task='vision', ...)         # agent/auxiliary_client.py
    → _resolve_task_provider_model('vision')   # 读 auxiliary.vision config
        ↓
    → resolve_vision_provider_client()         # 第5391行
        │
        ├─ [A] resolved_base_url 不为 None
        │   → resolve_provider_client('custom', model, explicit_base_url=..., explicit_api_key=..., api_mode=...)
        │   → 直接创建 OpenAI client（走 custom 分支，不查 PROVIDER_REGISTRY）
        │
        └─ [B] resolved_base_url 为 None
            → _get_cached_client('custom_ark', ...)
              → resolve_provider_client('custom_ark', ...)
                → _normalize_aux_provider → 'custom_ark'（保留原值）
                → 命中「Named custom providers」分支（第4703行）
                  → _get_named_custom_provider('custom_ark') 从 config 读
                  → _to_openai_base_url()  重写 base_url
                  → _create_openai_client() 创建 client
                  → OpenAI SDK 自动追加 /chat/completions
```

## 🚨 路径重复 Bug

**现象：** vision 调用报错 `InvalidAction: /api/v3/chat/completions/chat/completions`

**根因：** 路径被拼接了两次：

1. 当 `providers.custom_ark` 的 `api_mode: chat_completions` 时，Hermes 在 `_to_openai_base_url` 处理 base_url 时可能会追加路径
2. OpenAI Python SDK 的 `client.chat.completions.create()` 默认在 base_url 后追加 `/chat/completions`

两个叠加 → 路径重复。

**修复：**
- `api_mode: ""`（空字符串，不是 `chat_completions`），避免 Hermes 在处理 api_mode 时追加路径
- base_url 设为 `.../api/v3`（ARK endpoint 的基础路径），不带 `/chat/completions`，让 SDK 自动追加

## 🚨 Client 缓存穿透问题

**现象：** 配置改了但 vision 还是报旧错误（同一会话内）

**根因：** `_get_cached_client()` 在进程内缓存了旧 client：
```python
# agent/auxiliary_client.py 第5766行
cache_key = _client_cache_key(provider, async_mode, base_url, api_key, api_mode, ...)
```
只有 key 变了才会重建 client。如果只改了 `providers` 下的配置而 `auxiliary.vision` 没有 base_url/api_key，key 可能不变。

**修复：** 在 `auxiliary.vision` 下也加上 `base_url` + `api_key`，这样 `_resolve_task_provider_model` 会返回值，走代码路径 [A]（`resolved_base_url` 不为 None），避开 `_get_cached_client` 的缓存。

## 配置生效验证

```bash
# 1. 直调 ARK API 验证模型和 key 可用
curl -s "https://ark.cn-beijing.volces.com/api/v3/chat/completions" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seed-2-0-mini-260428",
    "messages": [{"role": "user", "content": [{"type": "text", "text": "描述图片"}, {"type": "image_url", "image_url": {"url": "https://picsum.photos/200/300"}}]}],
    "max_tokens": 100
  }'
# 返回 200 + choices 说明 API 本身没问题

# 2. 用 Hermes 的 async_call_llm 测试（子进程）
python3 -c "
import os, asyncio
os.environ['HERMES_HOME'] = '/home/ubuntu/.hermes'
async def t():
    from agent.auxiliary_client import async_call_llm
    r = await async_call_llm(task='vision', messages=[{'role':'user','content':[{'type':'text','text':'描述'},{'type':'image_url','image_url':{'url':'https://picsum.photos/200/300'}}]}], temperature=0.1, max_tokens=500, timeout=30)
    print(r.choices[0].message.content[:200])
asyncio.run(t())
"
# 返回描述内容 → 配置正确
```

## 关键源码位置

| 功能 | 文件 | 行号 |
|:----|:----|:----:|
| `vision_analyze_tool` | `tools/vision_tools.py` | 1063 |
| `async_call_llm` | `agent/auxiliary_client.py` | 7031 |
| `resolve_vision_provider_client` | `agent/auxiliary_client.py` | 5259 |
| `resolve_provider_client` | `agent/auxiliary_client.py` | 4380 |
| Named custom providers 分支 | `agent/auxiliary_client.py` | 4703 |
| `_to_openai_base_url` | `agent/auxiliary_client.py` | 714 |
| `_get_cached_client` | `agent/auxiliary_client.py` | 5727 |
| `_resolve_task_provider_model` | `agent/auxiliary_client.py` | 5857 |
| `_get_named_custom_provider` | `hermes_cli/runtime_provider.py` | - |
