---
name: video-render-gate-debugging
description: 视频出片被门禁拦截时排查放行。触发：出片BLOCKED/哈希不符/评审误扫。
version: '1.0'
author: hermes-curator
license: internal
metadata:
  hermes:
    tags: [video, gate, seedance, debugging]
    related_skills: [video-production, workflow-execution-guard, seedance-2-0-mini-workflow]
---

<!-- CANONICAL-RULINGS-BEGIN -->
> ⚠️ **本文件与视频线统一口径冲突的地方，一律以统一口径为准（用户 2026-10-01 逐条拍板），旧写法作废。**
> 统一口径单一事实源：`.hermes/skills/newmedia-operations/huolong-replica-template/references/current-rulings-20261001.md`
> 摘要：段时长＝字数÷5.5（不提速）；句数不限、只看语言逻辑；双人段必须互相说；画面/人物/禁止事项照旧写，只有配音部分不写段首段尾语速；画幅听用户当次要求（默认竖屏 720×1280，双人优先横屏）；LOGO 念到 CTA 时淡入保持 1.5 秒；默认只用快乐马出片，婵镜/Seedance/探店线用户点名才用；成片响度 -14 LUFS；BGM 0.25；CRF 18／aac 128k／24fps；实念率底线 90%；参考片＝过审基准，照抄不退稿。
<!-- CANONICAL-RULINGS-END -->


# 视频出片门禁排查与 API 提交清洗

## When to Use

- 出片任务被 BLOCKED：出片确认未通过、工作流门禁不过、哈希不符、评审误扫
- 派 codex/claude 写分镜/提示词/出片分析被知识库卡点拦截
- 提示词包要提交出片 API 前的格式清洗（默认快乐马 happyhorse-1.1-r2v；Seedance 仅用户点名时才用）
- 多镜分片声音一致性检查

## 适用场景

出片前被多层门禁拦截（默认只走快乐马 happyhorse-1.1-r2v；婵镜/Seedance 仅用户点名时才用，门禁链路同样适用）：出片确认、工作流门禁、导演意图评审、知识库卡点。以及提示词包提交 API 前的格式清洗。

## 出片链路 gate 顺序（SG 机 execute_api.py run_seedance_exact）

```
闸0 project_dir 必须有（fail-closed）
闸1 confirm_gate node12_render（出片确认，跳过不放行）
TEST_RUN 入口拒绝进入出片
闸2 workflow_gate G_RENDER_READY（LIGHT 白名单豁免；FULL 强制）
闸3 billing_gate（无 precheck 能力时降级审计，不拦）
```

排查第一步：`python3 /opt/hermes/gates/confirm_gate.py check <项目> node12_render` 与
`python3 /opt/hermes/gates/workflow_gate.py status <项目>` 并行看状态。

## 坑1：旧确认未绑定产物（R7 单向棘轮）

2026-08-23 R7 起 confirm_gate 启用产物哈希绑定。旧确认记录无 `artifact_sha` 时，check 带产物即拦：
「旧确认未绑定产物；当前已启用产物校验，需重新确认」。

处理（绑定当前验收产物）：

```bash
echo "staging/xxx分镜脚本.md" > guard/confirm_artifact   # 显式指定确认产物
python3 /opt/hermes/gates/confirm_gate.py confirm <项目> node12_render "<用户原话>" <产物路径>
```

确认点 accept 关键词：node12_render 接受「跑、出、开始、可以、行、上、搞、发」——用户原话必须含其一。

## 坑2：A_STORYBOARD 正式产物位哈希

G_RENDER_READY 的 check_upstream_hashes 要求 A_STORYBOARD 哈希 == G_CREATIVE_READY 获批记录。
分镜脚本更新后若只放 staging、没同步正式产物位 → 哈希不符拦截。

