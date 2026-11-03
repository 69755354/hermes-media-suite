## 五之补、项目进度盘点清单（用户问「搞完了没/还有哪些没弄完」时用）

用户会反复追问产线进度，不要凭记忆汇报——照方案 §八 里程碑清单逐项对照项目目录实测状态：

- `runs/` 看**实际产出**（成稿/报告文件）vs 只有代码骨架：runs 里 `文章_*.md`（20260819_2304 宇树/20260819_2358 朱雀/20260820_0007 云南）+ `_anchor_report.json`（43 篇锚点）= M1 文字链三篇验收已跑通（编造闸 2026-08-19 落地：50→5→0；**小标题/字数硬门 2026-08-20 落地**：format_gate 强制小标题 2-4 个、字数 1800-2200）；配图链 2026-08-20 域名覆盖修复后：site_selectors 8 站（原 6 + 澎湃 2：chinanews/news.sina/people/news.cn/xinhuanet/fj.news.cn/m.thepaper/www.thepaper），illustrate.py 按域名判头条已修（A1 取图 0→9 张），**澎湃当期图 CDN 本机不通 → A1 对澎湃仍 0 张（2026-08-20 已实测 relay 中转可解并派活接入，见「当前配图链状态」）**；cj.sina.com.cn robots 404 不配、stcn 高防超时不配
- `modules/` 对照方案职责表查**缺哪些模块**：M1.5 配图三件套 `illustrate.py` / `search.py` / `fetcher.py` + 编造闸 `fabrication.py`（2026-08-19 晚：代码全建；site_selectors 已补见下，配图链待重跑实测）
- `config.yaml` 数 `_calibrated: false` 数量 → 判断阈值校准状态（未校准 = 仍是 dry-run 只记分不判 FAIL，真闭环未开）
- `corpus/_anchors/` 数量 vs 验收线（≥30 篇，目标 60-70）→ 判断 M0 是否达标（2026-08-19：27 篇差 3）
- `guard/kb_checked.json` → 知识库物理卡点是否已过
- 方案「待验」标记位置 = 还没实测的数字（A0 命中率/按域名带图率等），说「搞完了」前必须区分「文档定稿」vs「代码落地」vs「实测验收」三层

汇报口径：分层列（已搞完 / 没弄完按优先级排 / 待验数字 / 范围外遗留），每项给证据（文件状态），最后给下一步建议。

**盘点欠账必须实测复核，不照抄昨天的汇报（2026-08-20 教训）**：记忆/旧汇报里记的「欠账」可能已随时间解决——例：8-19 说「两机成本回填都是 0（cron 没跑过）」，8-20 查 cron `cost_backfill.py` last_run_at=01:00 ok、state.db `sessions.actual_cost_usd` 近 7 天已有值 182.34 美元 → 该欠账已消。查法：cronjob list 看 last_run_at/last_status + 查实际数据（SQLite 列值）双确认，报告里把「已解决不欠账的」单独列一段，避免用户以为还欠着。

### M1 验收第一跑实测（2026-08-19，宇树科技上市素材）

验收样例怎么跑、跑完发现什么，详见 `references/acceptance-run-20260819.md`。核心结论：

