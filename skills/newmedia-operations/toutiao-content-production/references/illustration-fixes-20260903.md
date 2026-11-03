# 配图修复 2026-09-03

## 问题
产线配图环节卡死在 0/3 死循环（23分钟反复重试），所有图源全挂。

## 根因+修复

### 1. 移动版域名没配 site_selectors
m.chinanews.com、m.sohu.com 被 `unknown_domain_policy: skip` 跳过。

修复：config.yaml site_selectors 加：
- `m.chinanews.com.cn` → `div.left_zw`, `div.content_maincontent_content`
- `m.sohu.com` → `div.article`, `#articleContent`, `div.article-content`
- `chinanews.com.cn` → `div.left_zw`, `div.content_maincontent_content`
- `sohu.com` → `div.article`, `#articleContent`

### 2. Wikimedia Commons 搜出 PDF 不是图片
Commons API 返回 PDF/DJVU/PPTX 文件被当图片候选。

修复：illustrate.py cands_commons() 加 PDF 过滤：
```python
title = p.get("title", "")
if re.search(r"\.(pdf|djvu|pptx?|docx?|tif)", title, re.I):
    continue
```

### 3. Commons topic_queries 缺副业/兼职搜索词
事件含「副业」但 topic_queries 无匹配关键词 → fallback 到默认 query 搜不到相关图。

修复：config.yaml stock_commons.topic_queries 加：
- keywords: ['副业','兼职','骗局','诈骗','刷单','网络诈骗'], query: 'smartphone money'
- keywords: ['赚钱','收入','手机','在线'], query: 'person working laptop home'

### 4. Commons 搜索词要短不要长（关键教训）

**长查询词返回0张，短查询词返回12张真实图片。**

| query | 结果 |
|---|---|
| `smartphone money` | 12 张真实 JPEG（Android Smartphone with Money.jpg 等）✅ |
| `computer virus scam smartphone money` | 5 张全是 PDF ❌ |
| `person working laptop home` | 6 张真实 JPEG（Couple working at home.jpg 等）✅ |
| `person working laptop home office` | 6 张但混入 .ogg/.webm ❌ |
| `phishing email` | 11 张真实图片 ✅ |
| `smartphone money online` | 4 张质量差 ❌ |

**规则：Commons API 搜索词越短越好（2-3个词），长查询词要么返回0要么全是PDF。**

### 5. filetype:bitmap 在 Commons API 不生效

尝试在 gsrsearch 加 `filetype:bitmap` 过滤 PDF → 返回0页。Wikimedia Commons API 的 `generator=search` 不支持 `filetype:` 语法（与 web 搜索不同）。靠代码层 PDF 过滤就行，不要在搜索词里加 filetype。

## chinanews 素材来源页本身无新闻配图
A0 素材来源页（chinanews.com.cn/sh/2026/08-24/10683175.shtml）正文只有一张广告图，不是选择器问题而是文章本身没图。A0 命中率受素材来源页带图率限制。

## 配图死循环
所有图源全挂时 illustrate.py 内部循环补图不停重试，GLM 产线卡 23 分钟。需在所有降级路径走完后及时退出不阻塞全链。临时解法：kill 进程 + 关 illustration.enabled 跳过配图先出文字稿。

## 验证状态
- cands_commons('smartphone money') → 12 cands ✅
- cands_commons('phishing email') → 11 cands ✅
- cands_commons('person working laptop home') → 6 cands ✅
- 但产线端到端跑配图仍 0/3（待验证清洗七条+视觉终判是否放行）

---

# 配图超时优化 2026-09-03（续）

## 问题
配图模块端到端跑 300 秒超时，永远跑不到 Commons 兜底。A0+A1 阶段就把时间预算全部吃光。

## 根因链路定位

用分段计时逐级定位：A0 抓头条来源页只要 1 秒（robots 0.2s + get_text 0.8s，但 0 张图）；卡在 **A1 豆包搜索后的页面抓取**。

豆包搜索本身 1.5 秒返回 8 个 URL（很快），但搜回来的 URL 全是未配选择器的域名（geewandou.com / worktile.com / www.sohu.com）或被 robots 拦的头条 group 页（m.toutiao.com Disallow /group/）。

**致命问题**：`images_from_page` 对每个 URL 先走 robots.txt 检查（超时 12s），然后才判断有没有配选择器——未配选择器的域名白等 12 秒超时后才 skip。8 个 URL × 12s = 96 秒，加上降级级1列表页盲碰返回 237 个候选每个抓 12s = 2844 秒，整个 A0+A1 阶段卡死。

## 六处修复

### 修复1：images_from_page 先查选择器再查 robots
`modules/illustrate.py` 的 `images_from_page()` 函数：未配选择器的域名直接 skip（0秒），不先等 robots.txt 超时。只有已配选择器的域名才花时间查 robots。

**改动**：把 site_selectors 检查移到 robots_allowed 调用之前，未配域直接 return [] 不走网络。

