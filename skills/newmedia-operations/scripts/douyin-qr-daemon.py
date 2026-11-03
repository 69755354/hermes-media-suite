#!/usr/bin/env python3
"""抖音创作者中心二维码常驻服务 v4
- 常驻后台，每45秒自动刷新二维码
- 不刷新整个页面，直接取当前页面的二维码
- 使用 img[class*=qrcode] 精确选择
- 如果二维码过期，点击页面刷新按钮重新生成
- 发送时直接读 /tmp/qr_v4.png 文件
"""
import asyncio, json, websockets, base64, os

TAB = "3760E12DCD0747A10C15DF7AC1A08F8A"
QR_FILE = "/tmp/qr_v4.png"

async def refresh():
    try:
        ws = await websockets.connect(f'ws://127.0.0.1:9222/devtools/page/{TAB}')
        
        # 直接取二维码
        await ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':"document.querySelector('img[class*=qrcode]')?.src||''"}}))
        r = json.loads(await ws.recv())
        src = r.get('result',{}).get('result',{}).get('value','') or ''
        
        if not src.startswith('data:image/png'):
            # 可能需要点扫码登录
            await ws.send(json.dumps({'id':2,'method':'Runtime.evaluate','params':{'expression':"var e=[...document.querySelectorAll('*')].find(x=>x.innerText&&x.innerText.indexOf('扫码')>=0&&x.offsetWidth>0);if(e){e.click();'ok'}else{'no'}"}}))
            await json.loads(await ws.recv())
            await asyncio.sleep(3)
            
            await ws.send(json.dumps({'id':3,'method':'Runtime.evaluate','params':{'expression':"document.querySelector('img[class*=qrcode]')?.src||''"}}))
            r3 = json.loads(await ws.recv())
            src = r3.get('result',{}).get('result',{}).get('value','') or ''
        
        await ws.close()
        
        if src.startswith('data:image/png'):
            raw = base64.b64decode(src.split(',')[1])
            if len(raw) > 500:
                with open(QR_FILE, 'wb') as f:
                    f.write(raw)
                return True
    except:
        pass
    return False

async def main():
    while True:
        ok = await refresh()
        sz = os.path.getsize(QR_FILE) if os.path.exists(QR_FILE) else 0
        print(f'{"ok" if ok else "fail"} {sz}', flush=True)
        await asyncio.sleep(45)

if __name__ == '__main__':
    asyncio.run(main())
