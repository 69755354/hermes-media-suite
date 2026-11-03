### M2 校准完成（2026-08-20 凌晨）

- 锚点池：43 篇（超 30 线；AI 味分布 min 0.0/P25 7.9/中位 11.9/P75 16.9/max 27.4）
- `tools/calibrate.py` 回填：ai_score_max=16.9（锚点 P75）、part_pass_score=61（`--with-llm` 逐篇 flash 自检 P25，43 篇 ≈ 0.02 元）、真闭环已开（_calibrated: true）
- **机制偏离警告（真实信号）**：成稿 AI 味分布 N=4 min 25.8/中位 36.3/max 44.0，中位数 > 锚点 P75 → 去AI味环节没做到「像真人稿」。**已诊断+六项修复落地（2026-08-20 晚，见下「去AI味失效诊断与六项修复」）**，评分器升级 density_v2、阈值重校准 16.9→8.4。

### 去AI味失效诊断与六项修复（2026-08-20 晚，诊断 codex `诊断报告_头条产线去AI味失效_20260820.md`，修复任务书 `brief_deai_fix_20260820.md`）

**根因证据（Hermes 独立复算过，不是自报）**：
1. **主根因 = 破折号密度超锚点 6.5 倍**（成稿均值约 3.2 次/千字 vs 锚点 0.5），占总 AI 味分差 74.2%——AI 稿爱用破折号是最大「非人」信号
2. **⑤去味有改文但不降分**：三篇 ⑤ 前后相似度 0.85/0.85/0.64（确实改了），但 AI 味 24.95→28.51、45.39→45.07、32.40→36.29（两篇变差）——「字符改了」≠「往人话方向改」
3. **④拟人化近乎没改文**：相似度 0.9877/1.0000/0.9970，白跑一轮
4. **calibrate.py 中位数 bug**：`article_scores[len//2]` 偶数样本取错值，「中位 36.3」实际标准中位 31.21（方向不变仍超 16.9，但偏离被放大 5 分）
5. **旧产物 ≠ 校准后真闭环失败**：三篇验收稿是旧阈值（ai_threshold=25）+ dry_run=true 时代的产物，不能当「校准后闭环失效」证据——校准后真闭环还缺一轮独立验收

**六项修复落地（全部验收过）**：
- P0-1 质量单调门：⑤ 只接受「总分下降或已≤阈值 + 破折号不增加 + 卡片硬上限过」的结果；采用前跑 fabrication_gate + 事实保留校验；相似度降级为异常日志不再代表成功
- P0-2 分项反馈：pipeline 向下一轮传结构化 ai_detail（如「破折号 13→≤2」），不再「只打印不传参」（原 L608-609）；每轮只处理贡献最高的 1-2 个分项
- P0-3 校准口径：calibrate.py 用 `statistics.median`，只统计 ai_pass 非 null / dry_run=false / 阈值版本匹配的 run
- P1-1 废除 difflib>0.9 单一判据：相似度只在「几乎逐字相同且 AI 分未下降」时触发 fallback；fallback_retry 已接入代码（humanize.py L295 / pipeline.py L313），不是死配置
- P1-2 编造回炉后 ④⑤ 持久关闭：fact_locked=true（pipeline.py L378/L564），后续只走独立 `fact_locked_deai`（humanize.py L352，不新增/改写专名数字），不能安全降分时 rc=3 人工复核
- P1-3 密度制评分器：否定排比/三段式/破折号改每千字符密度；**ai_score_max 16.9→8.4**（density_v2，43 锚点 P75 独立复算 8.46 一致），config 记录 ai_scorer_version=density_v2 / ai_threshold_version=density_v2_anchor43_p75_8.4

**验收**：新增 `tools/test_ai_score_density.py`（11 断言）、`tools/test_calibrate_effect_scope.py`（7）、`tools/test_deai_quality_gate.py`（16）；全量 316 断言全过 + py_compile 过，零 API 零出网。三篇旧成稿新制下 6.68/10.5/9.91——宇树过线，朱雀/云南仍超（破折号密度 3.6/3.3 仍是锚点 6 倍），符合预期：修的就是让回炉拿分项反馈把破折号压下来。

