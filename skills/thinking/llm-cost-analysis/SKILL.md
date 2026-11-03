---
name: llm-cost-analysis
description: 模型涨价/价格对比/成本账单/token优化。触发：查DeepSeek价格涨幅、对比模型、分析账单、降token。
---

# LLM 成本分析与模型选型

## 触发
- 模型涨价（DeepSeek 等）：查当前价、算涨幅
- 对比各家模型价格（API 单价 / 订阅套餐）
- 分析 DeepSeek 后台导出的成本/用量 CSV
- 优化 token 消耗（降成本）
- 模型选型（写作 / 编程 / 批量场景）

## 核心流程

### 1. 官方价格抓取
- DeepSeek 官方定价：`api-docs.deepseek.com/zh-cn/quick_start/pricing`（JS 渲染，用 python 抓文本解析；**峰谷价**：高峰=北京 9:00-12:00、14:00-18:00 价格翻倍，其余空闲=半价）
- 历史价格：官方公告（如 news260813）正文常只有图片无旧价 → 用新闻源（北京日报/第一财经/爱范儿）或 archive.org（国内可能被墙，超时就换路）
- 汇率：美元 ×7.2 → 人民币，统一口径「人民币/百万 tokens」

### 2. 成本账单 CSV 解析（DeepSeek 后台导出）
- **amount CSV**（列：user_id/start_time/model/api_key/type/price/amount）：
  - `price` = 每 token 单价（2026-08 新价：flash 空闲 0.00000005 缓存命中 / 0.0000015 未命中 / 0.0000045 输出；高峰翻倍；pro 约 3 倍）
  - `amount` = tokens 数；**成本 = price × amount**
  - `request_count` 行无 price（请求计数不算钱，不参与金额计算）
- **cost CSV**：按 小时×模型 的成本合计
- 分析维度：按模型（flash vs pro）、按小时（高峰/空闲占比）、按类型（缓存命中/未命中/输出）
- 关键判断：
  - 缓存命中率高（>99%）= 好，但量大仍是大头（330M 命中 → 23 元）
  - 平均 token/请求 >10 万 = 每次上下文太大（问题在输入量，不是请求数）
  - 高峰时段占比 >50% = 错峰空间大

### 2.5 本地真实用量（Hermes 侧诊断优先查这个，0819 实测）

用户报「token 消耗过多」时，先查本地数据源，不靠猜：

- **`/home/ubuntu/.hermes/state.db` 表 `session_model_usage` = 真实 usage 记录**：列含 session_id/model/api_call_count/input_tokens/output_tokens/cache_read_tokens/cache_write_tokens/reasoning_tokens/estimated_cost_usd/actual_cost_usd。按 session_id+model 聚合可看出：长会话输入量、缓存读取量（单会话可达 806M）、reasoning 占比。这是诊断大头的主数据源。
  - **⚠️ first_seen/last_seen 是 unix 时间戳（float 秒），不是字符串**（2026-08-24 实测）：`WHERE last_seen >= '2026-08-24'` 字符串比较**永远返回 0 行**。正确写法：`start = datetime(2026,8,23,tzinfo=timezone(timedelta(hours=8))).timestamp()` 再用数字比较；活跃会话过滤用 `last_seen >= start AND first_seen <= end`。
  - 查每日消耗时注意缓存读（cache_read_tokens）常是输入的几十倍（418M vs 3M）——命中价极低，别拿它吓用户；先报 输入/输出 token，再单独说缓存命中占比。
