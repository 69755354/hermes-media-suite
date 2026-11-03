---
name: content-hunter
description: 内容捕手 (Content Hunter) - 短视频平台热门内容抓取机器人。支持小红书、抖音、快手、B站，可分批抓取热门内容并自动生成汇报。/Content Hunter - Hot content crawler for Xiaohongshu, Douyin, Kuaishou, Bilibili. Supports batch scraping and scheduled reporting.
version: 1.10.0
changelog: |
  - 1.10.0: 视觉模型更新(doubao-seed-1-6-vision退役→doubao-seed-2-0-mini-260215)。新endpoint: ep-20260710211910-f65h9。API调用模板更新为通用endpoint模式。重建接入点提醒加入"每2周过期"说明。
  - 1.9.0: 9.9抖音反爬突破(手机UA绕过验证码)。9.10反拆提示词铁律(用户多次纠正"不要自己编"+"是你自己编的还是实际视频的")。9.11新增SOCKS5代理+抖音单视频页访问工作流。references/kuaidaili-proxy-setup.md新增「八、抖音视频访问工作流」。
  - 1.7.0: 9.8铁律「只提取不编造」嵌入用户多次纠正。9.8加入ffmpeg帧提取+抖音快手画面获取分支。changelog去重修正。
  - 1.6.0: 9.6节「豆包视觉模型分析视频画面」完整内容更新到9.8。9.5头部加成本确认纪律(先问用户再调用)。
  - 1.4.0: agent-browser CDP模式修复方案(已验证可用): `--cdp 9222`连接systemd托管Chrome。9.1更新为CDP修复方案(旧诊断移至9.2)。8.5更新为CDP模式首选+Playwright备用。references/playwright-direct-scraping.md重写。
  - 1.3.0: 用Playwright替代agent-browser作为浏览器后端。新增scripts/browser_playwright.py脚本 + 故障排除章节
  - 1.2.0: 新增快手平台支持（浏览器自动化抓取热门内容）
  - 1.1.0: 支持定时多次抓取模式，每次创建独立任务文件夹，支持10次批量抓取
  - 1.0.0: 初始版本，支持单次抓取和晚8点汇报
---

# 内容捕手 / Content Hunter

## 概述 / Overview
持续刷小红书、抖音、快手、B站4个平台，每次每平台抓取40条热门内容并保存，晚上8点生成汇报。/Scrapes 4 platforms (Xiaohongshu, Douyin, Kuaishou, Bilibili), 40 items each, generates daily report at 8 PM.

---

## 一、浏览器标签管理 / Browser Tab Management

| 平台 / Platform | 网站URL / URL | 提取要素 / Data Fields | 备注 / Notes |
|------|---------|----------|------|
| 小红书 / Xiaohongshu | https://www.xiaohongshu.com | 标题、作者、点赞、收藏、评论、话题、内容总结 / Title, Author, Likes, Saves, Comments, Tags, Summary | 需要登录 / Login required |
| 抖音 / Douyin | https://www.douyin.com | 标题、作者、点赞、话题、内容总结 / Title, Author, Likes, Tags, Summary | 仅文本层面数据。看不到视频画面/角色/场景。如需画面分析需vision能力。 |
| 快手 / Kuaishou | https://www.kuaishou.com | 标题、作者、点赞、评论、话题、内容总结 / Title, Author, Likes, Comments, Tags, Summary | JS SPA，需浏览器全量渲染 / JS SPA, needs full browser render |
| B站 / Bilibili | https://www.bilibili.com | 标题、UP主、播放、弹幕、点赞、投币、收藏、字幕、内容总结 / Title, UP, Views, Danmaku, Likes, Coins, Favs, Subtitles, Summary | 尝试提取字幕 / Try extract subtitles |

**每次每个平台抓取40条热门内容 / Scrape 40 hot items per platform each time**

---

## 二、存储位置 / Storage Location

工作空间 / Workspace：`~/.openclaw/workspace/content-hunter/`

**重要：每次任务新建独立子文件夹，不覆盖历史数据！** / **Important: Create new subfolder for each task, NEVER overwrite historical data!**

```
content-hunter/
├── task-2026-03-11-0900/     # 任务1：按时间命名
│   ├── xiaohongshu.md
│   ├── douyin.md
│   ├── kuaishou.md
│   ├── bilibili.md
│   └── summary.md              # 本次任务汇报
├── task-2026-03-11-0930/     # 任务2
│   ├── xiaohongshu.md
│   ├── douyin.md
│   ├── kuaishou.md
│   ├── bilibili.md
│   └── summary.md
└── task-2026-03-11-2000/     # 晚8点汇报任务
    └── summary.md
```

**文件夹命名规则**：`task-YYYY-MM-DD-HHMM`

每次任务执行前：
1. 创建新文件夹：`task-$(date +%Y-%m-%d-%H%M)`
2. 在新文件夹中抓取和保存数据

---

## 三、记录格式 / Data Format

**重要：每条记录必须包含以下所有字段，缺一不可！** / **Important: Every record MUST have ALL these fields!**

### 小红书 / Xiaohongshu
```markdown
### 第X条 / Item #X
- 标题 / Title: xxx
- 作者 / Author: xxx
- 点赞 / Likes: xxx
- 收藏 / Saves: xxx
- 评论 / Comments: xxx
- 话题 / Tags: #xxx #xxx
- 内容总结 / Summary: 详细描述... (3-5句话 / 3-5 sentences)
```

### 抖音 / Douyin
```markdown
### 第X条 / Item #X
- 标题 / Title: xxx
- 作者 / Author: @xxx
- 点赞 / Likes: xxx
- 话题 / Tags: #xxx
- 内容总结 / Summary: 详细描述... (3-5句话 / 3-5 sentences)
```

