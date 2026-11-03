# 工程/架构类任务派活（0819 实测）

gate_config 六类任务（复刻/分镜/生图/出片/文案/分析）不含「工程/架构」。架构/代码骨架类任务用 `TASK_TYPE=分析` + `DATA_SOURCE=<规格文档路径>` 可过（mode=WARN 不阻断）。

## kb_gate 前置：项目目录必须打标记（0819 实测，第一版漏了）

只写 `DATA_SOURCE=` 引用文档**不够**——kb_gate_sg.py 检测到 PROJECT_DIR 存在时，会找 `<PROJECT_DIR>/guard/kb_checked.json`（checked=true），缺失直接 exit 1 BLOCK，整单作废。派活前顺序：

1. `mkdir -p <项目目录>`
2. `read_file` 实际读知识库（skill/PRD/索引），不能假读
3. 写 `<项目目录>/guard/kb_checked.json`：`{"checked": true, "checked_at": "<ISO时间>", "task": "<任务名>", "sources": ["<实际读过的文件路径>"]}`
4. 再走 hermes_task_dispatch.py

### 不要用 SKIP_KB_GATE 豁免工程/架构任务（0819 实测连续两发 BLOCK）

工程/架构任务的任务书必带 `TASK_TYPE=分析`（gate_config 六类没有「工程」类），任务书全文含「分析」意图词 → kb_gate_sg.py 的 `has_content_intent()` 命中 → 即使声明了 `SKIP_REASON=` 也 BLOCK「内容生产任务不允许 SKIP_KB_GATE 豁免」。SKIP 只适用于 prompt 里没有任何内容生产意图词的纯运维/环境任务。

踩坑实录（2026-08-19，头条产线架构方案定案落盘）：
- 发 1：任务书缺 `TASK_TYPE=分析` 标记 → task_brief_gate BLOCK「缺少有效 TASK_TYPE」→ 补四件套（TASK_TYPE/PROJECT_DIR/DATA_SOURCE/PRELOAD_NODES）
- 发 2：任务书带 `SKIP_KB_GATE=1` + SKIP_REASON → kb_gate BLOCK「内容生产任务不允许 SKIP_KB_GATE 豁免」→ 删豁免，补 guard/kb_checked.json 走正常闸
- 发 3：正常闸 PASS，成功派活

正确姿势：**工程/架构类任务 = 任务书四件套 + 项目目录 guard/kb_checked.json，不写 SKIP_KB_GATE**。同一任务书第一次派成功、改过后第二次 BLOCK 的情况出现过（prompt 意图词变化导致），别赌豁免。

### 派活失败后的排查顺序（0819 两连拦总结）

`hermes_task_dispatch.py` BLOCK 后先看错误是哪个闸报的：
- 「缺少有效 TASK_TYPE」→ task_brief_gate：任务书缺 `TASK_TYPE=` 行首裸标记（必须是行首顶格 `KEY=VALUE`，不能带 `>` 前缀），按 gate_config 六类补全四件套
- 「内容生产任务不允许 SKIP_KB_GATE 豁免」→ kb_gate：删 SKIP_KB_GATE 行，补 guard/kb_checked.json 走正常闸
- 「知识库未查询」→ kb_gate：项目目录没打 guard 标记，补 checked=true
- 「权限 denied docker」→ codex 通道不可用，走 ds_native 降级，别反复重试

## Claude 单锁排队（0819 实测）

`claude_remote_wrapper.sh` 有 `flock /tmp/claude_remote.lock`：同时只能跑一个 claude 任务。第二个任务会等锁，但派活 token TTL=10min，等锁期间过期 → BLOCK 白派。**第二任务的任务书+guard 标记提前备好，等第一个跑完（notify_on_complete）再派。**

### 锁的来源（用户问「单锁是谁设定的/我能打开锁」时直接答，别重新查）

- 位置：`claude_remote_wrapper.sh` 138 行 `flock /tmp/claude_remote.lock \`，注释「Claude 使用独立锁，避免从已持有 codex.lock 的执行器调用时自锁」
- 时间：2026-08-18 02:00 加，比备份 `.bak_20260818`（01:58）晚 2 分钟，diff 显示那次改动只加了这两行；会话历史无明确归属，结合时间线大概率是 8/18 凌晨三通道壳加固（ds_fallback AGENTS 注入/SOUL 走壳条款/task_brief_gate 落地）那轮顺手加的
- 打开锁的两种方式（给用户选项）：① 杀持有进程=杀掉在跑的付费任务，白烧钱，违反「已提交任务绝不杀」；② 改脚本删 flock=以后可并发，但失去防自锁保护+多任务同时调 Bedrock 成本叠高。默认建议保持单锁
- 同族并发锁：codex 壳 `/tmp/.codex_gate.lock`（并发槽）、`/tmp/codex.lock`；ds_fallback `/tmp/ds_fallback_codex.lock`、`/tmp/ds_fallback_cc.lock`

## Claude 通道传参顺序（0819 实测）

```bash
python3 hermes_task_dispatch.py --brief <brief.md> --project <名> --target claude \
  -- "$(cat <brief.md>)" /home/ubuntu/workflow/projects/<名>
