---
name: llm-api-cost-analysis
description: LLM API 账单/成本/涨价分析。触发：涨价多少/账单/tokens消耗/算下多少钱/API费用/成本优化。
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [llm, cost, billing, pricing, deepseek, api]
---

# LLM API 成本/账单分析（DeepSeek 实测沉淀 2026-08-17）

分析 LLM API（DeepSeek/豆包/OpenAI）的账单明细、涨价幅度、成本构成，给错峰/用量优化建议。

## When to Use
- 用户问「XX 涨价了多少」「算下现在是多少钱」「昨天消耗了多少 token」「怎么省钱」
- 用户发 API 账单 CSV（cost / amount 两个文件）要求分析
- 需要按账单事实给出错峰/缓存/模型降档建议时

## 触发场景
- 用户问「XX 涨价了多少」「算下现在是多少钱」「昨天消耗了多少 token」
- 用户发账单 CSV（cost / amount 两个文件）
- 要给 API 调用做成本优化（错峰/缓存/模型降档）

## 🚨 关键事实（DeepSeek 2026-08 实测）
- **官方定价页是 JS 渲染 SPA**：`curl`/简单抓取拿不到正文——用 python `urllib + re.sub(r'<[^>]+>',' ',html)` 正则抓文本片段（找「价格」「元」「百万」）
- **余额 API 无用量明细**：`GET https://api.deepseek.com/user/balance`（Authorization: Bearer key）只返回余额（total/granted/topped_up），查「昨天消耗多少」必须用账单 CSV 或后台
- **🚨 无 key 列表/消耗分布 API（2026-08-18 实测）**：`GET /user/api_keys` 返回 404，`/user/balance` 也不返回 key 级明细——平台网页「API Key」标签页显示 N 个 key 和总消耗，但**各 key 各自的消耗只能用户网页端看，API 够不着**。用户问「哪些 key 在烧钱」：本地对账（agent.log 两机合计 ≈ 平台总量）确认无漏网后，直接答复「没异常，废 key 不影响花钱，要清理去网页删」
- **平台截图不标时间范围**：deepseek 开放平台首页三卡片（消费/请求数/tokens）默认今日，但页面不写「今日」——先跟用户确认口径再算，别把累计当今日
- **账单 CSV 两种**：
  - `cost-*.csv`：按 `start_time_iso,model,cost,currency` 每时段每模型一行金额（可直接汇总）
  - `amount-*.csv`：按 `start_time_iso,model,type,price,amount` 每时段每类型一行——**`amount` 是 tokens 用量，`price` 是每 token 单价，金额 = price × amount**（CSV 里没有直接金额列，别把 amount 当金额）
- **涨跌对比必须用同一份 tokens × 新旧价**：把 amount CSV 的 tokens 分别乘旧价和新价，才是同口径涨幅
- **DeepSeek 2026-08-13 官宣调价（8/17 0 时生效）**：峰谷定价，高峰=北京 9-12、14-18 点（价格=空闲 2 倍），其余空闲半价；`deepseek-chat`/`deepseek-reasoner` 2026-07-24 已停用映射到 V4 Flash/Pro。具体价格表见 `references/deepseek-pricing.md`

## 分析工作流

### 0. 从 Hermes 本地 agent.log 自统计今日消耗（不依赖账单 CSV，2026-08-18 实测）

平台后台给总量（总消耗/请求数/tokens），要拆「哪台机/什么结构/为什么这么多」必须从本地 agent.log 统计。

**日志行格式**（`~/.hermes/logs/agent.log`，广州 customer profile 在 `~/.hermes/profiles/customer/logs/agent.log`）：
```
API call #644: model=deepseek-v4-flash provider=custom in=217545 out=329 total=217874 latency=4.3s cache=217472/217545 (100%)
```
- `in`=输入 tokens（含缓存命中），`out`=输出，`total`=in+out
- `cache=命中/总输入`——分子是缓存命中，分母≈in；miss = in − 命中