### B站 / Bilibili
```markdown
### 第X条 / Item #X
- 标题 / Title: xxx
- UP主 / UP: xxx
- 播放 / Views: xxx
- 弹幕 / Danmaku: xxx
- 点赞 / Likes: xxx
- 投币 / Coins: xxx
- 收藏 / Favs: xxx
- 字幕 / Subtitles: 有/无 / Yes/No
- 内容总结 / Summary: 详细描述... (3-5句话 / 3-5 sentences)
```

### 快手 / Kuaishou
```markdown
### 第X条 / Item #X
- 标题 / Title: xxx
- 作者 / Author: xxx
- 点赞 / Likes: xxx
- 评论 / Comments: xxx
- 话题 / Tags: #xxx
- 内容总结 / Summary: 详细描述... (3-5句话 / 3-5 sentences)
```

---

## 四、执行流程 / Execution Flow

### 4.1 抓取要求 / Scraping Requirement
**每次每个平台抓取40条热门内容 / Scrape 40 hot items per platform each time**

### 4.2 初始化 / Initialization
1. **创建新任务文件夹** / Create new task folder：`mkdir -p ~/.openclaw/workspace/content-hunter/task-$(date +%Y-%m-%d-%H%M)/`
2. **先用 `scripts/browser_playwright.py` 测试 Playwright 是否可用** / Test if Playwright works first:
   ```bash
   python3 scripts/browser_playwright.py open "https://www.baidu.com"
   ```
   - 返回 `success: true` → Playwright 可用，后续用 Playwright 抓取
   - 返回 `success: false` → Playwright 也坏了，改走 web_search 降级方案
3. **Playwright 可用时**，直接用 Python 脚本抓取各平台（见 `references/playwright-direct-scraping.md` 中的代码模板）
4. **Playwright 不可用时**，降级到 web_search + web_extract 手动收集

### 4.3 循环执行 / Loop Execution
1. browser.snapshot() 获取页面内容 / Get page content
2. **必须提取所有字段！每条必须包含：标题、作者、热度、内容总结** / **Must extract ALL fields: title, author, views/likes, content summary**
3. **保存到当前任务文件夹** / Save to current task folder：`~/.openclaw/workspace/content-hunter/task-YYYY-MM-DD-HHMM/`
4. 等待3-5分钟 / Wait 3-5 minutes
5. **⚠️ 抓取过程中不发送任何进度消息到群聊，只保存数据** / **⚠️ Do NOT send any progress messages to group chats during scraping, only save data**
6. **汇报任务执行完毕后，停止抓取，等待下次定时任务** / **After report is sent, stop scraping and wait for next scheduled task**

### 4.4 汇报数据范围 / Report Data Scope
**重要：汇报时需要汇总当日所有抓取任务的数据，而非仅最近一次！** / **Important: Report must summarize ALL data from all tasks on that day, not just the latest one!**

汇报生成流程：
1. 读取当日所有task文件夹 / Read all task folders for the day
2. 合并各平台的抓取数据 / Merge data from all platforms
3. 去重后生成汇报 / Deduplicate and generate report
4. 汇总数据量 = 所有任务的累加总和 / Total = sum of all tasks

### 4.5 B站字幕提取 / Bilibili Subtitle Extraction
使用 bilibili-youtube-watcher 技能的 get_transcript.py 脚本提取字幕

---

## 五、晚上汇报 / Daily Report

### 汇报流程 / Report Flow
1. **读取数据**：从最新的task文件夹读取各平台md文件 / Read from latest task folder
2. 生成汇报 / Generate report
3. 发送汇报到群里 / Send report to group
4. **汇报后自动清理**：执行 `openclaw cron list` 找到所有内容捕手相关 cron（名称含"内容捕手"或"hunter"），逐一删除
5. **汇报后停止，等待下次任务** / After cleanup, stop and wait for next task

### 汇报内容 / Report Contents
1. 发原始数据文件链接 / Send raw data links
2. 热门内容TOP20（必须包含内容总结！）/ TOP 20 (MUST include content summary!)
   - 格式：按平台分类，每条包含：标题 | 热度 | 内容总结（1-2句话）
   - 例如：小红书暖心正能量：标题 → 热度 | 内容总结
   - Format: By platform, each item: Title | Views/Likes | Summary
3. 各平台趋势 + 整体趋势 / Platform trends + Overall trends
4. 推荐深度阅读 / Recommended deep reads
5. 呱呱感悟 / Guagua's thoughts
6. 关闭浏览器 / Close browser tabs

---

## 六、可用平台 / Supported Platforms

| 平台 / Platform | 状态 / Status |
|------|------|
| 小红书 / Xiaohongshu | ✅ |
| 抖音 / Douyin | ✅ |
| 快手 / Kuaishou | ✅ |
| B站 / Bilibili | ✅ |


---

## 七、使用方式 / Usage

### 7.1 触发方式 / How to Trigger

#### 方式一：手动对话 / Method 1: Manual Chat
- "帮我刷短视频平台" / "Scrape short video platforms"
- "抓取热门内容" / "Get trending content"
- "生成内容汇报" / "Generate content report"
- "启用内容捕手" / "Enable content hunter"

#### 方式二：定时任务 / Method 2: Cron Job (Recommended)
定时任务需要手动创建，参考以下配置：
- 抓取任务：每30分钟执行一次（9:00-20:00），静默执行不发群消息
- 汇报任务：晚上20:00执行，发送到小红书群

**⚠️ 绝对原则：内容捕手的所有任务和汇报，只允许发送到小红书呱呱群（<CHAT_ID>），禁止发送到任何其他群！**

### 7.2 可配置参数 / Configurable Parameters

