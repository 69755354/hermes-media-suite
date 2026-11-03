# 头条文章全文提取 + 展现量数据抓取

头条 m.toutiao.com / www.toutiao.com 反爬严重。展现量等数据藏在URL编码的JS变量里，需真实浏览器执行JS后才能拿到。

## 展现量/阅读量数据抓取（Playwright，2026-09-07 验证通过）

**可用脚本**: `scripts/toutiao_metrics.py`（本skill目录下）

```bash
python3 ~/.hermes/skills/newmedia-operations/toutiao-content-production/scripts/toutiao_metrics.py <URL或group_id> [url2] [url3]
```

可提取字段：
- `showCount` = 展现量
- `readCount` = 阅读量
- `commentCount` = 评论数
- `diggCount` = 点赞数
- `shareCount` = 分享数
- `repinCount` = 收藏数
- `forwardCount` = 转发数

**原理**：数据在HTML中URL编码的JS变量里，curl/jina reader抓不到（需执行JS渲染后才能拿到），Playwright（headless Chromium）能拿到。

**用途**：①验证范文有没有量，值不值得对标；②查自己发出去的文章展现量，校准选题方向。

**实测样例**（2026-09-07）：group_id 7661524195775463970（灵活就业社保补贴4050政策）→ 展现148880/阅读6670/收藏183/评论15/点赞53/分享262。数据完整拿到。

## 全文提取方法

### 方法1: Playwright提取正文全文（推荐）

**可用脚本**: `scripts/toutiao_content_extract.py`（本skill目录下）

```bash
python3 ~/.hermes/skills/newmedia-operations/toutiao-content-production/scripts/toutiao_content_extract.py <URL1> [URL2] [URL3]
```

原理：头条文章页是JS渲染的，curl/jina reader 都拿不到完整正文。Playwright打开页面后用 `page.evaluate()` 取 DOM `innerText`，能拿到完整正文。选择器优先级：`article` > `.article-content` > `.pgc-article` > `div[class*="article"]` > `main` > `body`。

**与 toutiao_metrics.py 的分工**：metrics 脚本只抓数据（展现量/阅读量等），content_extract 脚本只抓正文。两脚本配合使用：先跑 metrics 看数据，再跑 content_extract 拿全文做拆解。

### 方法2: curl带移动端UA（简单但只能拿正文，拿不到展现量）
```bash
curl -sL -A "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36" \
  "https://m.toutiao.com/article/<ID>/" 
```
返回HTML，正文在 `<article>` 标签或 `window.__INITIAL_STATE__` JSON里。不稳定，部分文章拿不到。

## 失败的方法（记录避坑）
- `web_extract` 工具：只返回494字符（被截断）
- `jina-ai-reader` (r.jina.ai)：HTTP 400 Bad Request
- curl 不带UA：返回空内容
- curl 带UA但没JS执行：能拿正文，但展现量字段全空
- 头条搜索API（so.toutiao.com/search）直接curl：被滑块验证拦截

## 注意
- 头条反爬会变，方法可能随时失效
- Playwright需安装chromium：`python3 -m playwright install chromium`
- 如果正文提取不到，可以让用户复制全文发过来
- 头条极速版链接格式不同，article ID提取方式一样