- `wiki/shop-info/costs.db` + `costs.jsonl` **只是 cost-meter 验收测试数据**（几行验证记录），不是真实账单，别拿它算成本。
- `~/.codex`（~984M）说明 codex 调用量大，但 codex token 走 OpenAI 通道，要另查 codex 日志/账单，不在 state.db。
- **claude（Bedrock）通道 usage 在 jsonl 的 message.usage，直接可读（2026-08-24 修正，推翻早前「无 usage」结论）**：`~/.claude/projects/**/*.jsonl` 每条 assistant 消息的 `message.usage` 带完整 usage（`input_tokens`/`cache_creation_input_tokens`/`cache_read_input_tokens`/`output_tokens`），`message.model` 也有模型名。早前「claude 无 usage 记录」是**查询脚本 bug**（查 `d.get('usage')` 顶层而不是 `d.get('message',{}).get('usage')`）——先看一条 assistant 消息完整结构再写聚合，别凭 grep 下「无记录」结论。codex 侧同理：`~/.codex/sessions/**/rollout-*.jsonl` 带 `token_count` 字段（992 个里 968 个 98% 覆盖，全量 13.7 亿 token），也不是无记录。
- **轮数统计必须按 message.id 去重（2026-08-24 claude 评审实测）**：同一次 API 调用的 text/thinking/tool_use 被拆成多条 jsonl 记录——160 条 assistant 记录按 `message.id` 去重后只有 **68 次真实调用**。按条数数轮虚高 ~2.4 倍（早前「160 轮 × 1 万注入 = 160 万」的统计假象），轮数 = 去重后的 message.id 数 ≈ 工具调用数 × 1.9
- **DS V4 Flash 上下文「纸面 1M，实际缩水」查证链（2026-08-24）**：官方 pricing 页纸面=上下文 1M / 输出 384K / 并发 2500；但三个实际坎——① max_tokens 参数上限官方文档没写死（「取值范围详见文档」但无具体数字），实际输出可能到不了 384K；② 思考模式默认开，reasoning tokens 计入输出预算，实际可用输出缩水；③ Hermes 本机 `compression.threshold: 0.12`（config.yaml）→ 会话到模型窗口 12%（约 12 万 token）就触发压缩归档，**Hermes 主对话永远不会真塞满 1M**。回答「1M 上下文实际多少」：纸面 1M，直调 API 敢塞但输出受限+思考吃预算，走 Hermes 顶多 10 万级就压缩。查证工具：`GET /models` 元数据接口只返回 id/owned_by 不返回 context_length，要查官方 pricing 页
- **真实成本结构：thinking token 是大头（2026-08-24 claude 评审实测，$12.78/典型分析会话）**：输出 45.4%（其中 **99% 是不落盘的 thinking**）> 缓存写入 27.2% > 缓存读取 27.1% > 未缓存输入 0.3%。优化火力应打「减少 thinking/输出」不是「压固定前缀」——压 AGENTS.md 前缀只省缓存读（$0.50/M）约 $0.12/任务，改稳定前缀触发缓存失效反而 $0.55；按字节估算成本会低估 thinking 78 倍。打包会话 $16.04 比执行会话还贵（打包环节同样烧 thinking）。
  - **🔴 模型确认必须实测自报，attest 硬编码不可信（2026-08-24 血泪）**：attest 行硬编码 `claude claude-sonnet-4` 但实测是 **claude-opus-5**——按 attest 估成本低估约 50%。实测法（成本极低的一句话）：
    ```bash
    CLAUDE_CODE_USE_BEDROCK=1 AWS_REGION=us-east-1 AWS_BEARER_TOKEN_BEDROCK="$(cat ~/.hermes/claude_bedrock_key)" \
    claude -p "只回复你当前的模型ID" --output-format text
    ```
  - **估算**：输出 ≈ 产物文件字节数（UTF-8 中文 3 字节/字 ≈ 1 token/字）；输入 ≈ 任务书 + DATA_SOURCE 文件总字节 ≈ 字数 × 会话轮次（claude code 多轮重复带上下文，粗估乘 2-3 倍）；轮数 = jsonl 里 `type=='assistant'` 消息数 ≈ 工具调用数 × 1.9
  - **轮数为什么这么多（2026-08-24 实测拆解，用户「这太臃肿了吧」）**：一轮 = 一次 API 调用 = 一个动作。读 1 个文件 ≈ 2 轮（发工具 + 看结果）；大文件一次读不完要分段（huoshan SKILL 196KB 一个文件 Read 9 次）；写 1 个文件 ≈ 2-4 轮（分段写 + Edit）；自检逐项跑 ≈ 每项 1-2 轮。典型分析任务（读 6 文件 + 写 3 文件 + 自检 10 项）自然 30-55 轮——不是执行器低效，是动作数本身多。对照实测：简单任务 1 轮 11,194 tokens
  - **派活瘦身四招（2026-08-24 总结，核心：把「让它自己找」变「给它现成的」）**：①任务书内嵌关键定案（4 段结构/贴片时点/台词时码直接写进任务书，执行器就不用翻源文件全文）；②给模板（分镜/分段表模板照着填，省设计结构轮数）；③指定自检脚本（用现成 `verify_storyboard_checks.py` 一次跑完 25 条，替代逐项 grep——自检 10-15 轮 → 2-3 轮）；④数据源给精炼版或指向具体行号（减少大文件重复读）。瘦身后典型任务 30-55 → 15-25 轮，砍一半
  - **价格锚（2026-08-24 实查）**：**本机 Opus 5 = $5/M 输入、$25/M 输出、缓存 $0.50/M**（2026-07-24 发布）；Sonnet 4/4.6 = $3/$15；Sonnet 5 更便宜；GPT-5.6 Sol = $5/$30。×7.2 汇率；输入侧误差大，汇报给范围不给单点