**🚨 轮转坑（2026-08-18 实测漏统计 9600 万）**：`agent.log` 会轮转（旧文件 `agent.log.1`）。统计「今天」必须把 `agent.log` + `agent.log.1` 都扫——凌晨 0-2 点的调用在轮转文件里，只扫主文件会跟平台账单对不上（实测漏 404 次调用 / 9600 万 tokens，平台 9.85 亿 vs 只扫主文件 8.8 亿）。

**算钱**：按行首时间 `2026-08-18 HH:MM` 判高峰（北京 9-12、14-18 = Flash 0.10/3.0/9.0 元每百万）或空闲（0.05/1.5/4.5），分两段算再合计。

**对账**：平台 tokens ≈ Σ(in)+Σ(out)；平台请求数 ≈ `API call #` 行数（含轮转文件）；剩余零头 = 直调脚本（node1_analysis.py / cost_meter.py 等不走 gateway 日志）。

**会话臃肿诊断（「9 亿多怎么来的」）**：
- 平均上下文 = Σ(in)/调用次数——实测新加坡 28 万/次、广州 15 万/次
- 查胖会话：`SELECT session_id, COUNT(*), SUM(LENGTH(content)) FROM messages GROUP BY session_id ORDER BY 3 DESC LIMIT 5`（广州路径 `~/.hermes/profiles/customer/state.db`）
- **结论模式**：9 亿 tokens 里 99% 是缓存命中（单价 0.05-0.1 元/百万）= 背历史不是烧钱；真贵的是 miss 和输出。降消耗唯一正路 = 归档胖会话，不是调模型
- 现成脚本 `scripts/analyze_agent_log_cost.py`（自动含轮转文件 + 高峰/空闲分价格）

### 0.1 从 state.db session_model_usage 统计（2026-08-24 实测，比 agent.log 更准）

Hermes 有 `session_model_usage` 表（`~/.hermes/state.db`），按会话×模型×任务记 `api_call_count / input_tokens / output_tokens / cache_read_tokens / estimated_cost_usd / actual_cost_usd`。

**🔴 时间戳坑**：`first_seen/last_seen` 是 **unix 时间戳（float）不是字符串**——`WHERE last_seen >= '2026-08-24'` 字符串比较**查不到任何行**（返回空，别误判为没记录）。正确写法：
```python
from datetime import datetime, timezone, timedelta
start = datetime(2026,8,23,0,0,0,tzinfo=timezone(timedelta(hours=8))).timestamp()
# WHERE last_seen >= start（float 比较）
```
- `estimated_cost_usd`/`actual_cost_usd` 可能是 0.0（没启用计价）——只给 token 数，价格单独换算
- 覆盖 Hermes 主对话 + vision（doubao）调用；**不覆盖** claude/codex 直调（走独立 wrapper，见下）
- 按会话范围筛选：`WHERE ls >= start AND fs <= end`（会话在范围内有活动就算）

### 0.2 claude/codex 直调无 usage 记录时的估算（2026-08-24 实测）

claude 走 Bedrock **不落 usage**：`~/.claude.json` usage 空、session jsonl 无 `model`/usage 字段。估算方法：
- **轮数**：`~/.claude/projects/<工作目录>/*.jsonl` 里 `type=='assistant'` 消息数 = API 调用轮数；轮数 ≈ 工具调用数 × 1.9
- **输出 token** ≈ 输出文件 UTF-8 字节 ÷ 3（中文 1 字 ≈ 1 token）——输出侧误差小
- **输入 token** ≈ 读入文件总量 × 会话轮次（粗估，误差大；claude code 每轮重复带上下文，累积输入才是大头）
- **价格**：Sonnet 4/4.6 $3/M 输入、$15/M 输出；GPT-5.6 Sol $5/$30；DeepSeek V4Pro 见 references
- 精确对账要给 wrapper 补 usage 采集（当前缺口，别假装有精确账）

### 0.5 响应慢排查（用户问「机器人怎么这么慢」，2026-08-18 实测）

