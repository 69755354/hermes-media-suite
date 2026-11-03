# 赛道选题池设计 + hotlist_selector 改造（2026-08-30）

## 背景

赛道化改造完成后（职场副业 P1 优先、字数分档、专属红线），产线跑出来的仍是时事热点稿（朱雀火箭/动博馆/尼泊尔冰崩）。根因：hotlist_selector 只从头条热榜选题，热榜50条命不中职场副业赛道关键词。

## 改动

### 1. 新增 `select_from_topic_pool()` 函数（hotlist_selector.py L159）

```python
def select_from_topic_pool(log=print):
    """从赛道选题池取第一个 pending 选题，
    用豆包搜索抓素材，生成 material.json。
    选题池为空→返回 rc=2（调用方回退热榜）。"""
```

逻辑：
- 读 `inputs/topic_pool_career.json`
- 取第一个 `status='pending'` 选题
- 用 `query` 字段调豆包 web_search（Custom版，复用 modules/search.py）
- 搜到的 Summary/Snippet 组装成 material.json（domain 取选题的 domain 字段）
- 选题 status 改为 `'used'`，写回选题池文件
- material.json 落盘到 `inputs/material_topicpool_{id}_{slug}.json`
- 豆包配额用尽/正文抓取失败 → rc=1（回退热榜）

### 2. `run_hotlist_selection()` 开头优先调选题池（L288）

```python
def run_hotlist_selection(log=print):
    pool_result = select_from_topic_pool(log=log)
    if pool_result["rc"] == 0:
        return pool_result
    if pool_result["rc"] == 1:
        log("[选题池] 搜索/抓取失败，回退热榜流程")
    # rc=2 = 选题池空，也回退热榜
    # ... 原热榜流程 ...
```

### 3. 选题池文件结构

路径：`inputs/topic_pool_career.json`

```json
[
  {
    "id": "tp001",
    "category": "实操步骤",
    "title": "下班后每天1.5小时做副业，普通人月入2000+的4条落地路径",
    "domain": "职场副业",
    "domain_id": "career_side_hustle",
    "source": "头条爆款",
    "source_url": "https://www.toutiao.com/article/7644806840522293795/",
    "query": "下班副业 月入2000 普通人 落地路径",
    "status": "pending"
  },
  ...
]
```

20个选题，分布：实操步骤10个、避坑提醒6个、认知反思4个。全部副业变现方向（非劳动维权）。

## 赛道方向纠正记录

1. 用户说「优先职场赛道」→ 初始选题池混入大量劳动维权选题（N+1/劳动仲裁/社保维权）
2. 用户纠正：「副业」→ 选题池全换为副业变现方向（下班接单/线上赚钱/副业避坑/兼职防骗）
3. 纪律：「职场副业」赛道 = 副业变现方向，不是职场维权法律科普

## 验证

- dry-run 成功取用 tp001（豆包搜到8个URL、新浪财经1019字摘要）
- 选题 tp001 status 改为 used，写回选题池
- 19个 pending 待用
- material.json 落盘到 inputs/material_topicpool_tp001_*.json
- py_compile 通过

## 待办

- [ ] 挂 cron 定时跑（当前无 cron，手动触发）
- [ ] 选题池用完后补充新选题（20个跑完回退热榜）
- [ ] 实跑一篇验证全链 PASS
