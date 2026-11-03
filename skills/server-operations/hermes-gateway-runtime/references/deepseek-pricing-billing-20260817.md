# DeepSeek 2026-08-17 涨价 + 账单 CSV 分析 + 大模型价格性能对比

> 2026-08-17 实测。老板问「涨了多少/对比其他大模型」时的完整参考。

## 一、DeepSeek 8/17 涨价（峰谷价，¥/M tokens）

- 生效：2026-08-17 0 时（北京）。高峰=北京 9:00-12:00、14:00-18:00；高峰=空闲×2。
- 官方公告：api-docs.deepseek.com/zh-cn/news/news260813/（正文价格表是图片，未列旧价——历史价要靠媒体/archive 补）。

| 模型 | 项 | 8/17前旧价 | 新·空闲 | 新·高峰 | 涨幅(空闲/高峰) |
|---|---|---|---|---|---|
| V4 Flash | 输入命中 | 0.02 | 0.05 | 0.10 | +150%/+400% |
| V4 Flash | 输入未命中 | 1 | 1.5 | 3.0 | +50%/+200% |
| V4 Flash | 输出 | 2 | 4.5 | 9.0 | +125%/+350% |
| V4 Pro | 输入命中 | 0.025 | 0.15 | 0.30 | +500%/+1100% |
| V4 Pro | 输入未命中 | 3 | 4.5 | 9.0 | +50%/+200% |
| V4 Pro | 输出 | 6 | 13.5 | 27.0 | +125%/+350% |

- **实际账单涨幅**（同用量，8/17 实测）：flash 10.91→34.13、pro 0.85→2.38，合计 11.76→36.51 元/天（**+211%，约 3 倍**）。
- 主力驱动：①缓存命中价涨最狠（flash +150%~400%），命中率高的用户被砍最痛；②高峰时段（9-12 点）成本占 58%，错峰省一半。
- 兼容：`deepseek-chat`/`deepseek-reasoner` 2026-07-24 停用，映射 V4 Flash/Pro——配置写旧名要核实际账单模型名。

## 二、DeepSeek 账单 CSV 解析（后台导出的两种 CSV）

**cost CSV**（按小时+模型，每行 = 时段×模型成本）：
```
user_id,start_time_iso,end_time_iso,model,wallet_type,cost,currency
...,2026-08-17T00:00:00+08:00,...,deepseek-v4-pro,Paid,0.1178574,CNY
```
**amount CSV**（用量明细，type 分 input_cache_hit_tokens / input_cache_miss_tokens / output_tokens / request_count）：
```
...,model,api_key_name,api_key,type,price,amount
...,deepseek-v4-flash,更新,sk-...,input_cache_hit_tokens,0.00000005,22710144
```
- **金额 = price × amount**（price 是单 token 价：0.00000005 = 0.05 元/M；amount 是 tokens 数；request_count 行无 price）。
- 注意：**8/17 当天 CSV 已是新价**（空闲/高峰价自动区分）；12:00-13:00 是空闲时段（高峰 9-12/14-18 之外）。
- 分析要点：分时段汇总找高峰占比（本次 9-12 点 58%）、按 type 找大头（本次缓存命中 3.3 亿 tokens=23 元，占 63%）、算旧价对比涨幅。
- 余额查询 API（无用量明细）：`GET https://api.deepseek.com/user/balance`（Bearer API key）→ balance_infos。

## 三、其他大模型价格（2026-08-17，¥/M tokens，输入未命中→输出，$1=¥7.2）

| 模型 | 输入 | 输出 | LMArena 综合 |
|---|---|---|---|
| DeepSeek Flash 空闲/高峰 | 1.5/3.0 | 4.5/9.0 | #82 / 1435 |
| DeepSeek Pro 空闲/高峰 | 4.5/9.0 | 13.5/27.0 | #51 / 1458 |
| GPT-5.6 Luna | 7.2 | 43.2 | #62 / 1450 |
| GPT-5.6 Terra | 18 | 108 | #43 / 1464 |
| GPT-5.6 Sol | 36 | 216 | #19 / 1481 |
| Claude Sonnet 5 | 14.4 | 72 | #42 |
| Claude Opus 5 | 36 | 180 | #8 / 1488 |
| Gemini 3.7 Flash（促销到12/31） | 5.4 | 27 | #9 / 1490 |
| Gemini 3.1 Pro | 14.4 | 86.4 | #11 |
| 豆包 Doubao-Pro | 6 | 30 | 文本榜未查到 |
| Kimi K3 | 20 | 100 | #13 / 1489 |
| Qwen 3.8 Max | 12 | 36 | #5 / 1497 |
| Qwen 3.7 Plus | 2 | 8 | #47 / 1459 |
| GLM-5.2 | 8 | 28 | #33 / 1471 |

