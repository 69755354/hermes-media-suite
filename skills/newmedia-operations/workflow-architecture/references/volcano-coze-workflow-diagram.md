# 工作流画图：口径确认 + 19 节点主链速查 + 画图流水线

> 2026-08-19 三次纠正后终版。背景：老板三次纠正「工作流」口径，最终确认要的是 **19 节点语义主链完整图**（每节点标注 skill），不是扣子 Coze 概念图（画了被否：「打法分析/平台策略/自动发布/数据分析那些节点都没有啊」）。

## 一、19 节点语义主链速查（老板要的「火山工作流」= 这张）

成品：`workflow/outputs/火山工作流19节点主链.html` / `.png`（2026-08-19）。数据来源：`workflow/wiki/spec/WORKFLOW_REGISTRY.yaml`（19节点/95产物/19门禁）+ `WORKFLOW_SPEC.yaml` 的 `node_registry` 段（模型/persona）。查 SPEC 用 python yaml 读 `spec['node_registry']`，不是顶层。

| display_order | 语义ID | 名称 | model / persona | 出口门禁 |
|:--|:--|:--|:--|:--|
| 0 | PROJECT_CHARTER | 合作立项与资料建档 | none / 信息采集员（纯采集） | G_PROJECT_AUTHORIZED |
| 1 | BUSINESS_DIAGNOSIS | 门店经营诊断 | deepseek-v4-flash / 用户分析师 | G_BUSINESS_BASELINE_READY |
| 2 | MARKET_INSIGHT | 顾客商圈竞争洞察 | deepseek-v4-flash / 用户分析师（+豆包搜索） | G_INSIGHT_VERIFIED |
| 3 | OFFER_PATH | 主推项目与预约路径 | deepseek-v4-flash / 策略编辑 | G_OFFER_VIABLE |
| 4 | GROWTH_STRATEGY | **打法分析**：平台/北极星/漏斗/预算 | deepseek-v4-flash / 策略编辑 | G_STRATEGY_APPROVED |
| 5 | OPERATING_INFRA | **平台策略基建**：账号/POI/预约/数据 | deepseek-v4-flash / 信息采集员 | G_INFRA_READY_FOR_PUBLISH |
| 6 | CONTENT_CALENDAR | 周月内容矩阵排期 | deepseek-v4-flash / 策略编辑 | G_CONTENT_PLAN_READY |
| 7 | TOPIC_EXPERIMENT | 选题实验 | deepseek-v4-flash / 策略编辑 | G_TOPIC_READY |
| 8 | COPY_PACKAGE | 多版文案（三版盲评≥60） | deepseek-v4-flash / 创意总监 | G_COPY_READY + 四硬门 |
| 9 | CREATIVE_BLUEPRINT | 分镜画面视觉基线 | deepseek-v4-flash / 分镜师 | G_CREATIVE_READY |
| 10 | MEDIA_PREP | 素材与生成准备 | none / 创意总监（Seedream 生图） | G_RENDER_READY |
| 11 | MEDIA_PRODUCTION | 成片图文制作检验 | none / 创意总监（Seedance/婵镜/ffmpeg） | G_TECHNICAL_QC_PASS |
| 12 | DELIVERY_PACKAGE | 终检与发布承接包 | deepseek-v4-flash / 策略编辑（四维终审≥68） | G_DELIVERY_READY |
| 13 | PUBLISH_OPERATE | **自动发布**：上线+首轮运营 | none（人工验证+脚本） | G_PUBLISH_READY |
| 14 | LEAD_OPERATION | 评论私信线索运营 | deepseek-v4-flash | G_LEAD_CAPTURED |
| 15 | CONVERSION_OPERATION | 预约到店成交履约 | deepseek-v4-flash | G_CONVERSION_RECORDED |
| 16 | RETENTION_OPERATION | 复购与转介绍 | deepseek-v4-flash | G_RETENTION_LOOP_READY |
| 17 | WEEKLY_REVIEW | **数据分析**：每周归因四层指标 | deepseek-v4-flash / 数据分析师 | G_WEEKLY_REVIEW_READY |
| 18 | MONTHLY_CLOSE | 月度报告与下周期 | deepseek-v4-flash / 数据分析师 | G_CYCLE_CLOSED |

**用户点名的节点 = 判断要哪套的信号：** 打法分析=4、平台策略=4/5、自动发布=13、数据分析=17/18。用户说这些 = 语义主链，不是扣子图。

## 二、扣子Coze 图纸（中间答案，被否，备用参考）

- 图纸位置：本机 `workflow/wiki/coze-workflow-diagram.html` + 广州机 `~/wiki/coze-workflow-diagram.html`（2026-06-28 概念图，两机同款）
- 重绘成品：`workflow/outputs/火山工作流节点0到结束.html` / `.png`（本会话中间版，**被老板否**）
- 标题：「扣子Coze · 实体店AI短视频工作流 · 周氏无厘头喜剧风格 · 输入店铺信息 → 自动出片 · 全自动化」
- 8 节点（画布从 0 编号）：0 开始(参数输入) → 1 选题(豆包4.0) → 2 剧情文案(四段式模板) → 3 分镜(模板) → 4 视频生成(即梦AI/可灵API，5镜并行9:16) → 5 自动拼接(ffmpeg) → 6 发布素材(可选) → 7 结束
- 工具选型：即梦AI ★★★★★、可灵AI ★★★★☆、剪映AI图文成片 ★★★☆☆、豆包/DeepSeek（剧本）