1. **验收素材构造**：豆包搜索直调（POST `https://open.feedcoopapi.com/search_api/global_search`，Bearer key 读 `~/.hermes/config/doubao_search.key`，响应结构是 `Result.Documents` 不是 `data.web`）。**必须选外站源**（新浪财经 `cj.sina.com.cn` 可 curl + `<p>` 正则提取正文，够厚 3000+ 字）；头条站内链接（`m.toutiao.com`）不能用——违反原则 A「全程零头条抓取」验收项。
2. **跑前预检（不花钱）**：raw_text vs corpus 4-gram 包含率、原则 A 断言、校准状态——三步都过再花钱。
3. **跑法**：`pipeline.py <material.json>` **不带 `--model`**。带 `--model flash` 会被原样透传成模型名 → API 400「supported API model names are deepseek-v4-pro or deepseek-v4-flash, but you passed flash」。config 默认就是 flash，不需要 override。
4. **关键坑：humanize 生效判据对财经长文过严**——`deai_rule_card` 用字符级 difflib ratio > 0.9 判「未生效」→ fallback → 仍超则 rc=3。但财经稿必须保留全部数字/人名/事实（1100元、629%、4449亿、王兴兴），字符级相似度天然高；本跑实际改写有效（肉眼口语化 + AI味分 25.78→23.94 + 原创度 97.14→97.8%）仍被判 0.9053 > 0.9 误杀。判据应改 4-gram 相似度或放宽字符阈值，并以 AI 味分下降为辅助信号。
5. **红线词观察**：「第一」命中是「第一天」误报（白名单未覆盖）；「跟着买」用于描述市场参与者行为也命中财经词表，严谨应改写（虽然语境是第三人称描述不是荐股）。
6. **成本基准**：单跑 13 次调用合计 0.1126 元（非高峰 flash，含去味 fallback 重试 1 次 0.014 元）。
7. **AI 编造细节 = fact_check 检测盲区（发布即虚假信息，最重）**：成稿出现 30+ 项素材原文里没有的具体数字/公司名/时间点——门禁 428 人、特斯拉 Model S 傍晚 6 点 10 分、量化模型 1 点 30 分触发卖出、大单买入 61%/卖出 73%、双环传动涨 7.2%、汇川涨 5.8%、乐视、波士顿动力、锁定期 36 个月、1334.7 亿等。素材 3329 字里实际只有 王力宏/每台50万/持股30% 三处。现有 `modules/detect.py` fact_check 只做「成稿数字能在素材里找到」的一致性检查，**素材里没有的数字被当"新信息"放行**。真人写稿只写自己知道的事，AI 会生成一堆听起来很真但没出处的时间/数字/公司名——这是比 AI 味更危险的雷。修复方向：编造细节检测闸——成稿出现素材 raw_text 里没有的具体数字/专名/时间点 → 触发重写（带「只用素材里的事实」约束）或 rc=3，不许静默放行；**已交付并验收（2026-08-19 Claude 实现，任务书 `brief_fabrication_gate.md`）**。落地：`modules/fabrication.py`（词表逻辑）+ `detect.fabrication_gate()`（只判不改）+ `pipeline.fabrication_rewrite()`（独立计数器不占 loop.max_rounds，回炉用尽 rc=3）+ `rules/fabrication_rules.yaml` + `prompts/08_fabrication_rewrite.txt` + 5 个创作提示词末尾「事实边界硬约束」（02 明确「技能五联网实际不存在」——编造头号来源是模型以为能联网，治本在提示词层）。config 只在 `fact_check:` 下加 3 开关（fabrication_check/max_rewrites/max_hits，非统计阈值不受 dry-run 豁免）。**验收基线（Hermes 独立复测，不信自报）**：素材 raw_text 0 命中（零误杀）、draft/humanized 40+ 命中（max_hits=40 截断）pass=False。**第二跑实测验证（编造闸真生效）**：编造 50 处（第一跑）→ 提示词约束后初稿仅 5 处 → 编造闸触发回炉 1 次清零；文字链全通（4756 字、AI味 26.16、原创度 97.78%、零敏感词、无 AI 标注），rc=3 只剩配图门（site_selectors 未补 0/3 张）。**已知漏检（如实记录）**：无后缀品牌名（高盛/英伟达）、纯汉字数字的编造抓不到——取向宁漏不误杀，误杀会让 100% 稿子 FAIL 闸门即废。防误杀边界：词边界（「第一天」不算）、同义改写（「三千台」vs「3000台」不算）、抽象评论/合理推断语言不算，只抓具体事实性细节（数字/专名/时间点）；编造检测是客观事实判定，不受 dry-run 影响一律真判（同配图门口径）。

### site_selectors 补选择器（2026-08-19 23:23 Claude 交付，派活任务书 `brief_site_selectors.md`）

豆包返回的报道页域名多数没配选择器 → `unknown_domain_policy: skip` 整站跳过 → 配图 0/3 张。补选择器任务书要点：域名清单 = 豆包实际返回但未配的；硬约束 = 每站先查 robots（404/禁抓 → 写清原因不配，照 news.cctv.com 先例）、选择器必须 curl 实测不许猜、未知域名保持 skip；允许 curl 抓单篇分析结构（与实测 37 同口径）；不真跑产线不调豆包。交付结果：