处理：
1. 备份旧版 `cp artifacts/creative/A_STORYBOARD.md A_STORYBOARD.md.bak_<日期>`
2. 最新验收分镜复制到 `artifacts/creative/A_STORYBOARD.md`（注册表定位的正式产物位）
3. `workflow_gate.py check <项目> G_CREATIVE_READY`（更新获批哈希）→ 再 G_RENDER_READY

## 坑3：导演意图评审误扫任务书

`locate_creative_prompt_files` 按 CREATIVE_ROUTE_TABLE scope_guard 扫描
（applies_to_artifacts: A_STORYBOARD/A_PROMPT_PACKAGE + filename_patterns `**/*prompt*.md`、`**/*prompt*.txt` + storyboard 文件名），
`check_director_intent` 取**最新 3 个文件**按 mtime 评审。**派活任务书（briefs/xxx.md 含 "prompt"）会被误扫**，
任务书无逐镜内容 → 全维度低分 → action_tie high 强制 BLOCK。

识别：`导演评审报告.md` 描述「提交内容为任务工单，不是分镜脚本；全文未提供任何逐镜动作与台词」。
排查：用 python 复刻 locate 逻辑列出最新 3 个被评审文件，确认混入 briefs 任务书。

## 坑3b：评审报告递归自噬（2026-08-24 实证）

`guard/director_review/` 下上一轮生成的「导演评审报告_*.md」会被 `locate_creative_prompt_files`
**递归扫进下一轮评审**：排除正则只覆盖 briefs/tasks 等，`guard/director_review/` 不在排除名单，
报告文件名含「评审」不含被排除关键词 → 被当创作文件评审。报告本身只有头部（判定/总分/问题清单），
不是分镜 → 四维全 0 分 → 判定 REWORK → action_tie high → 整体 BLOCK，且真实分镜（如 S01 v3 评审 81 分 PASS）
被连带拦死。

识别：`guard/director_review/` 出现嵌套命名（`导演评审报告_导演评审报告_S01_分镜脚本_v3...md`，
内容仅 300-700B 的「# 导演意图评审报告 / 判定: REWORK / 总分: 0.0」）。评审输出的日志会列出
被评审文件，含 `导演评审报告_*` 与 transcript/py 等无关文件。

修复：双保险——① `workflow_gate.py` 的 excluded 正则加「导演评审报告」前缀（或 guard/director_review/ 路径）；
② `CREATIVE_ROUTE_TABLE.yaml` 的 `exclude_path_prefixes` 加 `guard/director_review/`（现为 briefs/、tasks/）。
改全局闸按规矩：人批 + 单独提交 + 单独验证 + 实现者不得自验。修复后回归：重跑 G_CREATIVE_READY
只评审真实创作文件，S01 v3 应 PASS。

## 坑4：派 codex/claude 的知识库卡点

出片意图任务（分析出片链路/写分镜/出提示词）派 codex/claude 时任务书必须：
- `TASK_TYPE=出片`（写「分析」会被判与出片意图不匹配）
- `READ_SKILL=seedance-2-0-mini-workflow` + 正文第零步要求先 read_file 该 skill

否则 BLOCKED：「知识库物理卡点拦截」+「TASK_TYPE=分析 与出片意图不匹配」+「缺 seedance skill 加载标记」。

**误判变体（2026-08-24 实测）：纯分析任务（如融合分析）的 USER_REQ 里含天行者原话「出片」两字（如「抽帧+豆包反推 → 出片 → 对比诊断」）也会被 SKILL_CONTRACT 误判为出片意图**，报「TASK_TYPE=分析 与出片意图不匹配」+「缺 READ_SKILL」。处理：**不改 USER_REQ 原话**（用户原话一字不动），只在任务书头部补 `READ_SKILL=seedance-2-0-mini-workflow` 标记即过闸。带「出片」字样的分析类传话书默认先加标记防拦。

## 坑5：G_CREATIVE_READY 内容级不合格（解析已过但分镜不合格）