**⚠️ 真实验收（2026-08-21 凌晨）暴露质量门密度误杀 bug → 已修复（任务书 `brief_regression_judge_fix_20260821.md`）**：`evaluate_deai_candidate`（humanize.py L211-215）的 `component_regressions` 第一版比较 `detail["分项"]`（**密度值**），容差 `after > before + 0.01`。但密度 = 次数/千字符，模型删掉破折号后文本长度微变 → **绝对次数没变**（过渡词 5 仍 5、否定排比 3 仍 3）密度却微升 0.02-0.25 → 误判「分项倒退」→ 整单拒稿。实测：朱雀 AI 味 8.17→6.6、破折号 4→0、事实门/编造门全过仍被拒（回归项：过渡词密度 1.36→1.38、否定排比 2.45→2.48、三段式 2.72→2.75）；云南 10.43→9.52 同样被拒（0.83→0.87、1.67→1.73、6.68→6.93）。**修复（已落地）**：分项回归判定改用**绝对计数**（detail 顶层的 过渡词/AI词/否定排比/三段式 原始计数，`after > before` 才算回归），密度只留日志展示；破折号由独立 dash_ok 硬门把关不参与回归；回归测试补两个真实失败样例重放（必须 accepted）+ 反例（绝对次数 0→1 必须拒绝）。修复后 `tools/test_deai_quality_gate.py` 16→26 断言全过。**教训：评分器用密度归一后，任何改动文本长度的操作（删破折号/删句）都会改变分母——涉及「分项不得倒退」的判定一律用绝对次数，密度只用于展示。** 两篇日志的「候选未通过质量单调门/事实门（相似度仅记日志：0.9984）」容易误导成「模型没执行改写」——实际模型改了（破折号 4→0 是实打实的），是判定逻辑误杀。

### Prompt字数指令冲突根因（2026-09-03 定位，已派 codex 修复）

**问题**：GLM 初稿写 3078 字（目标 1450），三部分各写 ~1000 字加起来远超 1600 上限。

**根因（Hermes 独立定位，非自报）**：`prompts/02_feed_write.txt` 模板 83 行很长，中间第 67 行写了「全文汉字数以 {{WORDCOUNT_TARGET}} 字为目标」（1450 字），writer.py 在模板末尾追加分部额度「本部分必须为 195-240 字」。两个字数指令冲突——GLM 执行了中间的全文字数（1450），末尾的分部额度被淹没。三部分各按 ~1450 字理解 → 各写 ~1000 字 → 合计 3078 字。

**模板还误导模型**：写了「按以下顺序输出三个部分」——但实际是分三次调用每次只写一个部分，这条指令让模型以为要一次性输出全文。

**修复方向（已派 codex 重写模板）**：
1. 模板里不要写固定全文字数（用 {{WORDCOUNT_TARGET}} 占位让动态注入）
2. 删掉「按以下顺序输出三个部分」（分次调用不是一次性输出）
3. 末尾分部字数指令要更强硬，明确覆盖全文额度
4. 明确告知「只写当前部分，字数上限就是末尾分部额度」

**教训**：模型对长 prompt 中部的指令执行强、末尾追加指令执行弱（writer.py 注释已写「模型对长提示词中部的额度执行弱」但没根治）。字数指令必须清晰、唯一、不矛盾——中间不能有固定全文字数干扰分部执行。