先别下结论「系统臃肿」，三步定位：

1. **排除系统资源**：`free -h` + `uptime`——负载 <0.5、内存有富余 = 机器没事（本机 3.6G/负载0.18、广州 1.9G/负载0.19 都正常）
2. **看 API latency 区分模型排队 vs 本地慢**：日志 `API call ... latency=Xs`——正常 3-9s；**30-640s = 模型上游排队**（DeepSeek 高峰 9-12/14-18 点，实测 17-18 点单次等 225-640s）。`response ready: time=640s api_calls=1` = 单次 API 等 10 分钟 = 模型排队不是本地
3. **看会话膨胀**：`grep "API call" agent.log | tail` 的 `in=` 值——20-30 万/次 = 会话背太多历史。两机共慢 = 同一模型同一通道高峰排队 + 两会话都胖，不是单一机器故障

**用户追问「是不是系统臃肿」**：拿硬数据回（负载/内存/磁盘/进程数），再给会话膨胀证据（input tokens 21-31 万），最后给治本方案（归档胖会话）——别只答一半。

### 1. 当前价：抓官方定价页
```python
import urllib.request, re
req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
html = urllib.request.urlopen(req, timeout=15).read().decode('utf-8','ignore')
text = re.sub(r'<[^>]+>',' ',html); text = re.sub(r'\s+',' ',text)
# 找含「价格」的段落，打印一定长度；URL 编码注意（zh-cn 路径）
```

### 2. 历史价/涨价事件：codex Tavily（本地 web_search 常挂）
派 codex 用 Tavily 搜「调价公告/news/历史价格对比」，带来源 URL；官方 news 页正文价格表常是图片（`news260813` 只有「8/17 生效」没旧价）——旧价从新闻（北京日报/第一财经/澎湃）拿。

### 3. 账单 CSV 分析（重点脚本见 scripts/analyze_cost_csv.py）
- cost CSV：按小时/模型汇总金额，标高峰/空闲（`9<=h<12 or 14<=h<18` = 高峰）
- amount CSV：`price × amount` 算出每项金额；按模型/类型（input_cache_hit / input_cache_miss / output）汇总
- 同用量旧价：tokens × 旧价表（Flash: 0.02/1/2 元每百万；Pro: 0.025/3/6 元每百万——2026-08-17 前）
- 涨幅 = 新/旧 − 1；注意「命中缓存价涨得最狠（+150%~400%）」而命中率高的用户最受伤

### 3.5 对比其他模型价格：订阅套餐（Coding Plan）必加（2026-08-17 用户纠正）
- **用户原话**：「其他模型应该都有 COIDING PLAN」——对比模型价格**不能只看 API 单价**，订阅套餐（月费制）对重度用户可能更划算。
- 必查项：ChatGPT Plus/Pro/Team（OpenAI）、Claude Pro/Max 5x/20x（Anthropic）、Gemini AI Pro/Ultra（Google）、GitHub Copilot Pro/Enterprise。
- 判定：用户月 API 费（如 36.5 元/天 ≈ 月 1000+ 元）vs 订阅月费（几百元档）——超过回本点就用订阅。写进对比报告第四/五章。

### 3.6 性能对比必加（2026-08-17 用户纠正：「同时要对比性能」）
- 用户原话：「其他模型多比两个版本，比如 gpt5.6sol 同时要对比性能」——**价格对比必须带性能维度**，只比价格会被纠正。
- 必查项：LMArena 综合排名/Elo（真人偏好）、SWE-bench Verified（编码，注意厂商口径不一：OpenAI 报 SWE-bench Pro 不是 Verified，别混填）、LMArena 创意写作榜（写作场景）。
- 结论模板：「DeepSeek 涨价后仍比海外同档便宜；面对 Qwen/GLM 只有谷时优势稳，峰时不再是默认最低价」。

