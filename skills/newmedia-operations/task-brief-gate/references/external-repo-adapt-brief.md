# 外部仓库/skill 适配分析任务书模板（2026-08-21 newme-adapt-analysis 实例）

> 场景：用户给了一个外部 skill 仓库（别人的业务自动化，跟我们的产线无关），要求「复制下来，分析怎么适配我们的其他东西」。
> 交付物 = 能力提取 + 适配映射到我们自己的产线，不是分析对方业务怎么用。

## 第一步：复制落盘（Hermes 做，机械操作）

```bash
# 1) 存档副本（用户要的「复制下来」落点，去 .git 保完整文件）
mkdir -p /home/ubuntu/workflow/external && cp -r /tmp/<repo> /home/ubuntu/workflow/external/<repo>
rm -rf /home/ubuntu/workflow/external/<repo>/.git

# 2) 项目内副本（codex 容器只挂项目目录，读不到 /tmp/ 和 workflow/external/）
mkdir -p /home/ubuntu/workflow/projects/<adapt-project>
cp -r /home/ubuntu/workflow/external/<repo> <adapt-project>/external_<repo>
```

## 第二步：派活前读知识库 + kb 卡点

- Hermes 必读：仓库 AGENTS.md + 核心 SKILL.md + README + HANDOFF + examples/ 模板；再读我们自己产线的 skill 头部（video-production / local-life-douyin-launch 等）作为适配目标现状
- 写 `guard/kb_checked.json`：sources 列实际读过的仓库文件 + 我们产线 skill 路径
- **DATA_SOURCE 和任务书里所有 read_file 路径必须指项目内副本**，不是 workflow/external 存档路径

## 第三步：任务书结构（TASK_TYPE=分析）

```
TASK_TYPE=分析
PROJECT_DIR=/home/ubuntu/workflow/projects/<adapt-project>
DATA_SOURCE=/home/ubuntu/workflow/projects/<adapt-project>/external_<repo>

[角色] 后台分析执行器，产出结果文件，不跟用户对话。

[客户需求] 用户把外部仓库 <repo>（<来源>，别人的 XX 自动化 skill，跟我们的业务无关）复制下来，
要求分析这套 XX 自动化能力怎么适配到我们自己的业务线上。重点不是分析对方客户业务，
而是提取通用自动化能力，给出适配我们现有产线的方案。

[上下文]
## 一、被分析对象（项目内副本，只读引用）
- 仓库根 / 核心 skill / 操作规程 / 交接书 / N 个生产脚本清单

## 二、该 skill 的核心能力（从原文提炼，分析以仓库原文为准）
逐条列能力：发布自动化/定时/判据方法论/数据回读/登录保活/素材筛选/工程纪律

## 三、我们自己的业务线现状（适配目标，分析时核对路径）
1. <产线A>（路径）：现状描述，缺什么能力
2. <产线B>（路径）：...
（逐条写现状，codex 才能对着适配）

## 四、用户意图（原话引用）
「把它那个短视频自动化的那个东西，那个 skill 复制下来，然后分析一下怎么去适配我们的其他的那些东西，跟我们没关系」
= 这个仓库是别人的，不用管对方客户业务；要的是把自动化能力适配到我们自己的产线上。

[产出要求] 适配分析报告，包含：
1. 能力映射表：能力 → 适配哪条业务线 → 适配价值(高/中/低) → 改造难度(高/中/低) → 关键改造点
2. 方法论沉淀建议（如判据阳性对照 → 我们自己的质量门禁落地形式）
3. 最值得先适配的 1-2 个切入点（带理由和优先级）
4. 改造清单（账号体系/平台差异/位置/合规/时区/文案分叉，哪些脚本可复用哪些重写）
5. 风险与边界（平台合规/风控/部署位置差异如 macOS vs Linux/发布责任边界）
6. 落地路线图（分阶段 + 验收标准）

[硬约束]
- 只读分析，不修改仓库任何文件、不改我们任何产线代码
- 不真跑发布脚本、不操作真实账号、不调任何付费 API
- 分析基于仓库真实文件内容，引用具体脚本名/函数/段落，禁止脑补
- 结论区分事实与推断：仓库实测标「仓库记录」、我们产线现状标「现有代码」、判断标「建议」
- 报告末尾 OUTPUT: /home/ubuntu/workflow/projects/<adapt-project>/<报告名>.md

[方法]
- 第一步 read_file 仓库 AGENTS.md（操作规程全文）
- 第二步 read_file 核心 SKILL.md
- 第三步 read_file README + HANDOFF
- 第四步 抽查 scripts/ 关键脚本头 docstring
- 第五步 核对我们产线（只读头部即可）
- 第六步 写报告

[约定] 产出写文件，结尾一行 OUTPUT: <路径>；有合规问题 COMPLIANCE: <点>；卡点 BLOCKED: <原因>；缺信息 NEED_INFO: <缺什么>
```

## 派活

```bash
cd /home/ubuntu/workflow && sg docker -c "python3 hermes_task_dispatch.py \
  --brief <adapt-project>/brief_<...>.md --project <adapt-project> --target codex -- \
  \"\$(cat <adapt-project>/brief_<...>.md)\" /home/ubuntu/workflow/projects/<adapt-project>" 2>&1 | tail -60
```

## 收结果后 Hermes 质检要点

