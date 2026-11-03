## 五、全自动产线架构定案（2026-08-19，claude 实测 + 天行者拍板）

架构方案落盘：`/home/ubuntu/workflow/projects/toutiao-shoufa-tools/工作流架构方案_20260819.md`（已迭代到 **v7：366KB / 2476 行**，备份 v1-v6 同目录，含实测数据；v7 起豆包搜索接入定案）。三个实测结论直接改变实现方式：

### 实测结论 1：humanizer-zh 的 SKILL.md 不能整篇当 system prompt 投喂
- 实测：全文（5055 tokens）当 system prompt 投给 deepseek-v4-flash，返回与原文**逐字相同**（difflib 相似度 1.000）。它是写给有 Read/Write/Edit 工具的 agent 看的操作手册，纯 chat 模型把它当「审阅要求」而非「执行改写」。
- 修复（实测有效）：编译成祈使句规则卡（约 1481 tokens，写「必须逐句改写，禁止原文照抄输出」+ 硬约束），1987 字 → 1695 字、相似度 0.381。**用它的规则内容，不用它的文档形态。**
- 附加：改写后必须做相似度校验，否则失效是静默的（返回 200、看着没问题）。

### 实测结论 2：中文困惑度 AI 检测方向是反的
- DS `/beta/completions` 能返回 logprobs，但 temp=0 时是 `-9999.0` 哨兵，必须 temp=1.0 才拿真值。
- 更致命：AI 段 top1 命中率 0.33、真人段 0.50，平均 logprob AI −3.82 vs 真人 −2.41——按「AI 更可预测」假设恰好相反（中文短句口语反而好猜）。**困惑度检测在中文+单模型 self-perplexity 不成立**。
- 改用规则特征法，实测区分度 49.5 倍（AI 段 109.0 vs 真人段 2.2）。

### 实测结论 3：去味自己会引入新 AI 痕迹
- 破折号 1 → 5 个（humanizer 明令禁止的），AI 味分 7.6 → 15.2。**检测必须放在去味之后**，且检测项要含「破折号密度」这类去味自身副作用。

### 天行者三案定案 + 原则 D（2026-08-19，三案→四案演进）
1. **审批章 = AI 自审，不走人工**（「人工来审的话肯定不方便嘛」）。冲突解法 = 方案甲：工具链独立、产出落 `runs/`、不进 19 节点主链、不调 workflow_gate 的 approve 人工门，所以 AGENTS.md 铁律 7（人工门只能由人批）不构成冲突。AI 自检闭环（评分器+数据源+合规全过）即章，人工零参与成立。
2. **真实稿/校准锚点 = 按话题搜今日头条真实稿件**（「我说今天说一个话题，你就去搜对应的话题」）——后被原则 A 修正（见下）。
3. **配图 = 按话题搜真实图**（「配图不也是去搜」）——配图环节从「需人工/AI 生图」改为全自动搜索：搜真实图既贴合事件又不踩「AI 虚构」的线。配图是当篇发布内容、必须与事件绑定，与真实稿（可攒批）逻辑不同，大概率每次产线跑时搜。
4. **原则 D：产出禁标 AI**（「我本来就是用真人角度去发的，你标注个AI的话，那有什么卵用？」）——产线产出文件不带任何 AI 标注；平台 AI 声明由客户自选（详见「一之补」）。publish.py 不写标注提示、发布清单不设勾选硬项、M2 验收删「AI标注提示在位」。

### 天行者设计原则 A/B（2026-08-19 补丁，修正上表第 2 条）

**原则 A：真实稿 = 校准机制的标尺，不是每次产线的原料**
- 否决「每个新话题跑前现抓 6-10 篇」节奏——生产环节不允许依赖每次现抓真实稿。
- 改为：冷启动攒批 + 长期复用 + 月度/季度复算，**生产链零抓取**。
- 代码层写死断言：`allow_pipeline_fetch: false`，pipeline 启动读到 true 直接 BLOCKED（防有人改回现抓）。
- 机制自证性：如果每篇都要现抓真实稿才写得像真人，说明规则卡和阈值没校准好——现抓是在用外部输入掩盖机制没做到位。

**原则 B：去AI味机制的北极星 = 产出像真实稿**
- 整套去AI味+检测+回炉机制的唯一目的：让产出稿「看起来像真实稿」，所有阈值以「真人写的稿长什么样」为参照系。
- 锚点池定位 = 「像不像真实稿」的尺子（量具），不是原料。
- 新增机制效果验证：成稿分布 vs 锚点池分布月度对比（验证机制真的做到「产出即真实」）。

### 天行者设计原则 E/F（2026-08-19 补丁 v6/v7，配图源与发现层定案）

**原则 E：配图源不锁死头条站内**
- 头条站内（A）从主源降为兜底之一；**A0（素材自己的来源页）从来不是头条站内源**——它抓的是 material.json 里素材的来源页（新浪/澎湃/中新网），本来就是外部新闻站，继续留在首位。
- 源优先级重排：**A0 素材来源页 > A1 其他新闻站同事件报道 > B Wikimedia Commons > A2 头条站内（事件图兜底）> B Pexels（末档）**。
- 实测支撑：外站图 544-1080 宽（中位 1018）、账号水印 0/27、分辨率更好；头条站内 31% 水印、640 宽锁死。
- 外站取图必须**先定位正文容器（site_selectors）再取 `<img>`**——直接扫全页拿到的全是站点图标（实测 70 张图标、可用 0 张）。