| 参数 / Parameter | 说明 / Description | 默认值 / Default | 设置方式 / How to Set |
|------|------|--------|----------|
| 平台 / Platforms | 要抓取的平台 / Platforms to scrape | 全部4个 / All 4 | "只刷抖音" / "Only Douyin" |
| 数量 / Count | 每平台抓取条数 / Items per platform | 40条 / 40 | "每个刷30条" / "30 items each" |
| 汇报时间 / Report Time | 生成汇报的时间 / When to generate report | 20:00 / 8 PM | "晚上6点汇报" / "Report at 6 PM" |
| 存储路径 | 数据保存目录 | ~/workspace/content-hunter/task-YYYY-MM-DD-HHMM/ | 一般不改 |

### 7.3 实际存储示例 / Storage Example

**任务执行后，文件夹里有什么？**

例如：用户说"帮我刷短视频平台"
```
~/.openclaw/workspace/content-hunter/
└── task-2026-03-11-2100/           # 任务文件夹（按时间命名）
    ├── xiaohongshu.md              # 小红书数据（40条，每条含标题、作者、点赞、内容总结）
    ├── douyin.md                    # 抖音数据
    ├── kuaishou.md                  # 快手数据
    ├── bilibili.md                 # B站数据
    └── summary.md                  # 汇报文件
```

**每个md文件内容示例：**
```markdown
# 小红书热门内容

### 第1条
- 标题: 最近大家都在安装openclaw
- 作者: 美丽的一天
- 点赞: 1000
- 内容总结: 介绍OpenClaw的安装和使用方法...

### 第2条
- 标题: ...
...
（共40条 / 40 items total）
```

### 7.4 汇报内容示例 / Report Example

**晚上8点汇报长这样：**

```
📊 2026年3月11日 内容捕手汇报

🔥 热门内容TOP20
【小红书】
1. 标题 → 热度 | 内容总结
2. ...

【B站】
1. 标题 → 热度 | 内容总结
...

📈 各平台趋势总结
- 小红书：xxx
- 抖音：xxx
...

🎯 整体趋势
1. xxx
2. xxx

📖 推荐深度阅读
- xxx

🐸 呱呱感悟
xxx
```

### 7.5 对话示例 / Chat Examples

```
用户A：帮我刷短视频平台
→ AI：好的，启动内容捕手，默认抓取4个平台，每平台20条
/User A: Scrape video platforms
→ AI: OK, starting Content Hunter, 4 platforms, 20 items each

用户B：我只刷抖音和B站，每个刷30条
→ AI：好的，只抓取抖音和B站，每平台30条
/User B: Only Douyin and Bilibili, 30 each
→ AI: OK, Douyin + Bilibili, 30 items each

用户C：每天早上9点开始抓取，晚上6点汇报
→ AI：好的，设置抓取时间为9:00-20:00，汇报时间为18:00
/User C: Start at 9 AM, report at 6 PM
→ AI: OK, scraping 9 AM - 8 PM, report at 6 PM

用户D：现在帮我抓一次
→ AI：好的，马上抓取
/User D: Scrape now
→ AI: OK, scraping now

用户E：今天的热门内容有哪些？
→ AI：读取已有数据，生成汇报
/User E: What's trending today?
→ AI: Reading existing data, generating report
```

### 7.4 注意事项 / Notes
- 定时任务可能因Gateway重启而丢失，需定期检查 / Cron may be lost on Gateway restart
- 抓取过程中请勿关闭浏览器 / Don't close browser during scraping
- 建议保持浏览器标签页稳定 / Keep browser tabs stable

---

## 八、依赖 / Dependencies

### 8.1 依赖的Skill / Required Skills
| Skill | 用途 / Purpose |
|-------|------|
| bilibili-youtube-watcher | 提取B站视频字幕 / Extract Bilibili subtitles |

### 8.2 依赖的工具 / Required Tools
| 工具 / Tool | 用途 / Purpose |
|------|------|
| playwright (Python) | 浏览器自动化抓取 / Browser automation（替代agent-browser） |
| yt-dlp | 视频字幕提取 / Video subtitle extraction |

### 8.3 爬虫策略参考
| 技能 | 用途 / Purpose |
|-------|------|
| scrapling-scraping-strategy | Scrapling替代方案：绕过Cloudflare + 轻量HTTP爬取（B站/百度），用于browser不可用时 |
| Scrapling StealthyFetcher | 可截图验证页面存活（已验证抖音截图），但无法获取JS渲染内容（抖音/快手/小红书）。B站HTTP直连即可取全文。 |

### 8.4 前置要求 / Prerequisites
- Python playwright已安装 / Playwright installed：`pip install playwright`
- Chromium浏览器 / Chromium browser：通过Playwright或系统自带
- bilibili-youtube-watcher技能已安装 / bilibili-youtube-watcher skill installed

### 8.5 浏览器后端方案

**当前首选：CDP 模式** — 通过 systemd 服务保持 Chrome 运行，agent-browser `--cdp 9222` 连接。详见 `references/playwright-direct-scraping.md` 头部的完整修复方案。

**备用：Playwright 脚本** — `scripts/browser_playwright.py`，不依赖 agent-browser 服务。

**命令参考：**
```bash
# CDP 模式（首选）
agent-browser --cdp 9222 open <url>
agent-browser --cdp 9222 snapshot <url>

# Playwright（备用）
python3 scripts/browser_playwright.py snapshot <url>
```

---

## 九、故障排除 / Troubleshooting

### 9.1 CDP 模式修复方案（2026-07-06 ✅ → 2026-07-18 更新）

**状态更新：** agent-browser 自身启动 Chrome 的路径有 bug（全版本超时），但 `--cdp 9222` 连接手动启动的 Chrome 模式已验证完全正常。

**2026-07-18 新增：CDP WebSocket 连接修复** — 手动启动 Chrome 时必须加 `--remote-allow-origins=*` 参数，否则 Python websocket 连接会被 Chrome 的 CORS 策略以 403 拒绝。

**正确启动命令：**
```bash
chromium-browser --headless=new --no-sandbox --disable-dev-shm-usage \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --user-data-dir=/tmp/chrome-cdp-data \
  --disable-gpu --lang=zh-CN &
```

