---
name: astrbot-deployment
description: AstrBot Docker部署、WebUI配微信机器人(weixin_oc) + AI Provider全流程
---

# AstrBot 部署与配置

用户本地跑 AstrBot Docker，WebUI 端口 6185。微信官方 openclaw-weixin 适配器，Volcengine 方舟 ARK 调 DeepSeek。

## 快速部署

```bash
# 拉镜像（空间不够先 docker system prune -af）
docker pull soulter/astrbot:latest

# 跑容器（volumes 必需配/data持久化）
docker run -d \
  --name astrbot \
  --restart always \
  -p 6185:6185 \
  -e TZ=Asia/Shanghai \
  -v /path/to/data:/AstrBot/data \
  -v /etc/localtime:/etc/localtime:ro \
  soulter/astrbot:latest
```

## 初始密码

Docker 每次重启生成随机密码。从日志中提取：

```bash
docker logs astrbot 2>&1 | grep "Initial password"
```

格式：`Initial username: astrbot / Initial password: xxxxxxxx`

如果 Docker 重启过，密码已变，需要重新从日志提取。

## API + Token 鉴权

所有 API 在 `/api/v1/` 下。先用 login 拿 token：

```bash
LOGIN=$(curl -s -X POST http://localhost:6185/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"astrbot","password":"<current_password>"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['data']['token'])")
```

关键 API 端点：
- `GET /api/v1/bot-types` — 可用的适配器类型
- `GET /api/v1/bots` / `POST /api/v1/bots` — 机器人管理
- `GET /api/v1/provider-sources` / `POST /api/v1/provider-sources` — Provider 源
- `GET /api/v1/providers` / `POST /api/v1/providers` — Provider 实例

## Provider 配置（两级系统）

AstrBot 的 Provider 分两层：

### 1. provider_sources（配置主体）

存 API key、api_base、模型列表等真实配置。

```json
{
  "id": "source_id",
  "type": "openai_chat_completion",
  "name": "显示名",
  "key": ["your-api-key"],
  "api_base": "https://ark.cn-beijing.volces.com/api/v3",
  "model_configs": [{"model": "ep-xxxxx", "enable": true}]
}
```

### 2. providers（引用层）

轻量级配置，引用 source_id：

```json
{
  "id": "provider_id",
  "provider_source_id": "source_id",
  "enable": true,
  "modalities": [],
  "custom_extra_body": {}
}
```

运行时 `get_merged_provider_config()` 会将两者合并。

### Volcengine 方舟 ARK 特例

```bash
# 配源
curl -X POST /api/v1/provider-sources \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "id": "ark_main",
    "type": "openai_chat_completion",
    "key": ["<ARK_API_KEY>"],
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "model_configs": [{"model": "<endpoint_id>", "enable": true}]
  }'

# 配实例
curl -X POST /api/v1/providers \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "id": "ark_main",
    "provider_source_id": "ark_main",
    "capability": "chat",
    "enable": true
  }'
```

注意：model 填 ARK endpoint ID（`ep-xxx`），不是 `deepseek-chat`。

## WeChat 微信机器人（weixin_oc）

### 前提
- AstrBot v4.22.0+
- 微信 iOS ≥ 8.0.70 / Android ≥ 8.0.69，有 ClawBot 功能
- 适配器文件在 `astrbot/core/platform/sources/weixin_oc/`

### 创建

通过在 cmd_config.json 的 `platform` 数组中添加：

```json
{"type": "weixin_oc", "id": "bot_id", "enable": true}
```

或者通过 API：

```bash
curl -X POST /api/v1/bots \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"type": "weixin_oc", "id": "bot_id", "enabled": true}'
```

### 扫码登录

重启 AstrBot 后，适配器自动发起 QR 码登录流程。QR 码链接在日志中：

```bash
docker logs astrbot 2>&1 | grep "qr_link"
```

输出如：
```
qr_link=https://liteapp.weixin.qq.com/q/xxx?qrcode=xxx&bot_type=3
```

下载 QR 码图片发给用户扫描：

```bash
# 从 QR 码 URL 中提取 data 参数
curl -s -o /tmp/qr.png "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=<encoded_url>"
```

登录成功日志：`login confirmed, account=xxx@im.bot`

### 注意事项
- 适配器懒加载，启动时才注册到 bot-types 列表
- 登录态自动持久化，重启无需重扫（除非 token 过期）
- 适配器通过长轮询 (`get_updates`) 收消息，无 Webhook

## 常见坑

| 问题 | 原因 | 修复 |
|:----|:-----|:-----|
| `JSONDecodeError: Unexpected UTF-8 BOM` | 文件有 BOM 头 | `encoding='utf-8-sig'` 读取 |
| `Missing API key` | Token 过期/无 provider 权限 | 重新 login 拿新 token |
| `Provider adapter not found: XXX` | provider 类型名称不对 | 检查 type 字段（如 `openai_chat_completion`） |
| `Selected as default` 但仍报 401 | key/endpoint 配置有误 | 检查 merged config 的实际值 |
| 密码每次重启都变 | Docker 镜像设计 | 从日志取最新密码 |
| `Authentication Fails`（Key结尾b41d等DeepSeek字样） | 用的是 DeepSeek key 而非 ARK key | ARK key 以 `ark-` 开头，且 endpoint 需配 ep-xxx |

## 验证

1. 确认 provider 加载成功无 error
2. 给 bot 微信号发消息，看回复
3. 日志中 `respond.stage` 显示回复内容
