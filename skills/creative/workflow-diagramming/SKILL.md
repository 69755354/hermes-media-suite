---
name: workflow-diagramming
description: 把系统工作流/业务流程画成图片交付。触发：把XX工作流/流程/节点流程用图片做出来。
author: Hermes (curator-managed)
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [diagram, workflow, flowchart, svg, png, guangzhou, ai-video-factory]
---

# 工作流流程图制作

把系统/业务工作流画成可交付图片（PNG）。覆盖：范围确认 → 事实查证 → HTML/SVG 制作 → 截图转 PNG → 质检交付。

## When to Use

- 用户说「把XX工作流/流程/架构用图片/图做出来」
- 用户提到 node 编号、泳道、流程图
- 需要把 wiki/spec/WORKFLOW_REGISTRY.yaml 里的语义节点可视化

## 第一步：识别是哪个工作流 + 确认粒度（血泪教训，2026-08-19，连错 4 次）

用户说「把广州机的工作流流程用图片做出来」，我连错 4 次才对上：先画 ai-video-factory 三泳道 12 步 → 纠正「node 0 to node 1」→ 画语义节点 0→1 → 纠正「我说的是火山工作流」→ 画扣子 7 节点概念图 → 纠正「打法分析/平台策略/自动发布/数据分析那些节点都没有」→ 画 19 节点主链 → 纠正「I think it's Xiao Lu's work flow」「最新的工作流」→ 最终是小鹿做视频流程 v2。

「工作流」在本环境有多个候选，画图前必须对上号：

| 候选 | 特征 | 权威源 |
|:---|:---|:---|
| ai-video-factory 12 步 | 客户/工厂/账务三泳道、O1 授权、settle 扣 750 | ai-video-factory/README.md |
| 19 节点语义主链 | 节点 0-18、打法分析/平台策略/自动发布/数据分析、display_order | WORKFLOW_REGISTRY.yaml + WORKFLOW_SPEC.yaml |
| 扣子 Coze 概念图 | 7 节点、选题/文案/分镜/即梦AI、周氏无厘头 | workflow/wiki/coze-workflow-diagram.html |
| 小鹿做视频流程 v2 | 客户说「做个视频」、7 步创作链、3 人工确认点、三通道出片 | customer/SOUL.md（详见 references/xiaolu-video-workflow-v2.md） |

规则：
- 用户说「XX 的工作流」时，**先列候选让用户确认**，或按点名特征反推：含「打法分析/自动发布/数据分析」= 19 节点主链；含「火山/扣子/即梦」= 扣子概念图；含「小鹿/客户说做个视频」= 做视频流程 v2；含「O1/settle 扣积分」= ai-video-factory 12 步
- 用户说「最新的」= 找最近修改的 SOUL/流程文件——小鹿最新版在 `/home/ubuntu/.hermes/profiles/customer/SOUL.md`（8/17 更新），不在 `/home/ubuntu/SOUL.md`（7/7 旧版）
- 用户提到 node 编号（node 0 → node 1）时，**先查注册表确认 node 定义**，不凭感觉猜是哪个节点
- 拿不准时宁可先问一句/列候选，不要画完被纠正再返工——一张图从制作到质检要 5+ 步，画错整张重来
- 用户明确给了编号范围（node 0 → node 1）时直接按范围做；全流程图和节点段图是两种产物，别混着交付

## 第二步：查证事实源（禁脑补）

画图前必须核对真实定义，不凭记忆拼：

| 事实源 | 位置 | 内容 |
|:---|:---|:---|
| 节点注册表 | `workflow/wiki/spec/WORKFLOW_REGISTRY.yaml` | node 定义：display_order/name/produces/requires/exit_gate |
| 节点参数 | `workflow/wiki/spec/WORKFLOW_SPEC.yaml` | model/temperature/persona/note/input_deps |
| 广州机工厂实现 | `ssh -p 2222 ubuntu@127.0.0.1` → `/home/ubuntu/ai-video-factory/app/orchestrator.py` | produce_node 实际产出、状态机 set_node/advance |
| 广州机门禁实现 | 同上 → `app/gates.py` | build_gate_manifest / _copy_hard_gate 检查逻辑 |
| 广州机业务路径 | 同上 → `ai-video-factory/README.md` | 火锅店演示路径 12 步、端口、入口 |
| 小鹿最新工作流 | `ssh -p 2222` → `/home/ubuntu/.hermes/profiles/customer/SOUL.md`（8/17 版，**别读 /home/ubuntu/SOUL.md 旧版**） | 做视频流程 v2、三通道、confirm_gate 三确认点 |
| 扣子 Coze 概念图 | `workflow/wiki/coze-workflow-diagram.html` | 7 节点短视频工作流概念图（6/28 旧图，节点 0-7） |