**验证 CDP WebSocket 可用性：**
```bash
python3 -c "
import requests, json
cdp = 'http://127.0.0.1:9222'
tab = requests.put(f'{cdp}/json/new', timeout=10).json()
print('CDP WebSocket OK:', tab['webSocketDebuggerUrl'][:50])
"
```

**一行快速验证：**
```bash
agent-browser --cdp 9222 open "https://www.baidu.com"
```
返回 ✅ → CDP 模式可用。详见 `references/playwright-direct-scraping.md` 头部（完整修复方案：systemd 服务 + Hermes config + agent-browser PATH）。

**Playwright 脚本**（`scripts/browser_playwright.py`）仍保留作为备用方案。

### 9.2 浏览器工具超时（旧版诊断 — browser_navigate 不响应）

**现象：** 所有 `browser_navigate` 调用均超时（包括百度等简单页面）

**诊断步骤：**

1. **检查Chromium能否直接启动**
   ```
   timeout 10 chromium-browser --headless=new --no-sandbox --disable-dev-shm-usage --dump-dom https://www.baidu.com 2>/dev/null | head -5
   ```
   - 能返回HTML → Chromium本身正常，问题在agent-browser
   - 不能返回 → 系统Chromium坏了，需重装

2. **检查agent-browser进程状态**
   ```
   ps aux | grep -E "agent-browser|chrome.*headless" | grep -v grep
   ```
   - 留意 `<defunct>`（僵尸）进程，说明之前挂了
   - 多个Chrome实例残留说明agent-browser反复启动Chrome但连接不上

3. **测试agent-browser二进制**
   ```
   timeout 15 /home/ubuntu/.hermes/hermes-agent/node_modules/agent-browser/bin/agent-browser-linux-x64 --session test_session --json open "https://www.baidu.com"
   ```
   - 超时 → agent-browser二进制卡死，需重启

**恢复操作：**
```
# 杀掉所有agent-browser和chrome进程
pkill -f "agent-browser-linux-x64" 2>/dev/null
pkill -f "chrome.*agent-browser" 2>/dev/null
sleep 3
# 确认清干净了
ps aux | grep -E "agent-browser|chrome.*headless" | grep -v grep
# 下一次 browser_navigate 调用会自动重启agent-browser
```

**如果反复挂掉：**
- 检查服务器内存：`free -h`（Chrome headless吃内存，快照模式单实例约2-3GB）
- 检查agent-browser版本：重新 `cd /home/ubuntu/.hermes/hermes-agent && npm install agent-browser@latest` 可能修复bug
- **从国内服务器下载Chrome**：agent-browser内置的Chrome下载走Google CDN，从中国服务器下载极慢（≤100KB/s，178MB的zip下载5分钟+超时）。**解决方案**：用 `curl -L -o /tmp/chrome.zip "https://registry.npmmirror.com/-/binary/chrome-for-testing/150.0.7871.46/linux64/chrome-linux64.zip"`（~11MB/s，14秒完成）。然后解压到 `~/.cache/agent-browser/chrome-linux64/`。

### 9.3 浏览器不可用时的降级方案

如果 CDP 模式和 Playwright 都不可用，降级到 web_search：

**优先顺序：**
1. **CDP 模式**（首选）— `agent-browser --cdp 9222` 连接 systemd 托管的 Chrome
2. **Playwright**（备用）— `python3 scripts/browser_playwright.py snapshot <url>`
3. **web_search + web_extract**（最终降级）— 搜关键词+逐条提取

**方案一：Playwright 直接抓取（推荐）**

Playwright 已预装，可直接用 Python 操作 Chromium，不依赖 agent-browser 服务。

| 平台 | Playwright 可用性 |
|:---|:---:|
| 快手 brilliant 页 | ✅ 已验证（热榜+短视频标题） |
| 抖音 | ✅ 已验证（单视频页元数据提取） |
| 小红书 | ⏳ 待验证（需登录态） |
| B站 | ✅ SSR渲染，预期可行 |

详细代码和参数见 `references/playwright-direct-scraping.md`

**方案二：web_search + web_extract**

| 替代方式 | 能做什么 | 不能做什么 |
|:---|:---|:---:|
| **Playwright 直接抓取**（推荐） | 渲染JS SPA、取完整内容、滚动加载、DOM提取 | 需要登录态的页面拿不到（如小红书个人页） |
| `web_search` + `web_extract` | 搜平台爆款关键词→抓页面标题/描述/作者/互动数 | 不能拿完整列表，需手动逐条查 |
| `scrapling-scraping-strategy` | B站全文爬取 | 抖音/快手/小红书拿不到JS渲染内容 |

**web_search替代方案示例：**
1. `web_search("site:kuaishou.com 好剧推荐")` 搜快手热门
2. `web_extract(各结果URL)` 逐条提取标题/作者/互动
3. 手动整理格式存入 task 文件夹

注意：这是**降级方案**，效率和完整性不如正常browser抓取，每次只能取几条而非40条。

### 9.4 个人页需要登录

快手个人页（profile/xxx）和小红书一样，需要登录才能查看完整信息。
`web_extract` 只能拿到登录提示页，拿不到粉丝数/作品列表。
→ 通知用户需提供登录态，或放弃该数据源。

### 9.5 ⚠️ 内容分析的红线：文本抓取 ≠ 画面可见

> **先确认再动手：** 调用豆包视觉API需要消耗token/额度。每次调用前**必须先问用户"要跑吗？"告知大概成本**。用户说跑再执行。不打招呼直接调用=违纪。

**Playwright/agent-browser只能提取页面的文本数据**（标题、作者、互动数、标签、发布时间、页面描述），**不能看到视频画面本身**。

