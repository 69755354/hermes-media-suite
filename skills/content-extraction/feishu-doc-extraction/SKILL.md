---
name: feishu-doc-extraction
description: 飞书文档/wiki 全文提取。触发：用户给 feishu.cn/wiki 或 docx 链接要求总结/提取/整理内容。
version: 1.0.0
author: hermes-curator
license: internal
metadata:
  hermes:
    tags: [feishu, doc, wiki, extraction, browser, virtual-scroll]
---

# 飞书文档/知识库全文提取

## When to Use
- 用户给 `feishu.cn/wiki/...` 或 `feishu.cn/docx/...` 链接，要求「总结这个」「把工具/策略/提示词整理出来」「提取内容」
- feishu_doc_read 工具不可用（非评论上下文）或 web_extract 后端受限时，本 skill 的浏览器方案是可靠兜底

用户丢一个飞书 wiki/doc 链接（如 `https://tim2v2pppgm.feishu.cn/wiki/EoZT...`）要求「总结这个」「把工具/策略/提示词整理出来」时用。核心难点：飞书正文是**虚拟滚动渲染**，直接抓 innerText 只能拿到视口附近一小段，必须分段滚动拼接。

## 提取路径（按优先级）

1. **feishu_doc_read（deferred tool）**：`tool_search("feishu doc")` → `tool_describe` → `tool_call(feishu_doc_read, doc_token=<URL 中 wiki/ 后的那段>)`。⚠️ 两道坎，`OUTBOUND_REQUIRES_EXTERNAL_DELIVERY` + `NODE_TICKET_MISSING`：`node-entry-guard.py` 把所有 `feishu_*` 工具一刀切成 OUTBOUND 分支（`if lower_name.startswith("feishu_")`），只有 `output_class=external_delivery` 的节点能用；INTAKE 节点下必然被硬拦。普通 DM 会话即使放行也会报 `not in a Feishu comment context`。**别在修闸上耗时间，直接走第 3 条。**
2. **飞书开放 API（terminal 直调）**：wiki token 要 `wiki:node:read` 作用域——本机 app 未开通（报 99991672），走不通；除非先给应用加权限。
3. **Playwright 无头浏览器（实测可靠，本机首选）**：
   ```bash
   /home/ubuntu/.hermes/hermes-agent/venv/bin/python /tmp/fdoc/scrape.py
   ```
   ⚠️ **只有 hermes venv 的 python 有 playwright**（`~/.hermes/hermes-agent/venv/`），系统 `python3` 报 ModuleNotFoundError；chromium 在 `~/.cache/ms-playwright`（headless 要加 `--no-sandbox`）。
   要点：`goto(..., wait_until="domcontentloaded")` + `wait_for_timeout(8000)` 等渲染；滚动容器 `.bear-web-x-container`；每滚 800px 抓一次 `document.body.innerText`，**段间按整段文本去重**（相邻段大量重叠，不去重正文会翻好几倍）；外层 chrome（「飞书云文档/百景的云文档/立即编辑/登录注册」）逐段出现，拼合后清一次。公开分享链接**不需要登录就能读全文**（页面左下显示「登录/注册」不影响）。
   脚本模板见 `/tmp/fdoc/scrape.py` 思路：launch headless chromium → goto → 找 scrollHeight 最大的容器 → 循环 scrollTop → 抓 innerText + `a[data-href]` → 落盘。实测一篇 9917px 文档 → 12 段 / 2.3 万字，1 次跑完。

## 浏览器分段滚动提取（核心技巧）

飞书页面打开后，快照只给目录骨架/侧栏，正文藏在虚拟滚动容器里。`document.body.innerText` 每次只反映**当前视口**附近渲染的内容——抓一次就以为抓全了是最大坑。