## 三、工作流画图流水线（2026-08-19 多版实测）

### 1. 先确认口径（最重要，三次被纠正的血泪）
用户说「工作流/节点N」先查是哪种：语义ID主链（19节点 display_order 0-18）vs 火山/扣子画布 vs ai-video-factory 客户流程。**判断信号见第一节；拿不准直接问「要 19 节点语义主链还是扣子画布图」**，别拿 coze-workflow-diagram.html 当默认。用户说「从节点0到最后」= 要全图，不是只画 0→1 两个节点（范围画窄同样被纠正）。

### 2. 数据来源：读真实系统，不脑补
- 广州机：`ssh -p 2222 ubuntu@127.0.0.1`（反隧），`timeout` 包裹防挂死
- ai-video-factory README（火锅店演示路径12步）+ orchestrator.py / gates.py 核对节点状态机
- WORKFLOW_REGISTRY.yaml / WORKFLOW_SPEC.yaml（本机 `workflow/wiki/spec/`）；SPEC 的节点参数在 `node_registry` 段，用 python yaml 读
- 图内容必须来自真实 README/代码，标注来源行（「来源：xx README + 代码核对」）

### 3. 渲染：architecture-diagram skill 模板（深色 SVG HTML）
- 颜色语义：cyan=前端/客户、emerald=后端/工厂、violet=数据库/账务、rose=门禁/安全/人工点、amber=执行/扣费/远程/关键节点
- ⚠️ **中文必须加 font fallback**：`font-family: 'JetBrains Mono', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', monospace`
- 泳道图用大虚线框（stroke-dasharray 8,4）+ 泳道标题文字；阶段分组框必须框住对应节点，画完用 vision 查空分组
- ⚠️ **自定义 marker 必须全定义**：用了 `url(#arrowhead-amber)` 但 defs 里没有 → 箭头头不显示（不报错）。写完 grep 一遍 `marker-end="url(#` 是否全在 defs
- 中文圈号（①②③）和「节点 0/节点 1」两种编号风格都能用，19 节点主链用数字编号

### 4. HTML→PNG 截图（Playwright executable_path 修复）
playwright 版本要求不存在的 `chromium_headless_shell-1234`，实际只装了 1228 → `Executable doesn't exist`。**修复：`find ~/.cache/ms-playwright -name chrome` 找实际路径，launch 传 executable_path**：

```python
from playwright.sync_api import sync_playwright
import pathlib
exec_path = '/home/ubuntu/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'  # 按 find 实际结果
html = pathlib.Path('xx.html').resolve().as_uri()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exec_path)  # 关键
    pg = b.new_page(viewport={'width': 1600, 'height': 1200}, device_scale_factor=2)
    pg.goto(html, wait_until='networkidle')
    pg.wait_for_timeout(800)
    pg.screenshot(path='xx.png', full_page=True)
    b.close()
```
- device_scale_factor=2 出高清图；full_page=True 截全页（含卡片/图例）
- 运行路径：`/home/ubuntu/.hermes/hermes-agent/venv/bin/python3`（playwright 已装，chromium 在 ~/.cache/ms-playwright）

### 5. 自检 + 交付
- vision_analyze 先看一遍再发（文字重叠/箭头压字/截断/编号错位/**空分组框**），vision 超时重试一次即可
- MEDIA:<绝对路径.png> 直接发图，正文不发路径文本
- 一次发一张等确认，用户说改哪改哪，逐版迭代

## 四、广州机节点事实核对（node 0/1 深挖实录）

- **PROJECT_CHARTER（display_order 0）**：model:none 纯采集（persona 信息采集员），产出 5 档案（A_PROJECT_CHARTER/A_STORE_FACTS/A_ASSET_REGISTER/A_RIGHTS_REGISTER/A_AUTHORIZATION_REGISTER），出口 G_PROJECT_AUTHORIZED（授权登记齐全 + 问题清单空 + O1 内部授权 5 分钟 token）
- **BUSINESS_DIAGNOSIS（display_order 1）**：model deepseek-v4-flash temp 0.1 reasoning low（persona 用户分析师），读取 charter+store_facts+authorization，产出 4 档案（A_BUSINESS_DIAGNOSIS/A_BASELINE_LEDGER/A_CAPACITY_PROFILE/A_DATA_GAPS），铁律「无数据标未测量禁编造、无历史数据不判断转化效率」，出口 G_BUSINESS_BASELINE_READY
- 广州机 produce_node 实现在 `ai-video-factory/app/orchestrator.py`；门禁 manifest 在 `app/gates.py`（G_PROJECT_AUTHORIZED 走 _project_authorization_context）
