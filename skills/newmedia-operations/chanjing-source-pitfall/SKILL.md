---
name: chanjing-source-pitfall
description: "Use when 蝉镜数字人头像不对/换来换去. source:0 vs source:1 静默失败."
version: 1.0.0
---

# 蝉镜 source 参数静默失败坑

## 症状

蝉镜数字人视频生成出来后，**数字人头像不对**或**头像在不同帧之间换来换去**，但提交时 API 返回 code:0 success，没有报错。

## 根因

蝉镜 Web 端（chanjing.cc GUI）和 API 端数字人资产**不互通**：
- `source:0` = 调 API 端数字人
- `source:1` = 调 Web 端数字人

如果数字人是在 Web 端克隆的（如小鹿的 C-049f...），提交 create_video 时传 `source:0`，蝉镜不会报"数字人不存在"，而是**静默匹配到别的数字人或公共数字人**，导致生成的视频头像不对。

## 诊断方法

1. 查提交参数 JSON 里的 `source` 值
2. 查数字人创建方式：Web 端克隆 → 必须 source:1；API 端 create_customised_person 创建 → source:0
3. 抽帧对比视频里的数字人面部特征是否与预期一致

## 修复

把 `source:0` 改成 `source:1` 重新提交。Web 端克隆的数字人必须用 source:1。

## 婵镜数字人创建方式

| 创建方式 | 平台 | API 支持 | source 值 |
|:--|:--|:--|:--|
| 视频克隆 | API | ✅ POST /open/v1/create_customised_person | 0 |
| 视频克隆 | Web 端 | ✅ Web GUI | 1 |
| 照片生成数字人 | Web 端 | ❌ API 无此接口 | 1 |
| 文生数字人 | Web 端 | ❌ API 无此接口 | 1 |

**API 端只支持视频克隆**，照片生成和文生数字人只有 Web 端能做。Web 端创建的数字人 API 调用时必须加 source:1。

## API 创建数字人参数（create_customised_person）

```
POST /open/v1/create_customised_person
```

| 参数 | 说明 |
|:--|:--|
| name | 数字人名称 |
| file_id | 视频文件ID（先上传到婵镜文件管理） |
| train_type | both（脸+声）/ figure（仅形象）/ voice（仅声音） |
| resolution_rate | 0=1080p, 1=4K |
| is_remove_bg | 默认false |
| error_skip | 跳过声音克隆失败 |

视频要求：30秒-5分钟，mp4/webm/mov，真人口播露脸视频，公网可访问 URL。

## 实测记录

- 2026-08-31 火龙漫剧 P 段：小鹿数字人 C-049f... 是 Web 端克隆的，提交时传 source:0 → API 返回 success 但生成的视频头像与预期不符，用户发现"头像换来换去"
- 同一个数字人 ID、同一份台词，改 source:0→source:1 后头像恢复正常

## 查询视频状态正确接口

```
GET /open/v1/video?id={task_id}&source=1
```

- status: 10=处理中, 30=完成
- progress: 0-100
- video_url: 下载链接

注意：`/open/v1/video_status` 和 `/open/v1/video/status` 都返回 404，正确接口是 `/open/v1/video`。
