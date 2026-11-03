# 首篇中年职场文章完整生产工作流（2026-09-05）

## 从选题到终稿的完整流程

### 1. 选题池取题
```python
import json
with open('inputs/topic_pool_career.json') as f:
    d = json.load(f)
# 取第一个 status='pending' 的选题
topic = next(t for t in d if t.get('status') == 'pending')
```

### 2. 搜索真实素材构建 material.json

用产线 search 模块（豆包 Custom 版 web_search）搜索选题关键词，抓取真实报道正文：

```python
import modules.search as search_mod
import modules.fetcher as fetcher_mod
from modules.fetcher import get_text, find_container, _strip_tags, robots_allowed

trace = search_mod.new_trace(sc)  # sc = config['illustration']['doubao_search']
result = search_mod.search(topic_query, sc, trace)
# 抓取 2-3 篇报道正文，组装 raw_text
```

**坑**：选题池选题没有 `query` 字段（hotlist_selector 会 KeyError），需要手动从 title 提取搜索词。

material.json 必须包含：event / raw_text / source_urls / domain / fetched_at / hotlist_meta / topic_pool_meta

### 3. 跑 pipeline

```bash
python3 pipeline.py inputs/material_xxx.json --model glm
```

GLM 通道免费但慢（5-8分钟/篇）。`--model` 透传到 config alias 路由。

### 4. 读质检报告

pipeline 跑完后（rc=3 是 MANUAL_REVIEW_REQUIRED，正常）：

1. **读 `verdict.json`** — 看文字四项（AI味/编造/格式/敏感词）是否 PASS
2. **读 `detect_report_r3.json`** — 看 `platform_rules.dimensions` 的 shadow 报告
3. **读 `发布清单_*.md`** — 看发布前检查清单

### 5. shadow 报告 4 个 FAIL 的修法

| FAIL 维度 | 原因 | 修法 |
|:---------|:-----|:-----|
| title | 标题超30字 / 多余字符 | 删多余字符，保留数字钩子 |
| paragraph_density | 段落超4句/超180字 | 长段拆成2-3段 |
| repetition | 同一数字事实跨段重复3次 | 只保留首次完整出现，后文用代词 |
| ending | 强制CTA堆叠 | 删所有"收藏这篇"，留一个开放问题 |

**人读检查（检测器查不到的AI残留）**：
- 戏剧化金句（"打死人的兵器"→"真正管用的东西"）
- AI升华句（"砸碎职业停滞僵局"→"总还能蹚出一条路来"）
- 极端措辞（"耗着等死"→"继续等机会"）

### 6. 手动修订 → 终稿

直接改 md 文件，不重跑 pipeline。修完后用 python 验证：

```python
import re
with open('文章_终稿.md') as f:
    text = f.read()
hanzi = len(re.findall(r'[一-龥]', text))
print(f'汉字数: {hanzi}')  # 900-1500 区间
for kw in ['第一条', '第二条', '第三条', '耗着等死', '打死人的兵器']:
    count = text.count(kw)
    if count: print(f'  仍残留: "{kw}" {count}次')
```

### 7. 配图制作（HTML+playwright）

按文章三个小标题设计统一视觉体系的 800×800 信息卡：
- 统一配色（暗调深蓝+暖橙）
- 每张图对应一个段落主题
- HTML → playwright 截图 → vision_analyze 逐张检查

详见 `references/article-illustration-workflow-20260905.md`

## 关键坑

- **标题数字前缀bug**：pipeline 有时在标题开头生成多余数字（如"2投200份"应为"投200份"）。手动删除即可，不是功能设计。
- **选题池无query字段**：topic_pool_career.json 的选题没有 query 字段，需要从 title 提取搜索词。
- **robots限制**：头条(m.toutiao.com)/搜狐(m.sohu.com) 全站 robots 禁抓，搜索到的这些域名被跳过。中新网/腾讯网可抓。
- **rc=3不等于失败**：rc=3 是 MANUAL_REVIEW_REQUIRED，文字门可能全过，只是配图不足或其他非文字项。