- 报告是否按能力映射表结构输出、引用具体脚本名（不是泛泛而谈）
- 切入点优先级有没有依据（我们客户结构/人力/账号资源），不是拍脑袋
- 部署差异有没有指出（原仓库 macOS+keychain → 我们 Linux 服务器，哪些脚本不可直接跑）
- 归档：报告放 outputs/，skill 投影按需（agent-skill-sync）

## 后续步骤：方法论单独沉淀（2026-08-21 用户「把阳性对照做成方法论存到另外文件夹」定案）

适配分析跑完后，用户常会要求把仓库里**最有价值的方法论**单独提取沉淀（脱离对方客户上下文，变成咱们自己的通用资产）。流程：

1. **建独立文件夹**：`mkdir -p /home/ubuntu/workflow/external/<方法论名>/`（例：publish-safety-methodology/）
2. **派 codex 提取任务书**（TASK_TYPE=分析，同 kb_gate 纪律）：
   - 输入 = 仓库副本重点文件（AGENTS.md 假判据清单节 / 核心 SKILL.md 对应节）+ 已完成的适配分析报告对应节
   - 产出 = 独立方法论文档，结构：核心命题与适用范围 → 方法论步骤 → 已实测假判据清单（通用化改写，客户特例保留为示例并标注）→ 夹具模板表 → 门禁状态机与证据链 → 集成建议 → 维护纪律
   - 硬约束：只提取指定方法论，不提取对方账号/位置/固定文案/坐标选择器；不修改仓库任何文件；禁编造新案例
3. **kb_gate 注意**：提取任务书里若必须讨论 Seedance/视频生成（绕不开），同「kb_gate 出片正则误伤」例外——补 `READ_SKILL=seedance-2-0-mini-workflow` + 方法区写「第零步：read_file 该 skill」，标记与真实读取成对出现
4. **落盘**：方法论文档写进独立文件夹（不是项目目录），任务书 OUTPUT 指向该路径
   - **root 所有目录写不进（2026-08-21 实测）**：`/home/ubuntu/workflow/external/` 由 root 所有、容器无 sudo → codex 报「BLOCKED: 指定父目录由 root 所有且不可写」但**内容其实写完了**，暂存稿在项目 `_staging/<方法论名>/` 下（输出尾部有「完整暂存稿」提示）。解法：任务书 OUTPUT 写项目内路径（如 `<adapt-project>/_staging/publish-safety-methodology/判据阳性对照方法论.md`），codex 写完 Hermes 用 `mv` 搬到 `workflow/external/<方法论名>/`，再清掉 `_staging`。识别特征：BLOCKED 提示父目录不可写 + 同时给出完整暂存稿路径 = 产物在暂存稿里，不是真失败。

## 后续步骤：用户点名 Claude 做架构级适配（2026-08-21 实测）

适配分析（codex 产出能力映射/路线图）跑完后，用户可能进一步点名「让 claude 分析怎么适配到我们这个环境」——这是**架构级**适配（从「能力提取」升级到「接缝设计 + 门禁安全 + 部署位置」），执行者换成 Claude（点名才用，架构/审查/终审归 Claude）。与第一轮 codex 适配分析的区别：

1. **输入打包升级**：除了仓库副本，还要把**我们自己工作流的真实环境文件** cp 进项目目录 `env_ref/` 给执行器读（Claude 容器同样读不到 `workflow/wiki/` 和 `workflow/projects/` 外路径）：
   - `WORKFLOW_SPEC.yaml`（19 节点主链、PUBLISH_OPERATE 节点定义、产物/门禁）
   - `PLATFORM_CONTRACTS.md`（平台契约：DELIVERY_PACKAGE 产出哪些 artifact）
   - 真实项目产物样例（如 `A_PUBLISH_PACKAGE.md` + `A_PUBLISH_LOG.md`——接缝设计的实据）
   - 业务视角架构优化报告（已知痛点：14 字段人工录入/无平台数据权限）
   - `AGENTS.md` + 相关 skill 头部（video-production / local-life-douyin-launch）
2. **任务书结构（TASK_TYPE=分析，但产出是架构方案）**：
   - 现状架构图（文字版）：目标节点现状（输入产物/人工动作/输出/门禁/痛点）
   - 目标架构：外部能力接进来后节点应该长什么样（节点改造/新增组件/数据流/控制流）
   - 接缝设计：我们已有产物（A_PUBLISH_PACKAGE 等）↔ 外部方案字段的映射表（直接映射/新增/废弃）
   - 门禁与安全设计：方法论怎么变成物理卡点；人工审批令牌/幂等键/发布回执/审计证据链；合规终检不能因自动化跳过
   - 平台适配策略（POI 从对方固定位置改我们客户真实门店等）
   - 部署位置建议（新加坡机 vs 广州机、控制面与浏览器 worker 分离）
   - 分阶段实施路线（每阶段交付物/验收/风险）
   - 明确不做/暂缓清单（破坏性操作、扫码依赖平台、不该硬塞的业务线）
   - 硬约束：结论区分【现有代码/文档】vs【建议】；已知缺口（账号库存/授权/发布量数据缺失）诚实标注
3. **派活**：Claude 通道 `python3 hermes_task_dispatch.py --brief <brief> --project <proj> --target claude -- "$(cat <brief>)" <proj_dir>`（不需要 sg docker，Claude 走 wrapper 不碰 docker 组）
4. **收结果**：报告归档 outputs/；跟第一轮 codex 适配分析报告并存（codex=能力提取/切入点，claude=架构接缝/门禁/部署），用户两轮决策链路完整

