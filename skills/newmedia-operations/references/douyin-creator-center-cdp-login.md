# 抖音创作者中心 CDP 扫码登录

## 核心限制（2025年后）
- 网页端已下线手机号验证码/密码登录入口，**仅保留抖音APP扫码登录**
- 二维码有效期 2 分钟
- 登录会话 Cookie 有效期 7~30 天
- 无头浏览器有 webdriver 特征，抖音会拦截 Cookie 写入

## 可选方案

| 方案 | 成本 | 自动化度 | 说明 |
|:----|:----|:--------|:-----|
| OAuth API（推荐） | 600元/年企业认证 | 100%自动 | 一次授权永久，不走网页 |
| CDP 浏览器扫码 | 0元 | 30天手动扫码一次 | 需处理 webdriver 特征 |
| Composio MCP | 按量付费 | 100%自动 | 第三方中间件 |

## CDP 扫码登录关键要点

### 1. webdriver 特征抹除
使用 `Page.addScriptToEvaluateOnNewDocument` 在页面加载前注入：
```js
Object.defineProperty(navigator, 'webdriver', {get: () => undefined})
```
在 `Page.navigate`/`Page.reload` **之前**注册，不是之后。

### 2. 二维码定位
抖音登录页二维码的CSS选择器：`img[class*=qrcode]`
- 尺寸 248x248，自然尺寸 512x512
- 格式：`data:image/png;base64,...`（PNG）
- 注意：页面上有多个 base64 img，需要过滤

### 3. 禁止刷新！禁止刷新！禁止刷新！
用户扫码 → 手机上点确认 → 后端下发 Cookie，**此期间绝对不能执行`Page.reload`**，否则会话丢失。

扫码后轮询检测登录状态，等 120 秒，不做任何页面操作。

### 4. 完整流程
```
1. Page.addScriptToEvaluateOnNewDocument 注册webdriver抹除脚本
2. Page.navigate 到 creator.douyin.com
3. 等页面加载（8-10秒）
4. 点击"扫码登录"按钮
5. 等二维码渲染（3-4秒）
6. 提取二维码 img[class*=qrcode] 的src
7. 保存为PNG，发送给用户
8. 用户扫码 → 手机上确认
9. **不刷新页面**，轮询检测登录状态
   - "需在手机上进行确认" → 等待
   - 出现"作品"/"播放"等数据 → 登录成功
10. 登录成功 → Network.getAllCookies → 保存 Cookie 文件
```

### 5. 常见失败模式
| 故障 | 原因 | 修复 |
|:----|:-----|:-----|
| Cookie没写入 | webdriver特征被检测 | 用 addScriptToEvaluateOnNewDocument |
| 确认后还是WAITING | 二维码过期或Cookie被拦截 | 重新生成二维码再试 |
| 二维码取到SVG | 选择器不对，取到了背景图 | 用 `img[class*=qrcode]` 精确选择 |
| 页面加载慢 | 抖音SPA首次加载 | 等 8-10 秒，不行就重试 |
