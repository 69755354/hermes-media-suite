---
name: model-cost-analysis
description: 大模型 API 成本分析。触发：模型价格/涨价对比/token消耗分析/怎么省token/哪个模型划算/成本优化。
version: 1.0.0
author: hermes
license: internal
metadata:
  hermes:
    tags: [cost, llm-pricing, token-optimization, deepseek, api]
    related_skills: [hermes-storage-health]
---

# 大模型 API 成本分析（价格对比 / 涨价 / token 优化）

用户问「X 涨了多少」「哪个模型便宜」「怎么省 token」「对比下价格」时的完整方法论。2026-08 价格快照见 `references/2026-08-price-snapshot.md`（会过时，先看它再查证）。

## When to Use
- 模型 API 涨价/价格对比/订阅套餐（Coding Plan）对比
- 账单异常（token 暴增、成本上涨）——**先查超长会话**（见 hermes-storage-health「超长会话」节），别先怀疑用量
- 优化方案：怎么降 token / 省成本

## 核心方法论

### 1. 价格获取（真实来源，不编造）
- **官方价页直抓**（python urllib + 正则）：DeepSeek `api-docs.deepseek.com/zh-cn/quick_start/pricing`；但定价页常是 JS 渲染/图片，抓不到就派 codex 用 Tavily 搜 + 标来源
- **注意峰谷价**：DeepSeek 2026-08-17 起高峰（北京 9-12、14-18 点）翻倍，空闲半价——**对比必须同时给峰价和谷价**（用户会点名要峰谷对比）
- **涨价幅度**：官方不给历史价 → 搜新闻（北京日报/第一财经/澎湃）+ 历史公告；对比时给出「旧价 vs 新价 vs 涨幅 %」

### 2. 成本结构分析（账单 CSV）
用户给账单 CSV（cost + amount 两个文件）时：
```python
# amount CSV：price（每 token 单价）× amount（tokens）= 成本；type 有 input_cache_hit/miss/output
# 算：总成本、按模型拆、按时段拆（高峰 vs 空闲）、按类型拆（命中/未命中/输出）
# 关键指标：缓存命中率 = hit/(hit+miss)；平均上下文 = 总 tokens/请求数
```
**判断钱在哪（2026-08-17 实测结论）：**
- 缓存命中输入单价极低（0.05-0.15 元/M）但量巨大 → 占成本大头（63%）
- 未命中（1.5-9 元/M）和输出（4.5-27 元/M）单价高但量小 → 真正的漏点
- **缓存命中率 99%+ 是最值钱的资产**：命中 vs 未命中单价差 32 倍——任何优化先问「会不会砸缓存」

### 3. 优化杠杆（按性价比排序，2026-08-17 两版方案对抗后的定论）
1. **超长会话归档**（零风险、收益最大）：sessions 表 cache_read_tokens 找大头 → UPDATE archived=1（见 hermes-storage-health）
2. **输出限长**（max_tokens 分用途：分类 800/分析 2000/初稿 3000/长篇段 4000）+ 分段续写
3. **前缀字节级冻结**（system prompt 稳定 = 保缓存命中；动态字段后置到用户消息侧）
4. **错峰**：批处理排 12-14 / 18 点后（峰谷差 2 倍）；先查自己用量落在峰还是谷
5. **模型路由**：日常/正文用 Flash（输出 4.5-9），高难才 Pro（13.5-27）
6. **文档索引按需检索**（不整篇塞上下文）
7. **⚠️ 别做：压缩阈值激进调低（如 500K→96K）**——滚动摘要改前缀 = 缓存全废 = 净亏（codex 方案被 Claude 对抗审查打掉：40 次摘要 ≈ 多花 21 元 > 省的 6.9-11.6 元）

### 4. 多维度对比（用户硬要求，缺一不可）
用户问「对比其他模型」时，必须给全：
- **价格**（输入未命中/输出，人民币/百万 tokens，峰谷分开）
- **性能**（LMArena 综合 Elo + 写作榜排名，codex Tavily 搜）
- **订阅套餐（Coding Plan）**：ChatGPT Plus/Pro、Claude Pro/Max、Gemini Pro/Ultra、Copilot——**注意国产（Qwen/豆包/Kimi/GLM）无 API 订阅制**（App 会员接不了 API）；千问的 Token Plan 是「人用 Credits」禁止脚本/批量（咱们自动化用不了）
- **利弊**（每个方案列利/弊/回滚——用户会点名要）
- **峰谷价**（DeepSeek 必须）
- 最后给「写作/API 场景各推荐谁」

### 5. 方案评审纪律（用户 0817 纠正）
- 方案类必须 codex/claude 出（智力活外包），Hermes 只执行
- 用户要「让 claude 也出个方案」= 双执行器对抗，Claude 默认不调、用户点名才用（memory 规则）
- 评审时黑帽先问：**改核心 vs 收益**——省 17-20 元/天但改 Hermes 核心（rollover/冷热会话）风险 > 收益时，用户倾向「先不改」
- 用户会质疑「0风险」声称——没有真正零影响的改动（改配置也是行为变更），诚实标注实施风险

### 6. 免费/零成本模型通道（2026-08-23 梳理，用户问「内置哪些免费模型」时的答案）

Hermes 不内置模型本体，内置的是「接入通道」（35+ provider 插件）。免费通道按真零成本排序：

1. **本地模型（真·免费，要算力）**：custom provider 接 Ollama/本地 OpenAI 兼容端点，API 成本 0，吃本机 GPU/内存（新加坡机 4GB 只能跑 qwen3 0.5B/1.5B 小模型）
2. **Google Gemini 免费层**：内置 gemini provider，`gemini-3.6-flash` 是默认辅助模型，API 免费额度档
3. **OpenRouter `:free` 模型**：内置 openrouter provider，开源模型免费档（qwen/deepseek 蒸馏等），有速率限制
4. **Nous Portal**：`hermes auth add nous` OAuth，Nous 自家通道
5. **HuggingFace 免费推理**：内置 huggingface provider

**主对话 vs 执行器是两条线（用户常混淆）：** 主对话模型（微信/飞书聊天本体）当前是 DeepSeek V4；codex 是 OpenAI 系执行器（gpt-5.6-sol，走订阅额度），两者不是一回事——「接了 codex ≠ 主对话接了 GPT」。想主对话用 GPT 需另配 OpenAI provider（api.openai.com 新加坡机直连通，HTTP 401 = 网络通只缺 key）。

## 关键事实（2026-08 快照，详见 references）
- DeepSeek 峰谷价、各模型价格/性能、订阅套餐表、千问 Token Plan Credits 机制
- **Ox Alpha（stealth/ox-alpha）**：OpenRouter 2026-08-20 匿名免费模型（1M 上下文/128K 输出/免费预览期/DeepSWE 80%）——情报见 `references/ox-alpha-20260820.md`

## 执行要点
- 价格数字必须标来源 URL（准确性铁律）
- 派 codex/claude 调研时把已知价格/用量数据打包进 prompt（自包含，避免沙箱读文件失败——Claude 沙箱常读不了 ~/.hermes）
- 汇率：美元 ×7.2 转人民币统一口径