```

- 第 1 个参数 = PROMPT 全文：用 `$(cat brief.md)` 展开（含标记行+正文），wrapper 写进 PROMPT_FILE 过 kb_gate
- 第 2 个参数 = WORKDIR：必须在白名单（`/home/ubuntu/workflow*`、`/tmp*`、`/home/ubuntu/billing-system*`），目录必须已存在
- 任务书开头钉死「你的唯一产出是真实文件 + 结尾 OUTPUT: 路径」防跑偏（架构任务同样适用）

## DS 原生通道派活（0819 实测：codex docker 不可用时的降级路径）

codex 通道依赖 docker sandbox（codex_sandbox.sh 内 `docker run`）。docker 不可用/无权限时 dispatch 会直接报 `permission denied while trying to connect to the docker API` 并带 docker.sock 路径——这是 codex 通道不可用的信号，不是任务书问题，不要反复重试。按降级规矩走 DS 原生通道：

```bash
cd /home/ubuntu/workflow && TASK_GATE_ENABLED=1 \
python3 hermes_task_dispatch.py --brief <brief.md> --project <名> --target ds_native \
  -- <brief.md> <输出文件.md> --model deepseek-v4-pro
```

- `--` 后第 1 个参数 = 任务书文件路径，第 2 个 = 输出落盘路径，`--model` 可选（默认 flash，分析/策略类升 pro）
- ds_native_invoke.py 内部硬校验 TASK_GATE_TOKEN——必须走 dispatch 拿 token，禁裸调（裸调输出 BLOCK 提示）
- ⚠️ 执行时间 >180s 是常态（分析类全文生成），dispatch 前台跑必超时——用 `terminal(background=true, notify_on_complete=true)` 跑，别前台等
- 返回 JSON：`{"decision":"PASS","output":"<路径>","len":N}`；PASS 后检查输出文件真实存在且非空（本实例 len=7691）
- **中文文件名输出 read_file 误判 binary**（`Binary file - cannot display as text`，实际是正常 UTF-8）——用 `cat`/terminal 读，别当文件损坏
- dispatch 未带 `--` 时可能因 target=codex 撞 docker 报错；确认 target 值用 claude/ds_native 时 `--` 后参数才会透传给执行器壳

## 同一产出文件必须串行派活（0819 实测：两任务并发改同一文件）

claude 单锁只保证「同时只有一个 claude 任务在跑」，**不保证改同一文件的多个任务按序落盘**。头条产线架构方案连续迭代时，原则 C 任务（PID 2152051 跑 40 分钟）与原则 D 任务同时改同一 `工作流架构方案_20260819.md`——执行器实测到「文件 md5 在我只做了一次编辑的情况下两次变化」，只能靠等对方退出 + 重建备份自保，差点后写覆盖前者。

正确姿势：
1. **同一产出文件的任务，前一个 notify_on_complete 后再派下一个**，不要贪并行
2. 任务书末尾写明「本轮为本文件唯一写者，等本轮完成后再派下一个」——执行器看到这句话会主动等并发者退出
3. 迭代式方案更新（v1→v2→v3…）天然是串行链，每个任务书带上当前版本号 + 备份名，让执行器从正确的基线开工

## 实现类任务验收清单（2026-08-19 头条 M1.5 实测）

执行器（claude/codex）返回 OUTPUT 后，Hermes 收结果必须逐项验证再向用户汇报，**不只看 OUTPUT 行**：

1. **编译检查**：`python3 -m py_compile` 所有改动文件（modules/search.py、fetcher.py、illustrate.py、pipeline.py、detect.py、publish.py、tools/test_*.py），编译错 = 当场打回。
2. **跑执行器自带的 mock 单测**：`python3 tools/test_illustrate_mock.py`（M1.5 是 85 项 0 失败）。**mock 覆盖的关键红线要看全**，不是只看总数：计数器硬拦（第 2 次请求真没发出去）、返回结构无 Snippet、源优先级顺序（A0 凑满不调豆包）、无生图代码路径（import 表干净/剥注释无生图端点）。
3. **grep 关键约束落实**：search.py 不 import cost_meter/search_client/doubao_search.py；key 走 env/key_ref 不硬编码（`grep` 代码字面量无 >24 位 key 串）。
4. **执行器报告的环境缺口自己补掉再交付**：本次 claude 说 `~/.hermes/config/doubao_search.key` 本机不存在 → Hermes 从 doubao_search.py L6 提取 API_KEY 建文件（`chmod 600`），再跑一个小验证脚本确认 search 模块 `_key()` 能读到——key_ref 死路补齐后配置才是真可用，不是执行器说缺就缺着交付。
5. **「待验」数字如实标注**：执行器标注未实测的数（A0 命中率/月账区间 40 还是 112 元）在汇报里必须如实说「未实测、等验收跑 5 篇回填」，不冒充已验口径。
6. **范围外遗留单独列**：执行器发现但不属于本轮范围的 bug（如 data_source_gate.py check_body() 只检查第一个文件）单独列「范围外只报告不修」，留给用户定夺，不偷偷改。
7. **复现执行器的自测基线（不信自报，2026-08-19 编造检测闸验收实测）**：执行器报「draft 50 命中」后，Hermes 用验收样本直接调检测函数独立复测（素材 raw_text 应 0 命中、draft/humanized 应命中），与自报对比一致才收。注意口径对齐：本次 hits 被 `max_hits=40` 截断，执行器报总数 50、hits 字段只有 40 条——两个数都真实，验收时按函数签名和配置读懂截断再对比，别把 40 vs 50 当执行器撒谎。
8. **查「只追加不修改」范围外零改动（2026-08-19 编造检测闸验收实测）**：改动类任务重点验证执行器没动范围外的东西——config 只在既有段下加新开关没动模型/阈值（`grep -n -A8 "^fact_check:" config.yaml` 段内确认）；提示词只末尾追加硬约束、原指令一字未改（对每个文件 `tail -3` 确认追加块边界）。执行器报「未动 X」不等于真没动，逐文件抽查。
9. **「守纪律不配」也是合格交付（2026-08-19 site_selectors 派活验收实测）**：配置类任务执行器报告「某域名不配」时，先判是**守纪律**还是**偷懒**——守纪律 = 给了实测依据（robots 404/禁抓、连接超时、结构不支持、同族 robots 不顶替），没写猜测值，且明确写了「什么时候该重测」；这种**不该打回**，验收点 = robots 查了没、猜测值写没写、只改该改的文件、unknown_domain_policy 是否保持。cj.sina.com.cn（豆包最高频源）robots 404 → deny 不配是正确执行，配了才是死配置（永远取不到图还假装活着）。验收别拿「没配齐所有域名」当失败。执行器发现的范围外代码缺口（illustrate.py 分支判据要按域名选 UA）列 M4 上报、不擅动 = 正确行为，收下记入待办。

验收完再汇报：交付文件清单 + 验证结果 + 遗留项 + 下一步（要花钱的步骤等用户「跑」字）。

## 实例：星广归因系统架构（2026-08-19）

- 项目目录 `workflow/projects/attribution/`，任务书 `brief_architecture.md`（可复用模板）
- 范围：目录结构 / SQLite schema（Raw+归因事实+素材版本+批次水位+缺失标记）/ 采集-归因-窗口-可比池-报告模块接口 / CLI / 配置模板
- 口径按极简版 PRD；数据源凭证未确认部分做接口抽象+配置占位，不编造 API 字段
- 派活走 hermes_task_dispatch.py --target claude

## 实例：头条产线 M1.5 配图自动化派活（2026-08-19，codex 通道）

架构方案定稿后派「实现代码」类任务（方案里里程碑 M1.5：配图自动化）。与「出方案文档」任务不同的关键点：

### 派活前必做（顺序不能乱）
1. **先读方案原文关键章节**（§4.7 配图全章/§4.6 判据/§八 里程碑），不是读个标题就打包——任务书要引用方案原文，约束以方案为准
2. **读交接包/项目现状**（.hermes/AGENTS.md 的 handoff 段 + 项目目录 ls + config 校准状态）——上次 cron 会话跑到一半断了，交接包有「代码就位、验收卡搜索通道」的进度，不读就会重复盘点或漏掉已有代码
3. **更新 guard/kb_checked.json**：task 字段写明本轮派活前读了哪些，sources 列实际读过的路径（含 task-brief-gate 自身）
4. 写任务书 → dispatch

### 实现类任务书的结构（0819 实测好使）
- **任务范围清单**：新增/修改哪些文件逐文件列（本例：新增 modules/search.py/fetcher.py/illustrate.py + 改 config.yaml/pipeline.py/detect.py/publish.py）
- **「本轮不做」边界显式写**（本例：不真调豆包 API、不真抓外站图、不真跑产线、不跑 5 篇实测——那步花钱+要素材，等用户确认）——写清楚防止执行器顺手真调付费 API
- **必做项与「不做」分开列**（本例：site_selectors 补人民网/新华网/央视网三家是必做，允许 curl 抓单篇文章页分析结构，与实测 37 同口径）
- **硬约束编号列出**（本例 5 组：search.py 四条/清洗七条/源优先级/illustration.json 契约/配图门判据），每条带方案章节引用
- **执行方法节**：先 read_file 方案原文 → 先读现有模块风格保持一致 → 实现 → 本地 py_compile + mock 单测（不真抓网）→ 交付清单
- **带「Hermes 已核对的证据清单」+「自测基线」（2026-08-19 编造检测闸派活实测，两类都省执行器时间/防跑偏）**：
  - 证据清单：Hermes 已逐项核对的事实（本次：素材 vs 成稿 30+ 项编造细节，逐项列「素材里有/没有」，附核对方法），任务书直接给，执行器不用重复核对、直接基于证据设计规则；
  - 自测基线：给执行器可量化的验收标准（本次：draft.json 应命中 ≥10 编造项、素材 raw_text 自身零命中、humanized 同批命中），执行器自测跑完对照基线，通过与否一目了然，Hermes 收结果也好验证——比「实现后自查」模糊指令强得多。
- 任务书与方案冲突时**以方案原文为准**——避免任务书抄漏时执行器死磕任务书

### codex 通道本次可跑
本次 `--target codex` 派活成功（background + notify_on_complete），未触发 docker permission 错误——与 0819 上午「codex docker 不可用走 ds_native」记录不同，环境可能已修。**判定通道可用性以当前实测为准，别拿旧记录当死结论**；dispatch 报 docker 错时再走 ds_native。

### 向天行者盘点项目进度 = 大白话（0819 用户两次要求「大白话说」）
用户问「还有哪些没弄完的」时，盘点方法：方案 §八 里程碑清单 vs 项目目录实际文件（modules/ 缺哪些、config `_calibrated: false` 几处、runs/ 有无成稿）→ 按优先级列缺口。**但汇报必须翻大白话，术语要翻译**：
- M1.5 = 配图自动化（写代码自动找图配图）
- `_calibrated: false` = 分数线还没校准（只能试跑、不能真判稿子合不合格）
- dry-run = 试跑只记分不判 FAIL
- A0 命中率 = 多少篇稿子靠素材自带图就够（不用花钱搜）
- 里程碑编号/模块名/字段名一律不裸用，先讲人话再带括号
用户明确表示技术报告要翻白话（记忆里 0812 已记，0819 又触发一次——说明盘点汇报最容易犯术语病）。

### 并行编排：执行器改代码 + Hermes 自己跑现有工具（2026-08-20 实测，与「同一产出文件串行」互补）

用户「全部弄完啊」一次给多个待办时，按产出冲突分组并行：

- **执行器（claude/codex）独占改的**：代码/提示词/config 修改类（串行派，claude 单锁）——本次 A+C（文字链三修复）→ B（域名覆盖）串行派，任务书提前写好，A+C 一交付验证完立刻派 B
- **Hermes 自己跑现有工具的**：已有 CLI 的离线工具/验证类（不写代码、不冲突）——本次与 A+C 并行跑了：`tools/calibrate.py --with-llm`（校准，~0.02 元）、`tools/hotlist.py --dry-run`（免费验证）、`tools/anchor.py`（攒批补锚点，纯 HTTP）、`tools/hotlist.py --json`（完整链路真跑 0.30 元）。这些不占 claude 锁、不依赖执行器产出，放着浪费
- **判据**：只跑不改文件 = 并行安全；改文件 = 串行（照「同一产出文件串行派活」）；cron 这类依赖前置产出的（素材链没通建 cron 每天 BLOCKED 没意义）等依赖解除再建

执行器跑重任务（三修复类 30-40 分钟）时不要反复 wait 刷屏，用 `process(action=wait)` 间隔 + notify_on_complete 兜底，中间查一次 `ps aux | grep claude` 确认进程活着即可（CPU 正常=在干活，不是卡死）。

### 给 A/B 选项前先摆验收标准原文（0819 用户「你那个标准你都没发给我，我怎么去定啊」）

验收跑出 rc=3/FAIL 后想让用户在「修判据重跑 vs 先看稿」这类选项里拍板时，**必须先引用验收标准原文**（架构方案里程碑验收条款逐条照抄，别只转述），再对照当前实测状态（哪条过了哪条没过）列选项。用户点破过：光给结论让人盲选 = 信息不全下拍板。两个连带纪律：① 标准里涉及的定性（官方规则/客户标准/行业经验/自己脑补）必须分来源层，脑补的「经验」直接收回别说，用户会一句「哪里来的」点破；② 选项里提到的每个数（字数/成本/命中数）都要能说出处，说不出来就先搜再答。本会话实例：验收第一跑后只给 A/B 没摆 M1 验收标准 → 被点破；随口说「头条长文 1500-2500 字数据最好」→ 被追问来源，搜索证实真实区间 1000-2000 字、官方门槛仅 100 字。