- **www.xinhuanet.com**（新华网主域，豆包返回的是这个域而非已配的 www.news.cn）：实测 9 篇、89% 带图率，与 news.cn 同构 → 复用 `span#detailContent`（回落 div#detailContent/div#detail）。site_selectors 按 netloc 精确匹配，配了 www.news.cn **不会**自动覆盖本域，必须单独列。隐患：700×420「栏目标识图」（主色 0.397 < 0.65 过文字卡门）靠清洗拦不住，只能靠相关性/图注判据挡
- **fj.news.cn**（福建频道）：实测 8 篇、38% 带图，同构复用；robots 只能走 http（https 504）；**水印风险**——右下角「新华社/XINHUA NEWS」蓝底块，watermark_edge_ratio 0.617-1.618 < 2.0 初筛放行，会漏到视觉终判，已记为已知风险（调阈值牵连其它站，M4 待决）
- **cj.sina.com.cn**（豆包最高频）：robots.txt HTTP 404 → deny **不配**。⚠️ 不能拿同族域 robots 顶替（www.sina/news.sina/finance.sina 都 200 但 cj.sina 404 各判各的）——没实测就不写「财经频道大概同构」的猜测值
- **www.stcn.com**：http/https 30s 超时（阿里云 DDoS 高防屏蔽本机出口）→ 不配；注明是网络屏蔽非站方禁抓，通了须重跑实测
- **m.toutiao.com**：不在 site_selectors 补——A2 走独立实现（`is_toutiao` 分支 `div.pgc-img` data-src）完全不查选择器；日志那条 skip 是豆包把头条页当外站返回。⚠️ 决定性实测：UA_COMPLIANT 下头条页 302 到 www.toutiao.com 静态壳（三篇 len 全 72914、img 数 0），配任何选择器都是死配置；要取豆包返回的头条页图须改 illustrate.py 分支判据（按域名而非 source_type 选 UA）——已列 M4，范围外不擅动
- **纪律沉淀**：配置「看着活的死配置」比不配更坑（robots 拦的域配了选择器也永远取不到图）；不写猜测值是执行器纪律；交付验收 = YAML 解析过 + modules 零改动 + unknown_domain_policy 保持 skip + 验证脚本从 config 读选择器不硬编码

**当前配图链状态（2026-08-20 四尾巴修复落地后）**：文字链全通（编造闸生效）；site_selectors 已配 8 站（原 6 + 澎湃 2，见下「域名覆盖修复交付」）；illustrate.py 的 m.toutiao 判定 bug 已修（A1 取图 0→9 张）。**澎湃当期图 CDN（imgpai.thepaper.cn）新加坡机直连不通 → 已落地 relay 中转解（2026-08-20 实测全通）**：fetcher.py 新增 `get_image()`（relay 优先、失败自动降级直连、URL 必须 `urllib.parse.quote(url, safe='')`）+ config 开关 `illustration.image_relay`（**默认空串=不启用**，启用需设 `http://127.0.0.1:8899`；经广州机 8899 relay 中转下载实测 HTTP 200/171KB/JPEG 1035x582）。**覆盖率天花板在发现层**：11 个跳过域名 10 个被 robots 拦，补选择器已到顶；2026-08-20 已调 doubao query 模板为「{event} 新闻报道，优先中新网、新华网、人民网、澎湃新闻、新浪新闻」并实测（见下「豆包 query 调优实测」）。**2026-08-21 更新**：B 源 Commons 已修 HTTP/1.1 限流（403→HTTP/2 降级）；文字链四门（AI味/编造/格式/敏感词）已验证收敛；配图门最终 **3/3 过**（Commons 泛图兜底 + 视觉合规走 18888 代理 3s/张 + B 源 relevance 门槛 0 放行 + detect 豁免 downgraded 图，详见「去AI味失效诊断与六项修复」剩余卡点 3 的「配图链剩余两连根因」）。A1 事件图覆盖仍受 robots/未配选择器限制（合规补不了），事件图靠豆包返回已配域碰运气。

### 域名覆盖修复交付（2026-08-20 凌晨，Claude 实现，任务书 `brief_domain_coverage.md`，84 PASS / 1 FAIL）

豆包返回域名大面积覆盖不上 → 配图链卡死（A1 取图 0 张）和 M2 素材链（取不到正文不产素材）。任务书 = 按 `search_trace.skipped_domains` 频次补 site_selectors，每站先查 robots，硬约束 curl 实测不许猜。结果：

**配上（1 家媒体 / 2 个域名）——澎湃：**
- `m.thepaper.cn` + `www.thepaper.cn` → 容器 `div.cententWrap__UojXm`（**站方把 content 拼成 `centent`，照抄**；m 站还有外层 `div.cententWrapBox__X5Ljo`；www 站无 Box 外层只配一个）
- 实测 4 篇当期文章各出 5/9/12/16 张正文图；`data-src` 载真图、`src` 是 1×1 base64 占位；无 width/height（declared_w/h=0）；图注在紧随 `<p>` caption 抽得到；样本 1080×720 JPEG 67KB 无水印
- ⚠️ 哈希后缀 `__UojXm` 是 Next.js 构建期生成，**对方前端发版会变**——失效表现 = 该域名 0 张图（风险 11 典型）

