# 头条 Feed API 字段结构与频道映射（2026-08-19 cron 实测）

## API 端点

```
GET https://www.toutiao.com/api/pc/feed/?category={cat}&utm_source=toutiao&widen=1&max_behot_time=0&max_behot_time_tmp=0&tadrequire=true
```

UA: 普通 PC UA 即可（`User-Agent: Mozilla/5.0 ...`）

## 关键字段坑：无 `article_url`，用 `group_id`/`item_id`

feed 返回的 item 字段：
```
abstract, article_genre, behot_time, comments_count, group_id, group_source,
has_gallery, image_list, image_url, is_feed_ad, item_id, media_avatar_url,
media_url, middle_image, middle_mode, more_mode, single_mode, source,
source_url, tag_url, title
```

**无 `article_url` 字段**。拼文章 URL 用 `group_id`（或 `item_id`，值相同）：
```
https://m.toutiao.com/article/{group_id}/
```

## 频道映射（实测可用 vs 返回 0）

| 领域 | 频道参数 | 实测结果 | 备注 |
|---|---|---|---|
| 社会民生 | `news_society` | **0 条** | 改用 `news_hot`（综合热榜）补 |
| 财经养老 | `news_finance` | 10 条 | 正常 |
| 消费争议 | `news_consumption` | **0 条** | 改用 `news_food` 补 |
| 娱乐八卦 | `news_entertainment` | 11 条 | 正常 |
| 健康生活 | `news_health` | 10 条 | 正常 |

**实测可用频道**（按返回量排序）：`news_hot` 14 条、`news_entertainment` 11 条、`news_history` 11 条、`news_finance` 10 条、`news_health` 10 条、`news_tech` 10 条、`news_military` 10 条。

**死频道**（返回 0）：`news_society`、`news_consumption`。

## 去重机制

同频道第二次抓取同批文章会被正确拒绝（`正文同源转载`），攒批时自动去重生效。

## 攒批清洗规则实测

- 字数 < 800 拒绝（快讯）
- AI 味分 > 30 拒绝（AI批量稿）
- 正文同源转载拒绝
- 实测：第一批 31 篇抓取、15 篇入锚点池、9 篇被清洗规则拒绝
- 锚点池 AI 味分布（N=15→26）：min 0.0 / P25 7.6 / 中位 10.7 / P75 15.0 / max 27.4
