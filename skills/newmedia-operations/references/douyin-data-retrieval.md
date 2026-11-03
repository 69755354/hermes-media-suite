# 抖音创作者中心数据获取方案

## 三种方案对比

| 方案 | 成本 | 自动化度 | 适用阶段 |
|:----|:----|:--------|:---------|
| **Composio MCP（推荐）** | 免费版0元，月2万次 | 100%自动，一次授权永久 | 长期稳定用 |
| **CDP 浏览器扫码** | 0元 | 30天扫码一次 | 短期过渡用 |
| **抖音开放平台 OAuth** | 600元/年企业认证 | 100%自动 | 企业级用 |

## Composio MCP 方案

### 配置方式

```yaml
mcp_servers:
  composio:
    url: "https://connect.composio.dev/mcp"
    headers:
      x-consumer-api-key: "你的API Key"
    connect_timeout: 120
    timeout: 180
```

### 注册方式
- 海外/香港服务器直接访问 https://dashboard.composio.dev 注册
- 国内服务器需要香港中转或CDP浏览器操作
- Composio CLI: `composio login --no-browser`（需新版API）

### 授权方式
1. Composio后台绑定抖音账号（抖音APP扫码一次）
2. Hermes配置MCP后直接拉数据
3. 支持多账号（multiAccount模式，最多同时3个）

### 调用指令
```
调用Composio抖音工具，拉取近7天短视频：播放量、完播率、点赞、评论、粉丝数据，生成复盘报告
```

## CDP 浏览器扫码方案

### 常驻二维码服务
脚本：`scripts/douyin-qr-daemon.py`
- 后台常驻，每45秒自动刷新二维码
- 保存到 `/tmp/qr_v4.png`
- 用户说"发"时直接读取发送

### 关键要点
1. `Page.addScriptToEvaluateOnNewDocument` 在页面加载前注入webdriver抹除脚本
2. 二维码CSS选择器：`img[class*=qrcode]`
3. 用户扫码确认后绝对不要刷新页面（会丢失Cookie）
4. MEDIA发送二维码时注意微信可能不显示超小PNG，必要时转RGB JPG

## 数据源选择建议
- **常规复盘**：Composio MCP（T+1延迟，稳定）
- **实时看当日数据**：CDP浏览器直接打开创作者中心（需先扫码登录）