- `~/.hermes/cron/output/cost-meter-retry-5m/` 是**扣费补偿脚本**（输出 `{"retried": 0}`），不是 token 统计，别拿它当用量。
- config.yaml 的 `compression` 段（threshold/target_ratio/protect_first_n/protect_last_n）是当前压缩策略，诊断「上下文太大」必读。
- 用户习惯拿 DeepSeek 平台截图对账（9 亿级 token ≈ 100 元），汇报前先核截图数字，别误读界面序号。

### 3. 价格对比（⚠️ 必须用峰谷价）
- 用户明确要求：对比同时给 DeepSeek **空闲 + 高峰**价（只给空闲价会被纠正；高峰是实际成本大头）
- 对比表列：输入未命中 / 输出（人民币/百万 tokens）
- 2026-08 实测锚点：Flash 空闲 1.5/4.5 全场最低；Flash 高峰 3/9 仅输 GPT-5.6 Luna（1.44/8.64）；Pro 空闲 4.5/13.5、高峰 9/27（与 Gemini 3.7 Flash 27 持平）；国产旗舰输出 GLM 28 < 豆包 30 < Qwen 36 < Kimi 100

### 4. 性能对比
- LMArena 榜（arena.ai/leaderboard）综合 + 创意写作榜（Elo 分数，标注快照日期）
- SWE-bench Verified / Pro 口径不同不混填
- 2026-08 锚点：第一梯队 Qwen 3.8 Max #5、Claude Opus 5 #8、Gemini 3.7 Flash #9、Kimi K3 #13；DeepSeek V4 Pro #51、Flash #82

### 5. 订阅套餐（Coding Plan）
- 海外有：ChatGPT Plus/Pro（$20/100/200）、Claude Pro/Max（$20/100/200）、Gemini Pro/Ultra、GitHub Copilot（$10/39）
- 额度是「5 小时窗口 + 周限额」动态制，**官方不公布固定 token 数**（Reddit 实测 Plus ≈ 340 万 tokens/窗口）
- **国产无 API 订阅**：Qwen/豆包/Kimi/GLM 按量充值；App 会员不能接 API/自动化
- Qwen 有 Token Plan（Lite 39 元/2500 Credits 等，1 元≈200 Credits 用量包，夜间 5 折）——但**禁脚本/批量自动化**，只给人用交互工具
- 订阅 vs API 判据：人用（写文章/编程交互、日耗 <$20 档回本线）→ 订阅划算；批量自动化/后端/CI → 必须 API