BLOCK 信息是「分镜不合格（共N镜）」且能数出镜数 → 已过解析关，卡在**内容级校验**（5 类 43 条：四层标注 28 / 负面区 7 / @图用途 8 / 情绪 7 / 口播时长 1）。处理前先分类：

- **改剧本的**：四层标注字面串缺失、负面区被粗体 `**` 挡正则（`NEGATIVE_LABEL_RE` 要求 `(专属负面|通用负面|负面约束|负面词|负面)[：:]` 直接命中）、情绪措辞没落 `ACTION_RE` 闭集、口播单镜超上限
- **口播时长上限 = `talking_head_max_shot_duration_seconds`（注册表 CREATIVE_BLUEPRINT.validation，2026-08-24 天行者拍板「sd单镜最长15秒，规则不能定死10」从 10 改 15）**：段时长一律＝字数 ÷ 5.5 向上取整，复刻片也一样，不按原片实测时码；旧口径「S01 10.050s vs 上限 10s → 用最小合规标注调整」已作废。单段超 15s 就按话轮拆段，不得提速压字。注册表改的是全局配置（所有项目生效），分镜产物仍要保证每段口播时长 ≤15s。
- **改代码的（不是剧本错，别迁就旧代码）**：@图「仅作人物参考」是 AGENTS.md 规范、旧 gate 只认「仅用」→ 代码兼容；多段 @图N 只查全文第一个 → 代码遍历；briefs/tasks 误扫 → 目录级排除；S01 语义编号解析 → 代码扩展
- 口播段时长＝字数 ÷ 5.5 向上取整（复刻片同样不按原片 SHOT_REF 实测时码）；单段超 15s → 按话轮拆段，不提速压字
- 修复纪律：先备份 → 四层内容从 PROMPT_PACKAGE 搬（不新造）→ 台词不动、段时长按字数 ÷ 5.5 向上取整（不按原片时码） → 改完同步 staging 副本字节一致 → 用 staging 新版 gate `importlib` 离线验证（生产 gate 未部署时口径不对），残余问题如实列，禁虚报通过

完整五类口径、正则、ACTION_RE 闭集、43 条明细与修复流程见 `references/check-storyboard-content-criteria.md`。

## 坑6：复刻任务被导演意图评审错位评审（2026-08-24 火龙 G1 提交实测，用户「复刻需要导演意图评审吗」「都是抄的别人的」）

`check_director_intent`（G_CREATIVE_READY 内）对所有任务无条件跑导演四维评审——**复刻任务没有豁免**。但复刻的「导演意图」= 照原片（人物硬切/原片台词/原片动作/素材贴法），分镜写法是「按原片实测记录」不是创作性描述；创作评审维度（导演意图/情绪/镜头语言）对复刻是**错位**的，评审 LLM 容易评低分 → action_tie high → 误 BLOCK。正确评审对象是「**复刻一致性**」：切点对不对、台词一字不差、动作/贴片时点回指原片证据——跟创作评审两个维度。这是门禁设计缺口（workflow_gate.py 没有按任务类型分流评审）；改全局闸按规矩：人批 + 单独验证。当前绕过路径：评审超时（180s）是 WARN 不拦截、action_tie 未触发时能过；被误 BLOCK 时用「坑3/坑3b」排障手法确认分镜本身没问题后处理，别改分镜内容迁就评审。

## 坑7：分镜产物格式必须兼容 parse_seedance_shots（2026-08-24 火龙 V2 提交实测 BLOCK）

