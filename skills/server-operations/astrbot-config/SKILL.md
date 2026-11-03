---
name: astrbot-config
description: Deploy, configure, and troubleshoot AstrBot with model providers and platform adapters. Covers Docker deployment, provider source setup, persona configuration, and common bug workarounds.
tags: [astrbot, docker, wechat, persona, deepseek, deployment]
---

# AstrBot 配置技能

部署和配置 AstrBot 聊天机器人框架，包括模型提供商、消息平台适配器和人格系统。

> **注意重叠:** 本技能与 `im-bot-deployment`（server-operations）覆盖同一领域。本技能更聚焦配置和排障细节，`im-bot-deployment` 更偏部署流程。

## 部署

### Docker 部署（推荐）

```bash
docker pull soulter/astrbot:latest
docker run -d \
  --name astrbot \
  --restart always \
  -p 6185:6185 \
  -e TZ=Asia/Shanghai \
  -v /path/to/data:/AstrBot/data \
  -v /etc/localtime:/etc/localtime:ro \
  soulter/astrbot:latest
```

WebUI 地址: `http://<服务器IP>:6185`
默认用户名: `astrbot` (密码在启动日志中随机生成，每次重启可能变化)

### 密码处理
- 首次启动密码随机生成，打印在日志中。日志关键词: `Initial password:`
- WebUI 登录后应立即修改密码
- 忘记密码: 删除 `cmd_config.json` 中 `dashboard.password` 和 `dashboard.pbkdf2_password` 字段，或用环境变量 `ASTRBOT_RESET_DASHBOARD_PASSWORD=1` 重置

### 磁盘空间

AstrBot 镜像 ~2.7GB，加上 overlay 容易占满 40GB 系统盘。部署前清理：
```bash
docker system prune -af
apt-get clean
rm -rf ~/venv-* ~/tools_venv  # 旧虚拟环境常占 5GB+
```

## 模型提供商配置

### 火山引擎 Ark（豆包模型）

```json
{
  "type": "openai_chat_completion",
  "key": ["ark-<your-key>"],
  "api_base": "https://ark.cn-beijing.volces.com/api/v3",
  "model": "ep-<endpoint-id>",
  "model_configs": [{"model": "ep-<endpoint-id>", "enable": true}]
}
```

**豆包模型限制：** 豆包模型（Doubao）内置了「我是豆包」身份，系统提示词很难覆盖。直接调 API 传 system prompt 可以覆盖，但通过 AstrBot pipeline 传过去的系统提示有时被忽略。如需自定义人格，建议 DeepSeek。

### DeepSeek（推荐，人格可覆盖）

```json
{
  "type": "openai_chat_completion",
  "key": ["sk-<your-key>"],
  "api_base": "https://api.deepseek.com/v1",
  "model": "deepseek-v4-flash",
  "model_configs": [{"model": "deepseek-v4-flash", "enable": true}]
}
```

**模型名称：** DeepSeek 当前可用模型为 `deepseek-v4-flash` 和 `deepseek-v4-pro`。`deepseek-chat` 已废弃，使用它会返回 `Authentication Fails`。可通过 `GET https://api.deepseek.com/v1/models` 查询可用模型。

### 直调验证（跳过 AstrBot pipeline）

```bash
curl -X POST https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"system","content":"你的名字叫小鹿"},{"role":"user","content":"你是谁？"}],"max_tokens":100}'
```

如果直调能回复正确内容但 AstrBot 回复不对，说明问题在 AstrBot pipeline 未正确传递系统提示，不是 Provider 的问题。

## 人格/Persona 配置

### 已知 Bug