### 3.7 订阅额度实测（Coding Plan 的 token 上限）
- **ChatGPT/Codex 订阅不公布固定 token 数**（「5 小时窗口 + 周限额」动态制）——不能拿「订阅包含多少 token」跟 API 比。
- 实测反推（Reddit）：Plus $20 ≈ 340 万 tokens/5 小时窗口（0.68M/小时）、单会话折 API $6.66；Pro 5x/20x 理论 5x/20x 但周限额打空快。
- **判定：API 日用量 vs 订阅窗口量**——如 3.3 亿/天 API 用量，订阅 340 万/窗口差 100 倍，订阅扛不住，结论是「订阅只适合人用（写作/编程交互），自动化必须 API」。

### 3.8 国产 Token Plan / Credits（2026-08-17 用户追问沉淀）
- **国产主流无 API 订阅制**：Qwen/豆包/Kimi/GLM 都是按量充值；「会员」（通义/Kimi App）与 API Key 不互通，不能跑自动化。
- **千问例外：百炼 Token Plan**（个人 Lite 39 元/2500 Credits、Standard 139/1 万、Pro 499/4 万；用量包 100 元/2 万 Credits = **1 元 ≈ 200 Credits**）——但**禁止脚本/后端/批量调用**，只给交互工具（Claude Code/Cursor 等）；夜间 22:00-08:00 Credits 5 折。官方不公布 Credits→token 精确换算，只能控制台实测。
- **自动化省钱正解**：阿里云百炼「AI 通用型节省计划」（月承诺 1000 元起，8.8 折，最高 6.8 折）；豆包文本资源包已下架；GLM 有 API 资源包 + Coding Plan（限编程工具）。

### 4. 优化建议（按账单事实给，不套模板）

#### ⚠️ 缓存保护第一性原理（2026-08-17 Claude 对抗审查定论，最重要）
- **命中率是最值钱的资产**：命中价 0.07 元/M vs 未命中 2.24 元/M（差 32 倍）。省钱的本质 = **别把便宜的命中 token 变成贵的 miss**，不是压小上下文。
- **「压缩阈值调低 + 滚动摘要」可能净亏**：每次滚动摘要改写会话中段 → 前缀失效 → 当前请求整包 miss（23.65 万 × 2.24 ≈ 0.53 元/次）。粗算：每天 40 次摘要 ≈ 多花 21 元 > 省下的命中费 6.9-11.6 元。
- **「总 token 数下降」是骗人指标**——只看钱和 miss。命中 token 占 63% 的钱但单价 0.07（边际便宜），减 100M 命中只省 7 元还几乎必带缓存重建。
- **三条底线**：命中率 <97% 停手；miss 破 8M/天自动回滚；优化论证只用「钱和 miss」，不用总 token。
- **若平均上下文（如 23.65 万）远小于压缩阈值（500K）**——说明压缩从没触发过，命中率是「没压缩」跑出来的成绩；调低阈值 = 拿最值钱资产去赌。

#### 双执行器评审经验（codex vs Claude 方案，2026-08-17）
- codex 方案（96K 压缩/会话 8 轮/请求合并）与 Claude 方案（rollover 交接/前缀字节冻结/冷热会话/miss 红线）**真打起来**——Claude 的对抗审查抓出 codex 三处净亏/高估（96K 压缩净亏、8 轮会话文学失忆重写亏、请求合并收益算错 6 倍）。
- **评审裁决**：缓存保护优先（Claude 方向对），但 **rollover 等要改 Hermes 核心逻辑——实施风险 > 收益**（省 17-20 元/天 vs 一次长篇断线重写 10 万字 ≈ 60 元吃掉 3 天节省）。用户定论「先不改」。
- **给用户的方案必须列利弊**（每项：利=预期省多少；弊=风险/副作用/回滚）——用户明确要求过「要列出方案的利弊」。
- **「零风险」要拆两层**：概念零风险（不砸缓存）≠ 实施零风险（改 Hermes prompt 组装/输出限长仍有截断/行为异常风险）——被用户追问「0风险的对我们没影响？」后定论：真正的零影响 = 什么都不改。