**实测后不配 9 个域名（robots 纪律，逐条留档 config 注释）：**
| 域名 | 实测结论 |
|---|---|
| `m.sohu.com` | robots 200 但 `User-agent:* → Disallow: /` **全站禁抓**；只对 Baiduspider/Bytespider/Googlebot 等具名爬虫放行——不冒充具名爬虫，落在 `*` 段 |
| `news.sina.cn` | robots **404**（HTTP/2 404，body 是新浪首页 HTML）。⚠️ 与已配 `news.sina.com.cn` 不同——**子域各查各的**，不能拿同族域 robots 顶替 |
| `tags.news.sina.com.cn` | 连接超时 + 标签聚合页非报道页 |
| `finance.people.com.cn` | robots **404**（https 证书不含此 SAN 只能 http，http 下 404）；**结构上同构**（`div.rm_txt_con` 命中 2925B/2 张图）→ 「能抓但不许抓」，robots 结论优先于结构可行性，**不因同构复用主域选择器** |
| `chinaview.cn` | robots 404 |
| `www.trendsgroup.com.cn` / `www.yn.gov.cn` / `ccwb.yunnan.cn` / `xywb.jjxw.cn` / `zzwb.zznews.gov.cn` | **TCP 连接超时**（http+https、15s/40s 两轮全 000）→ robots 拿不到不谈选择器 |

**illustrate.py 修 m.toutiao UA 分支（连带故障，不是单 bug）：**
- 新增 `is_toutiao_page(url)` 按 host 后缀匹配（`host == "toutiao.com" or host.endswith(".toutiao.com")`）——**不用 `"toutiao.com" in url`**（会把 `http://evil.example.com/?u=toutiao.com` 误判成头条域）
- `images_from_page` 的 is_toutiao 改「域名判定 or source_type」
- 原 bug 两环：合规 UA 下头条页 302 到 www.toutiao.com 静态壳（`<img>` 0 个）+ 还会去查 site_selectors 把整域跳过 → 修后 **A1 路径取图 0 → 9 张**（A2 9 张无变化）
- `_download_and_accept` 的同类 UA 分支**故意不改**：实测图片 CDN 不挑 UA（合规 UA 200/68KB 正常），按「不伪装浏览器 UA」保持原样，并在代码里写明实测依据防下轮被当漏改

**当时两件没解决的事（后 2026-08-20 已跟进）：**
1. **澎湃图片 CDN 分两代**：当期新图在 `imgpai.thepaper.cn`（TCP 443 直连 3 次全超时），旧图在 `imagepphcloud` 能通。**2026-08-20 已实测出解**：经广州机 8899 relay 中转下载成功（HTTP 200/171KB 真实 JPEG，见「当前配图链状态」）——不是「代码修不了」，是「要走中转」；已派 codex 接入 fetcher/illustrate.py（config 开关 `image_relay`，relay 失败自动降级直连，URL 必须 `urllib.parse.quote(url, safe='')`）。M3 素材链只要文本不受影响（实测端到端取到 4219 字）
2. **1 项 FAIL 是既有 fixture 问题**：fixture 的 mock 正文触发编造闸，而 detect.py 里编造闸优先级高于配图门——2026-08-20 已打包进四尾巴修复任务（route_back_to 判定冲突：先分析测试期望 vs 业务意图——正文有编造时优先 fabrication 才是正确业务行为——再修 detect.py 或 fixture）

### M1 三篇验收走完实测（2026-08-19/20，三篇全跑，详见 `references/m1-acceptance-20260819.md`）

三篇素材（宇树科技 4727 字/朱雀三号 4477 字/云南低价团 3729 字）**文字链全部跑通**，编造闸三篇全验证（50→0、1→0、0），无极限词、无 AI 标注、零锚点抓取全过。暴露的四个问题及处置状态（**2026-08-20 三修复已落地，见下**）：