`parse_seedance_shots`（workflow_gate.py:744）只认**特定标题格式**：`^##\s*(?:镜头\d+|S\d+)\s*[｜|]`——写 `## 二、G1｜0.000—10.050｜男主｜覆盖 S01`（章节号+G 系列段名）**解析 0 镜** → `BLOCKED:G_CREATIVE_READY:分镜脚本无法解析出8列表格或Seedance四层镜头`。四层标题同理：`four_layer` 检查 `### 第一层`（三级标题），写 `#### 第一层：导演意图`（四级）**不匹配**。修复：① 段落标题改成 `## 镜头1｜0.000—10.050 秒｜男主`（镜头N + ｜ + 时段，duration 从标题范围推导）；② 四层标题从 `####` 降成 `###`（`### 第一层：导演意图`）；③ 改完本地验证 `python3 -c "from workflow_gate import parse_seedance_shots; print(parse_seedance_shots(open(f).read()))"` 出 4 镜再 cp 正式产物位 + 重新 confirm（哈希变了必须重绑） + 重跑 G_CREATIVE_READY/G_RENDER_READY。注意：内容定案不动，只改标题层级/格式兼容。

## 提示词包 → API 可提交格式清洗

PROMPT_PACKAGE 的「可独立投喂 prompt」是给人看的文档，**不能直接提交 API**。提交前清洗：

1. 去 markdown 噪音：`### 第一层/第二层…` 标题、列表符号、反引号、校验注释（「台词校验：9 个句级口播子镜…」「(5字)」）全部剔除
2. 去绝对路径：`@图1=/home/...jpeg` 改 `@图1`，路径走 `reference_images` 参数
3. 台词保留英文双引号 `"`（对口型分支标记，清洗时不能丢）
4. 时长：duration＝该段台词字数 ÷ 5.5 向上取整（整数秒，单镜上限 15s，不按原片实测时码，不提速）；算出不足 4s 的段按 API 下限 4s 生成再裁
5. 参考图顺序固定：@图1 人物 → @图2 场景 → @图3 素材（引用语法按快乐马 happyhorse-1.1-r2v 的规则走，不套 wan3.0/Seedance 写法）

prompt 长度：API 无硬性限制（1500-2150 字符可提交），但第三方实测超过 80 字符语义解析准确率断崖下跌（76%→39%）。
参考图已锁人物/场景时，prompt 只写参考图上没有的信息（机位、光线、动作、台词、负面）。

## 声音跨镜一致性

多镜分片声音最容易漂。规则：角色音色基线在**分镜脚本阶段锁死**（男主「25 岁清亮沉稳低中频干净」/女主「23 岁清亮偏甜不幼态」），
每镜同一段复制粘贴式锁定，逐句情绪可微调，但音色/年龄全片固定。提示词包沿用分镜声音描述不重复造。
配音部分只写四样：音色 ＋ 逐句情绪 ＋ 音量充足 ＋ 不说任何多余的字；段首／段尾／语速描述词和静默留白指令（如「开头先停顿半秒」「不新增半秒停顿」）一律不写。

## 成片卡顿/死帧诊断（像素帧差分法，2026-08-24 火龙镜1实证）

**触发**：用户反馈成片「中间卡了」「镜头卡住不动」「时间短了/重影闪烁」。

**不要凭视觉模型断言根因**。vision_analyze 后端可能不可用（本地主模型 deepseek-v4-flash 不支持默认 vision 后端，报 400 invalid model），
且「看着卡」可能有多种来源（素材死帧/镜长对位/音画脱节）。用**客观像素差分**替代猜。

### 方法：双帧像素哈希差分

抽连续时间点的帧，算相邻帧的像素级差异率（0-100%）。三分法判状态：

| 差异率 | 状态 | 含义 |
|---|---|---|
| >25% | 镜切/跳动 | 镜头切换或画面大变 |
| 5-25% | 微变 | 正常轻微动作 |
| <5% | **静止死帧** | 画面不动 = 卡顿根因 |

`scripts/frame_diff_diag.py`（见下）抽帧转 64×64 灰度 PGM，按字节比对求差异率。
现成脚本：`python3 scripts/frame_diff_diag.py <视频> <开始> <结束> [步进]`，一键出差分表。

### 关键坑：scene 阈值检测会误判「动作大」为「镜切」

