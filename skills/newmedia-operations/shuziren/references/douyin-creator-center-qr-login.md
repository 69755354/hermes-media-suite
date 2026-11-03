# 抖音创作者中心 · CDP二维码登录 & 数据抓取

## 背景

节点15（数据复盘）需要登录抖音创作者中心拉取视频数据。

## 核心困难

抖音创作者中心 (creator.douyin.com) 登录有三大障碍：
1. **二维码有效期仅2-3分钟** — 从生成到用户扫码时间窗口极短
2. **二维码img是PNG/SVG格式** — 需正确选择`img[class*=qrcode]`元素
3. **页面刷新重置登录态** — 导航/刷新后需要重新扫码

## 正确方案：常驻CDP二维码服务

### 技术栈
- Chrome CDP (端口9222，非9226)
- Python websockets 直连CDP
- ImageMagick `convert` 命令转SVG→PNG（服务器已安装）

### 二维码定位方法

页面上有多张base64图片，真正的二维码具备以下特征：
- className包含 `qrcode`（如 `qrcode_img-NPVTJs`）
- 尺寸 248x248（渲染尺寸） / 512x512（自然尺寸）
- src 为 `data:image/png;base64,...` 或 `data:image/svg+xml;base64,...`

**必须用精确选择器** `img[class*=qrcode]`，不能只按 `base64` 或 `width>80` 匹配（会误中背景装饰图）。

### 常驻服务逻辑

每50秒执行一次: 连接CDP → 检查有无二维码 → 无则点扫码登录按钮 → 等待3秒 → 取img[class*=qrcode].src → 保存PNG到/tmp/qr_cache.png

### SVG→PNG转换（备用）

```bash
convert /tmp/qr_raw.svg -resize 300x300 /tmp/qr_final.jpg
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

### 已知坑

| 坑 | 说明 | 解决 |
|:---|:-----|:-----|
| CDP端口配置错误 | browser_cdp工具写死9226，实际Chrome跑在9222 | 用curl或websockets直连9222 |
| 二维码过期 | 有效期2-3分钟 | daemon每50秒自动刷新；不Page.reload，直接点"扫码登录"或"点击刷新" |
| 二维码定位错误 | 误中背景装饰图（800x629的SVG，className=login-card-double-bg） | 用精确选择器 `img[class*=qrcode]`，真正二维码特征：className=qrcode_img-NPVTJs，248x248，PNG |
| 页面状态混乱 | daemon刷新和手动操作冲突 | 停daemon后再手动操作 |
| WebSocket消息错位 | 连续发送多条消息后recv()拿到错误的响应 | 每条消息收发成对处理，不批量发送 |
| MEDIA发图收不到 | 小图片(<2KB)可能发不出，SVG不显示 | 用>100KB图片测试，确认通道正常；二维码转JPG再发 |

### CDP WebSocket 消息顺序铁律

```python
# ✅ 每次发送后立刻await接收，不攒批
await ws.send(msg1)
r1 = json.loads(await ws.recv())
await ws.send(msg2)
r2 = json.loads(await ws.recv())

# ❌ 下面这样可能错位
await ws.send(msg1)
await ws.send(msg2)
r1 = json.loads(await ws.recv())  # 可能拿到msg2的响应
```

### CDP直连方式

```python
import websockets, json
ws = await websockets.connect('ws://127.0.0.1:9222/devtools/page/{tab_id}')
await ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':'...'}}))
result = json.loads(await ws.recv())
```
