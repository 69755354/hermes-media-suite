# 豆包搜索接入详情 — 头条产线原则 F

> 来源：2026-08-19 Hermes 实测 + claude v7 方案落盘；2026-08-30 Global→Custom 版切换。
> 适用：任何要接豆包搜索 API 找中文报道页/事件图的场景（头条配图、热词降级等）。

## 当前状态：Custom 版 web_search（2026-08-30 切换）

**根因**：原代码调 Global 版 `global_search` endpoint，但账号开的是 Custom 版 `web_search` 按量后付费。两者是火山引擎的独立产品，计费分开。Global 版免费 500 次/月耗尽后报 10406，Custom 版余额通用不受影响。

**改动**：
1. config.yaml endpoint：`search_api/global_search` → `search_api/web_search`
2. modules/search.py 请求体：`{Query, DocCount, MaxSnippetLength}` → `{Query, SearchType:"web", Count, Filter:{NeedUrl:true}}`
3. modules/search.py 响应解析：`Result.Documents` → `Result.WebResults`；字段 `Url`/`Title`（首字母大写）
4. 返回值增加 `snippet/summary/site_name/publish_time` 字段（Custom 版返回 Content 全文 + Snippet 摘要）
5. hotlist.py `fetch_material_for()`：砍掉抓网页流程，直接用 Summary 组装 material.json

## Custom 版 web_search API（当前）

```
POST https://open.feedcoopapi.com/search_api/web_search
Header: Authorization: Bearer <API_KEY> + Content-Type: application/json
Body: {"Query": "<中文关键词>", "SearchType": "web", "Count": 8, "Filter": {"NeedUrl": true}}
返回: Result.WebResults[]，每篇有 Url / Title / Content(完整正文) / Snippet / HostInfo
```

- 实测返回 8 条结果（新华网/央视网等），带完整 Content 正文 + Snippet 摘要
- API_KEY 在 `~/.hermes/config/doubao_search.key`（32 字节）。从环境变量 `DOUBAO_SEARCH_API_KEY` 读，回落 key_ref 文件。
- **用户定方向（2026-08-30）**：「搜索热点就是选题，你要把全文搞过来干嘛？」——不抓网页全文，用搜索返回的 Summary/Snippet 摘要组装 material.json 就够了，LLM 自己会写文章。

## Global 版 global_search API（已废弃，保留参考）

```
POST https://open.feedcoopapi.com/search_api/global_search
Body: {"Query": "<中文关键词>", "DocCount": 3-8, "MaxSnippetLength": 300}
返回: Result.Documents[]，每篇有 Title / Url / Snippet / HostInfo

🔴 Snippet 字段可能是 list：`doc.get('Snippet')` 有时是 `[{'Type': 'text', 'Text': '...'}, {'Type': 'image', ...}]`——取值先 isinstance 判断再拼。
```

## 三个必须绕的坑（Global 版时期，部分已过时）

1. **doubao_search.py 脚本本身走 cost_meter 计费封装会卡**：新模块 `modules/search.py` 只用标准库 urllib.request 直调。
2. **不经计费通道 ≠ 不花钱**：豆包按配额计，Custom 版按量后付费。必须自己记账——`search_trace{}` 里 `est_cost_cny` + `metered: false`。
3. **搜到了但取不到图（风险 15）**：Global 版时所有返回 URL 被跳过（域名不在 site_selectors 里）。**Custom 版已不抓全文，用摘要组装 material，不再依赖 site_selectors**——此坑已绕过。

## 硬约束清单（写代码时照抄）

- `max_search_calls_per_run: 1` 计数器硬拦
- `skip_if_a0_sufficient: true` 先跑完 A0 抽图再决定要不要调搜索
- 失败降级：timeout 15s / max_retry 0 / `search_trace.error` 记原因 + `fallback_used: true`
- **Snippet 红线已修订（2026-08-30）**：Custom 版返回的 Summary 是真实报道摘要，**允许进 material 作为 raw_text**。旧红线「Snippet 只许进相关性打分不许进改写上下文」是 Global 版时期的，已删除。返回值结构现在包含 snippet/summary 字段。

## search_trace 记账字段（14 项）

`provider` / `calls` / `max_calls` / `blocked` / `queries` / `doc_count` / `urls_returned` / `urls_with_selector` / `urls_skipped_no_selector` / `skipped_domains[]` / `error` / `fallback_used` / `est_cost_cny` / `metered`

## 免费额度与付费开通

**错误码 10406 = `FreeQuotaExhausted`**：火山引擎豆包搜索每个账号每月免费 500 次。Global 版耗尽后报此错。**解法：切到 Custom 版 web_search**（用户已开按量后付费，余额通用）。

- 判断姿势：直调 API，看 `ResponseMetadata.Error.CodeN`：10406=免费额度耗尽；10401=无效 token；10403=权限错误。

## 成本对比锚点

- 一次豆包搜索 ≈ 0.30 元（Global 版时期价格；Custom 版按量后付费价格以控制台为准）
- 日更 1 篇月约 9 元；日更 10 篇月约 67-112 元（取决于 A0 命中率）
- 发现层选型（2026-08-19）：Tavily 已停用，SearXNG 挂，豆包直调是当前唯一可用中文事件搜索。