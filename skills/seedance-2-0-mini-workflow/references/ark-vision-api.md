# ARK API 豆包Vision看图调用指南

## API 端点

```
POST https://ark.cn-beijing.volces.com/api/v3/chat/completions
```

## 模型

| 模型 | ID | 说明 |
|:----|:---|:-----|
| 豆包Vision（ARK端点） | `doubao-seed-2-0-mini-260428` | ✅ 主力看图模型（实测可用） |
| 备用 | `doubao-seed-2-0-mini-260215` | 旧端点，优先用260428 |

## 请求格式（带图）

```python
import requests, base64, json

key = "ark-xxx"
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

with open('/path/to/image.jpg', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()

payload = {
    "model": "ep-20260710211910-f65h9",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "描述这张图片的内容"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]
    }]
}

resp = requests.post(
    'https://ark.cn-beijing.volces.com/api/v3/chat/completions',
    headers=headers, json=payload, timeout=60
)
print(resp.json()['choices'][0]['message']['content'])
```

## ⚠️ 踩坑记录（2026-07-21 更新：vision_analyze配置修复）

1. **base64编码图片不能通过curl命令行传** → `curl: Argument list too long`，必须用Python或其它编程语言发送请求
2. **~~vision_analyze工具可能不支持~~ ✅ 已修复** — vision_analyze现在可以正常工作，配置方式见下方「Hermes vision_analyze配置排查」
3. **size限制** → 大图base64后体积大，不影响API调用
4. **计费** → 走免费推理资源包（Doubao-Seed-2.0-mini免费在线推理资源包），按token计费

## 🛠 Hermes vision_analyze配置排查（2026-07-21 踩坑记录）

如果 `vision_analyze` 工具报 `.../chat/completions/chat/completions` 路径重复错误，或者404，按以下顺序排查：

1. **config.yaml中 `providers` 和 `auxiliary.vision` 都要配** — 单配一个不行
2. **base_url** → 必须带 `/api/v3`，不能只写域名：`https://ark.cn-beijing.volces.com/api/v3`
3. **api_mode** → **必须为空字符串**（`api_mode: ""`），不能是 `chat_completions`，否则SDK路径拼接会重复追加
4. **auxiliary.vision** 下也要配 `base_url` 和 `api_key`，否则解析层可能找不到端点

### 正确配置样板

```yaml
# providers段
providers:
  custom_ark:
    base_url: https://ark.cn-beijing.volces.com/api/v3
    model: doubao-seed-2-0-mini-260428
    api_key: ark-xxx
    api_mode: ""    # 必须空，不能是chat_completions

# auxiliary段
auxiliary:
  vision:
    provider: custom_ark
    model: doubao-seed-2-0-mini-260428
    base_url: https://ark.cn-beijing.volces.com/api/v3
    api_key: ark-xxx    # 必须配，否则解析层找不到
```

5. **配置改完后需新会话生效** — `/reset` 或等下次对话。也可以用子进程 `async_call_llm(task='vision')` 绕开缓存测试

## Key提取

```bash
ARK_KEY=$(grep ARK_API_KEY /home/ubuntu/.hermes/profiles/customer/.env | sed 's/export ARK_API_KEY=//' | tr -d '"')
```

## 可用场景

- 分析用户发的参考图（风格/构图/色调/元素）
- 识取图片中的文字信息
- 对比多张图片的差异
- 图片合规检查
