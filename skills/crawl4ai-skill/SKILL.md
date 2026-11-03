---
name: crawl4ai-skill
description: "Web crawling and scraping tool with LLM-optimized output. 网页爬虫爬取工具 | Web crawler, web scraper, spider. DuckDuckGo search, site crawling, dynamic page scraping. 智能搜索爬取 | Free, no API key required."
version: 1.1.0
author: Lancelin
license: MIT-0
repository: https://github.com/lancelin111/crawl4ai-skill
homepage: https://github.com/lancelin111/crawl4ai-skill
pypi: crawl4ai-skill
issues: https://github.com/lancelin111/crawl4ai-skill/issues
tags:
  - web-scraping
  - web-crawling
  - crawler
  - scraper
  - spider
  - search
  - markdown
  - llm
  - token-optimization
  - duckduckgo
  - crawl
  - scrape
  - 爬虫
  - 爬取
  - 网页抓取
requires:
  bins:
    - crawl4ai-skill
---

# Crawl4AI Skill - Web Crawler & Scraper

**Web Crawling 网页爬虫 | Web Scraping 网页爬取 | LLM 优化输出**

智能网页爬虫和爬取工具，支持搜索、全站爬取、动态页面抓取。Free web crawler and scraper with LLM-optimized Markdown output.

## 核心功能 | Core Features

- 🔍 **Web Search 网页搜索** - DuckDuckGo search, 免 API key
- 🕷️ **Web Crawling 网页爬虫** - Site crawler, spider, sitemap 识别
- 📝 **Web Scraping 网页抓取** - Smart scraper, data extraction
- 📄 **LLM-Optimized Output** - Fit Markdown, 省 Token 80%
- ⚡ **Dynamic Page Scraping** - JavaScript 渲染页面爬取

---

## 快速开始 | Quick Start

### 安装 | Installation

```bash
pip install crawl4ai-skill
```

**⚠️ Playwright 浏览器依赖（pip 安装后必须额外操作）：**

crawl4ai 依赖 Playwright 来渲染 JavaScript 页面。pip 安装后需要下载浏览器二进制文件：

```bash
# 在 venv 中安装
python3 -m venv ~/venv/crawl4ai && ~/venv/crawl4ai/bin/pip install crawl4ai-skill
# 下载 Chromium 浏览器
~/venv/crawl4ai/bin/playwright install chromium
```

**🚨 Playwright CDN 下载失败时的替代方案（国内服务器/腾讯云常见）：**

从 CDN 下载 177MB Chromium 超时/失败时，用系统自带的 Chromium 创建符号链接：

```bash
# 1. 找到系统 Chromium 路径
find /snap/chromium -name "chrome" 2>/dev/null | head -1
# → /snap/chromium/3483/usr/lib/chromium-browser/chrome

# 2. 创建 Playwright 期望的目录结构
mkdir -p /home/ubuntu/.cache/ms-playwright/chromium-1228/chrome-linux64/

# 3. 符号链接到系统 Chromium
ln -sf /snap/chromium/3483/usr/lib/chromium-browser/chrome \
  /home/ubuntu/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome
```

注意：Playwright 版本号（如 `chromium-1228`）随版本更新变化，检查 `~/.cache/ms-playwright/` 目录名。不同 Playwright 版本对应的 chromium 子目录名不同。

**PEP 668 环境（Debian/Ubuntu）：** 系统 pip 会拒绝安装到全局，必须用 venv 或 `--break-system-packages`。推荐 venv（如上）。

### Web Search | 网页搜索

```bash
# Search the web with DuckDuckGo
crawl4ai-skill search "python web scraping"
```

### Web Scraping | 单页爬取

```bash
# Scrape a single web page
crawl4ai-skill crawl https://example.com
```

### Web Crawling | 全站爬虫

```bash
# Crawl entire website / spider
crawl4ai-skill crawl-site https://docs.python.org --max-pages 50
```

---

## 使用场景 | Use Cases

### 场景 1：Web Crawler for Documentation | 文档站爬虫

```bash
# Crawl documentation site with spider
crawl4ai-skill crawl-site https://docs.fastapi.com --max-pages 100
```