**重跑验收结果（2026-08-21，朱雀/云南两篇 pipeline 真跑）——去AI味修复确认有效，但整链出稿仍 rc=3**：朱雀 AI味 4.03-5.26、云南 5.87-6.38 全 ≤ 8.4（修复前 25.8-44）；编造 2→0 清干净、事实锁生效（日志「永久跳过通用路径」可见）；原创度 96-97%。剩余四个**非去AI味**卡点处置状态（2026-08-21 已全部推进过一轮，任务书 `brief_format_illustration_fix_20260821.md` + `brief_commons_http2_fix_20260821.md`）：
1. **格式字数控制失效 → 已修复落地（2026-08-21 codex，`交付清单_格式字数与配图选择器修复_20260821.md`）**：朱雀 2429 超→回 ② 重提炼大纲后 1767 不够（从超摆到不够）；云南 3214→格式回炉 3062→3062 原地踏步（回炉 2 次压不动）→ rc=3。格式回炉卡「压缩到 1800-2200」指令模型不执行。修复三件套：`02_feed_write.txt` 统一全文目标+收窄三段额度（300-450/1000-1300/350-500）、writer.py 单部分 prompt 末尾硬额度、pipeline.py **Pareto 回炉采用门**（比上一版更接近区间就采用，原地踏步/变坏拒绝）+ 距离 trace（当前 N 字需减 M 字写进回炉卡）。新增 `tools/test_format_rewrite.py`（17 断言，覆盖 3062→删差值渲染、1767→补写差值渲染、部分改善采用、原地踏步拒绝）。复跑验证：朱雀文字链全通（格式门过）、云南字数 3062→2297 逼近区间（小标题 5 个仍超 1 个）——有效但模型收敛仍需观察。
2. **配图选择器覆盖不足 → 合规上补不了（2026-08-21 codex 实测逐域 robots 后结论）**：豆包返回的人民网子域（sc.people.com.cn/bj.people.com.cn/finance.people.com.cn）、news.cctv.cn、english.news.cn、www.cnsa.gov.cn 全未配 site_selectors 被 skip；逐域查 robots 全拒（404/超时/soft-404 假放行/Disallow），**无合规新增项**。A1 最多 2/3 张凑不满；A2 头条站内 robots 拦（m.toutiao.com Disallow /group/）。出路只剩：改豆包 query 让返回更多已配域 / B 源走 HTTP/2（见下条）/ 上游搜索策略调整。
3. **B 源 Commons 403 根因 = HTTP/1.1 限流，HTTP/2 放行（2026-08-21 实测破案 + 修复已落地验收）**：Wikimedia Commons API 对 HTTP/1.1 请求返回 403 Too Many Reqs，HTTP/2 请求 200。python urllib / requests 默认 HTTP/1.1 全 403（加 Accept/换 UA 无效），curl 默认 HTTP/2 稳 200，`curl --http1.1` 也 403——差异在 HTTP 版本不在头。**修复已落地（codex `改动清单_B源Commons_HTTP2降级_20260821.md`）**：fetcher.get() 对 commons 域 403 自动降级 curl 子进程（--http2 + 合规 UA + 同 timeout）重试，blacklisted/_throttle 在 curl 路径同样生效，失败抛原始 403 不静默；`tools/test_fetcher_http2.py` 5 项离线 mock（403 触发/非 commons 不触发/参数透传）；真实集成验证 HTTP=200 VERSION=2 BYTES=23915。**通用排查启示**：python 库稳定 403 而 curl 稳 200 时，别只查 UA/头——先 `curl -sv` 看协议版本、`curl --http1.1` 复现 403 即定位。⚠️ 若以后 stock_commons.api 迁域名需同步加白名单，不能放宽成任意 403 都走 curl。**配图链剩余两连根因（2026-08-21 深夜已全部定位并修复，配图门最终 3/3 过）**：
- **视觉合规超时误杀（根因 2，2026-08-21 破案）**：`image_compliance_check.py` 读 `providers.custom_ark.base_url` **直连 ARK**——新加坡机直连 ARK 被网络挡 → `request_with_retry` 连接类错误重试 8 次（退避 2^n 上限 30s）→ 单张 >240s → 产线 `vision_check` timeout=180 超时返回 `(None, [...])` → `bool(None)=False` → L627 `picked = [i for i in picked if compliance.pass is not False]` 把全图当「合规未过」剔除 → 0/3。图本身 3 秒就能判 PASS（修复后实测 img1.jpg「火箭发射正常场景，无违规」）。**修复**：image_compliance_check.py（备份 .bak_20260821）改读 `auxiliary.vision.base_url`（`http://127.0.0.1:18888` 本地代理→隧道→广州 relay→ARK），实测 3.2s/张。**纪律：新加坡机所有 ARK 类调用一律走 18888 代理，直连必超时**（config.yaml auxiliary.vision.note 2026-08-09 就写了，脚本没跟上）。
- **B 源 relevance 恒 0 被 55 门槛拒（根因 3，docstring 与实现矛盾）**：B 源泛图 `relevance_score` 恒 0（来源分 0 + 英文泛图 vs 中文事件文本重叠 0 + alt 0）→ `rel_min=55` 必拒；降级级3 注释说「不阻断」实现却在拦；`illustration_gate` docstring 明说「relevance_downgraded 泛图仍算过门」实现 L310 也没豁免。**修复**：illustrate.py `try_candidates` 加 `rel_min_override` 参数，降级级3 B 源传 0 全放行（进入后仍标 `relevance_downgraded` + 发布清单「建议人工替换为事件图」）；detect.py `illustration_gate` 相关性判据加 `not img.get("relevance_downgraded")` 豁免。验证：降级图 3 张 pass=True；非降级 relevance 0 仍拒（没破坏原判据）。
- **配图门现状（2026-08-21 终态）**：Commons 泛图兜底 3/3 可过门（license/署名 attribution 串/视觉合规 3s PASS 齐全），发布清单标注 downgraded 建议人工换事件图；A1 事件图覆盖仍受 robots 纪律限制（人民网子域/央视/news.cn 旧页未配选择器或 robots 拦，补选择器已到顶）——事件图靠豆包返回已配域（澎湃等）碰运气，B 源兜底保证不空图。
- ### 配图三处修复（2026-09-03 实测定位+修复）