1. **小标题一个都没生成（M1 硬指标 FAIL）**：提示词要求「全文2-4个一级小标题（一、二、三）」，模型完全没执行，三篇正文无一个「一、」。发布清单小标题检查把主标题当小标题数，实际为 0——别被发布清单的「小标题 1」骗了 → **已修：detect.format_gate 强制小标题 2-4 个（`^[一二三四五六七八九十]+、` 独立行计数），不合格回炉（prompts/09_format_rewrite.txt）**
2. **字数没控住**：目标 1800-2000，实际 3700-4700 超一倍。**根因（Claude 交付时定位）不是模型不听话——`02_feed_write.txt` 按三个部分各渲染一次，每部分都收到「全文1800-2000字」，各写一遍 = 5000 字**。已修：追加块改成按部分分配额度（300-450/1000-1300/350-500）+ format_gate 字数硬门 1800-2200（汉字数，不含标点空白）
3. **配图链系统性失败（M1.5 一条验收没过）**：三篇全 0 张。豆包返回域名（m.toutiao 占大头、finance.people.com.cn、chinaview.cn、yn.gov.cn、ccwb.yunnan.cn 等）与 6 个已配站完全对不上；site_selectors 按 netloc 精确匹配子域不通用；B 源 Commons/Pexels 也 HTTPError。补站按 `search_trace.skipped_domains` 频次排优先级（2026-08-20 域名覆盖任务派活中）
4. **编造回炉后 humanize 重引入编造**：朱雀篇编造回炉清零后，拟人化/去味环节又引入 1 处新编造 → 撞满 max_rewrites=1 出 rc=3 → **已修：编造回炉后跳过 ④⑤ 环节**（拟人化是编造重引入头号来源），用调用计数断言证明无编造词

AI味实测 26-44 全超阈值 25（dry-run 只记分没判，M2 校准后都会 FAIL，回炉率会很高）。

### 文字链三修复交付（2026-08-20 凌晨，Claude 实现，任务书 `brief_three_fixes.md`，验证 73/73+35/35 全过）

- 新增：`prompts/09_format_rewrite.txt`（格式回炉卡）、`tools/test_format_gate.py`（73 断言）、`tools/test_rewrite_loop.py`（35 断言）
- 修改：detect.py 新增 `format_gate()`（只追加 4 字段不破坏兼容）、publish.py（严口径小标题+字数区间 1800-2200）、pipeline.py（格式回炉+编造回炉后跳 ④⑤+rc=3 出口）、config writing 节（target_chars 1900/min 1500/subhead 2-4）、提示词只末尾追加原指令零改动
- **测试卫生教训（Claude 如实披露）**：第一版测试 `import detect` vs `import modules.detect` 是两个模块对象导致桩失效，产生 8 次真实 compliance_llm 调用（0.015 元）越过「不真调 DS API」边界——已加零 API 硬断言结构性防；测试落盘的 runs/ 桩目录要删；run_id 分钟粒度会导致多组测试互相覆盖
- 效果：格式门（小标题/字数）是客观判定，不受 dry-run 豁免（同编造闸口径）

### M3 热榜选题完成（2026-08-20 凌晨，Claude 实现，任务书 `brief_m3_hotlist.md`，自测 49/49）

- `tools/hotlist.py` 从桩实现完整：四源聚合（头条 hot-board 复用 anchor.fetch_hot_board；百度/搜狗/新浪写了解析器）+ 选题打分（热度 `0.98^rank` 源内名次归一 × 领域适配 × 合规降权，金融/医疗 0.5 降权、涉政/司法/伤亡/未成年 0.0 硬排除）+ 素材链路（豆包搜 URL → 只抓已配站 → 正文 ≥300 字才算报道，取不到真正文不产 material.json——物理防编造）
- **实测源可用性**：只有头条 hot-board 开（robots 放行 50 条）；搜狗/新浪解析器写好了但 robots 404 → 不启用（拿到 robots 依据后开关一开就行）；百度主机被屏蔽（连接超时）→ 不写猜测解析
- 打分 dry-run 抓到的真 bug：某 finance 热词「美财政部救市」拿满分排第一（「财政/救市」不在词表）→ 改双路判据（词表+平台 InterestCategory）+ 回归单测
- **完整链路真跑验证（0.30 元）**：豆包搜 8 URL 全 skip（澎湃/搜狐/头条/新浪子域都没配选择器）→ BLOCKED 不产素材（防御路径正确，但再次证明选择器覆盖是核心瓶颈）
- cron 待素材链通了再建（现在建每天 BLOCKED 没意义）
- **⚠️ 豆包免费额度耗尽 = 10406（2026-08-30 实测，已解决）**：火山引擎每账号每月免费 500 次，8 月开发+测试用完了。**已切到 Custom 版 web_search**（用户已开按量后付费，余额通用）。Global 版 endpoint `search_api/global_search` → Custom 版 `search_api/web_search`，请求体和响应格式同步改。详见 `references/doubao-search-integration.md` Global→Custom 切换节 + `references/hotlist-sources-and-daily-auto-20260830.md`