**效果**：A1 阶段从 96 秒+ 降到 3 秒。

### 修复2：A0+A1 加总超时预算
`illustrate.py` run() 函数开头加 `_t0_a0a1 = time.monotonic()` + `_a0a1_budget = cfg_i.get("a0a1_budget_sec", 60)`。A1 入口和降级级1循环都检查是否超预算，超了直接跳到 Commons 兜底。

config.yaml 新增 `a0a1_budget_sec: 60`。

### 修复3：fallback 列表页候选上限
`_fallback_list_discovery()` 去重后截断到 `max_fallback_candidates`（默认15），不再返回 237 个候选让逐个抓取卡死。

### 修复4：Commons img_url 优先 upload.wikimedia.org
`cands_commons()` 的 `img_url` 从 `info.get("thumburl") or info.get("url")` 改为 `info.get("url") or info.get("thumburl")`。

thumb.wikimedia.org 被 429 限流，upload.wikimedia.org 有时能下。

### 修复5：429 触发 curl HTTP/2 降级
`modules/fetcher.py`：
- `_COMMONS_HTTP2_HOSTS` 加入 `upload.wikimedia.org` 和 `thumb.wikimedia.org`（原来只有 `commons.wikimedia.org`）
- HTTP/2 降级触发条件从 `original.code != 403` 改为 `original.code not in (403, 429)`

### 修复6：config 超时全面收紧
- `doubao_search.timeout_sec`: 15→10
- `illustration.timeout_sec`: 20→12
- `illustration.max_retry`: 1→0（失败即放弃不重试）
- `stock_commons.fetch_interval_sec`: 1.5（新增，避免限流）
- `stock_commons.timeout_sec`: 15（新增）
- UA 加联系邮箱：`ops@toutiao-shoufa.tools`（Wikimedia 要求 UA 有联系邮箱才不限流）
- stock 源下载单独配 timeout 和 interval（`_download_and_accept` 里按 source_type 区分）

## 修复后效果

| 指标 | 修复前 | 修复后 |
|---|---|---|
| A0+A1 耗时 | 300s+ 超时 | 3s ✅ |
| fallback 候选数 | 237 个 | 15 个 ✅ |
| Commons 兜底到达 | 跑不到 | 能到达 ✅ |
| Commons 图片下载 | 403/429 限流 | 部分 429 仍限流 ❌ |
| 端到端配图结果 | 超时 0/3 | 151s 但 0/3（Commons 429 未解） |

## 未解决：Wikimedia IP 级 429 限流 + 广州机直连 TLS 超时

所有代码修复到位后，Commons API 搜索正常（10 候选/1.2s），但**图片下载全部 429**——upload.wikimedia.org 和 thumb.wikimedia.org 都被 Wikimedia 服务器 IP 级限流，curl HTTP/2 降级也拿到 429。

这不是代码问题，是服务器 IP 被 Wikimedia 限流。解法选项：
1. 走 8899 relay 中转下载（config 里已配 image_relay=8899，但需确认 relay 服务在跑）
2. 等 Wikimedia 限流恢复（通常几小时到一天）
3. 启用 Pexels 图库（config 里 disabled，需配 API key）
4. 副业类文章直接跳过配图（之前也是泛图，意义不大）

### 2026-09-04 补充：广州机直连 upload.wikimedia.org TLS 超时

从广州机（ssh -p 2222 ubuntu@127.0.0.1）curl upload.wikimedia.org 测试：
- DNS 解析正常（103.102.166.240）
- TCP 443 连接成功
- TLS 握手开始后 **15 秒无响应→超时**
- curl -v 显示 TLS Client Hello 发出后一直等

**结论**：广州机直连 Wikimedia 被墙或被 Wikimedia 服务器 TCP 级屏蔽，不是代码问题。

解法：
- 新加坡机可能直连能下（走 8899 relay 中转到广州）
- 或用 Pexels API（不依赖 Wikimedia）
- 或用本机已有的缓存图（第一篇的 3 张图已经下好在本机）

**不要尝试从广州机直接下 Wikimedia 图片**——TLS 会超时，浪费时间。

## 教训

1. **robots 检查顺序**：images_from_page 应先查 site_selectors（内存操作0秒），再查 robots（网络操作12秒）。未配选择器的域名查 robots 是纯浪费——不管 robots 让不让，没选择器就抓不到图。
2. **降级路径要有候选数上限**：fallback_list_discovery 从列表页抓 237 个链接不可控，必须截断。
3. **时间预算保护**：瀑布式多级降级流程（A0→A1→降级1→降级2.5→降级3）必须在最外层加总时间预算，否则任何一级卡住都会让后面的兜底永远跑不到。
4. **Wikimedia 限流是 IP 级**：换 UA / 换 HTTP 版本 / 加间隔 都可能不够，最终可能需要走 relay 中转或换 IP。