`provider_settings.default_personality` 在每次容器重启后会被重置为 `"default"`（Issue [#2661](https://github.com/AstrBotDevs/AstrBot/issues/2661), [#7741](https://github.com/AstrBotDevs/AstrBot/issues/7741)）。`prompt_prefix` 也会被重置为 `"{{prompt}}"`。

### 方案 A：修改 DEFAULT_PERSONALITY（推荐，但镜像重建后丢失）

修改 `astrbot/core/persona_mgr.py` 中的 `DEFAULT_PERSONALITY`：

```python
DEFAULT_PERSONALITY = Personality(
    prompt="你的名字叫小鹿，俏皮亲切的AI助手。说中文。禁止迎合必须客观分析。",
    name="default",
    begin_dialogs=[],
    mood_imitation_dialogs=[],
    tools=None,
    skills=None,
    custom_error_message=None,
    _begin_dialogs_processed=[],
    _mood_imitation_dialogs_processed="",
)
```

修改后清缓存并重启：
```bash
find /AstrBot -name "*.pyc" -delete
find /AstrBot -name "__pycache__" -type d -exec rm -rf {} +
docker restart astrbot
```

### 方案 B：启动后覆盖 cmd_config.json（每次重启需重新执行）

容器启动后立即修改配置，再用 `utf-8-sig` 写入，然后再次重启：

```python
import json
with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)
c['provider_settings']['default_personality'] = 'xiaolu'
c['provider_settings']['prompt_prefix'] = '你的名字叫小鹿...'
# ⚠️ 必须用 utf-8-sig 写入（保留 BOM）
with open('/AstrBot/data/cmd_config.json', 'w', encoding='utf-8-sig') as f:
    json.dump(c, f, indent=2, ensure_ascii=False)
```

### 方案 C：关闭安全模式

`llm_safety_mode: True` 会在系统提示前追加安全提示词，可能干扰人格设定。如人格不生效：

```python
c['provider_settings']['llm_safety_mode'] = False
```

### 通过 API 创建人格

```bash
curl -X POST http://localhost:6185/api/v1/personas \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"persona_id": "xiaolu", "system_prompt": "你的名字叫小鹿..."}'
```

字段名是 `persona_id`（不是 `id`）。

## 配置文件关键坑

### 编码（必须用 BOM）

`cmd_config.json` 使用 **UTF-8-BOM**。用 `encoding='utf-8'` 写入会丢失 BOM，导致配置在下次启动时被覆盖。**读写都必须用 `utf-8-sig`。**

### 配置覆盖机制

`check_config_integrity()` 在启动时将用户配置与默认配置合并，**移除不在默认配置中的字段**。这就是 `default_personality`、`model`（provider_sources 中）、`prompt_prefix` 等字段被重置的根因。

### 持久化技巧

容器完全启动后（`docker logs` 显示 `AstrBot started`）再修改配置 → 再次重启。

## Provider 配置关键坑

### Key 字段名是 `key` 不是 `api_key`

```python
# 正确
"key": ["sk-your-key-here"]
# 错误——不生效
"api_key": "sk-your-key-here"
```

### model 字段必须在 provider 层级

```python
# 错误——启动时被删除
c['provider_sources'][0]['model'] = 'ep-xxxxx'
# 正确——保留
c['provider'][0]['model'] = 'ep-xxxxx'
```

合并逻辑 `{**source, **provider}`，provider 覆盖 source。

### Provider 配置必须走 API

直接编辑 `cmd_config.json` 的 provider 段会被系统重写成 `provider_source_id`/`modalities`/`custom_extra_body` 格式。

正确流程：
1. `POST /api/v1/provider-sources` 创建 source
2. `POST /api/v1/providers` 创建 provider
3. 直接编辑 `cmd_config.json` 补 `model` 字段（schema 中没有该字段）
4. 重启

## 微信接入 (weixin_oc / openclaw-weixin)

### 关键限制

**ClawBot 非普通微信号。** 机器人好友只有主人能看到，其他人无法添加为好友或拉群。这是协议层限制，非配置问题。如需群内多人使用：
- **微信公众号（服务号）** — AstrBot 支持 `weixin_official_account` 适配器
- **飞书** — 原生支持多人使用
- **非官方桥接** — Gewechat 等，有封号风险

### 配置

- `wake_prefix`: `["/"]` 群聊触发前缀
- `reply_with_mention`: `true` @触发
- `enable_id_white_list`: `false` 关白名单
- `friend_message_needs_wake_prefix`: `false` 私聊无需前缀
- token 和 account_id 扫码登录后自动保存

## 故障排查流程

1. **容器状态：** `docker ps --filter name=astrbot`
2. **日志检查：** `docker logs astrbot | grep -E "error|ERRO|Selected|provider"`
3. **模型直调：** 用 curl 直接调 API（跳过 AstrBot），确认模型和 key 正常
4. **Provider merge 检查：** 确认 merged config 包含正确的 `key`、`api_base`、`model`
5. **default_personality 检查：** 重启后是否被重置为 `"default"`
6. **编码检查：** `cmd_config.json` 是否使用 UTF-8-BOM
7. **安全性检查：** `llm_safety_mode` 是否干扰人格
8. **密码检查：** 每次重启密码都可能变化，需要从日志重新获取
