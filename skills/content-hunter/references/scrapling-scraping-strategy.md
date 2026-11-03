# Scrapling 爬虫策略（2026-06-28）

## 概述
Scrapling 是 Python 爬虫库，支持 HTTP 直连和 Playwright 浏览器模式。从香港服务器可绕过 Cloudflare 反爬。

## 三种模式

| 模式 | 类 | 说明 | 适合平台 |
|------|-----|------|---------|
| HTTP直连 | `Fetcher` | 原生http请求，轻量快速 | B站、百度等SSR渲染站 |
| DynamicFetcher | `DynamicFetcher` | Playwright浏览器，基础反检测 | JS不重的站点 |
| StealthyFetcher | `StealthyFetcher` | Playwright+全面反检测 | 有Cloudflare的站点 |

## 关键参数
```python
StealthyFetcher.fetch(
    url,
    headless=True,          # 默认
    network_idle=True,      # 等网络空闲
    load_dom=True,          # 等JS执行
    timeout=60000,          # 毫秒
    wait=5000,              # 加载后额外等待ms
    disable_resources=True, # 禁用图片字体加速
    solve_cloudflare=True,  # 解决CF验证
    hide_canvas=True,       # Canvas指纹保护
    block_webrtc=True,      # 防止IP泄露
    google_search=True,     # Google referer
    wait_selector=".class", # 等特定元素出现
    page_action=my_func,    # 自定义操作函数
)
```

## 平台实测结果

| 平台 | 可行模式 | 内容获取 | 备注 |
|------|---------|:--------:|------|
| **B站** bilibili.com | HTTP直连✅ | ✅ 完整HTML | SSR渲染，最简单 |
| **百度** baidu.com | HTTP直连✅ | ✅ 搜索结果 | SSR渲染 |
| **抖音** douyin.com | StealthyFetcher✅ | ❌ 0字节（JS渲染） | 绕过CF但拿不到SPA内容 |
| **快手** kuaishou.com | StealthyFetcher✅ | ❌ 0字节（302跳转+JS） | 同上 |
| **小红书** xiaohongshu.com | StealthyFetcher✅ | ❌ 0字节（JS渲染） | 同上 |

## 重要限制
- **所有中国短视频平台（抖音/快手/小红书）都是重度JS SPA** — Scrapling能绕过Cloudflare拿到HTTP 200和正确的Title，但Playwright捕获时JS尚未渲染完毕，内容为0字节
- **wait_selector + network_idle + 长wait** — 理论上可用于等待特定元素渲染，但实测因超时/404/无法定位选择器而失败（各平台DOM结构变化快）
- **B站是唯一能直接爬内容的短视频平台** — 它使用SSR渲染，HTTP直连即可
| 截图可行 | `page_action`参数可用于截图取证（已验证抖音截图2.4MB），证明页面存活但JS内容未被捕获 |
| CSS API 注意 | `.css("title")` 返回 `Selectors` 对象，不是字符串。取文本用 `.css("title").first.text` 而非 `.text`。否则报 `'Selectors' object has no attribute 'text'`。 |
| B站最稳 | SSR渲染 + 无Cloudflare，HTTP直连即可取全文。StealthyFetcher也能开，但没必要。 |

## 什么时候用 Scrapling 替代浏览器
用 Scrapling（而非 browser 工具）的场景：
1. **只要Title/Tag/Meta信息** — Scrapling HTTP模式能拿到页面Title，确认页面存活
2. **爬百度搜索结果** — 先爬百度搜"抖音爆款 xxx"拿到文章链接
3. **B站内容抓取** — SSR渲染，StealthyFetcher可直接拿到完整HTML
4. **绕过Cloudflare验证** — browser工具被CF拦截时，StealthyFetcher+`solve_cloudflare`可绕过

## 什么时候必须用浏览器
1. **需要渲染JS内容** — 抖音/快手/小红书的内容列表
2. **需要登录态** — 需Cookie/Token的页面
3. **需要用户交互** — 点击、滚动、表单填写
4. **需要截图** — `page_action` 用于截图取证
