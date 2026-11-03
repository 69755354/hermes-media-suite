# 文章配图生成工作流（2026-09-05 实测）

## 触发
文章产出后需要配3张正文信息卡（800×800），按文章段落内容生成。

## 工作流

### 1. 提取文章结构

从成稿中提取3个小标题和对应段落的核心内容：
```bash
grep -E "^一、|^二、|^三、" runs/<run_id>/文章_*.md
```

### 2. 设计统一视觉体系

三张图必须同一套视觉语言（跟合集封面/封面同一体系）：
- 背景渐变：深蓝暗调（#1a1a2e → #16213e → #0f3460）
- 强调色：暖橙（#ff8c32）
- 字体：Noto Sans SC（Google Fonts）
- 装饰元素：噪点纹理、细线分隔、圆角几何
- 文字层级：序号标签（橙小字）→ 主标题（白/橙粗体大字）→ 副标题（灰小字）

### 3. 写HTML（三张图一个HTML文件）

每张图一个 `.cardN` div，800×800px。三张图在一个HTML里竖排，用playwright按clip分块截图。

关键设计要点：
- 背景用 `radial-gradient` + `linear-gradient` 叠加造氛围
- 噪点用内联SVG `feTurbulence`（不依赖外部图片）
- 核心视觉符号要跟段落内容匹配（如纸箱=离职、手机空收件箱=石沉大海、柱状图=降薪）
- 文字集中在左下角，右上/右侧留视觉符号

### 4. playwright截图

```python
from playwright.sync_api import sync_playwright

html_path = os.path.abspath("illustrations.html")
out_dir = "runs/<run_id>/assets"
os.makedirs(out_dir, exist_ok=True)

cards = [(1, 0, 800), (2, 800, 800), (3, 1600, 800)]  # (num, y_offset, height)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 800, "height": 2400}, device_scale_factor=2)
    page.goto(f"file://{html_path}")
    page.wait_for_load_state("networkidle")
    for num, y, h in cards:
        out_path = f"{out_dir}/配图{num}_800x800.png"
        page.screenshot(path=out_path, clip={"x": 0, "y": y, "width": 800, "height": h})
    browser.close()
```

### 5. vision_analyze 逐张检查

对每张图调用 vision_analyze 检查：文字清晰度、布局平衡、渲染异常、视觉质量。全过才交付。

### 6. 交付

通过 MEDIA: 发送三张图片文件路径。

## 实操案例（2026-09-05 tp001「35岁被优化后投简历」）

| 配图 | 对应段落 | 画面内容 |
|:-----|:---------|:---------|
| 图1 | 一、滚蛋现场与石沉大海 | 悬空纸箱+暗色电梯门反光 |
| 图2 | 二、降薪求生的实操分点 | 手机空收件箱+大号"0" |
| 图3 | 三、你的卡点与出路 | 降薪柱状图递减（100%→80%→60%） |

## 合集封面制作

合集封面也用同一套视觉体系（800×800）：
- 标题居中，关键词用暖橙高亮
- 右上角双圈"合集"标签
- 上下细线分隔
- 底部署名行

封面模板见 session 20260905 的 cover_career_midlife.html。

## 注意事项

- HTML中不用外部图片（全部CSS/SVG/内联）
- Google Fonts用 `@import` 在HTML头部引入
- device_scale_factor=2 出2倍分辨率高清图
- 三张图必须视觉统一（同一配色/字体/装饰元素）
- 跟合集封面同一套视觉体系
