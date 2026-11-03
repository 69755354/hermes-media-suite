# SOUL 框架层改造：物理闸架构（Phase 0 实测，2026-08-15）

## 为什么做

Hermes default profile 原有 SOUL 内联业务人格+方法论（全栈运营/3点法/五智囊），
接任务默认直接干活、跳过工作流。根因：**自带方法论 → 觉得不需要工作流**，
而工作流节点表外置后是「可选参考」不是「物理约束」。

改造目标：学小鹿（customer profile）的框架层——无默认业务人格、节点驱动、
persona 外置、物理闸拦截。老板指令「直接把你设置成跟他一样的」，
但执行者职责比小鹿宽（内容生产 + 多执行器指挥 + 星广归因 + 分析决策），
不能照搬小鹿 17 个内容节点。

## 目标架构：三层分离

```
L0 框架层 SOUL（≤130 行）—— 只有分轨判定/全局铁律/断路器/三态/物理闸引用/保留区
L1 节点映射层 HERMES_NODE_MAP.yaml —— 五轨 × 节点 × persona × deps × requires × exit_gate
L2 人设层 wiki/personas/*.md —— 节点执行时由 workflow_ticket.py open 打印全文注入
```

**关键决策：节点表外置 YAML 而非内联 SOUL**——小鹿把节点表写 SOUL 正文，
改一行表要走全套重启协议；执行者职责宽、节点持续增补，外置后改表不动 SOUL。

## 五轨划分（51 节点 = 37 存量 + 14 新建）

| 轨 | 节点数 | 来源 |
|:--|:--|:--|
| T-CONTENT 内容生产 | 18 | 复用 huoshan 18 节点（0-17），legacy_ref 回指，不重编号 |
| T-OPS 客户运营主链 | 19 | 复用 WORKFLOW_REGISTRY 19 语义节点，registry_ref 回指 |
| T-ORCHESTRA 指挥审核 | 5 | 新建（INTAKE/PACKAGE/DISPATCH/CROSS_REVIEW/ADJUDICATE） |
| T-ATTRIBUTION 星广归因 | 5 | 新建（BUSINESS/ARCH/LOGIC/DATASPEC/PRD） |
| T-DECISION 分析决策 | 4 | 新建（FRAME/COUNCIL/HATS/CHAIR） |

设计逻辑「加映射层，不迁移存量」：存量两套工作流零改动，NODE_MAP 作映射层
回指（legacy_ref/registry_ref），新增节点才新建。

## 三闸联防

### 闸一：node-entry-guard.py（pre_tool_call shell hook，进程级）

- config.yaml 顶层 `hooks:` 块注册，matcher 正则匹配 tool_name，
  `fail_closed: true` 时脚本崩溃/超时/畸形输出一律 BLOCK
- 判定五类：READONLY 放行 / TERMINAL 白名单或需票据 / PRODUCE 需票据 /
  DELEGATE 需 T-ORCHESTRA 票据 / OUTBOUND 需 external_delivery 票据+飞书闸
- block message 必须是**可执行的下一步命令**（如 `workflow_ticket.py open T-CONTENT.DECONSTRUCT`），不是训话
- 逃生阀 `.entry_guard_off` 存在 → 全放行+写 GUARD_BYPASSED 告警（秒级止血）

### 闸二：workflow_ticket.py（文件级，票据系统）

- `open`：校验上游 requires 已 closed → **打印 persona 全文到 stdout**（加载人设
  变成脚本副作用，不是 LLM 声明）→ 校验 deps 文档存在 → 写票据 JSON + 台账
- `close`：产物存在 + 输出属性格式检查（external_delivery 跑脱敏扫描）
- `skip`：返回 rc=3 强制人工确认（跳节点从「不吭声」变「显式申报+人确认」）
- `classify`：三态+候选节点判定（用 NODE_MAP triggers 匹配）

### 闸三：hash-verify.sh + cron（监控级）

- FILES 数组扩容覆盖 NODE_MAP/guard/ticket/gate 脚本，30 分钟 cron 巡检
- **坑**：skill 文档声称「30 分钟 cron 告警」实际 crontab 为空——纸面规则要查实

## 必踩的坑（实测）

### 票据目录不一致 = 闸空转（本会话真 bug）

`workflow_ticket.py` 写 `REPO_ROOT/guard/tickets`，`node-entry-guard.py` 读
`HERMES_ROOT/guard/tickets`——open 写了票据但 guard 读不到，**整个闸是空转的**。
统一到 `workflow/guard/tickets`（Git 内可回滚），测试用环境变量
`NODE_ENTRY_GUARD_TICKETS_DIR` 覆盖到临时目录。