**原则 F：A1 发现层接豆包搜索 API（feedcoop global_search）**
- A1 报道页发现从「频道/首页列表碰」改为「豆包搜索定向找」；取图层一行不改（仍是 site_selectors → `<img>`）。
- 豆包一次查询**多站聚合**（实测返回人民网/新华网/央视网），候选数 candidate_articles_external 从 12 回落到 8。
- 成本：**单次 0.30 元 ≈ 3.7 篇文章文字成本（0.082 元）**，配图链付费项从 1 个变 2 个，发现层不再免费；单篇成本区间 0.13-0.57 → **0.13-0.87 元**（日更 10 篇 = 月 40-260 元）。
- 三条成本压制：`max_search_calls_per_run: 1`（计数器硬拦，超限返回空+`blocked:true`，不是配置自觉）+ `skip_if_a0_sufficient: true`（先跑完 A0 抽图+清洗+数够 3 张再决定搜不搜，顺序倒了=每篇都付 0.30 元）+ 豆包失败降级回列表页盲碰（`fallback_used:true`，不整篇 FAIL）。
- **真实月账取决于「A0 命中率」这个未实测数**：A0 命中率 70% → 月约 67 元；20% → 月约 112 元。A0 命中率 = 几成篇靠素材来源页就凑满 3 张合格图（即没调豆包），M1.5 跑 5 篇 + M2 跑 10 篇后回填收窄区间。
- 完整 API 细节、search_trace 记账字段、风险 15/16 等见 `references/doubao-search-integration.md`。
- ⚠️ **豆包直调 Body 参数坑（2026-08-20 实测）**：带 `"Filter": "article"` 会让响应 `Result` 变 None（解析报 NoneType）；不带 Filter 正常返回 `Result.Documents[]`。实测 `Count: 8` 实际返回 10 条。直调头：`Authorization: Bearer <key>`（key 在 `~/.hermes/config/doubao_search.key`）+ `Content-Type: application/json`，Body 字段 `Query` 大写（小写 query 误报 invalid_key，见 codex-cli-ops 搜索节）

### 成本锚点与省钱杠杆（实测）
- 单篇 0.08–0.36 元：全 flash 一轮 0.082 / 撞满 3 轮 0.166 / 升 pro 0.178，高峰 ×2。
- 杠杆按性价比排：排空闲时段（省 50%）> 吃满 prompt 缓存（命中价差 30 倍）> 别急着上 pro（pro 一轮 ≈ flash 三轮）。
- 提炼大纲步实测：in 131 / out 1166 tokens、16s、0.0054 元。

### 校准纪律（防全自动失效）
- 自检评分器给「明显改好的段落」只打 51 分——阈值凭直觉设 70 会每篇撞满 3 轮转人工、白烧 3 倍 token。**所有阈值带 `_calibrated: false`，未校准时强制 dry-run（跑 20 篇拿分布再回填），先测后定，不许拿未校准阈值当门禁。**

### 已知坑（写实现时注意）
- **产线测试全是脚本式（2026-08-20 回归实测）**：`tools/test_*.py` 是 `if __name__ == "__main__": ... sys.exit(0 if ok else 1)` 的脚本式，不是 pytest 用例——`pytest tools/test_hotlist.py` 收集会 INTERNALERROR（SystemExit），**必须 `python3 tools/test_<name>.py` 直接跑看退出码和输出尾部**。跑全量回归的姿势：`for f in tools/test_*.py; do python3 $f >/dev/null 2>&1 && echo "PASS $f" || echo "FAIL $f"; done` + `py_compile` 全部 tools/*.py。派 codex 回归任务书里写清楚「pytest 收集会 INTERNALERROR，直接用 python3 逐个跑」，否则执行器会用 pytest 白跑一轮。hotlist v2 改造完成验收：`python3 tools/test_hotlist.py` 65/65、EXIT=0。
- G_COPY_READY 审批门三层检查 + approve 通道的完整代码级拆解见 `references/gate-approval-mechanism.md`（node4_review/node4_body 审什么、approve 的 --by/--evidence/sha256 锁定、头条产线如何绕开人工门）。
- `workflow_gate.py` approve 通道存在（L689）：要求 `--by <审批人> + --evidence <非空文件>`，锁定 produces 每个产物 sha256（审批后改文件哈希对不上）。「19 门无一可达 ALLOWED」是过时判断。
- `scripts/data_source_gate.py` 的 `check_body()` 里 `return problems` 缩进在文件循环内部（L133 for / L180 return）——**只检查第一个文件就返回，后续文件全漏检**。本产线 detect.py 只 import 词表自实现扫描可避开；gate 本身漏检 2026-08-20 已打包四尾巴修复任务（把 return 移到循环外 + 多文件回归测试）。
- **titler.py 变量遮蔽 bug（2026-08-19 第二跑暴露，存量坑）**：`scored = sorted(((s, t) for t, s in ((_score_title(t), t) for t in candidates)), reverse=True)` 外层 `for t, s` 变量名遮蔽导致元组顺序反了——`chosen` 拿到的是**分数 float** 而非标题，pipeline 在 `titles.get('chosen')[:40]` 崩 `TypeError: 'float' object is not subscriptable`。修复：外层解包改 `for s, t` 保持 (score, title) 顺序；顺带加过滤模型开场白（「好的，已收到您的素材…」）进候选。第一跑没暴露是因为去味判据提前 rc=3 根本走不到标题环节——**验收跑通全程前，每环节的存量 bug 都可能被下一环节的提前退出掩盖**。

