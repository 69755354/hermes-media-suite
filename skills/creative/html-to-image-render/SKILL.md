---
name: html-to-image-render
description: 用 playwright 把 HTML/SVG 图渲染成 PNG 交付。触发：流程图转图片/架构图截图。
---

# HTML → PNG 渲染交付（2026-08-21 实测）

## When to Use

触发：用户要「把 X 用图片做出来」/ 流程图 / 架构图 / 报告图；已经写好 HTML（用 architecture-diagram 模板或手写 SVG），需要转成 PNG 发给用户。本机标准做法：**HTML 文件 + playwright 截图 → PNG → vision 自检 → MEDIA 交付**。

## 核心命令（playwright 截图）

```python
from playwright.sync_api import sync_playwright
import pathlib
html = pathlib.Path('<绝对路径>.html').resolve().as_uri()   # file:// URI
exec_path = '/home/ubuntu/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome'  # 用 find ~/.cache/ms-playwright/chromium-*/ -name chrome 定位实际版本
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exec_path)
    pg = b.new_page(viewport={'width': 1600, 'height': 1200}, device_scale_factor=2)
    pg.goto(html, wait_until='networkidle')
    pg.wait_for_timeout(1000)
    pg.screenshot(path='<输出>.png', full_page=True)
    b.close()
```

要点：
- **`executable_path` 必须指定**：playwright 默认找 `chromium_headless_shell-<版本>`，本机装的是 `chromium-1228`（`~/.cache/ms-playwright/` 下），版本漂移会报 `Executable doesn't exist`。用 `find ~/.cache/ms-playwright/chromium-*/ -name chrome` 定位实际路径
- `device_scale_factor=2`：出 2 倍高清图（微信/飞书看清晰）
- `full_page=True`：长流程图截整页（默认只截视口）
- `wait_until='networkidle'` + `wait_for_timeout(1000)`：等 Google Fonts/布局稳定

## 交付前必须 vision 自检（2026-08-21 实测 3 次抓错）

截图后先 `vision_analyze` 检查再发用户，重点：
1. **有没有空分组框/框住错节点**（改布局时分组框和节点位置不匹配——vision 抓出「阶段四分组框为空」）
2. **文字是否出框/重叠**（长 skill 标注行溢出节点框）
3. **链路是否截断**（图没画完、分支无结束标记——vision 抓出「basic 分支无后续流程」）
4. **箭头/折线是否压字**（跨泳道折线穿过文字）

vision 报问题 → 改 HTML → 重截图 → 再 vision 复查，绿了才发。用户会直接看图，不查就是发废图。

## 交付纪律

- 一次发一张等确认（用户偏好：禁批量刷图）
- MEDIA:<png绝对路径> 直接发图片本体，不发路径文本
- 图的信息必须来自真实来源（广州机 README/代码/注册表），不脑补节点

## 配图尺寸与风格统一规则

- **所有配图统一 800×800 正方形**：封面、正文配图、信息卡全部 800×800，不做横版/竖版混搭
- **多张图必须颜色统一、风格一致**：同一组配图（封面+正文图+信息卡）必须用同一套配色体系和底色风格。不要一张深色一张白底混搭——先定好视觉体系（底色+主色递进），所有图按同一套渲染
- **信息卡用 HTML 渲染**（不用 Seedream 生图做信息卡）：中文文字可控、数字精确、无英文乱入风险。HTML+playwright 截图 → vision 自检 → 交付
- **封面图也是组图之一**：不要额外做不同尺寸的封面，封面从正文配图组里选或同尺寸同风格制作

## 相关

- `architecture-diagram`（creative/，bundled）：dark 主题 SVG 架构图/流程图 HTML 模板（颜色语义/泳道/图例规范）
- 流程图内容来源：接「XX 工作流」任务先定位是哪个系统（见 workflow-first-discipline）