**问题**：产线配图环节卡死在 0/3 死循环（23 分钟反复重试），所有图源全挂。

**三处根因+修复**：
1. **移动版域名没配 site_selectors**：m.chinanews.com、m.sohu.com 被 `unknown_domain_policy: skip` 跳过 → 在 config.yaml site_selectors 补移动版域名的选择器（m.chinanews.com.cn → div.left_zw；m.sohu.com → div.article/#articleContent）
2. **Wikimedia Commons 搜出来全是 PDF 不是图片**：Commons API 返回 PDF/DJVU/PPTX 文件被当图片候选 → illustrate.py cands_commons() 加 `re.search(r'\.(pdf|djvu|pptx?|docx?|tif)', title, re.I)` 过滤非图片文件
3. **Commons topic_queries 缺副业/兼职搜索词**：事件含「副业」但 topic_queries 无匹配关键词 → fallback 到默认 query 搜不到相关图 → 补 `computer virus scam smartphone money` / `person working laptop home office` 等英文搜索词（实测 Commons 能返回 `Computer virus scam.jpg`、`Android Smartphone with Money.jpg` 等真实图片）

**配图死循环问题**：所有图源全挂时 illustrate.py 内部循环补图不停重试（max_illustration_rounds=2 但每轮内多次降级重搜），GLM 产线卡 23 分钟。需在所有降级路径走完后及时退出不阻塞全链。

