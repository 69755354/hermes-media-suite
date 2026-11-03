# 大模型价格/性能快照（2026-08-17，LMArena 检索日）

> 统一口径：人民币/百万 tokens（未命中输入 → 输出），美元 ×7.2。变动以官方价页为准。

## API 单价对比（含 DeepSeek 峰谷）

| 模型 | 输入 | 输出 | 备注 |
|---|---|---|---|
| DeepSeek Flash 空闲 | 1.5 | 4.5 | 全场输出最低 |
| DeepSeek Flash 高峰 | 3.0 | 9.0 | 仅输 Luna 4% |
| DeepSeek Pro 空闲 | 4.5 | 13.5 | 国产最便宜 |
| DeepSeek Pro 高峰 | 9.0 | 27.0 | 与 Gemini 3.7 持平 |
| GPT-5.6 Luna | 1.44 | 8.64 | 唯一比 Flash 高峰便宜的 |
| GPT-5.6 Terra | 14.4 | 86.4 | |
| GPT-5.6 Sol | 36 | 216 | SWE-bench Pro 64.6 |
| Gemini 3.7 Flash（促销至 12/31） | 5.4 | 27 | 写作榜 #3 |
| Gemini 3.1 Pro（≤200K） | 14.4 | 86.4 | |
| Claude Sonnet 5 | 14.4 | 72 | SWE-bench 85.2% |
| Claude Opus 4.8/5 | 36 | 180 | SWE-bench 96.0% |
| 智谱 GLM-5.2 | 8 | 28 | 综合 #33 |
| 豆包 Doubao-Seed-2.1-Pro | 6 | 30 | Code Arena #25 |
| 通义 Qwen3.8-Max | 12 | 36 | 综合 #5（1497） |
| Qwen3.7-Plus（≤256K） | 2 | 8 | 当前 8 折 1.6/6.4 |
| Kimi K3 | 20 | 100 | 综合 #13 |

## 性能锚点（LMArena 综合 Elo，2026-08-17）
- Qwen 3.8 Max #5（1497）、Claude Opus 5 #8（1488）、Gemini 3.7 Flash #9（1490）、Kimi K3 #13（1489）、GPT-5.6 Sol #19（1481）、GLM-5.2 #33、DeepSeek V4 Pro #51（1458）、V4 Flash #82（1435）

## 订阅套餐（Coding Plan，海外独有）
| 套餐 | 月费（¥） | 额度 |
|---|---|---|
| ChatGPT Plus / Claude Pro / Gemini Pro / Copilot Pro | $20 / $10-20 | 5h 窗口动态，不公布 token 数（Plus 实测 ~340 万 tokens/窗口） |
| Max 5x / Ultra 5x / Pro | $100 | Plus 的 5x |
| Max 20x / Ultra 20x | $200 | Plus 的 20x（纸面单位额度 2 倍） |

- 回本线：API 日耗 4.8 元 → $20 档回本；24 元 → $100 档；48 元 → $200 档
- 订阅不能跑 API 后端/批量自动化；重批量必须 API

## Qwen Token Plan（阿里云百炼）
- 个人 Lite 39 元/月（2500 Credits/7 天）、Standard 139（10000）、Pro 499（40000）；用量包 100 元=20000 Credits（1 元≈200 Credits）
- 夜间 22:00-08:00 Credits 5 折；周额度不用不结转
- **禁脚本/批量自动化/自定义后端**——只给人用交互工具
- 自动化省钱走「AI 通用型节省计划」：8.8 折起（月承诺 1000+ 元 3 个月），最高 6.8 折

## DeepSeek 涨幅（8/17 新价生效）
- Flash 同用量：旧 10.91 → 新 34.13 元（+213%）
- Pro：旧 0.85 → 新 2.38 元（+180%）
- 合计：旧 11.76 → 新 36.51 元（+211%）
- 大头：缓存命中输入（330M → 23 元，命中价涨 150-400%）；高峰时段占 58% 成本
