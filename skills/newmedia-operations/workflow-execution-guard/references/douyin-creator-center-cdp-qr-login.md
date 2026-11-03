# 抖音创作者中心 CDP 二维码登录

## 文档状态

- **创建**：2026-07-16
- **状态**：已验证可用但脆弱，建议作为过渡方案
- **替代方案**：Composio MCP（香港服务器走OAuth API，彻底抛弃CDP浏览器链路）

## 技术要点

### 二维码关键属性

```javascript
// 正确二维码：PNG格式，class名包含qrcode
img[class*="qrcode"]
// 特征：data:image/png;base64,..., 248x248, 自然尺寸512x512
// ⚠️ 页面上同时存在SVG格式的背景装饰图（class=login-card-double-bg-xxx），不要取错
```

### WebDriver 特征抹除

```javascript
// 必须在页面加载前注入，Page.addScriptToEvaluateOnNewDocument 而非 Runtime.evaluate
Object.defineProperty(navigator, 'webdriver', {get: () => undefined})
```

### 二维码有效期

- 单次有效期：2-3分钟
- 页面每60秒自动刷新二维码
- 最佳策略：常驻CDP daemon每45秒刷新一次，用户说发时直接取最新

### CDP 常驻 Daemon

- 脚本位置：`~/.hermes/scripts/qr_daemon_v2.py`
- 工作方式：后台长连接CDP，每45秒自动刷新二维码
- 信号文件：`/tmp/qr_v4.png`（最新二维码）
- CDP端口：9222（Chrome实际端口），9226（配置值，需对齐）

### 常见故障

| 故障 | 原因 | 修复 |
|:----|:-----|:-----|
| 取到SVG非PNG | 选择了login-card-double-bg的装饰图而非二维码 | 用 `img[class*=qrcode]` 精确定位 |
| Cookie写不进 | webdriver特征被检测拦截 | Page.addScriptToEvaluateOnNewDocument注入，非Runtime.evaluate |
| 二维码总过期 | 生成+发送链路超40秒 | 常驻daemon+内存直传，压缩到3-5秒 |
| 点确认后不进数据面板 | img被定时刷新销毁 | 扫码后暂停自动刷新，等120秒 | 
## 最佳替代方案

**Composio MCP**（当前最优解）：
- 香港服务器配Composio MCP
- 抖音开放平台OAuth授权，一次扫码永久有效
- 无需处理CDP/二维码/Cookie