**配图超时优化（2026-09-03 续）**：配图模块端到端 300s 超时的根因链：① `images_from_page` 对未配选择器的域名先查 robots.txt（12s/个×8候选=96s）才 skip，应先查选择器（0s）再查 robots；② `_fallback_list_discovery` 返回 237 个候选每个抓 12s=2844s 卡死，应截断到 15 个；③ A0+A1 缺总时间预算，任一级卡住后面 Commons 兜底永远跑不到。六处修复：images_from_page 选择器前置 + A0+A1 加 60s 预算（`a0a1_budget_sec`）+ fallback 截断 15 + Commons img_url 优先 upload.wikimedia.org + 429 触发 curl HTTP/2 降级 + config 超时全面收紧（豆包 15→10s/页面 20→12s/max_retry 1→0）。修复后 A0+A1 从 300s+ 降到 3s。**未解决**：Wikimedia IP 级 429 限流——代码全改到位后 Commons API 搜索正常（10候选/1.2s）但图片下载全 429，curl HTTP/2 也 429。这不是代码问题是 IP 被限流，解法：走 8899 relay 中转 / 等恢复 / 启用 Pexels / 副业类跳过配图。详见 `references/illustration-fixes-20260903.md` 配图超时优化节。

**chinanews 素材来源页本身无新闻配图**：A0 素材来源页（chinanews.com.cn/sh/2026/08-24/10683175.shtml）正文只有一张广告图，不是选择器问题而是文章本身没图。A0 命中率受素材来源页带图率限制。

**Commons 可用搜索词实测（2026-09-03）**：
- `computer virus scam smartphone money` → `Computer virus scam.jpg`、`Android Smartphone with_Money.jpg`（真实 JPEG）
- `person working laptop home office` → `Couple working at home (Unsplash).jpg`（真实 JPEG）
- `phishing email filetype:bitmap` → `Email account phishing fr.jpg`（加 filetype:bitmap 过滤 PDF）
- ⚠️ 不加 filetype 过滤搜 `online scam fraud` 全返回 PDF 文件