**教训**：两个脚本共享数据目录时，先 grep 两边的路径定义确认一致，
再信单元测试——测试建临时目录时如果环境变量没传，会掩盖不一致。

### classify 关键词打分歧义

「拆这个视频的提示词」→ 命中 T-CONTENT.PROMPT（文本含"提示词"），
真实意图是 T-CONTENT.DECONSTRUCT。triggers 是多义词/嵌套意图打分，会命中错节点。
修正方向：影子期观察偏差率，给 DECONSTRUCT 加「拆视频/拆解视频」trigger，
或引入意图优先级（拆解 > 提示词）。

### workflow_gate.py 存量死锁（硬前置）

只有 check/status 没有 approve，19 门 17 门 manual 只落 status:null，
`check_upstream_hashes` 要求 ALLOWED → 可达门为零。Phase 0 必须先补
`approve <proj> <gate_id> --by <人> --evidence <路径>` 才能让票据 close 委托它。

### 影子期是平滑过渡关键

Phase 0 全程不碰 SOUL、不重启网关（归因 PRD 互评零感知）；Phase 1 挂 hook 但
`entry_guard_mode=observe` 只记 audit jsonl 一律放行，3-7 天校准白名单
（误伤率<2% + 回归用例能 BLOCK 才转 enforce）；Phase 3 按 T-CONTENT →
T-DECISION → T-ORCHESTRA → T-ATTRIBUTION → T-OPS 分轨灰度；`fail_closed` 最后才开。

## 关键文件

- 方案：`outputs/SOUL框架层改造方案_20260815.md`（claude 出，含节点表/物理闸/迁移四 Phase）
- 节点表：`wiki/spec/HERMES_NODE_MAP.yaml`（五轨 51 节点单一事实源）
- 票据：`workflow/scripts/workflow_ticket.py` + 单元测试
- 守卫：`.hermes/guard/node-entry-guard.py` + 单元测试
- 门禁：`workflow/scripts/workflow_gate.py`（已补 approve）
- 新 SOUL 草稿：`outputs/SOUL_framework_draft.md`（130 行，Phase 2 才落盘）
- 校准清单：`wiki/spec/phase1-calibration-checklist.md`
## 迁移回退三级：L1 touch .entry_guard_off 熔断 / L2 注释 hooks 摘闸 / L3 SOUL 回滚+更 md5

## 执行进度（2026-08-15 晚更新：Phase 0 全部完成，Phase 1 影子期已启动）

**Phase 0（准备期）7/7 完成，全程未触碰运行态：**
- 0-A `workflow_gate.py` 补 `approve` 子命令（codex 实现，5 测试 PASS；L2 上线前需人签字）
- 0-B `HERMES_NODE_MAP.yaml`（claude 定契约，51 节点，字段/deps/requires 机器校验全过）
- 0-C `workflow_ticket.py`（codex，8 测试 PASS：open 上游/close 标注/classify 命中）
- 0-D `node-entry-guard.py`（codex，10 测试 PASS；修复票据目录不一致 bug 后全绿）
- 0-E 16 个 persona（codex 批量建，各 61-64 行，标尺可验证；原 18 个一字未动）
- 0-F 新 SOUL 草稿 `outputs/SOUL_framework_draft.md`（claude 出，130 行压线，未落盘）
- 0-G hash-verify.sh 扩容 10 文件 + crontab 30 分钟巡检（纸面规则补实）

**Phase 1 影子期已启动（2026-08-15 晚）：**
- config.yaml 挂 `hooks.pre_tool_call`（`hermes config set` 写入，matcher 覆盖 write_file|patch|terminal|image_generate|delegate|feishu_.*）
- `guard/entry_guard_mode` 写 observe → guard 只记 audit 不拦截，正常干活零感知
- 网关已重启（hook 注册需重启生效），归因 PRD 互评全程未被打断
- 影子期校准清单 `wiki/spec/phase1-calibration-checklist.md` 已预登记 2 条 classify 实测偏差

**老板拍板项（Phase 2 前必须做的两个决定，已落地）：**
1. 核心信条承接：共情六层 → `persona-creative-director.md`；成本控制 → `persona-render-engineer.md`（已写入并锁回 444）
2. 执行器分工：**Claude 只做架构/契约/对抗审查/终审；具体执行（文档/码/复盘示例）一律 codex；Claude 默认不用、点名才用**（见 multi-executor-orchestration 铁律零）

**Phase 2（SOUL 换血）前提条件**：approve 通道验证通过 + 影子期误伤率<2% + 回归用例「拆解抖音AI视频」能被 BLOCK。到点再走 soul-md-update-protocol（备份→644→写→444→更md5→清 sessions+gateway_routing→后台杀网关→验 sp_len>100）。