广州机目录速查：`ai-video-factory`（8090 工厂）/ `billing-system`（8080 账务，ARCHITECTURE.md）/ 新加坡机经 `127.0.0.1:2222` 反隧访问。

node 0/1 的已核对定义见 `references/guangzhou-factory-node-0-1.md`。

## 第三步：制作 HTML 图

- 基于 `architecture-diagram` skill 模板（dark 主题 SVG，自包含 HTML）
- **中文必须加 font fallback**：`font-family: 'JetBrains Mono', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', monospace;`——JetBrains Mono 不含中文字形
- 颜色语义：客户/前端=cyan `#22d3ee`、工厂/后端=emerald `#34d399`、账务/数据库=violet `#a78bfa`、门禁/人工确认=rose `#fb7185`、扣费/远程执行=amber `#fbbf24`
- 门禁用 rose 虚线框（stroke-dasharray 5,4）；泳道边界用大虚线框
- 跨泳道箭头用折线（M/L 路径）走空白区，**避开文字和框**；每条箭头标注语义（如「成片成功 → settle 扣 750 积分」）
- **用到的每个 marker 颜色都要在 defs 里定义**——漏定义箭头只显示线不显示头（本次漏了 arrowhead-amber 补过一次）
- 产物 ID（A_PROJECT_CHARTER 等）和参数（model/temp）按注册表原样写，不简化

## 第四步：截图转 PNG

playwright 可用，但**已装 chromium 版本可能和 playwright 期望版本不匹配**（报 "Executable doesn't exist at .../chromium_headless_shell-1234/..."）：

```python
from playwright.sync_api import sync_playwright
import pathlib
html = pathlib.Path('/path/to/图.html').resolve().as_uri()
exec_path = '/home/ubuntu/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome'  # 用 find 确认实际版本号
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exec_path)
    pg = b.new_page(viewport={'width': 1600, 'height': 1200}, device_scale_factor=2)  # 2x 高清
    pg.goto(html, wait_until='networkidle')
    pg.wait_for_timeout(1000)
    pg.screenshot(path='/path/to/图.png', full_page=True)
    b.close()
```

- 版本不对时先 `find /home/ubuntu/.cache/ms-playwright/ -name chrome` 找实际可执行文件，**指定 executable_path 绕过**，不要重新 playwright install（下载大且慢）
- `device_scale_factor=2` 保证文字清晰；`full_page=True` 截整页（含底部卡片）

## 第五步：质检后交付

- 发用户前先 `vision_analyze` 自检：文字重叠遮挡？箭头连接正确？跨泳道折线压字？图例/卡片完整？
- 通过后 `MEDIA:/绝对路径.png` 直接发图（用户禁路径文本）
- 附简短说明：图里几块内容 + 来源（真实 README/代码核对）+ 可调整项（如「要加小鹿飞书流程或画细某条链路直接说」）

## 坑清单

- 用户给的 node 编号不是「步骤编号」，是语义注册表的 display_order——先查 registry 再动手
- 用户说的「工作流」有多个候选（工厂12步/19节点主链/扣子概念图/小鹿v2），先对上号再画——小鹿做视频流程 v2 细节见 `references/xiaolu-video-workflow-v2.md`
- 全流程图被纠正为节点段图 = 粒度没确认，不是图画得不好
- 中文字体不 fallback = 中文变方框
- playwright 版本不匹配 = 指定 executable_path 而不是重装
- 漏 marker 定义 = 箭头没头，视觉 bug 但 vision 自检能发现