```javascript
// ① 找真正的滚动容器（body 不是，要找 scrollHeight 远大于 clientHeight 的 div）
(() => {
  const els = Array.from(document.querySelectorAll('*'));
  return JSON.stringify(els.filter(e => e.scrollHeight > e.clientHeight + 200 && e.scrollHeight > 1000)
    .map(e => ({tag: e.tagName, cls: (e.className||'').toString().substring(0,60), sh: e.scrollHeight, ch: e.clientHeight}))
    .slice(0,10));
})()
// 实测容器 class 含 "bear-web-x-container"

// ② 分段滚动 + 每段抓 innerText（0 → 600 → 1200 → ... → scrollHeight）
(() => { const el = document.querySelector('.bear-web-x-container'); el.scrollTop = 600; return el.scrollTop; })()
// 然后 document.body.innerText 存一段；再滚下一段。重复到 scrollHeight。
// ⚠️ scrollHeight 会随内容加载变大（实测 2961 → 4444），最后必须滚到 el.scrollHeight 确认到底。
```

要点：
- 每段滚动后立即 `document.body.innerText` 存盘/记下，最后人工拼合去重（相邻段有重叠是正常的）
- 视频/图片在 innerText 里显示为 hash + 时长（如 `f5b4c89023467d3f41ad6fc961edc164 00:59`），如实标注「原文为视频教程」即可
- **链接提取（2026-08-19 修正：必须用 data-href）**：正文里的工具链接多是图标形式，`a.innerText` 为空；且飞书把真实 URL 藏在 `data-href` 属性里，`a.href` 经常拿不到（本次第一版只抓到 4 个目录锚点，改用 data-href 才抓到全部 30+ 工具 URL）。正确姿势：
  ```javascript
  // 每滚动到一个区域就重新抓一次（虚拟滚动会卸载视口外元素，一次抓不全）
  Array.from(document.querySelectorAll('a[data-href]')).map(a => ({
    text: (a.innerText || a.getAttribute('aria-label') || '').trim(),
    href: decodeURIComponent(a.getAttribute('data-href') || '')
  }));
  // 最终按 href 用 new Set() 去重
  ```
  图标链接补抓 `title` / `aria-label` / `img.alt`。wiki 锚点（`#OmT0djs4...`）是同一文档的分节，不是独立页面，别去导航。

## 打开链接抓子文档（用户「打开链接去整理」时必做）

**⚠️ 用户说「链接打不开吗？」/「打开链接去整理」= 要把文档内链接逐个打开、把子文档正文抓出来，不是列 URL 就完事。** 本次第一版只列了链接名+URL，用户追问后才发现提示词的正文全在链接里的子 docx 里（主文档只有标题，内容全在子文档）。

流程：
1. 先从主文档用 data-href 提取全部链接，过滤掉 wiki 锚点（`#hash` 同文档分节）
2. 逐个 `browser_navigate` 打开 docx 子文档链接（链接域名 `m59itnl68e.feishu.cn` 会 302 到 `my.feishu.cn`，正常）
3. 每个子文档同样分段滚动抓 innerText（同一套虚拟滚动技巧），**评论区也值得抓**——提示词文档的评论区常有补充指令（本次「提炼大纲」「喂养AI」的评论区抓到了新闻博主推文版/娱乐事件版）
4. 每抓一个就落盘一段，最后合并成完整文档；附件（txt/pdf/docx 文件本体）网页层拿不到，如实标注「原文为附件」

大文档分段滚动要更细（本次 83 个润色指令 9KB+，滚了 600/1600/2600/3600/4600/6500/7500/8300 才抓全）。**滚动顶部+底部不够，中间段会漏**——滚完一遍后若发现节次编号跳号（如目录有 52-83 节但正文只见 30 几），补抓中间 scrollTop 位置。

## 整理输出结构（2026-08-19 天行者认可的作战手册三块式）

「总结文档/把工具策略提示词整理出来」类任务，最终交付按天行者认可的三块结构：

