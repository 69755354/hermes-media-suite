---
name: xingtu-backend-screenshot
description: Use when 截星图后台某条作品的数据行. Playwright+mac.sh。
---

# 星图达人后台截图（Mac / Playwright WebKit）

触发：用户要「星图后台某条作品的截图 / 那条 7 万多的数据 / 作品明细行」。数据不在 CSV，只能从登录态后台抓。

## 硬约束
- 传输只能走 `/home/ubuntu/ops/mac.sh '<单行命令>'`（三层 ssh）。**命令内禁双引号**，shell 脚本一律 base64 传输：`echo <b64> | base64 -d > /tmp/x.py`。
- 单次输出上限约 16–18 万字符 → 大图先缩到宽 ≤1400 再回传；base64 用 `base64 -i f -o f.b64`（**macOS 没有 `base64 -w0`**）后 `split -b 90000`，逐块 `cat` 回新加坡机再 `cat part.* | base64 -d`，最后 **md5 比对**两端一致才算成功。
- Playwright 解释器：`/Users/<MAC_USER>/publish-worker/.venv/bin/python`（系统 python3 没有 playwright）。profile：`/Users/<MAC_USER>/publish-worker/profiles/douyin-webkit`，`launch_persistent_context(..., headless=True)`。禁止扫码；未登录直接报 BLOCKED。
- 单浏览器进程，用完 `ctx.close()`，收工核对 `ps aux | grep -c '[p]laywright'` 为 0。

## ⚠️ 最大坑：作品明细的指标行是内层横向滚动容器
作品卡片的 6 个指标（视频评估/有效播放量/自然转化量/预估自然流量收益/投放流量收益/已结算收益）在 `.item-list` / `.star-ad-video-item` 里，**内容 966px 塞在 816px 的盒子里**，默认把最后两列（投放流量收益、已结算收益）裁掉。表现：截图上标签只剩「投放流」，最后两列整列消失 —— 此时 `getBoundingClientRect()` 仍返回完整坐标（1000–1110），按 rect 裁剪也没用，因为像素被 overflow 裁掉。
修复（仅内存改样式，不改文件）：把容器撑宽再截：
```js
document.querySelectorAll('.item-list,.star-ad-video-item,.task-item-list').forEach(function(x){
  if(x.clientWidth<1000){ x.style.width='1040px'; x.style.maxWidth='1040px'; }
  x.style.overflow='visible';
});
```
**不要**沿祖先链批量设 `overflow:visible`（会把整页布局顶下去，卡片跑到 y>2000，截图报 Clipped area is outside image）。截完必须再 `scrollIntoView({block:'center'})` 并复查 rect 的 y 仍在视口内。

## 可复用流程
1. 不能直接 deep-link 进任务详情（会 302 回首页），必须走 UI：`/sup/creator` → `/sup/creator/star-ad-unite` → 点 `a[href="/sup/user/task"]` → 在任务行里点「查看详情」（**会开新标签页**，用 `ctx.expect_page()`）。
2. 详情页数据是异步的，先轮询等就绪：标「有效播放量」的 `.indicator` ≥5 且 `.el-pager li` ≥5，再动手。
3. 找目标行：翻页（`.el-pager li` 点页码，10 条/页）后逐卡片读指标，用数值或标题前缀匹配。大量作品时目标常在最后一页（最旧）。
4. 取值（label/value 成对，别用 innerText 顺序猜，会错位）：
```js
[...card.querySelectorAll('.indicator')].forEach(x=>{
  const lab=x.querySelector('.indicator-label').innerText.trim();
  const val=x.querySelector('.indicator-value').innerText.trim();
});
```
5. 标红框：用绝对定位 `div`（`position:fixed;pointer-events:none;border:5px solid red`）盖在卡片 rect 上；**不要**用 `card.style.outline`（卡片常比可视内容窄，outline 会切过指标）。
6. 截图 `pg.screenshot(path, clip={...})` + `device_scale_factor=2`；回传前 `sips -Z 1400 -s format png in.png --out out.png`（要 JPEG 用 `-s format jpeg -s formatOptions 70`）。
7. 落地后**看图核对逐字数字**再回报 —— 卡片上的数字常与本地 xlsx/任务书口径不同（例：任务书写「投放流量收益 ￥49.22」，页面实际 ￥161.75），以页面为准并如实说明差异。

## 批量取数出表（作品级有效播放/分成）——老板表就用这套

目的：把每个任务下每条作品卡的「有效播放量 / 投放流量收益 / 已结算收益」取成表。

**铁律**
1. **用现成标签页**：从 `ctx.pages` 里挑已在星图域的那一页复用；禁止一任务一新页（用户当场骂过「一直打，一直打」）。任务行里点「查看详情」开的新页用完即关。
2. **禁止 deep-link**：直接 goto `/sup/creator/star-ad-unite/detail/...` 会 302 回首页；必须 `/sup/creator` → `/sup/creator/star-ad-unite` → 点 `a[href="/sup/user/task"]` → 任务行「查看详情」。
3. **禁止用 innerText 顺序猜值**：卡片文字流是「标签\n值」，遇到空值就整体错位，结果全是 0（2026-10-19 踩过，整张表分成判成 0）。一律取 `.indicator` 里的 `.indicator-label` + `.indicator-value` 成对读。