### 6. token 优化杠杆（按优先级）
**⚠️ 2026-08-17 Claude 版对抗审查结论：缓存保护优先，压缩要谨慎**
- **缓存命中率是全系统最值钱的资产**：命中 0.07 元/M vs 未命中 2.24 元/M（差 32 倍）。任何优化先问：会不会把命中 token 变成 miss？
- **压缩阈值调低（如 500K→96K）可能净亏**：高频压缩反复砸缓存前缀 → 当前请求整包 miss（~0.5 元/次），回本需 ~70 轮。codex 版方案（96K 压缩）被 Claude 对抗审查否决
- **别用「总 token 下降了」证明省钱**——只看钱和 miss，总 token 是骗人指标
- 三条底线：命中率 <97% 停手；miss >8M/天自动回滚；只看钱和 miss
- 会话尾巴/剩余轮次 <15 时压缩纯亏钱（防亏钱判据）

按此修正后的优先级：
1. **缓存稳定（零风险纯赚）**：前缀字节级冻结（冻结 system/tool 前缀，动态字段后置，改动走版本号）；Hermes `compression.threshold` 调低必须灰度（0.5→0.4 试 2 天），且**先确认当前平均上下文是否远低于阈值**（若 500K 从未触发，调低=从"从不压缩"变"高频压缩"，风险大）
2. **输出限长 + 分段续写**：max_tokens 按任务（分类 800/分析 2000/初稿 3000/长篇段 4000）；长篇用分段续写不吃超长输出
3. **文档索引按需检索**：不破坏前缀（检索结果追加在会话尾部），直接砍未命中
4. **模型路由**：正文/批量用 flash（便宜档），pro 只做结构/高难（白名单 + 升级原因）
5. **错峰调度**：批处理排 12-14 / 18 点后（高峰价 2 倍）——先确认实际高峰小时落在峰/谷
6. **会话滚动交接 rollover（替代原地压缩）**：160K 硬上限触发时结束旧会话开新会话，手写交接包（大纲+状态+最近 2 轮+约束），人工过一遍交接包再续；先单会话灰度
7. 请求合并（收益小，~0.35 元/日，可能不值延迟代价）