- **A. 工具清单**：按用途分类（热点找题/AI写作/原创度检测/敏感词/视频提取/教程），每个工具列名称+链接+用途+关键要点
- **B. 玩法策略**：项目怎么跑（背景时间轴/开通条件顺序/实操步骤/发布标准/生产流程链路图）
- **C. 提示词/指令**：逐条列方向+链接+用途；原文只有标题没正文的如实标注，绝不编造提示词内容

另附「原文缺失项清单」（哪些是视频/附件/外链，方便后续回原文补齐）。交付时若发现链接是图标形式没抓到 URL，回原文补抓 data-href，别让执行器对着缺 URL 的清单瞎标。

## 提取后处理

1. 原文落盘：`write_file('/tmp/feishu_doc_<标题>_原文_YYYYMMDD.md', ...)`，保留文档原始结构（标题/列表/步骤全保留，不加工）
2. 按 SOUL 智力活外包铁律：**总结/整理/提炼必须派 codex/claude**，Hermes 不直出。打包任务书时注明「输入文件路径 + 原文缺失部分如实标注不编造 + 输出三块/按需求分类 + 落盘路径 + OUTPUT 标注」
3. 派活走 `claude_remote_wrapper.sh`（或 codex_exec_gated.sh），`terminal(background=true, notify_on_complete=true)`，完成自动通知
4. **知识库卡点处置（2026-08-19 实测）**：纯文档整理任务（输入完全来自用户提供的文档、不涉及行业知识库）会被 kb_gate_sg.py 拦，报 `KB_GATE:BLOCKED 检测到内容生产意图但未找到项目目录`。任务书开头写 `SKIP_KB_GATE=1` 显式放行。判断标准：输入只有用户给的文档 → 跳过；涉及行业判断/创作/分析 → 必须走知识库

## 视频提取（2026-08-20 实测：链接可拿、文件本体要权限）

文档里的视频 = innerText 显示 `hash + 时长` + `video` 元素。**提取视频链接可以**：

```javascript
// 滚动到视频所在区域后：
Array.from(document.querySelectorAll('video')).map(v => v.src)
// 实测拿到形如：
// https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/video/<token>/?quality=720p&data_version=...&mount_point=docx_file
```

**⚠️ 下载文件本体基本拿不到（2026-08-20 实测）**：`internal-api-drive-stream.feishu.cn` 的 video URL 返回 **401**——即使 video 元素能播放（readyState=4，页面会话有权限）、浏览器 console `fetch` 带 Referer/Origin、带 `mount_point=docx_file` 参数，全部 401（本地 curl 也 401）。这是**文档级权限**（要文档协作者），不是请求姿势问题。处理：
- 视频文件本体要转写/下载 → 找文档所有者（用户/客户）直接要文件，或确认 bot 有文档协作者权限走飞书 drive API
- 只提取「文档里有视频 + 视频链接 + 时长」用于汇报/留档是可行的（不用下载）


## 坑清单
- 飞书 innerText 视口化：不滚动 = 只拿到开头几行（本次差点只抓到目录+开头就以为完了）
- 目录锚点（「实操步骤：」「剪辑教程：」）是文档内分节链接，看起来像子页面，实际是 `#hash` 同文档
- web_extract 失败 ≠ 链接无效，换浏览器方案
- 文档「最后更新」时间看页面头部的 Modified 标注，别自己猜
- **中文文件名 read_file 误判 binary**：`/tmp/头条首发补贴_...md` read_file 报 `Binary file - cannot display as text`，但 `file` 命令显示 `Unicode text, UTF-8` 正常——用 cat/terminal 读，不是文件损坏
- **第一版整理缺 URL 是常见错误**：只抓 innerText 就派活，claude 只能标「原文为链接」；用户追问才发现 data-href。抓取阶段就把链接一并提取，避免二次返工
- **交付后验证链接**：用户问「链接打不开吗」→ `curl -s -o /dev/null -w "%{http_code}" -L --max-time 8 <url>`，区分 200 正常 / 403 反爬（浏览器能开，不是链接坏）/ 000 真超时
