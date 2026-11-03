# 配图链三连根因 + 去AI味修复定案（2026-08-21 验收驱动复盘）

> 触发场景：头条产线「文字链通但配图 0/3」「AI味失效」「真实验收不过」的排查与修复复盘。
> SKILL.md「去AI味失效诊断与六项修复」一节的详细版；本文件含完整根因链、证据、修复对照。

## 一、去AI味失效 → 六项修复（结论速览）

- 主根因：成稿破折号密度 ~3.2 次/千汉字 vs 锚点 0.495（6.5 倍），占总 AI 味分差 74%
- ⑤去味「有改文没降分」：相似度 0.64-0.85 证明改了，AI 味分反升（24.95→28.51 等）
- ④拟人化「近乎没改文」：相似度 0.9877-1.0000
- 修复：P0-1 质量单调门 / P0-2 分项反馈 / P0-3 calibrate.py 口径（statistics.median + 只统计真闭环样本）/ P1-1 废 difflib>0.9 单一判据 / P1-2 编造回炉后 fact_locked 持久关 ④⑤ / P1-3 密度制评分器 density_v2 + 重校准 ai_score_max 16.9→8.4
- 验收：朱雀 AI味 2.87-5.41、云南 3.45-6.38（阈值 8.4），修复前 25.8-44；编造 2→0、事实锁生效

## 二、质量门密度误杀 bug（P0-1 落地时引入）

- 现象：朱雀 8.17→6.6、云南 10.43→9.52，破折号 4→0，事实/编造门全过，仍被拒 rc=3
- 根因：evaluate_deai_candidate 的 component_regressions 比较「分项」**密度值**（容差 +0.01）；删破折号后字符数变、分母变、密度微升 0.02-0.25，绝对次数没变 → 误判「分项倒退」
- 修复：只比较四类离散特征**绝对次数**（过渡词/AI词/否定排比/三段式），破折号由 dash_ok 独立把关
- 教训：密度归一后任何改文本长度的操作都变分母——「分项不得倒退」一律用绝对次数

## 三、配图链三连根因（B 源 0/3 → 3/3 泛图兜底）

### 根因 1：Commons API HTTP/1.1 限流
- 现象：cands_commons 一直「查询失败: HTTPError」（403 Too Many Reqs）
- 排查：curl 默认（HTTP/2）200；`curl --http1.1` 403；python urllib/requests（HTTP/1.1）稳定 403（加 Accept/换 UA 无效）→ **Commons 按 HTTP 版本限流，HTTP/2 放行**
- 修复（fetcher.py，codex）：get() 遇 HTTPError 403 且域名精确匹配 commons.wikimedia.org → subprocess curl --http2 重试（同合规 UA/timeout/blacklisted/_throttle）；非 Commons 域/非 403 不触发
- 通用排查启示：python 库稳定 403 而 curl 稳 200 时，先 `curl -sv` 看协议版本、`curl --http1.1` 复现即定位；别只查 UA/头

### 根因 2：视觉合规超时误杀（最隐蔽）
- 现象：img1.jpg 下载成功（JPEG 1080x607）且清洗过了，但 illustration.json images=0；fail_reasons 里没有对应记录
- 排查链：_download_and_accept 返回 img → 视觉合规终判 L612-627 → L627 `picked = [i for i in picked if compliance.pass is not False]` 过滤。vision_check timeout=180 超时返回 `(None, [...])` → `bool(None)=False` → 全剔
- 根因：`image_compliance_check.py` 读 `providers.custom_ark.base_url` **直连 ARK**（新加坡机直连被网络挡）→ request_with_retry 连接类错误重试 8 次（退避 2^n 上限 30s）→ 单张 >240s
- 修复（image_compliance_check.py，备份 .bak_20260821）：ARK_BASE/ARK_KEY 优先读 `auxiliary.vision.base_url`（`http://127.0.0.1:18888` 本地代理→隧道→广州 relay→ARK）；实测 3.2s/张 PASS（img1「火箭发射正常场景，无违规」）
- **纪律：新加坡机所有 ARK 类调用走 18888 代理，直连必超时**（config auxiliary.vision.note 2026-08-09 已写，脚本没跟上——改脚本前先查 config 里有没有现成代理配置）

