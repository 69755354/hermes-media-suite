---
name: webapp-subpath-reverse-proxy
description: 子路径反代路径前缀处理。触发：/factory/子路径、登录跳转丢前缀、深层页JS 404。
version: 1.0.0
author: Hermes curator
license: MIT
metadata:
  hermes:
    tags: [fastapi, caddy, reverse-proxy, subpath, 前缀, 路径]
    category: software-development
---

# Web 应用子路径反向代理部署（路径前缀处理）

## When to Use

- 任何 Web 应用（FastAPI/Flask 等）要挂到 Caddy/nginx 子路径（如 `/factory/`）对外访问时，先读本 skill 再动手
- 出现「登录跳转丢前缀」「深层页面 JS/CSS 404」「接口 404」「点按钮没反应」时，按本 skill 排查
- 一句话：**改路径问题前先想清楚 4 套来源，不要点状补漏**

## 触发场景

应用部署在 `127.0.0.1:8090`，通过 Caddy/nginx 以 **子路径**（`/factory/*`）反代对外访问。症状：
- 登录后跳转丢了前缀（`/projects` 而非 `/factory/projects`）→ 404
- 深层页面（`/projects/new`、`/projects/{id}/confirm`）JS/CSS 404 → 点按钮没反应
- API 请求 404（前端调 `/api/...` 而非 `/factory/api/...`）
- 越往深层点越坏

## 核心认知：路径生成有 4 套来源，必须收敛成单一事实源

1. **服务端重定向**（`RedirectResponse("/xxx")`、JSON `"next": "/xxx"`）
2. **模板 HTML**（`href="/xxx"`、`src="/xxx"`）
3. **前端 JS**（`location.href`、`fetch('/api/...')`、动态 `href`）
4. **服务端 JSON 返回的 URL**（`media_url`、`download_url`）

只修其中一两处 = 点状补漏，永远有新问题。**正确做法**：

### 服务端：FastAPI 用 `request.url_for()` 生成带前缀 URL

模板里**不要用裸相对路径**（`static/app.js` 在深层 URL 下解析错：`/factory/projects/static/...` 404），**不要硬编码绝对路径**（丢前缀）。用：

```jinja2
<link rel="stylesheet" href="{{ request.url_for('static', path='style.css').path }}?v=3">
<script src="{{ request.url_for('static', path='app.js').path }}"></script>
<a href="{{ request.url_for('projects_page').path }}">...</a>
```

`url_for(...).path` 在当前部署下生成 `/factory/static/...`，本地无前缀部署下生成 `/static/...`——一套代码两种环境都对。

重定向/JSON 路径统一走前缀 helper：

```python
def _prefix(path: str) -> str:
    root = os.environ.get("XG_FACTORY_ROOT_PATH", "").strip().rstrip("/")
    return f"{root}{path}" if root else path
# RedirectResponse(_prefix("/projects"))、JSONResponse({"next": _prefix("/projects")})
```

FastAPI `root_path` 只影响 OpenAPI 和部分重定向，**不影响** `RedirectResponse` 和模板——必须自己 `_prefix()`。

### 前端：统一 p() 函数，api() 对所有根绝对路径加前缀

```js
const API_BASE = (() => {
  const m = location.pathname.match(/^\/([^/]+)/);
  return (m && m[1] === 'factory') ? '/factory' : '';
})();
const p = (path) => (path.startsWith(API_BASE) ? path : API_BASE + path);

async function api(url, options = {}) {
  if (url.startsWith('/')) url = p(url);  // 不要白名单前缀（/api/、/projects/...），否则 /internal/ 等新路由必漏
  ...
}
```

所有 `location.href`、`fetch('/api/...')`、动态 `<a href>`、`<video src>` 一律过 `p()`。**服务端已带前缀的值再过一次 p() 是幂等的**（`p('/factory/x')` 不重复加）。

## 已知坑（2026-08-16 平台事故实录）

| 坑 | 症状 | 修复 |
|---|---|---|
| 模板裸相对路径 `static/app.js` | 深层页 `/factory/projects/new` 请求 `/factory/projects/static/app.js` 404 | 改用 `request.url_for('static', ...)` |
| 硬编码 `href="/projects/new"` | 点击跳 `/projects/new` 丢前缀 404 | `url_for` 或前端 `p()` |
| api() 白名单前缀（只认 /api/ /projects/） | 新路由 `/internal/...` 全 404 | `if (url.startsWith('/')) url = p(url)` |
| 服务端 JSON 返回裸 `/api/...` URL（media_url） | 视频 `<video src>` 404 | 服务端 `_prefix()` + 前端 `p()` 双保险 |
| 登录后 `location.href = data.next` | 跳丢前缀 | `location.href = p(data.next)` |
| 旧 JS 缓存 | 改完前端代码浏览器还在跑旧版 | 换文件名 `app.js → app_v3.js` + 服务端加 `Cache-Control: no-cache` 中间件 |

## 浏览器缓存根治

只改文件内容不够——浏览器缓存旧 JS/HTML。三招一起：
1. 静态资源/HTML 响应加 `Cache-Control: no-cache, no-store, must-revalidate`（FastAPI 中间件）
2. 改文件名（`app.js → app_v3.js`）彻底绕缓存
3. 用户端强制刷新/清缓存

## 子路径反代配置（Caddy admin API，无 sudo 时）

Caddy 有 admin API（默认 `127.0.0.1:2019`），**不需要 sudo 改 Caddyfile** 就能动态加路由：

```bash
# 读现有 routes
curl -s http://127.0.0.1:2019/config/apps/http/servers/srv1/routes
# PATCH 插入 /factory/* 反代（不剥前缀，前缀由后端 root_path/url_for 处理）
curl -s -X PATCH -H "Content-Type: application/json" \
  --data @routes.json \
  http://127.0.0.1:2019/config/apps/http/servers/srv1/routes
```

⚠️ admin API 配置**重启 Caddy 会丢**（没落盘 Caddyfile）——持久化需要 root。生产务必落盘 + systemd 守护。

## 完整验证清单（改完必跑）

用带 cookie 的 curl 模拟全流程，逐页检查 HTML 里的 href/src 都是带前缀的：
1. `curl -s <公网>/factory/login` → grep href/src 应为 `/factory/static/...`
2. 登录 POST → 返回 `"next": "/factory/..."`（带前缀）
3. 登录后 GET `/factory/projects`、`/factory/projects/new` → 资源引用带前缀、HTTP 200
4. 深层页（`/factory/ops/login`、`/factory/projects/{id}/confirm/C1`）资源引用也带前缀
5. 静态资源直接 curl → 200
6. **本地无前缀模式再跑一轮**，确认 `url_for` 双环境兼容

## 相关

- 广州隧道链路：见 `singapore-guangzhou-relay`（国内访问新加坡平台：新加坡机 ssh -R 18090 → 广州 Caddy /factory/ 反代）
- 飞书原生文件交付（COS 链接外部打不开的替代）：见 `references/feishu-file-delivery.md`（im/v1/files 上传 + im/v1/messages 发原生文件消息，报告 md→docx 后发群）
