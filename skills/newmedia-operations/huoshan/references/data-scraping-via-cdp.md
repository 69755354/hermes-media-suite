# Chrome CDP 数据抓取参考

> 用于节点15（数据复盘）从各平台创作者后台自动拉取数据。
> 浏览器已在服务器后台运行，CDP端口 9222（注意：配置文件中写的是9226，实际Chrome跑在9222，调用时用9222）。

## 环境确认

```bash
# 检查Chrome是否运行及CDP端口
ss -tlnp | grep 9222

# 查看当前所有页面tab
curl -s http://127.0.0.1:9222/json | python3 -m json.tool
```

## QR 码登录常驻服务（解决二维码过期问题）

**脚本位置：** `/home/ubuntu/.hermes/scripts/qr_daemon.py`

**原理：** 抖音创作者中心扫码登录的二维码只有2-3分钟有效期。传统方案从生成到发送耗时过久。该服务常驻后台，每90秒自动刷新一次二维码，确保用户请求时即取即用。

**启动：**
```bash
python3 /home/ubuntu/.hermes/scripts/qr_daemon.py
```
以background进程运行，保持CDP长连接。

**工作方式：**
1. 常驻CDP WebSocket连接（不需要每次都重连Python→CDP）
2. 每90秒自动刷新一次：导航到登录页→点扫码登录→提取二维码base64
3. 二维码base64保存在内存变量 + 信号文件 `/tmp/qr_ready`
4. 用户说「发」时，读取 `/tmp/qr_ready` 解码成图片直接MEDIA发送

**状态检查：**
```bash
cat /tmp/qr_status   # 显示最新状态
```

## Python CDP 调用模板

```python
import asyncio, json, websockets

async def scrape_page(tab_id: str, js_code: str) -> str:
    ws_url = f'ws://127.0.0.1:9222/devtools/page/{tab_id}'
    async with websockets.connect(ws_url) as ws:
        msg = {'id': 1, 'method': 'Runtime.evaluate', 'params': {'expression': js_code}}
        await ws.send(json.dumps(msg))
        resp = json.loads(await ws.recv())
        return resp.get('result', {}).get('result', {}).get('value', '')

async def main():
    import httpx
    tabs = httpx.get('http://127.0.0.1:9222/json').json()
    for t in tabs:
        if 'creator.douyin.com' in t.get('url', ''):
            tab_id = t['id']
            title = await scrape_page(tab_id, 'document.title')
            text = await scrape_page(tab_id, 'document.body ? document.body.innerText.substring(0, 3000) : ""')
            break
    print(f'Title: {title}\n{text[:1000]}')

asyncio.run(main())
```

## 常用操作

- **打开新页面**: `curl -s -X PUT "http://127.0.0.1:9222/json/new?https://creator.douyin.com/"`
- **点击元素**: JS遍历DOM找目标文本点击（注意`offsetWidth>0`过滤隐藏元素）
- **填输入框(React)**: 用 `HTMLInputElement.prototype.value` setter + `dispatchEvent(new Event('input', {bubbles:true}))`

## 抖音创作中心登录

扫码登录一次可保持数天到数周。

### 登录方式优先级

1. **扫码登录（首选）** — 二维码常驻服务，用户抖音App扫码确认
2. **手机验证码（备选）** — 填入手机号→获取验证码→用户收短信后填入
3. **密码登录（最后）** — 会触发人脸验证

### 验证码收不到排查

- 手机号没注册抖音 → 验证码发不出
- 发送频率限制 → 等30分钟再试
- 运营商拦截 → 检查短信拦截箱