| 能拿到（文本层） | 拿不到（画面层） |
|:---|:---|
| ✅ 标题、作者名、粉丝数 | ❌ 角色长什么样 |
| ✅ 点赞/评论/收藏/转发数 | ❌ 场景、服装、色调、构图 |
| ✅ 发布时间、话题标签 | ❌ AI生成用了什么视觉风格 |
| ✅ 作者声明（如"内容由AI生成"） | ❌ 视频实际画面帧 |
| ✅ 页面HTML嵌入的JSON元数据 | ❌ 字幕/口播内容（除非单独提取） |

**严禁行为：**
- ❌ 不要从标题+标签凭空编造画面描述（"女主角穿红色连衣裙"这种）
- ❌ 不要假装能反推视觉提示词（"这个场景的prompt是..."）
- ❌ 不要在看不到画面的情况下断言"分镜结构"

**正确响应：**
- ✓ 明确告知用户：能拿到文本元数据，看不到画面
- ✓ 如果要画面分析，确认当前模型是否有看图能力（`vision_analyze`）
- ✓ 如果没有看图能力，建议用户提供视频截图或文字描述画面
- ✓ 可以用已有的元数据做**策略层面的分析**（选题方向、互动率结构、完播逻辑），不做视觉层面的推断

### 9.6 平台登录策略

不同平台的登录难度和方式不同：

| 平台 | 登录方式 | 状态 | 说明 |
|:---|:---|:---:|:---|
| **抖音** | 无强制登录（可看页面） | ✅ | 未登录也能看视频页 |
| **快手** | QR扫码 / 密码登录 | ✅ QR码 | **CDP模式可渲染QR码**（Chrome 150 + CDP模式成功，snap Chromium+Xvfb失败）。登录页`passport.kuaishou.com/pc/account/login/`，默认密码登录，点`@e1`切换到扫码。 |
| **小红书** | Cookie/密码 | ❌ | 需要登录态，QR码方案未测 |

**快手扫码登录流程：**
```bash
# 1. 打开登录页
agent-browser --cdp 9222 open "https://passport.kuaishou.com/pc/account/login/"
sleep 3

# 2. 点击"扫码登录"（如果默认不是扫码）
# 【⚠️ 先snapshot找当前ref，不要硬写@e1 — 页面刷新后ref可能变】
agent-browser --cdp 9222 click @e1    # 确认@e1是"扫码登录"后再点
sleep 4

# 3. 截图
agent-browser --cdp 9222 screenshot /tmp/kuaishou_qr.png

# 4. 发给用户扫码（通过MEDIA:路径发）
# 用户扫完后，cookie自动保存在Chrome的user-data-dir(/tmp/chrome-cdp-data)
```

**密码登录（不用扫码）：**
快手登录页默认就是密码登录模式（有"请输入手机号"和"请输入密码"输入框）。可以直接填账号密码：
```bash
agent-browser --cdp 9222 fill @e18 "手机号"
agent-browser --cdp 9222 fill @e19 "密码"
agent-browser --cdp 9222 click @e13    # "登录"按钮
```

### 9.7 快手视频详情页反反爬方案（Cookie + 手机UA）

**核心发现：** 快手视频详情页在headless浏览器（无论是agent-browser CDP还是Playwright）中都被反爬系统检测，返回 `{"result":2,"error_msg":null}` JSON（result:2=未授权/被拦截）。

**绕过方案：** 使用直接的 Python `requests` HTTP 请求 + 已登录 Cookie + 手机 User-Agent。此方法返回完整SSR HTML，包含视频直链、标题、作者、话题标签、点赞数等所有数据。

#### 前置条件

1. **快手已登录（做过一次QR/密码登录）**
2. **Cookie已保存**到 `references/kuaishou_cookies.json`（格式：`[{name, value, domain}]`列表）
3. Chrome的user-data-dir（`/tmp/chrome-cdp-data`）持久化后重启不丢session

#### 工作流

```bash
# 从快手分享链接提取photoId
v.kuaishou.com/<短码>  →  重定向到  kuaishou.com/short-video/<photoId>

# 直接调API拿HTML（包含视频直链和数据）
Python requests GET https://www.kuaishou.com/short-video/<photoId>
  Headers: User-Agent=Mozilla/5.0 (Linux; Android 13; Pixel 7)...Mobile Safari/537.36
  Cookies: 从kuaishou_cookies.json读取
  → 返回完整SSR HTML
```

#### 从HTML中提取的数据

使用正则从HTML提取：

| 数据 | 正则模式 | 示例 |
|:---|:---|:---|
| 标题 | `<span class="text txt"[^>]*>([^<]+)<` | "我的假睫毛掉了" |
| 话题标签 | `<span class="topic txt"[^>]*>([^<]+)<` | #喜爱度激励计划 |
| 作者 | `"userName":"([^"]*)"` | "小鱼动漫社" |
| 点赞 | `"likeCount"[^:]*:"([^"]*)"` | "58423" |
| 视频直链(mp4) | `https?://[^"']*\.(?:mp4\|m3u8)[^"']*` | v4.oskwai.com/...mp4... |
| 作者ID | `"userId":"([^"]*)"` | 用户UID |
| 粉丝数 | `"fansCount":"([^"]*)"` | 粉丝数 |

#### Python模板

```python
import requests, json, re

with open('references/kuaishou_cookies.json') as f:
    cookies_list = json.load(f)
cookies = {c['name']: c['value'] for c in cookies_list}

headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36',
    'Referer': 'https://www.kuaishou.com/',
}

resp = requests.get(f"https://www.kuaishou.com/short-video/{photo_id}", headers=headers, cookies=cookies, timeout=15)
html = resp.text

# 提取标题
title = re.search(r'<span class="text txt"[^>]*>([^<]+)</span>', html)
# 提取话题
topics = re.findall(r'<span class="topic txt"[^>]*>([^<]+)</span>', html)
# 提取点赞
likes = re.search(r'"likeCount"[^:]*:"([^"]*)"', html)
# 提取视频直链
video_urls = re.findall(r'https?://[^"\']*\.(?:mp4|m3u8)[^"\']*', html)
```

