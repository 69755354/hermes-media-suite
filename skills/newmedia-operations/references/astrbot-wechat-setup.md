# AstrBot 微信个人号 Bot 部署指南

## 概述

基于 AstrBot + openclaw-weixin（腾讯官方 iLink 协议）部署微信个人号 AI 机器人。

**架构：** AstrBot (Docker) ← weixin_oc 适配器 ← 微信扫码登录 → 长轮询收/发消息

---

## ⚠️ 关键限制：ClawBot 非真微信号，仅主人可用

**openclaw-weixin（ClawBot）不是真正的微信号。** 它是在扫码者手机上创建的一个虚拟「插件好友」：

- ✅ 扫码者（bot 主人）可以正常聊天
- ❌ **其他微信用户无法搜索/添加/与 bot 互动**
- ❌ **无法拉 bot 进群聊**（群聊里有 bot 选项但实际不生效）
- ❌ 电脑版微信看不到这个 bot 好友

**这是 iLink Bot API 协议层限制，不是配置问题。**

**需要多人可用 → 换方案：**
- 微信公众号（服务号）：`weixin_official_account` 适配器
- 飞书：原生多用户群聊支持
- 非官方桥接（Gewechat）：小号挂载，有封号风险

---

## 快速部署

### 1. 启动 AstrBot（Docker）

```bash
docker pull soulter/astrbot:latest
mkdir -p /path/to/data
docker run -d \
  --name astrbot \
  --restart always \
  -p 6185:6185 \
  -v /path/to/data:/AstrBot/data \
  soulter/astrbot:latest
```

WebUI：`http://服务器IP:6185`
初始账号密码：查看 `docker logs astrbot | grep "Initial password"`

### 2. 创建微信机器人

API 方式（无浏览器场景）：

```bash
# 1. 登录 WebUI 获取 token
LOGIN=$(curl -s -X POST http://localhost:6185/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"astrbot","password":"<初始密码>"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['token'])")

# 2. 创建 weixin_oc 机器人
curl -s -X POST http://localhost:6185/api/v1/bots \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"weixin_oc","id":"my_wechat_bot","enabled":true,"config":{"type":"weixin_oc","id":"my_wechat_bot","enable":true}}'

# 3. 重启容器让适配器加载
docker restart astrbot

# 4. 从日志中提取二维码链接
docker logs astrbot 2>&1 | grep "qr_link"
# → "https://api.qrserver.com/...?data=https%3A//liteapp.weixin.qq.com/..."
# URL decode 后得到微信链接

# 5. 用手机微信扫码登录
```

### 3. 配置 LLM Provider

⚠️ **`model` 字段必须同时放在 provider_sources 顶层和 provider 顶层**（`openai_chat_completion.__init__` 读的是 `provider_config.get("model", "unknown")`，不是 `model_configs`）。

⚠️ **API key 字段名是 `key`（列表），不是 `api_key`。**

```bash
# 创建 provider source
curl -s -X POST http://localhost:6185/api/v1/provider-sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my_source",
    "type": "openai_chat_completion",
    "name": "My LLM",
    "key": ["<API_KEY>"],
    "api_base": "https://api.deepseek.com/v1",
    "model": "deepseek-v4-flash",
    "model_configs": [{"model": "deepseek-v4-flash", "enable": true}]
  }'

# 创建 provider 实例
curl -s -X POST http://localhost:6185/api/v1/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "deepseek_main",
    "provider_source_id": "my_source",
    "capability": "chat",
    "enable": true
  }'
```

---

## 配置文件关键字段

文件位置：`data/cmd_config.json`（**必须用 `encoding='utf-8-sig'` 读写，即 UTF-8 BOM**）

### 群聊配置（对 ClawBot 不生效，仅作参考）

```json
{
  "platform_settings": {
    "wake_prefix": ["/"],
    "enable_id_white_list": false,
    "reply_with_mention": true,
    "friend_message_needs_wake_prefix": false
  }
}
```

| 字段 | 说明 |
|:----|:-----|
| `wake_prefix` | 触发前缀，`["/"]` 表示 `/开头` 触发 |
| `enable_id_white_list` | 白名单开关，`false` 关闭（否则空白名单=所有人被拦） |
| `reply_with_mention` | 回复时 @ 用户 |
| `friend_message_needs_wake_prefix` | 私聊是否需要前缀，`false` 直接回 |

### 模型 Provider 配置（完整示例）

```json
{
  "provider_sources": [{
    "id": "source_id",
    "type": "openai_chat_completion",
    "name": "DeepSeek Direct",
    "key": ["<API_KEY>"],
    "api_base": "https://api.deepseek.com/v1",
    "model": "deepseek-v4-flash",
    "model_configs": [{"model": "deepseek-v4-flash", "enable": true}]
  }],
  "provider": [{
    "id": "deepseek_main",
    "enable": true,
    "provider_source_id": "source_id",
    "model": "deepseek-v4-flash"
  }],
  "provider_settings": {
    "default_provider_id": "deepseek_main",
    "llm_safety_mode": false,
    "default_personality": "default"
  }
}
```

⚠️ **模型名必须匹配服务商实际名称** — DeepSeek 当前（2026-07）模型名为 `deepseek-v4-flash` 和 `deepseek-v4-pro`，不是 `deepseek-chat`。

