# DeepSeek API Key 提取

Hermes 配置中存储的 DeepSeek API Key 提取方式：

```bash
# 从 customer profile config 提取
grep "api_key:" /home/ubuntu/.hermes/profiles/customer/config.yaml | head -1 | sed 's/.*sk-/sk-/;s/"//' | tr -d ' '
```

注意：
- 该 key 在 Hermes `.env` 中被引用为 `CUSTOM_CUSTOM_API_KEY`
- Key 前缀 `sk-ff0...`
- DeepSeek API 地址: `https://api.deepseek.com/v1`
- 当前有效模型: `deepseek-v4-flash`, `deepseek-v4-pro`
- 旧模型名 `deepseek-chat` 已不再有效
