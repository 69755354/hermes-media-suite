### 常驻服务脚本

位置：`/home/ubuntu/.hermes/scripts/qr_daemon.py`

```python
# 核心逻辑：保持CDP长连接 → 每90秒自动刷新二维码
# base64存 /tmp/qr_ready（每次用户说「发」时读取此文件）
# 启动方式（后台进程）：
#   python3 /home/ubuntu/.hermes/scripts/qr_daemon.py

# 快速取码发送：
#   1. python3 /tmp/quick_qr.py  （独立脚本，不依赖daemon，但会重连CDP）
#   2. 读取 /tmp/qr_ready → decode → MEDIA发送

# 脚本入口文件详情见 /home/ubuntu/.hermes/scripts/qr_daemon.py
```

### webdriver 特征抹除（关键修复）

无头浏览器有 `navigator.webdriver=true` 特征，抖音前端安全脚本会拦截登录 Set-Cookie 响应。

**必须**用 `Page.addScriptToEvaluateOnNewDocument` 在页面加载前注册，不是在页面加载后用 `Runtime.evaluate`：
```python
# ✅ 正确：页面加载前注册
await ws.send(json.dumps({'id':1,'method':'Page.addScriptToEvaluateOnNewDocument','params':{
    'source':"Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
}}))
# 然后再 Page.navigate / Page.reload

# ❌ 无效：页面加载后才注入，抖音JS已检测到webdriver特征
await ws.send(json.dumps({'id':2,'method':'Runtime.evaluate','params':{
    'expression':"Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
}}))
```

### 扫码确认后禁止刷新（硬铁律）
用户扫码 → 手机上点确认 → 后端下发 Cookie。**此期间绝对不能执行 Page.reload**，否则会话丢失。

```python
# 状态轮询，只读不写
while True:
    await ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':'document.body.innerText.substring(0,200)'}}))
    text = json.loads(await ws.recv()).get('result',{}).get('result',{}).get('value','')
    if '作品' in text and '播放' in text:  # 登录成功特征
        break
    if '需在手机上进行确认' in text:  # 等待用户确认
        await asyncio.sleep(2)
        continue
    # 千万不能 Page.reload 或 Page.navigate
```

### 避坑总结

2026-07-16 登录创作者中心踩过的坑：

### 核心发现
1. 网页端2025年后**仅扫码**，无验证码/密码入口（不要浪费时间试这两种方式）
2. 二维码img选择器必须精确 `img[class*=qrcode]`，页面上有多个base64图片，SVG背景装饰图（800x629）会被误认为二维码
3. 真正二维码特征：`className=qrcode_img-NPVTJs`，size=248x248，natural 512x512，PNG格式
4. **不要用 Page.reload 刷新页面**，SPA加载极慢（6-8秒以上），直接在当前页面点击"扫码登录"或"点击刷新"即可
5. 不要用 `browser_cdp` 工具（配置写死9226端口），直连CDP 9222端口
6. 微信MEDIA发图片大图（>100KB）比小图（<2KB）更稳定；SVG格式图片直接不显示

### WebSocket 消息ID错位问题
CDP的WebSocket通信中，`await ws.recv()`只是按接收顺序读取，不匹配消息ID。如果前一条消息的响应延迟，会导致取到错误返回值。

**正确做法：** 每条消息发送后立即await一个响应，处理完再发下一条。不要在同一个连接里快速发送多条消息。

```python
# ✅ 正确：收发配对
await ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':'...'}}))
r1 = json.loads(await ws.recv())
# 处理r1后再发下一条
await ws.send(json.dumps({'id':2,'method':'Runtime.evaluate','params':{'expression':'...'}}))
r2 = json.loads(await ws.recv())

# ❌ 错误：连续发送再连续接收（消息顺序可能错乱）
await ws.send(msg1)
await ws.send(msg2)
r1 = json.loads(await ws.recv())  # 可能拿到msg2的响应
```

### 二维码生成 v4 方案（最稳定）
1. **不刷新页面**，直接查询 `document.querySelector('img[class*=qrcode]')?.src`
2. 如果没取到：点扫码登录按钮 → 等待3-4秒 → 再取
3. 如果二维码过期：页面显示"二维码失效"和"点击刷新"按钮，点刷新即可
4. 取到的src是 `data:image/png;base64,...`（PNG格式），可直接base64解码保存
5. 如果src是 `data:image/svg+xml;base64,...`（SVG），说明定位到了背景装饰图，换选择器
