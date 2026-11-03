# 免费模型通道速查 + Ox Alpha 调研（2026-08-23）

## Hermes 内置免费模型通道（用户问「Hermes 内置哪些免费模型」时的答案）

Hermes 不内置模型权重，内置的是「免费接入通道」（plugins/model-providers/ 35+）：

| 通道 | 成本 | 备注 |
|---|---|---|
| custom/Ollama 本地 | 0 API 成本 | 接本地开源模型（qwen/llama 小模型），吃本机算力；新加坡机 4GB 内存只能跑 0.5B/1.5B 小档 |
| Google Gemini 免费层 | 免费额度档 | `gemini-3.6-flash` 是默认辅助模型；日常对话够用 |
| OpenRouter `:free` 模型 | 免费 | qwen/deepseek 蒸馏版等，有速率限制 |
| Nous Portal（Hermes 自家） | 注册即用 | `hermes auth add nous` 走 OAuth |
| HuggingFace | 免费推理额度 | 内置 huggingface provider |

本机现状：主对话走 DeepSeek（付费但便宜）+ GLM + 豆包看图，不是免费档。

## Ox Alpha（stealth/ox-alpha）调研

OpenRouter 2026-08-20 上线的**匿名免费模型**，中文社区外号「牛来模型」——ox 是公牛、alpha 是第一。

### 规格（OpenRouter 官方页 + 实测社区数据）
- 模型 ID：`stealth/ox-alpha`（stealth = 厂商匿名预览期）
- 上下文：1,048,576 token（完整 1M）；最大输出 131,072 token（128K）
- 输入模态：文本、图片、视频全吃；输出仅文本（拒绝音频输入——被当作归属线索）
- 价格：输入 $0 / 输出 $0，完全免费（预览期）
- 定位：编码、长程 Agent、生产负载
- 性能：开发者实测 DeepSWE 编程题通过率 80%，同期 Claude Fable 5 = 65%、GPT-5.6 Sol = 52%
- 速度：外部观测 ~49-78 tok/s（负载相关）
- 归属猜测（无实锤）：智谱 GLM-5.3 变体 / 腾讯混元 / Gemini / 小米——OpenRouter 只路由不背书中立声明「不是其开发者/所有者/提供方」

### 接入 Hermes
```bash
hermes config set model.aliases.ox openrouter/stealth/ox-alpha
```
前置：OpenRouter API key（`sk-or-` 开头）配进 `~/.hermes/.env` 的 `OPENROUTER_API_KEY`。

### 风险提示（建议接前泼的冷水）
1. 免费预览期 + 匿名厂商：随时可能涨价或下线，不能当生产依赖
2. 只走 OpenRouter：注册 openrouter.ai 需网络借道（见 network-relay-ops SSH SOCKS 节，国内直连卡死）
3. 用途决定配法：主对话 vs 备用执行通道，配置位置不同

### 注册 OpenRouter 要点（国内用户）
- 国内直连 openrouter.ai 注册/验证环节反复卡，借道新加坡机 SSH SOCKS 代理秒开（network-relay-ops「个人设备借道新加坡」节）
- GitHub OAuth 一键登录可绕过邮箱验证
- 邮箱验证链接 10 分钟过期；链接是开放 GET，复制给 Hermes 用新加坡机代开也能完成验证