**配图门六链修复（2026-08-21 下午，codex `交付清单_配图门发现兜底判定修复_20260821.md`，两篇复验 PASS）**：从 1/3 到 3/3 的系统性修复，六条链全部落地并验证：① **A1 已配域优先**——modules/search.py 新增 `prioritize_selector_domains()` 按 hostname 稳定排序，已配 8 域前置、未知域后置（豆包返回 8 页里混 1-2 个已配域就能出图，日志可见「已配域 2 个优先」）；② **fallback 列表页 2→5 个**——新增 people.com.cn/xinhuanet.com/fj.news.cn（curl 实测：新华网首页 180 条链接 172 条属已配域），新浪/澎湃实测 0 条/403 不硬加；③ **Pexels 定性禁用**——web 搜索 Cloudflare 403 无 key API 401，`stock_pexels.enabled=false` 摘链留恢复路径（配 key 后单独复测）；④ **Commons 查询词**——事件关键词→英文场景词映射（火箭→space rocket launch、低价团→group tourism travel crowd），B 源降级分支 `rel_min_override=0` 豁免相关性前置门但仍标 relevance_downgraded；⑤ **A2 零候选真相**——feed 无事件标题命中（非水印误杀），加命中观测不放宽阈值；⑥ **配图门判定语义**——降级图 3/3 可 PASS、1-2/3 仍 MANUAL_REVIEW_REQUIRED，required_count=3 不降。验收：87+37+5 项 mock 全过 + YAML 不变量守住（8 选择器未变/skip/deny 未松/门槛未降）。
- **「每段加粗一句」硬门落地（2026-08-21 下午，codex `brief_bold_fix_20260821.md`）**：发布清单「每段加粗」长期 FAIL（朱雀 0/15、云南 0/20）根因=**检查存在但无消费方**——publish._check_bold_per_para 只报告、detect.format_gate 不查加粗、09 回炉卡还明令「不动加粗」→ 永不触发回炉（同 M1 前小标题/字数的坑）。修三件套：① format_gate 加加粗判定（**detect import publish._check_bold_per_para 共用口径**，防两套判据漂移）；② 09 卡改法第 5 条「加粗不足→每段挑重点句 `**...**` 包裹，不许加粗整段、不包含句末标点、不新造文字」；③ pipeline `bold_per_para_fallback()` 程序兜底（回炉仍不听时，无加粗段落选第一句 ≥10 汉字否则第二句，只加 `**` 不改字，小标题行不加粗）。**坑：codex 只改代码没更新测试 fixture**——旧测试「合格稿」无加粗被新硬门误拦（test_format_gate 6 项 + format_rewrite 1 项 + rewrite_loop 1 项），需补 fixture（应 PASS 的稿每段加 `**...**`）+ 加粗专项用例，再全量回归。**教训：给硬门加新判定项时，测试 fixture 的「合格稿」必须同步补新项数据；codex 交付后 Hermes 必须全量跑 tools/test_*.py，失败反馈执行器补 fixture（实现与验收分离），不自己改测试。**
- **配图模块单独验收姿势**：`python3 modules/illustrate.py --material inputs/x.json --run-id test_x --title "t" --subheads "一、a,二、b,三、c"` 看 `assets/test_x/illustration.json` 的 result/count，1-2 分钟出结果，不必跑全链。
- **格式回炉最终态（2026-08-21 深夜，第 8 跑后追加）**：`format_max_rewrites: 2→4`（config.yaml，初稿常超 300-500 字、2 次压不到位）+ prompts/09_format_rewrite.txt 加「压缩幅度硬要求」——超上限时每轮至少削（当前字数-上限）×60%，按「删整段 > 合并短段 > 删第二处论证」顺序，禁止同义改写式微调；低于下限时每轮至少补满缺口。**第 8 跑最终验收数据**：朱雀 AI味 2.55-2.8（历史最佳）、编造 0、敏感词无、**配图门 3/3 PASS**、格式 2404 字差 204 卡（初稿 2684）；云南配图 3/3 PASS、AI味 3.45-10.56（模型随机波动偶超）、格式 2381-2489 差 100-200 卡。**结论：文字链四门 + 配图门均已能过，唯一剩余不稳定项 = 模型初稿字数超限时格式回炉压缩速度赶不上（已用轮次 4 + 幅度硬要求对冲，待下一跑验证）**；AI味偶超靠既有回炉兜底。
- **两篇验收全 PASS 终态（2026-08-21 中午，第 10/11 跑，配图门六链修复后）**：朱雀（12:04 cron 自动跑）AI味 4.32 / 原创 97.72 / 编造 0 / 敏感词无 / 格式 3 小标题 2083 字 / 配图 3/3（Commons 兜底）→ PASS；云南（12:28 手动跑）AI味 7.19（5 轮回炉从 8.88 压下来）/ 原创 97.2 / **编造 0（「城市接待网」彻底清干净）** / 敏感词无 / 格式 3 小标题 2189 字（从 2668 字五轮压到区间，format_max_rewrites=4 + 压缩幅度硬要求生效）/ 配图 3/3 → PASS。**六链修复全部生效：A1 已配域优先（日志「已配域 2 个优先、其余 6 个后置」）、fallback 列表页 2→5 入口、Pexels 禁用短路、Commons 事件查询词、A2 事件命中观测、B 源 rel_min_override=0 降级语义**。两篇配图均为 3 张 Commons 泛图（rel=0.0、发布清单标「建议人工替换为事件图」）——A1 事件图覆盖仍是 robots 纪律上限，属已知非 bug。修复交付清单 `交付清单_配图门发现兜底判定修复_20260821.md`。
- **验收2（2026-08-21 13:26 朱雀跑）复盘——格式回炉终态 + 「第一」新误报变体 + 豆包 blocked 全降级链实证**：
  - **格式回炉 4 次仍卡字数（2334 差 134）**：2876→2585→2457→2334→2334（第 4 次原地踏步被 Pareto 采用门弃用）→ 撞满 3 轮仍 FAIL（行业红线「第一」+ 格式硬门）→ **格式门兜底仅补 Markdown 加粗 0/17→14/17（发布加粗项 PASS，正文实际无加粗结构）** → verdict=FAIL rc=3 MANUAL_REVIEW_REQUIRED（字数超限人工复核）。验证：加粗程序兜底有效，但字数超限无法自动修——压缩速度仍是唯一不稳定项（同第 8 跑结论，模型压缩到 2300 上下就原地踏步）。
  - **「第一」序数豁免新误报**：r5 行业红线命中「第一」——正文「第一份完整的周期数据」里「第一份」**不在 _ORDINAL_PATTERNS**（只有 第一步/第一次/第一天/第一个/第一回合）→ 误拦。待办：白名单补「第一份」等序数变体；另注意「第一宇宙速度」是专有名词，后续命中同样要豁免，别当广告极限词。
  - **豆包 blocked 全降级链实证（配图 3/3 仍能过）**：A0 0/3（素材来源页 finance.people.com.cn 未配选择器）→ A1 豆包 8 页全 skip（未配域 + m.toutiao robots 拦）→ 降级级1 换关键词重搜 **blocked（calls=1/1 blocked，豆包不可用）** → 列表页盲碰 232 候选 → A2 头条站内 0 事件命中 → B 源 Commons 3/3（rel=0.0）。**豆包 blocked ≠ 配图 FAIL**：B 源兜底保证不空图，发布清单标「建议人工替换为事件图」。
  - **「图加进去了？」答复姿势（用户验收后常问）**：文章 md 是纯文本（**无 `![图]` 引用、无 http 链接**）；图以 `assets/<run_id>/` 落盘文件 + 发布清单「配图」段关联段落交付；头条发布正文/图片分开传，按清单传图。核对配图 = 看发布清单配图段（每图对应段落/来源页 URL/直链/版权/downgraded 标注）+ `file` 命令验证 JPEG 有效性与尺寸；**不要只看文章 md 找图**——找不到图引用不代表图没交付，是交付形态如此。
  - **「抽图出了问题？」诊断路径（2026-08-21 用户追问后实测验证）**：配图全泛图时用户会怀疑抽图坏了——先分清「抽图坏」vs「发现层坏」。实测姿势：`python3 -c` 直调 `_fallback_list_discovery` + `images_from_page` + `relevance_score` 抽降级候选样本页（1-2 分钟出结论，别凭日志猜）。实测结论：news.cn 页能正常抽 1-9 张图（抽图功能没坏）；232 个降级候选抽前 25 页得 51 张图，但 relevance 全 0-7 分（门槛 55）→ 0 张过线。**「A1 0/3」= 0 张被采纳，不是 0 张被抽出**——抽图可能成功很多张但全被相关性门拒；降级候选是列表页盲碰的当日无关新闻（news.cn 210/232 占大头 + 2022 旧链接混入），图与事件零重叠。另：**降级级1「换关键词重搜」是死路径**——`max_search_calls_per_run: 1` 第一次 A1 已用完额度，重搜必然 `blocked`（日志「豆包不可用」有误导性，不是豆包挂了是计数器超限）；要让重搜真正生效须把该配置提到 2（多 0.30 元/篇）。诊断时看 `detect_report_r*.json` 的 `illustration.search_trace` 字段（urls_with_selector/skipped_domains/blocked）比看日志全。