#### 与其他方法的对比

| 方法 | 快手热榜 | 快手单视频 | 抖音 | 依赖 |
|:---|:---:|:---:|:---:|:---|
| **CDP模式** (agent-browser --cdp) | ✅ | ❌ 反爬封 | ✅ | systemd Chrome |
| **Playwright** | ✅ | ❌ 反爬封 | ✅ | pip playwright |
| **Python requests + Cookie + 手机UA** | ❌ 热榜JS渲染 | ✅ 完整数据 | ❌ SPA | cookie文件 |

**结论：** 快手全平台覆盖需要组合使用CDP模式（热榜页）+ Cookie直调API（视频详情页）。


### 9.8 利用豆包视觉模型分析视频画面 + ffmpeg视频帧提取

9.5说"看不到画面"，但这条可以把画面内容读出来——**用 Volcengine Ark 豆包视觉模型分析截图**。

#### 🚨 铁律：只提取不编造

用户多次纠正过（"不要自己编"、"是你自己编的还是实际视频的"、"我让你拆视频的提示词"）。

- 只能从**实际数据源**提取（截图/HTML/API响应/视觉模型输出/视频帧）
- 不能用标题+标签+常识拼凑出"提示词"然后谎称是反推的
- 如果拿不到画面/数据，必须诚实说「拿不到」，不能编一套通用模板
- 拿到视觉模型输出后做结构化反推时，必须声明"基于画面分析反推，非原视频作者公开的prompt"

#### 完整工作流

```
① 截图/获取视频帧
   ├─ 抖音：agent-browser --cdp 9222 screenshot（v.douyin.com优先，避免直链触验证码）
   ├─ 快手：Python requests + cookie + 手机UA → mp4 URL → ffmpeg取帧
   └─ B站/其他：Playwright screenshot
   ↓
② 调豆包视觉模型分析
   ↓
③ 拿到画面描述（角色/场景/色调/字幕/文字）
   ↓
④ 基于画面描述做结构化反推（声明"基于画面分析反推"）
```

#### 所需工具

| 工具 | 用途 |
|:---|:---|
| **Playwright** (`scripts/browser_playwright.py screenshot`) | 截图 |
| **agent-browser --cdp 9222 screenshot** | 也可截图（CDP模式） |
| **Volcengine Ark 豆包视觉模型** | 分析画面 |
| `.env` 中的 `ARK_API_KEY` + `ARK_ENDPOINT` | API凭证 |

#### 已验证可用的视觉模型

从Ark API列表中选择状态为""（可用）的视觉模型。**注意：模型名前缀和版本号会随火山引擎更新而变化，每次使用前应自查。当前（2026-07-10）有效的看图端点：**

- **当前可用：** `ep-20260710211910-f65h9` → `doubao-seed-2-0-mini-260215` ✅ **2026-07-10已验证可用**（多模态，同时支持文本对话+看图）
- 旧模型 `doubao-seed-1-6-vision-250815` 已退役
- 旧推理接入点 `ep-20260627215622-82xh6` 已过期

**注意：** ARK 推理接入点大约每2周过期一次。过期时需去火山引擎方舟控制台重建接入点，然后在 `.env` 中更新 `ARK_ENDPOINT`。

#### ARK_ENDPOINT 过期自查

```bash
# 自查命令
curl -s --max-time 15 "https://ark.cn-beijing.volces.com/api/v3/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -d "{\"model\":\"$ARK_ENDPOINT\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":3}"
# 返回 InvalidEndpointOrModel.NotFound → endpoint过期
# 返回正常响应 → endpoint有效
```

**注意：** `$ARK_ENDPOINT` 是环境变量中存的 endpoint ID（如 `ep-20260627215622-82xh6`），不是模型名。这两个都在火山引擎方舟控制台创建和管理。

**2026-07-06实测：** `doubao-seed-1-6-vision-250815` 成功分析了抖音视频截图（`/tmp/douyin_screenshot.png`），准确描述了：机场场景、女性深蓝连衣裙+金色腰带+长卷发、小女孩黄上衣+背带裙+蓝色棒球帽、字幕"我家阿妹很乖的啦"、互动数据等。

#### API调用模板（Python）

```python
import requests, base64, os

# 读截图
with open('/tmp/screenshot.png', 'rb') as f:
    img_b64 = base64.b64encode(f.read()).decode('utf-8')

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {os.environ['ARK_API_KEY']}"
}

# 用当前有效的ARK_ENDPOINT（存于.env）
endpoint = os.environ['ARK_ENDPOINT']  # 当前: ep-20260710211910-f65h9

payload = {
    "model": endpoint,  # 直接用endpoint ID，内部指向 doubao-seed-2-0-mini
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "详细描述这张截图中的所有视觉内容"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ]
    }],
    "max_tokens": 1500
}

resp = requests.post(
    "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    headers=headers, json=payload, timeout=60
)
```

#### 快手画面获取（Cookie → mp4 → ffmpeg帧提取）

当目标视频来自快手且CDP截图失败（反爬返回JSON）时：

```python
import requests, re, subprocess, json

# ① Cookie+手机UA拿视频页HTML
with open('references/kuaishou_cookies.json') as f:
    cookies = {c['name']: c['value'] for c in json.load(f)}
headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Mobile Safari/537.36'}
resp = requests.get(f"https://www.kuaishou.com/short-video/{photo_id}", headers=headers, cookies=cookies, timeout=15)

# ② 提取MP4直链
video_urls = re.findall(r'https?://[^\'"]*\.(?:mp4|m3u8)[^\'"]*', resp.text)
video_url = video_urls[0] if video_urls else None

# ③ ffmpeg取帧
if video_url:
    subprocess.run(["ffmpeg", "-y", "-ss", "2", "-i", video_url, "-frames:v", "1", "-q:v", "2", "/tmp/kuaishou_frame.jpg"], timeout=30)
```

