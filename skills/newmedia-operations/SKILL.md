---
name: newmedia-operations
description: 全平台行业知识库映射表，涵盖抖音/小红书/快手/视频号/公众号5个平台，用于工作流节点5行业适配表的路由参考。
---

# 行业知识库映射表

## 结构总览

```
wiki/concepts/
├── industry-strategy-overview.md           # 🎯 抖音7赛道总览
├── industry-catering.md                    # 🍜 餐饮（3案例）
├── industry-education.md                   # 🎓 教育/知识付费（3案例）
├── industry-emotion.md                     # 💚 情感励志（3案例）
├── industry-fitness.md                     # 💪 健康健身（3案例）
├── industry-maternal.md                    # 👶 母婴（2案例）
├── industry-finance.md                     # 💰 财经商业（5案例）
│
├── xiaohongshu-industry-strategy.md        # 📕 小红书6赛道总览
├── xiaohongshu-industry-beauty.md          # 💄 美妆个护（难做，不深入）
├── xiaohongshu-industry-food.md            # 🍜 餐饮探店
├── xiaohongshu-industry-home.md            # 🏠 家居家装
├── xiaohongshu-industry-education.md       # 🎓 教育/知识付费
├── xiaohongshu-industry-pet.md             # 🐱 宠物
├── xiaohongshu-industry-fitness.md         # 💪 运动健身
├── xiaohongshu-industry-fashion.md         # 👗 服饰穿搭
├── xiaohongshu-industry-maternal.md        # 👶 母婴育儿
│
├── kuaishou-industry.md                    # 💥 快手行业策略（5赛道+3案例+vs抖音对照）
│
├── wechat-video-industry.md                # 🔗 视频号行业策略（7赛道+各赛道写法+案例）
│
├── wechat-public-account-industry.md       # 📰 公众号行业策略（7赛道+各赛道写法+案例）
│
├── xiaohongshu-title-and-copy-templates.md # 小红书标题公式与文案模板
├── xiaohongshu-ces-algorithm.md            # 小红书CES算法
├── security-hardening.md                   # 安全加固方案

wiki/strategies/
├── douyin-kuaishou-publishing-strategy.md  # 抖音快手发布策略
├── kuaishou-content-strategy.md            # 快手内容策略
├── xiaohongshu-publishing-strategy.md      # 小红书发布策略
├── wechat-video-content-strategy.md        # 视频号内容策略
├── wechat-public-account-strategy.md       # 公众号推文策略

wiki/references/
├── xiaohongshu-community-rules.md          # 小红书社区规范
```

## 各平台行业文档引用

| 平台 | 节点5适配表 | 文档路径 |
|:----|:----------|:--------|
| 抖音 | industry-*.md 7份 | `wiki/concepts/industry-{catering,education,emotion,fitness,maternal,finance}.md` |
| 小红书 | xiaohongshu-industry-*.md 7份 | `wiki/concepts/xiaohongshu-industry-{food,home,education,pet,fitness,fashion,maternal}.md` |
| 快手 | kuaishou-industry.md 1份 | `wiki/concepts/kuaishou-industry.md` |
| 视频号 | wechat-video-industry.md 1份 | `wiki/concepts/wechat-video-industry.md` |
| 公众号 | wechat-public-account-industry.md 1份 | `wiki/concepts/wechat-public-account-industry.md` |

## 核心铁律

**写任何内容前（所有平台），必须先判断客户行业，再读对应的行业策略文档。不准凭感觉写。**

### 🎯 先搜数据 再动笔 不准凭逻辑推
写任何营销/推广/内容方案前 必须执行：
1. 确认行业知识库文档存在 → 有就读 没有就先搜该行业各平台近期爆款（至少5条）拆结构建文档
2. 搜数据验证自己的判断 不准觉得「这样应该行」
3. 拆标题/开头/结构/评论区 找到可复用的规律
4. 搜不到确切依据 → 标注「无确切来源 需实测验证」

### ⚠️ 避坑：不要写模板化方案
用户明确纠正过：「太模板化了」「天天发广告」
- 不要列12345的模板结构 要站在目标用户视角想他们需要什么
- 推广内容不等于罗列功能 要设计人设+内容线+转化路径
- 参考小鹿自己出的推广方案：大叔人设 + 三条内容线（引流款/信任款/收割款）
- 小鹿推广核心策略文档已建：`wiki/concepts/ai-tool-recommend-strategy.md`

### 📌 用户偏好铁律：输出格式
- 发送密码、Token、API Key、URL等干货时**禁止加任何标点符号**（。，！？等），用户明确纠正过
- 成本/价格数字必须亲自实测或查官方定价，禁止脑补（如「年费480」无来源的被用户抓过）
- 分析结论必须有数据来源标注，禁止「大概」「可能」「应该」
- 结论先行：先说结论再给理由，禁止先铺推理再出结论

## 数据复盘铁律（2026-07-17 用户强制要求）
- 各平台复盘指标必须有来源，不可凭经验编造
- 已建成数据复盘文档 `wiki/concepts/data-review-template.md`，含抖音/小红书/快手/视频号/公众号各平台指标参考线
- 抖音数据来源：官方算法公开框架+新榜
- 小红书数据来源：CES评分官方说明+2026新版流量机制
- 快手数据来源：飞瓜快手本地生活报告
- 视频号数据来源：友望数据生态报告
- 公众号数据来源：2025新媒体内容生态研究报告

## 建立历史

| 日期 | 平台 | 改动 |
|:----|:----|:-----|
| 2026-07-16 | 抖音 | 7赛道文档+总览+工作流引用 |
| 2026-07-16 | 小红书 | 9份行业文档+3份通用文档+工作流引用 |
| 2026-07-17 | 快手 | kuaishou-industry.md 含5赛道+3案例+vs抖音对照 |
| 2026-07-17 | 视频号 | wechat-video-industry.md 含7赛道+各赛道写法 |
| 2026-07-17 | 公众号 | wechat-public-account-industry.md 含7赛道+各赛道写法 |