- **新待完善项：每段加粗 FAIL → 已修（2026-08-21 两篇 PASS 后暴露，下午 codex 落地 `brief_bold_fix_20260821.md`）**：客户方法论要求「每段加粗一句」，发布清单有检查项但两篇均 FAIL（朱雀 0/15 段、云南 0/20 段）——产线文章没生成加粗格式，清单标 FAIL 但没回炉逻辑。**已修**：format_gate 加粗硬门 + 09 卡补粗指令 + pipeline 程序兜底（详见「每段加粗一句」硬门落地条）。**下次盘点报「已修待复验」——真跑一篇确认加粗 PASS 后再闭环。**
- **配图门验证节奏（2026-08-21 复用）**：两篇验收稿跑完即可同时验证配图门 + 攒 A0 命中率样本（豆包月账 67-112 元区间待回填）。cron 定时跑验证用 `once at <ISO>` + deliver=origin，LLM 型 cron 高峰期首轮 90-100s 属正常（见 hermes-cron-ops 坑 6），跑完自动回话。
4. **敏感词/行业红线回炉清不净 + 合规判定误报 → 已修（2026-08-21 第 9 跑定位、第 10 跑重验）**：朱雀「镇宅/第一/遥遥领先」、云南「永久/根治」——其中「第一」是**词表误报**（新闻事实语境「咱们才迈出第一步」非广告宣传，同「第一天」白名单教训）。**LLM 合规判定误报根因 = 素材上下文没传够**：朱雀第 9 跑「5 处风险」逐条核对全是素材里的事实——「中国成为继美国之后第二个掌握入轨级火箭陆地回收技术的国家」（素材标题新闻事实）、「重复用十次成本降到 30%」「每公斤五千美元便宜 20%」（素材原文数字，编造闸已 PASS 证明在素材里）——通用合规模型看到具体数字/「第二」就按「虚假宣传/编造」拦。**三处修复（2026-08-21 直接落地，均带验证）**：① `detect.sensitive_industry` 加「第一」序数守卫（_ORDINAL_PATTERNS：第一步/第一次/第一天/第一个/第一回合等全豁免，非序数命中如「全国第一」仍拦——单测三步全过）；② `detect.sensitive_llm` 素材截断 2000→8000（朱雀素材 4477 字，价格/成本数据在 2000 之后根本没传给合规模型；超 8000 保留头 6000+尾 2000）；③ `prompts/07_compliance_judge.txt` 加「判定优先级」：素材中出现过的数字/日期/人名/机构/价格/百分比及基于素材新闻事实的表述（如"继美国之后第二个"）属可核实事实不算编造；绝对化用语只限广告宣传语境（最好用/第一品牌/100%有效），新闻事实里的序数/程度描述（"第一步""推力从百分之百节流到百分之三十"）不算。**第 9 跑验证**：格式压缩硬要求生效（朱雀初稿 2921 字 → 回炉第 1 次 1884 字进区间，小标题 8→3）；文字链四门 + 配图门 3/3 全过，最终仅卡合规误报（AI味 2.55-2.79、编造 0）——合规修复后第 10 跑验证中。
5. **编造年份**：朱雀「2025年8月19日」回炉 1 次没清净（素材是 8月19日无年份，模型自补年份）——编造闸正确拦截，宁可不发布。待观察（年份自补类编造回炉命中率）。

