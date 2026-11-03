# 抖音创作者后台数据获取 · 方案对比

## 三种方案对比

| 方案 | 自动化程度 | 成本 | 数据时效 | 适用阶段 |
|:----|:----------|:----|:--------|:--------|
| **① Composio MCP** | 100%自动，一次授权永久有效 | 免费版2万次/月 | T+1延迟 | 长期稳定复盘 |
| **② CDP浏览器+持久Cookie** | 90%自动，每30天扫码一次 | 0元 | 实时 | 短期过渡方案 |
| **③ 手动截图报数** | 手动 | 0元 | 实时 | 应急兜底 |

## 方案① Composio MCP（推荐长期使用）

### 前置条件
- 香港服务器（访问composio.dev无504）或国内服务器配中转
- 注册 composio.dev → 创建应用 → 获取API Key
- Hermes配置MCP：`config.yaml` 加 `mcp_servers.composio`

### 配置
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
1. Hermes加载Composio MCP
2. 触发抖音OAuth授权链接 → 手机抖音扫码确认
3. Token自动管理，无需重复授权

### 常用指令
- "拉取近7天短视频播放、完播、互动数据"
- "对比近30天视频数据趋势"
- "拉取门店线索数据（导航点击、电话拨打）"

## 方案② CDP浏览器（过渡方案）

### QR码登录常驻服务
脚本位置：`scripts/douyin-qr-daemon.py`
工作原理：常驻后台，每45秒自动刷新二维码，QR码图片保存在内存/缓存文件

### 使用流程
1. 用户说「发」→ 读取缓存的二维码 → MEDIA发送
2. 用户抖音扫码 → 手机确认 → Cookie写入
3. Cookie有效期约30天，到期后重新扫码

### 已知问题
- 无头浏览器webdriver特征可能被抖音风控拦截Cookie写入
- 使用 `Page.addScriptToEvaluateOnNewDocument` 注入webdriver抹除脚本解决
- 页面SPA加载慢，扫码后需等待5-10秒检测登录状态

## 方案③ 手动（应急兜底）
用户去抖音创作中心截图或报数字 → 我出复盘报告。不依赖任何API或浏览器。
