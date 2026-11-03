### 爆款正文拆解方法论（搜→拆→对比→改）

用户发来爆款文章链接时，不要只抓数据——必须读正文、拆结构、对比自己的文章找差距、再据此重写。这是三点法（搜→拆→写）在头条文章正文层面的具体执行。

**完整流程：**
1. `python3 scripts/toutiao_metrics.py <URL>` 抓展现量/阅读量/收藏/评论——先确认这篇确实有量
2. 用 Playwright 提取正文内容（见下方 Playwright 提取正文段）——头条短链 jina reader 返回 400，必须用 Playwright
3. 拆5个维度：①开头钩子（前三行怎么钩人）②段落节奏（长短/留白）③金句密度（每几段一个截屏级句子）④情绪曲线（告知式还是人的困境式）⑤互动钩子（结尾问的是具体问题还是泛泛「你怎么看」）
4. 对照自己已发/待发的文章逐维找差距——不是笼统说「不够好」，是具体到「开头是告知式，爆款是场景+数字暴击」
5. 把5条差距写进codex任务书的「爆款拆解结论」段，让codex重写时逐条落地

**派codex重写时任务书必须包含：** 原文全文（事实来源，所有数字保留）、爆款拆解的5条改进方向（每条带具体前/后对比）、字数目标区间、硬约束（禁编造/禁内部术语/人称统一/禁编号小标题/纯文本输出）。

### ⚠️ Playwright 展现量抓取能力（2026-09-07 实测验证）

Playwright（真实浏览器）打开头条文章页，可从 HTML 源码提取完整数据：
- `readCount` = 阅读量
- `showCount` = 展现量
- `commentCount` = 评论数
- `diggCount` = 点赞数
- `shareCount` = 分享数
- `repinCount` = 收藏数

数据藏在 HTML 中 URL 编码的 JS 变量里，curl/jina reader 抓不到（需执行 JS 后渲染），Playwright 能拿到。侧边栏「TA的热门作品」的阅读量也在 HTML 的 `<span>588阅读</span>` 中。

**可用脚本**: `scripts/toutiao_metrics.py`（本skill目录下），用法：`python3 scripts/toutiao_metrics.py <URL或group_id> [url2] [url3]`，支持批量。

**用途**：①验证范文有没有量，值不值得对标；②查自己发出去的文章展现量，校准选题方向。

**提取文章正文（不只是指标）**：toutiao_metrics.py 的 Playwright 框架可以扩展用于提取文章正文——头条短链（m.toutiao.com/is/xxx）jina reader 返回 HTTP 400，web_extract（searxng 后端）也不支持头条页面。用 Playwright 打开文章页后执行 `document.querySelector('article')?.innerText || document.body.innerText` 即可拿到正文。完整脚本示例见 `references/toutiao-article-extraction.md` Playwright 提取正文节。