**验收模式教训（2026-08-21 实测）**：本地 mock 全绿（316 断言）≠ 真跑通过——质量单调门 bug 是 mock 覆盖不到的「判定度量选错」类问题（mock 用构造数据测逻辑分支，测不出「真实模型输出 + 真实评分器密度波动」的组合）。修复类任务本地测试过完后**必须跑真实验收（pipeline 真跑 1-2 篇，约 0.1-0.3 元/篇）**才能宣布修复生效。

**验收被拒稿的快速诊断路径（2026-08-21 实测有效）**：pipeline rc=3 后先读 `runs/<run_id>/humanized_v2_r1.json` 的 `quality_audit`，逐项看 `accepted / score_ok / dash_ok / component_regressions / fact_gate / fabrication_gate`——被哪个门拒一眼定位。score_ok=True + dash_ok=True + 两门全过但 accepted=False = component_regressions 误杀（查密度 vs 绝对次数）；日志相似度 0.99 说明模型只做了微改（删破折号这类小修），AI 味已达标时这是合理行为不是失败。

**环境观察项（已关闭，2026-08-21 定位为误报）**：data_source_gate 写安全告警日志遇缺失目录——codex 容器内跑测试报 FileNotFoundError，但宿主机 `/home/ubuntu/.hermes/guard/` 自 2026-08-09 就存在、security_alerts.log 正常追加。**根因 = codex 容器挂载视角问题**（沙箱只挂项目目录/skills/scripts/config，看不到 ~/.hermes/guard）——执行器报告「宿主机缺目录」类告警先查是不是容器视角，别直接当环境问题修。