### 根因 3：B 源 relevance 恒 0 被门槛拒（docstring 与实现矛盾）
- 现象：降级级3「B 源泛图兜底（…不阻断）」走了但 0 张
- 根因：B 源 relevance_score 恒 0（来源分 0 + 英文泛图 vs 中文事件文本重叠 0 + alt 0）→ rel_min=55 必拒；illustration_gate docstring 明说「relevance_downgraded 泛图仍算过门」实现没豁免
- 修复（illustrate.py）：try_candidates 加 `rel_min_override` 参数，降级级3 B 源传 0 全放行；detect.py illustration_gate 加 `not img.get("relevance_downgraded")` 豁免
- 验证：降级图 3 张 pass=True；非降级 relevance 0 仍拒

## 四、配图门终态（2026-08-21）

- Commons 泛图兜底 3/3 可过门：license/署名（attribution 串）/视觉合规（3s PASS）齐全；发布清单标注 downgraded「建议人工替换为事件图」
- A1 事件图覆盖仍受 robots 纪律限制（人民网子域 sc/bj/finance.people.com.cn、news.cctv.cn、english.news.cn 未配选择器或 robots 拦）；事件图靠豆包返回已配域（澎湃等）碰运气
- 配图模块单独验收（1-2 分钟）：`python3 modules/illustrate.py --material inputs/x.json --run-id test_x --title "t" --subheads "一、a,二、b,三、c"` → 看 `assets/test_x/illustration.json` 的 result/count
- 排查配图 0/3 看证据顺序：日志 slot 行 → assets/<run>/illustration.json fail_reasons → _rejected/*.txt 拒绝原因 → 对应模块代码

## 五、派活/测试卫生

- 任务书 TASK_TYPE 必须是白名单：复刻/分镜/生图/出片/文案/分析——写「测试验证」等自创类型会被 dispatch BLOCK（hermes_task_dispatch.py 配置任务类型不含）
- 离线 mock 全绿（316 断言）≠ 真实验收通过；修复后必须 pipeline 真跑 1-2 篇（DS 1-3 毛 + 豆包 0.3 元/篇）确认
- 被拒稿快速诊断：读 `runs/<run_id>/humanized_v2_r1.json` 的 `quality_audit`——score_ok/dash_ok/component_regressions/fact_gate/fabrication_gate 逐项看，被哪个门拒一眼定位

## 六、合规误报两修（2026-08-21 第 9 跑后，全链只差这道门）

- **行业红线「第一」词表误报**：朱雀正文「咱们才迈出第一步」被 `sensitive_industry` 拦（forbidden 词表含「第一」，简单 `kw in text` 包含匹配）。修：detect.py 加 `_ORDINAL_PATTERNS` 序数守卫（第一步/第一次/第一天/第一个/第一回合/第一轮/第一阶段/第一名等 20 个）——所有「第一」命中位置都被序数模式覆盖则整条豁免；「全国第一」「第一品牌」等非序数仍拦（单测三步验证过）
- **LLM 合规判定误报 = 素材没传够**：`sensitive_llm` 里 `json.dumps(material)[:2000]` 截断——朱雀素材 4477 字，价格/成本/「第二个掌握回收技术」等事实全在 2000 字符之后，合规模型看到数字就当「虚假宣传/编造」拦（第 9 跑 5 处风险逐条核对全是素材事实，编造闸 PASS 佐证）。修两处：
  - detect.py：素材截断 2000→8000（超 8000 保留头 6000+尾 2000，事实数字常在正文主体）
  - prompts/07_compliance_judge.txt 加「判定优先级」段：素材中出现过的数字/日期/人名/机构/价格/百分比及基于素材新闻事实的表述（"继美国之后第二个…"）属可核实事实不算编造；绝对化用语只限广告宣传语境（最好用/第一品牌/100%有效），新闻事实里的序数/程度描述（"第一步""推力从百分之百节流到百分之三十"）不算
- **通用启示**：合规/审核类 LLM 判定的 prompt 必须把「判定依据的素材事实」完整传进去 + 明示「素材事实不算违规」，否则通用审核模型会把新闻事实数字当编造、把序数表述当极限词。截断要按素材真实长度留余量，别拍 2000。