**结论（DeepSeek 涨价后）**：
- 仍比海外同档便宜（Flash 峰时 9 元 vs Luna 8.64 元，仅差 4%）；**面对 Qwen/GLM 只有谷时优势稳，峰时不再是默认最低价**。
- V4 Pro vs Qwen 3.7 Plus：性能几乎同档（1458 vs 1459），Qwen 2/8 更划算。
- 写作场景（输出大）：Flash 谷时 4.5 最低；性价比王是 Gemini 3.7 Flash（写作榜#3）和 Qwen 3.8 Max（中文高质量 12/36）。

## 五、订阅套餐（Coding Plan）vs API（2026-08-17 补充）

| 套餐 | 月费（$→¥，×7.2） | 额度 | API 日回本点 |
|---|---|---|---|
| ChatGPT Plus | $20→144 | GPT-5.6 Sol Medium/High；5小时窗口动态重置 | 4.8 元/天 |
| ChatGPT Pro 5x/20x | $100/$200→720/1440 | Plus 的 5x/20x | 24/48 元/天 |
| Claude Pro | $20→144（年付折月 122.4） | Free 的 5x；5小时窗口+周限 | 4.8 元/天 |
| Claude Max 5x/20x | $100/$200→720/1440 | Pro 的 5x/20x | 24/48 元/天 |
| Google AI Pro/Ultra 5x/20x | $20/$100/$200 | 免费档 4x 起 | 4.8/24/48 元/天 |
| GitHub Copilot Pro/Enterprise | $10/$39 | $15 AI credits + 无限补全 | 2.4/9.36 元/天 |

**关键结论：**
- **订阅 ≠ API 额度**——不能跑网站后端/批量自动化；「人在回路」（写文章/编程交互）用订阅，生产服务/自动化用 API，必要时两者并用。
- **Codex 订阅额度实测**（Reddit/OpenAI 社区，官方不公布固定 token 数，口径=「5小时窗口+周限」动态制）：Plus ≈340 万 tokens/5小时窗口（一次 2.4M tokens 用掉 71% 额度、折合 API $6.66）；$100 Pro 有人 Sol Extra High 2 小时打满；$200 分化大（任务形态比请求数更决定续航）。
- **对重度 API 用户（3.3 亿 tokens/天 = 1095 元/月）：订阅额度差 100 倍（Plus 5 小时才 340 万 tokens），完全扛不住批量自动化——订阅省不了这个钱，只能错峰 + 换便宜 API。**
- 国产（Qwen/豆包/Kimi/GLM）**无 API 订阅制**（纯按量充值）；千问的「token plan」= 阿里云百炼预付费资源包（按量为主，折扣待核）；国产「会员」是 App 端人用，接不了 API/自动化。

## 六、模型对比任务的口径教训（2026-08-17 用户纠正）

1. **必须用峰谷价对比**（不能只用空闲价）——DeepSeek 有峰谷，对比时两个价都要给。
2. **模型要全**（V4 Flash + V4 Pro 都算进去，别漏）。
3. **每个厂商多比 2-3 个版本**（GPT-5.6 Sol/Terra/Luna 等）。
4. **同时对比性能**（LMArena 排名/Elo、SWE-bench、写作榜），不只是价格。
5. **订阅套餐（Coding Plan）也要比**——用户会问「其他模型不是有 plan 吗」；只比 API 单价会漏掉「订阅 vs API」的省钱维度。
6. 数据来源：LMArena arena.ai/leaderboard（实时榜）、厂商官方价页、SWE-bench verified、OpenAI/Anthropic help center（订阅额度）。
