# 平台 /factory 前缀部署：路径问题全清单与修复模式

> 2026-08-16 实录。客户运营平台经广州 Caddy 反代 `/factory/*` 对外，FastAPI root_path=/factory。
> 症状：登录点没反应、登录后跳 /projects 404、深层页面 CSS/JS 404、下载/预览失败。
> 根因：同一应用存在四套互不一致的路径生成方式。逐条补漏会复发，要一次收敛成单一事实源。

## 核心原则

- 路由装饰器（`@app.get("/xxx")`）和 `app.mount("/static")` **不要**写 /factory（代理入口负责外部前缀）。
- 但**所有返回给浏览器的 URL**（模板 href/src、RedirectResponse、JSON 里的 next/media_url、JS location.href/fetch）必须带前缀。
- 收敛成「服务端 url_for + 前端 p()」两个生成器，不要手动拼。

## 常见坑（按破坏面排序）

| 坑 | 现象 | 正解 |
|---|---|---|
| 裸相对路径 `href="static/app.js"` | 深层页面（/factory/projects/new）解析成 /factory/projects/static/ → 404 | 模板用 `{{ request.url_for('static', path='app_v3.js').path }}` |
| 硬编码根绝对路径 `href="/projects/new"` | 丢 /factory → 404 | 模板用 `request.url_for('xxx_page').path`；JS 用 `p()` |
| 服务端 `RedirectResponse("/projects")` | 丢前缀 → 404 | `_prefix(path)` 包装（读 XG_FACTORY_ROOT_PATH） |
| JSON `next: "/projects"` | 登录后跳错 | `_prefix(...)` |
| JS `location.href = data.next` | 同左 | `location.href = p(data.next)`（幂等防重复前缀） |
| JS 原生 `fetch("/api/...")` 不走 api() | 404 | 统一 `fetch(p(...))` |
| 动态生成的 `<a href="/api/...">` / `<video src="${media_url}">` | 下载/预览失败 | 前端 p() 包裹；服务端 media_url 用 _prefix |
| api() 只给白名单路径加前缀（漏 /internal/ 等） | 新路由又漏 | `if (url.startsWith('/')) url = p(url);` 全量处理 |

## 关键实现片段

服务端 `_prefix`:
```python
def _prefix(path: str) -> str:
    root = os.environ.get("XG_FACTORY_ROOT_PATH", "").strip().rstrip("/")
    return f"{root}{path}" if root else path
```

前端 p()（幂等，/factory 已带时不再加）:
```js
const API_BASE = (() => { const m = location.pathname.match(/^\/([^/]+)/); return (m && m[[1]] === 'factory') ? '/factory' : ''; })();
const p = (path) => (path.startsWith(API_BASE) ? path : API_BASE + path);
```

## 浏览器缓存是第二杀手

- 即使代码修好，浏览器可能缓存旧 HTML/JS（尤其手机飞书内置浏览器）。
- 静态资源改文件名（app.js → app_v3.js）比加 ?v=2 更彻底（文件名变必然重新下载）。
- 服务端给 /static 和 .html 响应加 `Cache-Control: no-cache, no-store, must-revalidate` 中间件。

## 验证清单

- TestClient 设置 XG_FACTORY_ROOT_PATH=/factory，逐页 GET，提取全部 href/src 断言以 /factory/ 开头。
- 无前缀本地模式（不设 root_path）再跑一遍，确认不污染。
- 登录 API next、ZIP 下载、media 预览、/internal/ API 全链路断言带前缀。
- 参考：`outputs/平台前缀问题全面排查_20260816.md`（450 行审计）、`outputs/平台前缀修复完成_20260816.md`（10/10 测试）。