**注意：** 第②步的视频URL来自快手CDN，有时效性（约几小时）。截图后尽快调用视觉分析。

#### 分析维度

调用视觉模型时，prompt应包含以下维度（缺一不可）：

```
1. **视频播放器画面（最核心）**
   - 角色：性别、大概年龄、发型发色、服装款式颜色、表情、动作
   - 场景：室内/室外？具体环境（家/办公室/机场/街道等）？道具？
   - 色调：暖/冷？光线来源？有特效滤镜吗？
   - 文字：画面上的字幕/文字内容

2. **视频信息区**
   - 标题、作者、粉丝数
   - 互动数据（点赞/评论/收藏/转发）

3. **描述和标签**
```

#### 抖音截图特别说明

抖音对 headless Chrome 触发滑块验证码。2026-07-06 已验证两种绕过方式：

| 方式 | 效果 |
|:----|:----:|
| **agent-browser CDP 模式**（无登录） | ❌ 验证码 |
| **Playwright + 手机UA**（推荐） | ✅ **页面正常加载**，视频画面可截图 |

核心代码见 `references/douyin-mobile-ua-bypass.md`。简单说就是 Playwright 设 iPhone UA 和 390×844 viewport，绕过验证码拿到页面内容。

#### ⚠️ 关键纪律

| 纪律 | 说明 |
|:---|:---|
| **先问成本再跑** | 视觉API走token消耗。每次调用前必须说"大概几分钱，要跑吗？" |
| **不可凭空编造** | 视觉模型返回什么就用什么。**绝不**根据标题/标签自己编画面描述 |
| **大截图超时** | 1MB+截图可能超时。max_tokens设1500以内，timeout≥60s |
| **分步策略** | 如果详细分析超时，先让豆包描述画面（简版），再用结果去做反推 |
| **快手详情页** | headless浏览器被反爬封，需用cookie+手机UA直调API（见 `references/kuaishou-scraping-workflow.md`） |

#### 反推提示词策略

拿到画面描述后，从三个层面反推：

1. **剧本Prompt层面**：画面中的剧情（机场/姐妹对话）→ 推测故事梗概和剧本提示词
2. **角色Prompt层面**：人物外貌细节 → 推测角色设计提示词
3. **视频分镜Prompt层面**：场景 + 光线 + 色调 + 镜头 → 推测Seedance/即梦的视频生成提示词


### 9.7 任务焦点纪律

当用户明确指定要修/用某个工具时，不要擅自切换方案。例如：
- 用户说"搞agent" → 先死磕agent-browser，不要主动跳到Playwright
- 用户说"看你装好没" → 先确认已装工具的状态，不是直接开新功能
- 只有尝试用户指定的方案后确认不可行，才提供替代方案并征求同意

### 9.9 抖音反爬突破：手机UA绕过验证码

**发现（2026-07-06）：** 抖音对 headless Chrome 2 触发滑块验证码，但对手机 UA 放行。

**绕过方法：** 使用 Playwright 设置 iPhone UA 和手机 viewport：

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=CHROME_PATH, args=['--no-sandbox','--disable-dev-shm-usage'])
    context = browser.new_context(
        viewport={'width': 390, 'height': 844},
        user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
    )
    page = context.new_page()
    page.goto(url, wait_until='domcontentloaded', timeout=30000)
    time.sleep(6)
    page.screenshot(path='/tmp/douyin_mobile.png')
```

**已验证结果（2026-07-06）：**
- ❌ agent-browser CDP 模式 → 验证码/登录页
- ❌ agent-browser 分享链接 → 验证码/登录页  
- ❌ Playwright 桌面 UA → 验证码
- ✅ **Playwright + iPhone UA → 视频页面正常加载**（标题、作者、描述、互动数据、推荐视频全部可见）
- ❌ 但视频播放器被「打开App」遮罩覆盖，视频本身仍不能直接在web播放

**局限：** 手机UA虽能读取页面文本数据，但视频播放器被App下载引导遮罩覆盖，无法直接观看或下载视频内容。如需下载视频仍需登录cookie。

### 9.10 🚨 反拆提示词的铁律（用户多次纠正，优先级最高）

> "不要自己编" / "是你自己编的还是实际视频的" / "我让你拆视频的提示词" / "提示词这么简单？"

**核心原则：** 只能从**实际数据源**提取画面信息，**绝不能**根据标题+标签+行业常识拼凑出"提示词"然后谎称是反推的。

#### 反拆提示词的正确流程

```
① 截图/获取视频帧
   └─ 抖音：Playwright + iPhone UA → screenshot（手机UA绕过验证码）
   └─ 快手：Python requests + cookie + 手机UA → mp4 URL → ffmpeg取帧
   ↓
② 调豆包视觉模型分析截图
   └─ API: $ARK_ENDPOINT（当前: ep-20260710211910-f65h9 → doubao-seed-2-0-mini-260215） + ARK_API_KEY
   ↓
③ 拿到画面描述（视觉模型实际返回的内容）
   └─ 角色外貌/服装/表情/动作
   └─ 场景/色调/光线
   └─ 画面上任何文字/字幕
   ↓
④ 基于视觉模型输出，做结构化反推
   └─ ⚠️ 必须在结果前声明："基于画面分析反推，非原视频作者公开的prompt"