`ffmpeg -vf "select='gt(scene,0.3)',showinfo"` 在**正常动态镜头**上会全程报 75-98% 差异
（人物坐下→起身→走动、镜头移动每 0.5s 画面必然大变），**不能当作素材坏了**。
只有**某个时段差异骤降到 <5%** 才是真正的静止死帧/卡顿。高差异是动态，不是故障。

### 诊断节奏（层层逼近，避免误判）

1. `ffprobe` 确认文件完好（时长/编码正常 ≠ 无卡顿）
2. `scene` 检测粗扫硬切点 —— **只能看切点位置，不能判素材好坏**
3. **像素差分精确定位**：扫 8.0→11.0s 逐帧差分 → 找差异骤降到 <5% 的死帧段
4. 死帧段 vs 分镜硬切点对照：素材死帧起点是否是硬切点「该切未切」导致的裸露
5. **多素材对比**：同时扫「11s 新版」和「旧版 10.08s」两版素材，确认死帧是新版独有还是通病——决定修复只动当前版还是全链路

### 🚨 流程纪律：诊断出死帧 ≠ 立刻改合成（2026-08-24 用户纠正）

像素差分确认死帧/镜长问题后，**不要直接动手改合成脚本**。先停在该节点，做两件事：
1. **抽关键帧给用户过目**（开场/起身/走近/死帧临界 10.0s/死帧区 10.4s），发 MEDIA 让用户确认**镜头素材本身手感对不对、能不能用、该用哪版**（新版还是有死帧问题的旧版，得用户拍板）
2. 用户确认素材或修复方向后，才改合成脚本重合成

原因：死帧诊断是**技术推断**，用户对「镜1行不行、用哪版」有最终判断权；闷头改完用户一看素材本身不对，白重跑一次合成（烧钱）。**改片前先确认素材，不是改产物的确权豁免，是防返工的门禁。**

### 修复：改镜长必须量各镜实际时长 + 同步重算全部音频 adelay

改某镜 `trim=end` 后，**后续每一镜的音频 adelay 都要重排**，否则音画错位（画面切了/声音没跟上 = 也是「卡」）：

```bash
# ① 先用 ffprobe 量每个镜素材实际时长
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 镜N.mp4
# ② 每镜音频 adelay = 前序所有镜的实际累计时长(ms)
#    镜1=10.05 → 镜2 adelay=10050, 镜3=10050+D2, 镜4=10050+D2+D3, 依此类推
# ③ 别只裁视频不动音频(adelay 漏改 = 音画脱节=用户眼中的"卡")
```

### 本案例结论（火龙镜1）

- 镜1素材 11.104s，但 **10.0s 后是静止死帧**（差异 0.1-2.6%）—— 素材有效画面只到 ~10.0s
- 合成脚本 `trim=end=11.104` 把死帧算进去 → 成片 10.05 硬切点延后到 11.1 → **死帧裸露 = 用户看到的「中间卡了」**
- 镜2/3/4 同样 11.104s 但 9-11s 全程正常动态（扫过确认）→ 只有镜1有问题
- **修复**：镜1 `trim=end=10.05` 干净硬切 + 后续镜音频 adelay 前移对齐（别只裁视频不动音频，会音画错位）

### 教训

- 假设会被推翻：先猜「脚本音画对位错」→ scene 检测看似坐实 → 像素差分才发现真根因是**素材死帧**。**拿像素差分做最终裁决，不靠前面的推测**。
- 「镜1时间短了」类反馈，真相常是**素材尾部死帧被强行拉长裸露**，不是真的内容短。
- 改镜长必须**同步重算全片音频 adelay**（每镜 trim 变了，后续镜的 adelay=前一镜累计时长，漏改就音画脱节）。

## 交付偏好（天行者定案 2026-08-23）

分镜交付**只出一个文件**（分镜脚本本身，素材引用/待确认已合并进脚本）。实施报告、自审报告、素材映射表
是流程自检记录，归档不端给用户。派活时在任务书写明「产出要求：只出主产物，报告类不交付」。