⚠️ **配置文件编码必须为 UTF-8 BOM** — 用 `encoding='utf-8-sig'` 读写，否则重启会被 `check_config_integrity` 覆盖。

⚠️ **`default_personality` 会在重启后被重置为 `"default"`** — 已知 bug #2661。即使手动写入 `cmd_config.json`，`check_config_integrity` 也会抹掉。工作区见下方「人设配置」。

---

## 调试技巧

### 验证 Provider 是否工作

直接以 AstrBot 的配置调 API，比对 bot 回复：

```python
import json, urllib.request

with open('/AstrBot/data/cmd_config.json', encoding='utf-8-sig') as f:
    c = json.load(f)

key = c['provider_sources'][0]['key'][0]
model = c['provider_sources'][0]['model']
api_base = c['provider_sources'][0]['api_base']

body = json.dumps({
    'model': model,
    'messages': [
        {'role': 'system', 'content': '你的名字叫小鹿，俏皮亲切的AI助手。说中文。'},
        {'role': 'user', 'content': '你是谁？'}
    ],
    'max_tokens': 100
}).encode()

req = urllib.request.Request(f'{api_base}/chat/completions', data=body,
    headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
print(resp['choices'][0]['message']['content'])
```

**如果直调正常但 bot 回复不对 → 问题在 AstrBot pipeline，不在模型侧。**

### 切换模型后清历史

AstrBot 会记住旧对话历史。换模型后 bot 可能沿用旧回复模式。

```python
import sqlite3
conn = sqlite3.connect('/AstrBot/data/data_v4.db')
for t in ['conversations', 'platform_message_history', 'platform_sessions']:
    conn.execute(f'DELETE FROM {t}')
conn.commit()
conn.close()
```

---

## 人设/人格配置（核心痛点）

AstrBot 的人设系统有两个已知 bug，导致 system prompt 传不到模型：

### Bug 1: `default_personality` 被重置（#2661）

每次重启 `provider_settings.default_personality` 变回 `"default"`。配置文件中手动写入也会被 `check_config_integrity` 覆盖。

**唯一稳的修法：改源码**

```python
# 文件: astrbot/core/persona_mgr.py
DEFAULT_PERSONALITY = Personality(
    prompt="你的名字叫小鹿，俏皮亲切的AI助手。语气词多用哈~嘛呢呦咯呗。说中文。禁止迎合必须客观分析。有问题直接指出。",
    name="default",
    ...
)
```

改完清 `__pycache__`：

```bash
find /AstrBot -name "__pycache__" -exec rm -rf {} +
docker restart astrbot
```

### Bug 2: 豆包模型硬编码身份（#7741）

**现象：** 使用 Volcengine Ark 的豆包模型时，即使传了 system prompt，模型仍回复「我是豆包...」。

**根因：** 豆包模型在 RLHF 训练中固化了「豆包」身份，system prompt 优先级低于其内置指令。

**解决：** 换用其他模型。可用选项：
- DeepSeek (deepseek-v4-flash / deepseek-v4-pro) — 通过 `api.deepseek.com` 或火山引擎 Ark
- GLM (glm-4-5-air)
- Kimi (kimi-k2)

---

## 用户偏好（此项目用户）

记录自 2026-07-14/15 微信 bot 部署会话：

- **结论先行，不要铺垫** — 给方案直接给答案
- **被纠正时直接认错，不提理由** — 不说「疏忽」「忘了」
- **说「？」就是嫌啰嗦** — 立即打住只给结论
- **术语精确强迫症** — 文案=台词+情绪+人设同一节点，分镜=画面描述+镜头语言独立节点。不接受混用命名
- **两段式结构** — 段1文本分析 + 段2视频工作流，不搞三段
- **一切改动后必须重启/刷新** — 修改文件后重启服务，不要等用户报错

---

## Volcengine Ark 可用模型（2026-07）

| 模型 ID | 说明 |
|:-------|:-----|
| `deepseek-v4-flash-260425` | DeepSeek V4 Flash |
| `deepseek-v4-pro-260425` | DeepSeek V4 Pro |
| `deepseek-v3-2-251201` | DeepSeek V3.2 |
| `doubao-seed-2-0-pro-260215` | 豆包 Seed 2.0 Pro（⚠️ 硬编码身份） |
| `doubao-seed-2-0-lite-260215` | 豆包 Seed 2.0 Lite |
| `kimi-k2-250711` | Kimi K2 |
| `glm-4-5-air-20250728` | GLM 4.5 Air |

> ⚠️ 以上模型需在火山引擎 Ark 控制台「模型推理」→「创建 endpoint」后，用 endpoint ID 调用。直接用模型 ID（如 `deepseek-v4-flash-260425`）会报 403/not activated。

---

## 参考链接

- AstrBot 官方文档：https://docs.astrbot.app
- openclaw-weixin 接入文档：https://docs.astrbot.app/platform/weixin_oc.html
- iLink 协议分析：https://github.com/hao-ji-xing/openclaw-weixin
- AstrBot 配置文件参考：https://docs.astrbot.app/dev/astrbot-config.html
- 人格 bug #2661：https://github.com/AstrBotDevs/AstrBot/issues/2661
- 豆包身份 bug #7741：https://github.com/AstrBotDevs/AstrBot/issues/7741
