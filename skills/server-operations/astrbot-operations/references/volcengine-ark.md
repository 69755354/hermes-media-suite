# Volcengine ARK（火山引擎方舟）API 详情

## 基础信息

- **API 地址**: `https://ark.cn-beijing.volces.com/api/v3`
- **API Key**: 格式 `ark-<uuid>-<suffix>`（非 OpenAI 的 `sk-` 格式）
- **模型名**: Endpoint ID（如 `ep-20260710211910-f65h9`），不是模型名

## OpenAI 兼容性

Volcengine ARK 提供 OpenAI 兼容接口，AstrBot 中可用 `openai_chat_completion` 类型接入。

## Provider 配置关键字段

| 字段 | 值 |
|:---|:---|
| `type` | `openai_chat_completion` |
| `key` | `["ark-xxx"]`（列表格式） |
| `api_base` | `https://ark.cn-beijing.volces.com/api/v3` |
| `model` | `ep-20260710211910-f65h9`（必须写在 provider 节，不能只写在 source） |

## 环境变量

```bash
export ARK_API_KEY="<ARK_API_KEY>2"
export ARK_ENDPOINT="ep-20260710211910-f65h9"
```

## 402 错误

- `model or endpoint unknown` → `model` 字段未传，默认用了 `"unknown"`。修复：在 `provider` 节（不是 `provider_sources`）加 `"model": "<endpoint_id>"`
- `InvalidEndpointOrModel.NotFound` → endpoint ID 错误或过期
- `Authentication Fails` → API Key 无效（注意 ARK key 以 `ark-` 开头，不是 `sk-`）

## 运行时错误排查

**bot 回复「我是豆包」而非设定的人设：**
- `default_personality` 在重启后被 AstrBot 的 `check_config_integrity()` 重置为 `"default"`
- 修复：重启后在 `cmd_config.json` 重设 `default_personality` 或 `prompt_prefix`
- `prompt_prefix` 也会在重启后被重置为 `"{{prompt}}"`

**401 但 key 看起来正确：**
- 确认 key 是 ARK key (`ark-xxx`) 不是 DeepSeek key (`sk-xxx`)
- 确认 key 在 `provider_sources` 中是 `list` 格式：`["ark-xxx"]`

**404 / model unknown 的完整排查链路：**
1. 登录 WebUI → AI 提供商 → 检查 provider source 中有没有 `model` 字段（大概率被删了）
2. 查看 `cmd_config.json` 中 `provider` 节有没有 `"model": "ep-xxxx"`
3. 如果没有，直写后重启

## Seedance 视频生成（另见 huoshan skill）

```bash
# 提交任务
curl -s -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"<endpoint>","content":[...]}'

# 查询任务
curl -s https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/<task_id> \
  -H "Authorization: Bearer $ARK_API_KEY"
```