```

#### 必须向用户坦诚的约束

| 真实情况 | 怎么说 |
|:---------|:-------|
| 画面只拍到角色/场景，没有code界面 | "这视频是效果展示，不是教程/code画面，prompt是口述的" |
| 视频是口述/画外音讲解 | "画面里没有prompt文字，拿不到具体提示词" |
| 标题/描述里没写具体prompt | "只有标题和描述描述了这个skill的效果，没公开prompt" |
| 被反爬挡住了 | 如实说被挡，给出替代方案（用户手动看视频转述/github搜索同类开源项目） |
| 视觉模型分析出画面内容 | 在输出前声明"基于画面分析反推" |

#### 三个已知案例（已验证）

| 案例 | 可提取的数据 | 不可提取 |
|:----|:------------|:---------|
| 卡皮巴巴拉《临时关系》（抖音AI短剧） | ✅ 画面角色/场景/字幕 → 反推视觉prompt | ❌ 作者实际用的触发词和参数 |
| 小鱼动漫社《我的假睫毛掉了》（快手动漫） | ✅ 画面风格/构图/色调 → 反推画风prompt | ❌ 实际seed值和模型参数 |
| 望淮山《AIGC人物表情控制》（抖音） | ✅ 标题描述说了是"skill" + FACS微表情控制 | ❌ 视频是demo非教程，prompt口述的 |

#### 禁止行为清单

- ❌ 用标题+标签+常识拼凑"提示词"然后说"根据画面分析"
- ❌ 说"反推的提示词"但实际上是自己编的一套通用模板
- ❌ 拿到视觉模型输出后，往里面加自己想象的内容（"他还加了负面提示词"）
- ❌ 用户指出"你编的"时辩解或绕圈子 → 立刻认："你说得对，我编的，这是基于画面分析的推测"

### 9.11 代理基础设施：快代理私密代理

内容抓取需要代理服务器绕过平台地域/IP限制。本技能使用 **快代理私密代理** 作为基础设施。

**关键点：**
- 私密代理使用 **SOCKS5** 协议（非HTTP）
- **API白名单**（调提取接口）和 **代理白名单**（用代理上网）是两套独立系统
- Chrome 走 SOCKS5 需要 **白名单模式**（不带账密），带账密报 `ERR_NO_SUPPORTED_PROXIES`
- 代理IP有效时长 1~5 分钟，每次请求需重新提取
- **环境变量污染陷阱：** `http_proxy` / `https_proxy` 环境变量会影响提取API调用（提取API从代理IP检测白名单，而非服务器真实IP）。提取前务必 `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY`

详细接入步骤和完整命令见 `references/kuaidaili-proxy-setup.md`。
同样参见 server-operations/n8n-deployment 的 `references/kuaidaili-proxy.md`（基础配置）。

#### SOCKS5 + Chrome 访问抖音视频（已验证）

代理+SOCKS5白名单模式 + Chrome 可成功加载抖音**单视频页**（直接URL），获取完整元数据。搜索页仍触发验证码。
完整流程见 `references/kuaidaili-proxy-setup.md#八抖音视频访问工作流`。

#### 正确句式

```
✅ "基于画面分析，如果他用的是Seedance 2.0，prompt结构可能是：...（声明推测）"
✅ "目前能看到的是XX画面，但不代表他的实际prompt长这样"
✅ "实际prompt没公开，但行业标准做法是...（引用公开资料）"
❌ "他的提示词是：你故意蹭我车漆弄坏了"（这TM是字幕不是提示词）
```

### 9.12 🚨 Tavily/搜索引擎缓存数据可靠性警示（2026-07-18 实测验证）

**核心发现：** 搜索引擎（Tavily/Bing/Google）缓存的抖音视频赞数可能**严重偏离真实值**。

**实测案例（2026-07-18）：**
| 账号 | Tavily缓存数据 | 抖音App内实测 | 偏差 |
|:-----|:--------------:|:-------------:|:----:|
| Mora茉然「AI觉醒」 | 8.0万赞 | **9,396赞** | **差8.5倍** |
| 重燃「人一定要相信自己」 | 57.6万赞 | 待App验证 | — |

**偏差原因：**
- 搜索缓存可能是发布早期的快照（赞数还在涨），也可能是页面简化显示
- CDP页面显示的近似值（「9000+」）反而比Tavily缓存更接近真实值

**铁律（2026-07-18 用户确认）：**

**正确数据引用格式：**
```
赞数: 9,396（用户抖音App内实测）
赞数: 9,000+（CDP页面实时，未登录简化显示）
赞数: 8.0万⚠️（Tavily缓存数据，非实时精确值，仅供参考）
```

### 9.13 📌 用户命令理解规则："分析视频内容" 指视觉分析

用户说"分析视频内容"时，指的是**视频画面的视觉内容**（角色长相、场景、色调、字幕、AI生成风格），不是结构/策略层面的分析（章节划分、标签策略、选题方向）。**用户2026-07-10纠正过此错误：给了结构分析被用户回"我让你分析视频内容"。**

**正确响应路径：**
```
用户: "分析这个视频内容"
  → ① 截图/获取视频帧（SOCKS5代理+Chrome或Playwright）
  → ② 调视觉模型分析画面（豆包vision，注意check ARK_ENDPOINT是否有效）
  → ③ 给出画面描述（角色、场景、色调、字幕、AI风格）
  → ④ 再附加结构分析作为补充
```

**错误响应（用户2026-07-10纠正）：**
```
用户: "分析这个视频内容"
  → ❌ 只给标题+标签+章节结构+策略建议（用户不接受）
  → ❌ 不给画面描述，直接跳到"这个视频怎么样"
```

**优先顺序：** 视觉内容 > 结构分析 > 策略建议。三者都可以给，但视觉分析是用户的第一需求。

**当前视觉分析的状态（2026-07-10）：**\n- Hermes当前模型（deepseek-v4-flash）不支持图像输入\n- 豆包视觉分析走火山引擎ARK独立通道：`ARK_API_KEY` + `ARK_ENDPOINT`（需在 `.env` 中配置有效端点）\n- **当前可用端点：** `ep-20260710211910-f65h9` → `doubao-seed-2-0-mini-260215`（2026-07-10已验证可看图）\n- 如果豆包vision不可用（端点过期），告知用户在火山引擎方舟控制台重建推理接入点
