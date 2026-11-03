# 快手分享链接数据提取 + 爆款结构分析框架

## 链接格式
快手分享链接：`https://v.kuaishou.com/<短码>`
最终指向：`https://www.kuaishou.com/short-video/<photoId>`

## 提取方式
```python
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path='/snap/chromium/3477/usr/lib/chromium-browser/chrome',
        args=['--no-sandbox', '--disable-dev-shm-usage']
    )
    page = browser.new_page(viewport={'width': 1280, 'height': 720})
    
    # 短链接自动重定向到长链接
    page.goto('https://v.kuaishou.com/KJYjkvZy', wait_until='domcontentloaded', timeout=30000)
    time.sleep(8)
    
    # 从页面提取数据
    body = page.eval_on_selector('body', 'el => el.innerText')
    # 提取标题、作者、互动数据...
    
    browser.close()
```

## 限制
**单条视频详情页需要登录态才能提取完整数据。**
未登录时页面返回 JSON `{"result":2,"error_msg":null,"request_id":"..."}`（result:2 表示未登录/访问受限）。

## 爆款内容结构分析框架（不依赖登录）

即使拿不到详情页数据，从热榜列表也能做结构化分析：

### 框架：标题 → 类型 → 热度 → 情绪

```python
# 从热榜数据提取的结构化字段
{
    "title": "局中局中局！",
    "heat": "113.5万",
    "tags": ["#好剧推荐", "#快嘴唠唠剧", "#神仙剪刀手", "#精彩片段"],
    "author": "小圆混剪",
    "type": "mix_cut",     # 混剪类
    "hook_pattern": "叠词"  # 局中局中局 = 三叠句式钩子
}
```

### 快手爆款类型（基于热榜观察）

| 类型 | 占比 | 典型标题 |
|:---|:---:|:---|
| 时事新闻 | 高 | 直击广西暴雨抗洪救援现场 |
| 体育赛事 | 中 | 墨西哥vs英格兰 / 挪威2比1战胜巴西 |
| 社会热点（明星/事件） | 中 | 赵薇前夫黄有龙被曝6天赌光2.8亿 |
| 民生/天气 | 中 | 广东将停雨但空调外机接着来 |
| 混剪/娱乐 | 中 | （"精彩短视频"区域） |
| 知识/科普 | 低 | 知识播种计划相关 |

### 地域相关热点
快手热榜中国内民生/社会新闻占比高，不同地区用户关注点差异大。做同城引流时可结合热榜中的本地热点选题。