**取值脚本（在详情页执行）**
```js
() => [...document.querySelectorAll('.star-ad-video-item, .item-list > div')].map(card => {
  const m = {};
  card.querySelectorAll('.indicator').forEach(x => {
    const k = x.querySelector('.indicator-label')?.innerText.trim();
    const v = x.querySelector('.indicator-value')?.innerText.trim();
    if (k) m[k] = v;
  });
  const t = card.innerText.split('\n').map(s=>s.trim()).filter(Boolean);
  return { title: t[0], date: t.find(x=>/上传$/.test(x)), status: t.find(x=>/计费|公示|结算|驳回/.test(x)), metrics: m };
});
```
字段名就是页面中文：`视频评估`、`有效播放量`、`自然转化量`、`预估自然流量收益`、`投放流量收益`、`已结算收益`。

**翻页（关键）**：**必须点 `.btn-next`**，每页 10 条。`document.querySelectorAll('.el-pager li')` 里点页码**不会换数据**（Vue 分页不生效），只会把同一页重复采 5 遍 —— 表现是卡片数虚高、同一标题重复、合计比任务头部多。正确写法：
```js
const n=document.querySelector('.btn-next');
if(!n || n.disabled || n.classList.contains('is-disabled')) return false; // 到底
n.click(); return true;
```
每页采完 sleep 2s 再点下一页；另用「本页首条标题+有效播放」做指纹，指纹没变就是没翻动，立即停。

**必做校验**：单个任务所有卡片的「已结算收益」加总，必须**等于任务详情头部的「已结算收益」**（例：248.3 / 0.31 / 0.18）。不等就是漏页或重复采，重跑该任务，不得直接出表。

**跨任务不去重（按标题去重是错的）**：同一条标题文案会被多条不同作品复用（实测 7 组重名，例：「碎片时间看剧就能攒火龙币…」在任务0 是 1069 播放/0.71 元，在任务2 是 143 播放/0.31 元 —— 是两条不同视频）。每条任务记录各算一行，按标题去重会把合计从 248.79 压成 248.48。
**标题不能当唯一键**：匹配抖音行时只用来「借用」播放量等展示列，一条抖音行只认领一条星图记录；重名时按播放量最接近的那条配。对不上就留空，不得合并金额。

**任务来源**：`/sup/creator/user/task` → tabs 全部/待接收/进行中/已完成/已取消；先看「进行中」，已完成/已取消一般无「查看详情」按钮（0 个）。

**口径**：作品级分成 = `已结算收益`，不是任务头部那个「预估总收益」；合计只加作品级，禁止拿任务总额充合计（2026-10-19 用户当场否掉）。

## 抖音 ↔ 星图 按作品 ID 对齐（唯一正确口径）

**星图 `item_id` 就是抖音 `aweme_id`**（实测 55/55 全命中，19 位同一串）。禁止再拿标题当主键。

抖音侧取 ID（在已登录 creator.douyin.com 的现成标签页里 fetch，不用开新页）：
```js
// 分页：max_cursor 翻到 has_more=false
fetch('/web/api/media/aweme/post/?count=50&max_cursor=0&aid=1128&device_platform=web',{credentials:'include'})
// 取 aweme_list[].aweme_id / desc / create_time / statistics.play_count
```
该接口返回 `aweme_list / has_more / max_cursor / total`，一次 50 条。

星图侧：`out/xingtu/星图数据_YYYYMMDD.json` 的 `items[]` 已带 `item_id / item_name / valid_play / publish_time / task_id`；金额仍需卡片补，卡片没有 ID，用 `(标题去空白, 有效播放量)` 回填到 item（重名作品靠播放量区分，实测 75 个键对 76 张卡）。

合并顺序：卡片(标题+vv)→星图 item_id→抖音 aweme_id。这样标题重名也不会串行。

口径校验：星图 `valid_play` 合计 **144335**、卡片已结算合计 **248.79**（= 248.3+0.31+0.18），两者不相等就是没对齐。

## 出老板表（星图 + 抖音合并）

列固定 8 列：`抖音号｜作品名称｜发布时间｜审核状态｜播放量｜星图有效播放｜分成(元)｜预估收益(元)`，按播放量降序，末行合计，单 sheet。

合并规则：
- 星图标题按 `re.sub(r'\s+','',title)` 全串匹配抖音作品名；匹配不上再用「去 # 话题、去标点、前 14 字」兜底。
- 一条抖音作品只认领一条星图记录（按 id 标记已用），剩余星图记录单独追加成行。
- 空格口径要能当场解释：星图列空＝该号星图取不到（webkit 无调试端口）或标题未匹配；播放量空＝星图有、抖音列表里没有（已删/不在列表）。
- 「预估收益」= `预估自然流量收益 + 投放流量收益`；「分成」= `已结算收益`。

Windows 侧取数通道（1.2.36 远程 /exec）：CDP `http://127.0.0.1:9224` → `connect_over_cdp` → 取 `ctx.pages` 里已在 xingtu.cn 的那页复用；脚本用 `/write`（base64）+ `/exec`（`argv`，≤120s）下发，一次跑 1–2 个任务，避免超时。

## 没有单独的作品数据面板
作品卡片里没有任何 button/a（`[...card.querySelectorAll('button,a')]` 为空），点不进去。卡片本身就是该作品的数据面板；需要放大读数字就再截一张指标带（x≈380→右边缘，y 取 `.indicator` 的 top/bottom ±16）。
