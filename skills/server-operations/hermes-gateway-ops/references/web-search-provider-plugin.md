# Hermes 自定义 web 搜索后端插件（2026-08-06 豆包 provider 实操）

背景：Hermes 内置 web_search 后端（firecrawl/parallel/tavily/exa/searxng/brave-free/ddgs）没有国内可用的免费后端
（searxng 废弃、tavily 开发版 key 额度限制、ddgs 被墙）。豆包搜索（火山引擎 global_search）只能脚本方式，
接不进内置 web_search 工具。解法：写自定义 provider 插件注册。

## 插件结构（plugins/web/doubao/，三个文件）

```
plugins/web/<name>/
├── __init__.py      # register(ctx) → ctx.register_web_search_provider(Provider())
├── provider.py      # 继承 agent.web_search_provider.WebSearchProvider
└── plugin.yaml      # manifest: name/kind: backend/provides_web_providers
```

provider.py 要点：
- `name` = "doubao"（对应 config 的 web.search_backend 值）
- `is_available()`：检查 env key（`get_provider_env("DOUBAO_SEARCH_API_KEY")`），**不能做网络调用**
- `supports_search()` → True；`supports_extract()` → False（搜索 API 不含抓取）
- `search(query, limit, **kwargs)` → 返回标准 shape：`{"success": True, "data": {"web": [{"title","url","description","position"}]}}`；异常返回 `{"success": False, "error": str}`
- key 读取用 `from agent.web_search_provider import get_provider_env`（自动查 os.environ + ~/.hermes/.env）

## 配置（default + customer 都要）

```yaml
# config.yaml
web:
  search_backend: doubao
  backend: doubao
```
```bash
# .env
DOUBAO_SEARCH_API_KEY=<key>
```

## 生效与验证

- 插件改动要重启 gateway 才加载（default + customer）
- 验证：直接 import provider 类调 search()（不需要重启）
- 豆包搜索 API：POST https://open.feedcoopapi.com/search_api/global_search，body {"Query","DocCount","MaxSnippetLength"}，Bearer key
- 遗留坑：web_extract（抓网页）没有免费后端——临时方案用 curl/browser

## 类似可复用

接 Bing/GPT/其他搜索后端 = 复制 doubao 插件结构改 provider.py 即可。