**爬虫效果 | Crawler Output:**
- ❌ 移除：导航栏、侧边栏、广告
- ✅ 保留：标题、正文、代码块
- 📊 **Token：50,000 → 10,000（-80%）**

### 场景 2：Search + Scrape | 搜索+爬取

```bash
# Search and scrape top results
crawl4ai-skill search-and-crawl "Vue 3 best practices" --crawl-top 3
```

### 场景 3：Dynamic Page Scraping | 动态页面抓取

JavaScript 渲染的页面爬取（雪球、知乎等）：

```bash
# Scrape JavaScript-heavy pages
crawl4ai-skill crawl https://xueqiu.com/S/BIDU --wait-until networkidle --delay 2
```

---

## 命令参考 | Commands

| 命令 Command | 说明 Description |
|------|------|
| `search <query>` | Web search 网页搜索 |
| `crawl <url>` | Web scraping 单页爬取 |
| `crawl-site <url>` | Web crawling 全站爬虫 |
| `search-and-crawl <query>` | Search + scrape 搜索并爬取 |

### 常用参数 | Common Options

```bash
# Web Search 搜索
--num-results 10          # Number of results

# Web Scraping 爬取
--format fit_markdown     # Output format
--output result.md        # Output file
--wait-until networkidle  # Wait strategy for dynamic pages
--delay 2                 # Additional wait time (seconds)
--wait-for ".selector"    # Wait for specific element

# Web Crawling 爬虫
--max-pages 100          # Max pages to crawl
--max-depth 3            # Max crawl depth
```

---

## 输出格式 | Output Formats

### fit_markdown（推荐 Recommended）

智能提取，节省 80% Token。Smart extraction, save 80% tokens.

```bash
crawl4ai-skill crawl https://example.com --format fit_markdown
```

### raw_markdown

保留完整结构。Preserve full structure.

```bash
crawl4ai-skill crawl https://example.com --format raw_markdown
```

---

## 为什么选择这个爬虫？| Why This Crawler?

✅ **免费爬虫 Free Crawler** - 无需 API key，开箱即用  
✅ **智能爬取 Smart Scraper** - 自动去噪，提取核心内容  
✅ **全站爬虫 Site Crawler** - 支持 sitemap，递归爬取  
✅ **动态爬取 Dynamic Scraping** - JavaScript 渲染页面支持  
✅ **搜索集成 Search Integration** - DuckDuckGo 搜索内置  

## 已知局限 | Known Limitations

### 🚨 抖音搜索页：动态加载，基本爬不到视频内容

即使 Playwright 成功渲染页面，抖音搜索页的**视频列表**也是通过异步 XHR/WebSocket 加载的，Playwright 渲染后的 DOM 中只有导航栏（精选/推荐/关注/搜索等），**没有视频卡片、标题、点赞数、团购信息**。

```bash
# ❌ 不要期望这个能拿到视频列表
crawl4ai-skill crawl "https://www.douyin.com/search/眼部护理" -w "div" -t 30 --format fit_markdown
# → 只能拿到导航栏、登录按钮、搜索框，拿不到视频内容
```

**可行替代方案（按效果排序）：**
1. **有具体视频链接** → 直接 `crawl4ai-skill crawl <具体视频URL>`，可能拿到标题、描述和部分元数据
2. **小红书图文笔记** → URL 结构 `/explore/xxx` 可能能拿到内容（受反爬影响，不一定）
3. **web_search (Tavily)** → 搜抖音外的平台（知乎/B站/公众号），获取行业话术和用户痛点描述
4. **用户提供的截图** → vision_analyze 从截图中提取信息

### DuckDuckGo 搜索超时（海外服务器更常见）

```bash
# 可能超时（DuckDuckGo 路由到 Yahoo 被限速）
crawl4ai-skill search "keyword"
# → error sending request for url (https://search.yahoo.com/...) > operation timed out
```

此时降级使用 Tavily web_search 作为替代。

---

## 链接 | Links

- 📦 [PyPI](https://pypi.org/project/crawl4ai-skill/)
- 💻 [GitHub](https://github.com/lancelin111/crawl4ai-skill/)
- 🦞 [ClawHub](https://clawhub.com/skills/crawl4ai-skill)
