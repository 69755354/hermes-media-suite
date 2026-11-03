# 小鹿权限体系参考（2026-07-21 定稿）

## permissions.json 结构

```json
{
  "levels": {
    "basic": { "video": false, "image_gen": false, "daily_video_limit": 0, "daily_image_limit": 0 },
    "normal": { "video": true, "image_gen": true, "daily_video_limit": 1, "daily_image_limit": 10 },
    "unlimited": { "video": true, "image_gen": true, "daily_video_limit": 9999, "daily_image_limit": 9999 }
  },
  "defaults": { "role": "customer", "level": "basic", "trending_search": true, "copywriting": true, "analysis": true },
  "users": {
    "ou_xxx": { "level": "unlimited" }
  }
}
```

## 配额记录

位置：`/tmp/projects/quota_<YYYY-MM-DD>.json`
格式：`{"date": "2026-07-21", "user_xxx": {"video_used": 0, "image_used": 0}}`
重置：每日自动，不手动清理

## 工具白名单

| 工具 | 允许场景 |
|:----|:---------|
| read_file | 读知识库/接力文档/权限配置 |
| write_file | 写接力文档/复盘/配额记录 |
| web_search | 搜爆款/搜数据 |
| vision_analyze | 看客户图片 |
| terminal + curl | 仅限商业流程出片/娱乐直出/小红书配图 |

所有工具：对客户不提工具名，只说大白话。