## Pitfalls
- **成本回填根因 + 独立脚本（2026-08-19 实测修复）**：`actual_cost_usd` 全 0 的根因不是没回填逻辑——Hermes 内置回填（`conversation_loop.py` → `estimate_usage_cost`）用 `usage_pricing.py` 的 `_OFFICIAL_DOCS_PRICING` 查价，key 是 `(provider, model)`；本机 config `provider: custom_custom`，价格表只有 `("deepseek", ...)` → **匹配不上 → 价格 0 → 金额永远 0**。修复：独立脚本 `~/.hermes/scripts/cost_backfill.py`（Hermes 写，价格取自 references/deepseek-pricing-202608.md，flash/pro 分开，高峰加权 1.2，写 sessions.actual_cost_usd + cost_status=estimated，支持 --dry-run），实测 9.94 天 12 会话回填 177.67 元，已挂日频 cron `0 1 * * *`。广州用同脚本加 `--db profiles/customer/state.db`。注意 `cost_meter.py` 是**客户计费**（customer 扣费）不是 Hermes 会话成本回填——排查金额 0 别往 cost_meter 查
- **reasoning 不是独立成本项（2026-08-19 claude 实测）**：DeepSeek 把思考链计入 completion——`session_model_usage` 45 行中 `reasoning_tokens > output_tokens` 的行数为 0。算成本时**不能单独加一笔 reasoning 费**（否则重复计费）；pro 输出 75.2% 是思考链、flash 35%，已含在输出费内
- **state.db 只覆盖约 24% 账单量（2026-08-19 实测）**：`session_model_usage` 只记 Hermes 主进程 usage，日均 220M token / 21.3 元；老板平台截图 900M/日 ≈ 100 元。约 76% 在 codex（~/.codex 984M 无本地 usage 表）/claude Bedrock/广州机/第二个 DeepSeek key 上。且 `actual_cost_usd` 全 0、`cost_status=unknown`、`cost_source=none`——**成本回填没在跑**。只优化 Hermes 最多动到账单的 21-24%；先补多通道埋点才能验证任何优化
- **压缩阈值触发率是健康判据不是配置默认值（2026-08-19）**：实测 `threshold=0.5` 在 9.94 天只触发 22 次（主调用 0.28%），稳态上下文 273K 长期驻留几乎不压——这是**健康状态**。调低会从「几乎不压缩」变「高频压缩」，每次压缩砸缓存前缀 → 下一请求整包 miss（273K × 1.80 = 0.49 元），加压缩自身 0.22 元 ≈ 每次净支出 0.7 元。「维持阈值不动」是正式措施，不是遗漏
- **高峰占比口径分两种（2026-08-19）**：按调用条数实测 21.1%（8/14-8/19 messages 表 9396 条），按金额口径 references 说 58%——高峰单价翻倍所以 21% 调用量产生约 35% 金额；58% 那个数字可能含别通道（codex 白天调用）。**错峰收益按调用条数口径估（~2.66 元/日），别按金额口径高估**
- **成本恒等式（2026-08-19 定式）**：`缓存成本 = 调用次数 × 平均上下文 × 命中价`。命中率 99.33% 接近理论上限后，**优化空间只剩「调用次数」和「平均上下文」两个乘数**，不是命中率
- **稳态上下文是真实稳态不是峰值（2026-08-19）**：flash 273,513 缓存读/次、pro 202,322——与平台账单 235K/请求交叉验证同量级。每次调用付 273K 命中费是成本地板；最大杠杆 = 稳态 273K→150K（更早 rollover），配合砍调用上限按乘法叠加（×0.55 × 0.80 = ×0.44，不是加法）
- **`input_tokens` 是累计新增，不是单次上下文（2026-08-19 claude 实测纠正）**：真实单次上下文 = `cache_read_tokens / api_call_count`（`ctx_per_call`），两者无相关性——77 万累计的会话单次 316K 反而比 136 万累计的（271K）更贵。按累计值排序会误杀高频短上下文、漏掉低频长上下文，归档/优化排序必须用 ctx_per_call；`api_call_count=0` 时回退累计口径兜底。成本判据用累计 `cache_read_tokens`（实测新加坡最贵会话 3.25 亿缓存读 ≈ 65.5 元，比广州 241 万 input 那个贵三倍）
- **SQL LIKE 的 `_` 是通配符**：`LIKE '%ghp_%'` 会误匹配「ghpX」——搜 token/特殊字符必须用 `ESCAPE '\'` 或 python 字面 `in` 判断（本会话踩过：LIKE 误报 7 条命中，字面重搜为 0）
- 官方价格页 JS 渲染：直接 grep 拿不到价格，要用 python 抓文本再正则解析
- 订阅额度 ≠ API 额度：不能拿订阅跑批量自动化/后端
- **方案归属铁律**：价格分析/优化方案类必须 codex/claude 出（执行者标注），Hermes 只执行落地——用户会问「这是谁出的方案」，Hermes 自产参数不合规
- 优化方案落地：具体参数（阈值改多少）也要执行器定，Hermes 查配置后不自作主张给值
- 双执行器：用户点名 claude 时（「让 claude 也出个方案」）→ 打包上下文走 Bedrock（CLAUDE_CODE_USE_BEDROCK=1 + AWS_REGION + AWS_BEARER_TOKEN_BEDROCK）出独立方案 + 对抗审查

## 相关文件
- DeepSeek 2026-08 定价/涨幅/账单细节：`references/deepseek-pricing-202608.md`
- 全模型价格×性能×订阅快照（2026-08-17）：`references/price-snapshot-20260817.md`
- **`scripts/usage_ledger.py` — 只读 usage 聚合器（2026-08-24）**：一次跑出近 N 天 claude（jsonl message.usage）+ codex（rollout token_count）+ DS（state.db）三方汇总成本表。对账/验证优化效果前先跑它，别手动翻 jsonl。
