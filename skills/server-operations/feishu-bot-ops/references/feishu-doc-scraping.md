# 公开飞书 wiki/docx 全文抓取方法（2026-08-19 实测）

> 天行者「打开链接去整理」定案。用户给飞书 wiki 链接要求「总结/整理成文档」时，**必须把链接逐个打开，把里面的正文/提示词抓出来**，不能只抓 innerText 列个链接清单。第一次只给了 URL 清单被指正：「我的意思是打开链接去整理」。

## 关键坑 1：链接 URL 藏在 data-href，innerText 看不到

飞书把外链渲染成图标/卡片，文字层只显示链接文本，URL 在 `a[data-href]` 属性里（URL 编码）。只抓 innerText 会得到「原文为链接，无 URL」的错误结论。抓链接必须用 JS 读 data-href：

```js
(() => { const out = []; const all = document.querySelectorAll('a[data-href]'); const seen = new Set();
  all.forEach(el => { const href = decodeURIComponent(el.getAttribute('data-href') || '');
    if (!href || href.startsWith('javascript')) return; if (seen.has(href)) return; seen.add(href);
    out.push({text: (el.innerText || '').trim().substring(0, 50), href: href.substring(0, 250)}); });
  return JSON.stringify(out, null, 1); })()
```

- 先滚动到内容区再抓（虚拟滚动只渲染视口附近），或滚动到每段位置重复抓，合并去重
- 同页锚点（`#OmT0djs4...`）是目录跳转不是外链，过滤掉（`a[data-href]` 只抓 `http(s)` 开头的）

## 关键坑 2：正文虚拟滚动，document.body.innerText 只含视口内容

飞书正文在内部滚动容器（`.bear-web-x-container` 或 `[class*="container"]`），必须把容器 scrollTop 逐段推进再抓 innerText：

```js
(() => { const el = document.querySelector('.bear-web-x-container'); if (!el) return 'no container';
  el.scrollTop = 800; return '800: ' + el.scrollTop; })()
```

- 滚动间隔约 600-800px，每段抓一次 `document.body.innerText`，直到 `scrollTop == scrollHeight`（滚动到底）
- **别用 window.scrollTo**——飞书正文容器不是 window 滚动
- 判断容器：`document.querySelectorAll('*').filter(e => e.scrollHeight > e.clientHeight + 200 && e.scrollHeight > 1000)`，找 scrollHeight 最大的那个

## 关键坑 3：中文文件名 .md 会被 read_file 误判为 binary

`read_file` 对中文文件名 .md 返回 `Binary file - cannot display as text`，实际是 UTF-8 正常文本。用 `cat <文件>` 读，或 `file <文件>` 确认后 terminal 读取。抓取结果落盘建议用英文/拼音文件名（如 `toutiao-shoufa-project.md`）避免此坑。

## 关键坑 4：正文里的附件（txt/pdf/docx）在 DOM 里没有 href 可抓

`a[href]` 空、无 data-href——飞书附件是独立文件节点，网页层拿不到下载链接。遇到附件标注「附件未下载」，别假装抓到了。

## 完整工作流

1. `browser_navigate` 打开 wiki URL
2. 滚动容器抓 data-href 全量链接（标题+URL）
3. 逐个打开 docx 链接（`browser_navigate`）
4. 每个文档滚动容器逐段抓 innerText 直到底部
5. 落盘（英文文件名），用 cat 读回验证
6. 汇总成结构化文档（工具清单/策略/提示词分区）

**抓取顺序：先抓主文档，再抓每个链接，全部打开完才整理。** 不要先整理后补链接——这是用户「打开链接去整理」的核心要求。