#### 按杠杆排序（标注净亏风险后）
- **输入削减（第一优先，最大杠杆）**：先看「每次请求平均 token」——如 1,406 次请求 / 3.3 亿 tokens ≈ **23.65 万 token/次，问题在上下文太大不是请求多**。措施：⚠️ **不用「调低压缩阈值+滚动摘要」**（净亏，见上）；用 **会话滚动交接 rollover**（160K 硬上限触发新会话+手写交接包 8-12K，把不可控缓存崩塌换成每天 3-5 次可预算 miss，省 8-9 元/日但要人工过交接包防断线）；文档/素材建索引按需检索片段（不整篇塞，检索结果**追加会话尾部**别插回前缀区）；system prompt 去重（**必须静态一次性**，动态注入=每轮前缀变=命中率归零）。命中缓存输入量削减 30-50% 可省大头（如 23 元基线省 7-11.6 元/日）。
- **错峰**：批量/写作任务挪出高峰时段（9-12、14-18），挪空闲=省一半；58% 成本在高峰时，错峰是第二大的杠杆。
- **模型路由**：默认便宜档（Flash），高难任务才升 Pro；Pro 占比 7%→3.5% 灰度。
- **输出控制**：按任务设 max_tokens 硬上限（分类 800/分析 2000/初稿 3000/长篇段 4000），分段续写不重放全文。
- **缓存命中**：命中价（0.05）vs 未命中价（1.5）= 差 30 倍——提高命中率（长 prompt 前缀稳定，发布前缀按版本分批不在高峰全量换缓存）。
- 先按账单算清楚再建议，别信网上「千次固定单价」（官方不公布固定千次价）；上线先补埋点（request_id×任务×小时×模型×缓存），灰度 10% 再全量。

## 坑
- SQL LIKE 的 `_` 是通配符：`LIKE '%ghp_%'` 匹配「ghpX」——搜字面串用 python `'x' in content`（详见 hermes-gateway-runtime）
- archive.org wayback 访问常超时/502（跨境被墙）——别依赖，用 Tavily 新闻代替
- 用户贴的「输入命中/未命中/输出」数字顺序可能和 CSV 字段对不上——以 CSV 原始字段为准，先核对再算

## 单篇内容生产成本估算（2026-08-19 实测，用户问「写一篇文章成本高不高」）

标准算法（头条图文 1500-2000 字为例）：
- **token 估算**：输出 2000-3000（正文）+ 输入 3000-5000（喂养素材+提示词，模板部分缓存命中）；多次改写（写→降重→拟人化 3 轮）成本 ×2-3
- **成本区间（DeepSeek V4 Flash，2026-08-17 后峰谷价）**：空闲（非9-12/14-18）约 0.02 元/篇；高峰约 0.04 元/篇；3 轮改写后 0.06-0.12 元/篇；V4 Pro 高质量 1-2 毛/篇
- **配图是隐藏大头**：Seedream 0.25 元/张 × 至少 3 张 = 0.75 元，可被免费图库替代——算单篇成本时别只算 LLM token
- **结论模板**：大头不是 API 钱，是人工时间（单篇纯人工 40-60 分钟 vs 流水线 5 分钟）——先给「钱」再给「效率」，避免用户误以为环节多=成本高

## 验证
- 金额对账：cost CSV 每小时金额 ≈ amount CSV 同小时 price×amount 之和
- 涨幅计算：同 tokens 乘新旧价，结果与新闻给出的涨幅一致才算对

## 免费模型通道 + Ox Alpha（2026-08-23 调研）
- Hermes 内置免费通道（Ollama 本地/Gemini 免费层/OpenRouter :free/Nous Portal/HuggingFace）与 OpenRouter 匿名免费模型 `stealth/ox-alpha`（1M 上下文、免费、编码强）的规格、接入、风险：见 `references/free-model-channels.md`
- 用户问「内置哪些免费模型/能不能接这个模型」先读该 reference 再答
