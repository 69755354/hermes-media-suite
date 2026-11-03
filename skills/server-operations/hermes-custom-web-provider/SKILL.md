---
name: hermes-custom-web-provider
title: Hermes 自定义 web 搜索/抓取 provider 插件
description: 触发：web_search 后端不可用或想接新搜索源。写 plugins/web 三件套注册自定义后端。
version: 1.0.0
---

# Hermes 自定义 web provider 插件

给 Hermes 内置 `web_search` / `web_extract` 工具接自定义后端。当内置后端
（searxng/tavily/exa/firecrawl 等）不可用或不满足时，写一个 provider 插件注册进去。

## 触发场景（2026-08-06 实测）

- 内置 `web.search_backend` 一直是 searxng（已废弃，搜索返回空）+ `auxiliary.web` 走 tavily（开发版 key 额度限制）
- 豆包搜索（火山引擎 global_search）脚本方式验证可用，但 Hermes 内置后端列表里没有豆包
- **解法：写 plugins/web/doubao/ 插件，注册 `doubao` provider，配置 `web.search_backend: doubao`**

## 插件三件套（结构）

```
plugins/web/<name>/
├── provider.py      # WebSearchProvider 子类（核心逻辑）
├── __init__.py      # register(ctx) → ctx.register_web_search_provider(Provider())
└── plugin.yaml      # manifest（kind: backend, provides_web_providers: [name]）
```

## provider.py 接口要点（agent/web_search_provider.py ABC）

```python
from agent.web_search_provider import WebSearchProvider, get_provider_env

class DoubaoWebSearchProvider(WebSearchProvider):
    @property
    def name(self) -> str: return "doubao"           # 对应 web.search_backend 值

    def is_available(self) -> bool:
        # 只能做廉价检查（env var 是否设置），禁止网络调用
        return bool(get_provider_env("DOUBAO_SEARCH_API_KEY"))

    def supports_search(self) -> bool: return True
    def supports_extract(self) -> bool: return False  # 豆包搜索不含抓取

    def search(self, query, limit=10, **kwargs):
        # 返回标准 shape：{"success": True, "data": {"web": [
        #   {"title": str, "url": str, "description": str, "position": int}]}}
        # 失败返回 {"success": False, "error": str}
```

关键点：
- `get_provider_env(name)` 读 env → .env（config 层可见），key 放 `.env` 不用硬编码
- `is_available()` 禁网络调用（工具注册时执行）
- extract 不实现就返回 `supports_extract() → False`（web_extract 会 fallback 其他 provider）

## plugin.yaml

```yaml
name: web-doubao
version: 1.0.0
description: "豆包搜索（火山引擎 global_search）"
author: NousResearch
kind: backend
provides_web_providers:
  - doubao
```

## 配置生效（default + customer 都要改）

1. `.env` 加 `DOUBAO_SEARCH_API_KEY=...`
2. `config.yaml`：`web.search_backend: doubao` + `web.backend: doubao`
3. **重启 gateway 才加载插件**（default 和 customer 各一次）
4. 验证：`python -c "from plugins.web.doubao.provider import DoubaoWebSearchProvider; print(DoubaoWebSearchProvider().search('测试', limit=3))"`

## 已验证案例（2026-08-06）

- `plugins/web/doubao/`：火山引擎 global_search API（open.feedcoopapi.com），1.5s 出 5 条准确结果
- 火山文档/CSDN 精准命中，替代废弃 searxng 成功
- 豆包 API 参数：`{"Query": q, "DocCount": n, "MaxSnippetLength": 300}`，Bearer 认证

## Pitfalls

- **SearXNG 是废弃状态**（搜索返回空、不支持抓取）——别指望它，遇到直接换
- **ddgs（DuckDuckGo）国内服务器被墙**——搜不到不是配置问题，是国内网络
- **豆包搜索 API 不含网页抓取**——web_extract 没有免费内置后端；抓网页用 curl / browser 工具（已验证可用）
- **Tavily 开发版 key 有额度**——连续搜索几次就超额返回空，别当主后端
- 插件路径：`<repo>/plugins/web/<name>/`（内置自动加载）或 `~/.hermes/plugins/web/<name>/`（用户目录）
- 参考实现：`plugins/web/tavily/`（多能力 provider）、`plugins/web/searxng/`（简单搜索）
