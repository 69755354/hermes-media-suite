# 抖音反爬突破：手机UA绕过验证码

## 发现（2026-07-06）

抖音对 headless Chrome 触发滑块验证码（Page.captureScreenshot 返回 403 / 验证码弹窗），但对手机 User-Agent 放行。

## 绕过方法

使用 **Playwright + iPhone UA** 即可读取视频页面完整文本数据（标题、作者、描述、互动数据、推荐视频）。

```python
from playwright.sync_api import sync_playwright

CHROME_PATH = "/snap/chromium/3477/usr/lib/chromium-browser/chrome"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path=CHROME_PATH,
        args=['--no-sandbox', '--disable-dev-shm-usage']
    )
    context = browser.new_context(
        viewport={'width': 390, 'height': 844},
        user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
    )
    page = context.new_page()
    page.goto('https://www.douyin.com/video/7658863671771252409', wait_until='domcontentloaded', timeout=30000)
    time.sleep(6)
    
    # 截图
    page.screenshot(path='/tmp/douyin_mobile.png')
    
    # 读取页面文本
    body_text = page.inner_text('body')
    
    browser.close()
```

## 已验证结果

| 方法 | 结果 |
|:-----|:----:|
| agent-browser CDP → douyin.com/video/xxx | ❌ 验证码 |
| agent-browser CDP → v.douyin.com/share/xxx | ❌ 验证码/登录页 |
| Playwright 桌面UA → douyin.com | ❌ 验证码 |
| **Playwright + iPhone UA → douyin.com** | ✅ **页面正常加载** |
| 页面截图（手机UA） | ✅ 可看到视频画面 |
| 视频播放 | ❌ 被「打开App」遮罩覆盖 |

## 局限

- ✅ 能读取页面**文本数据**：标题、作者、描述、互动数据、推荐视频、作者声明（如"内容由AI生成"）
- ✅ 能**截图**视频画面（播放器区域可见）
- ❌ 视频播放器被App下载引导遮罩覆盖，无法直接web播放或下载
- ❌ 如需下载视频需登录cookie（和桌面端一样被反爬）
- ❌ `yt-dlp` 解析也需cookie

## 配合豆包视觉模型的完整工作流

当需要分析抖音视频画面时：

```
① Playwright + iPhone UA → 打开视频页 → screenshot
② 豆包视觉模型 → 分析截图 → 输出画面描述
③ 基于描述反推提示词结构（声明"基于画面分析反推"）
```

```python
import requests, base64

# ① 截图（见上方代码）
# ② 调豆包视觉
with open('/tmp/douyin_mobile.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('utf-8')

headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ARK_API_KEY}"}
payload = {
    "model": "doubao-seed-1-6-vision-250815",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "详细描述截图中的画面内容：角色、场景、色调、文字"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
        ]
    }],
    "max_tokens": 1500
}
resp = requests.post("https://ark.cn-beijing.volces.com/api/v3/chat/completions", headers=headers, json=payload, timeout=60)
```
