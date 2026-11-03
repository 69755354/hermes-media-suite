---
name: feishu-document-extraction
description: 抓取飞书 wiki/docx 文档全文与链接。触发：总结飞书文档/链接打不开/内容抓不全。
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [feishu, docx, wiki, extraction, browser]
    category: content-extraction
---

# 飞书 wiki/docx 文档抓取

抓取飞书 wiki 页面和 docx 文档的正文 + 链接。**核心教训（2026-08-19 实测）：飞书把链接 URL 藏在 `data-href` 属性里，`innerText` 只显示文字不显示 URL——只抓 innerText 会漏掉所有工具/资料链接，被用户追问「链接打不开吗」。**

## 触发
- 用户给飞书 wiki/docx 链接要求「总结/整理/把链接打开」
- 用户问「链接打不开吗」「内容是不是抓全了」
- 需要把飞书文档里的外链资源（工具站/资料文档）逐个打开取内容

## 步骤

### 1. 打开文档
`browser_navigate(url)`。飞书 wiki 公开分享链接可匿名访问（会显示 Log In or Sign Up 但内容可见）。docx 链接 `m59itnl68e.feishu.cn/docx/<token>` 会自动重定向到 `my.feishu.cn`，可正常读。

### 2. 抓正文（虚拟滚动分段抓）
**飞书是虚拟滚动，只渲染视口附近内容——必须分段滚动 + 每段抓 innerText。**

滚动容器选择（按优先级）：
```js
// 找滚动容器
(() => { const els = Array.from(document.querySelectorAll('*')); const scrollers = els.filter(e => e.scrollHeight > e.clientHeight + 200 && e.scrollHeight > 1000).map(e => ({tag: e.tagName, cls: (e.className||'').toString().substring(0,60), sh: e.scrollHeight, ch: e.clientHeight})).slice(0,5); return JSON.stringify(scrollers); })()
// 已知容器类：.bear-web-x-container
(() => { const el = document.querySelector('.bear-web-x-container'); el.scrollTop = 800; return el.scrollTop; })()
```

滚动节奏：0 → 600 → 1200 → 1800 → 2400 → 2800 → 3600 → ... → scrollHeight。每段 `document.body.innerText.substring(0, N)` 抓内容。**注意：滚动容器在两次导航后可能不存在（页面加载失败），返回空时重新 browser_navigate。**

### 3. 抓链接（关键！data-href）
```js
(() => {
  const out = [];
  const all = document.querySelectorAll('a[data-href]');
  const seen = new Set();
  all.forEach(el => {
    const href = decodeURIComponent(el.getAttribute('data-href') || '');
    if (!href || href.startsWith('javascript')) return;
    const key = href;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({text: (el.innerText || '').trim().substring(0, 50), href: href.substring(0, 250)});
  });
  return JSON.stringify(out, null, 1);
})()
```
- **必须用 `a[data-href]` 选择器**——飞书把真实 URL 存在 data-href（URL 编码），href 属性可能是锚点或空
- 页面未加载完时返回空数组 → 先滚动（触发懒加载）再抓
- 抓到的飞书 docx 外链（m59itnl68e.feishu.cn/docx/...）就是子资料文档，需要的话逐个打开抓正文

### 4. 附件/视频识别
- 视频教程在 innerText 里显示为 `f5b4c89023467d3f41ad6fc961edc164 00:59` 这样的块 ID + 时长，无文字内容 → 标注「原文为视频教程」
- txt/文件附件（如「指令词合集.txt」）无下载链接暴露在 a 标签 → 标注「附件未下载」
- 表格内容：innerText 按行输出，保留结构即可

### 5. 落盘交付
- 原文 + 整理版分两个文件：`/tmp/<主题>_原文_<日期>.md` 和 `/tmp/<主题>_整理_<日期>.md`
- 整理版要求：工具清单含 URL、提示词正文完整、原文缺失项清单（哪些是视频/附件/未打开的链接）
- 交付用 MEDIA: 路径直接发文件（飞书可收 md 附件）

## 踩坑
1. **只抓 innerText 漏链接**：第一版整理「原文为链接，无 URL」被用户问「链接打不开吗」——必须 data-href 补抓。抓完链接后要主动验证几个关键 URL（curl -I 或打开）确认可访问
2. **read_file 中文文件名误判 binary**：`read_file` 对中文文件名 md 报 "Binary file"，用 `terminal cat` 读
3. **web_extract 后端不可用时**：`SearXNG is a search-only backend` 报错 → 直接 browser_navigate 抓
4. **飞书正文含大量错别字**（完法=宪法、领十=领土等 OCR 痕迹）：整理时保留原文但可标注，不要「修复」后当原文输出

## 验证
- 链接抓取数 vs 原文可见链接数一致
- 关键 URL 抽查可访问（200/浏览器可开，403/000 可能是反爬非失效）
