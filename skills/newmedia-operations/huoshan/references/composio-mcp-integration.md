# Composio MCP 抖音数据复盘集成方案

> 替代 CDP 浏览器爬虫的长期稳定方案，彻底解决二维码过期、WebDriver检测、Cookie拦截等问题

## 方案对比

| 维度 | CDP浏览器爬虫 | Composio MCP |
|:----|:------------|:-------------|
| 鉴权方式 | 抖音App扫码登录（有效期7-30天） | OAuth授权扫码一次，永久自动续期 |
| 数据获取 | 浏览器抓取创作者中心页面 | 官方API返回结构化数据 |
| 稳定性 | 受抖音页面改版、WebDriver检测影响 | 官方API稳定 |
| 延迟 | 实时 | T+1天 |
| 风控 | 高风险（无头浏览器检测） | 合规（官方OAuth） |

## 接入方案

### 条件
- Composio 账号注册（海外网络，香港服务器可直连）
- API Key（免费版月2万次调用，个人复盘够用）

### Hermes 配置
```yaml
mcp_servers:
  composio:
    url: "https://connect.composio.dev/mcp"
    headers:
      x-consumer-api-key: "你的API Key"
    connect_timeout: 120
    timeout: 180
```

### 授权流程
1. Composio后台 → Integrations → TikTok → Connect
2. 手机抖音扫码授权一次
3. 系统自动维护 refresh_token，永久有效

### 使用示例
```
调用Composio抖音工具，拉取近7天所有短视频：播放量、完播率、点赞、评论、转发、涨粉
```

## 注意
- 国内网络访问 Composio 有概率 504 超时（跨国链路问题）
- 香港服务器直连无此问题，可在香港服务器上部署 MCP 中转
- 免费版调用2万次/月，单账号每日复盘够用
