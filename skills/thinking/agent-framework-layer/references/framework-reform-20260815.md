# 框架层改造 2026-08-15 勘探与落地细节

> 本文件是 `agent-framework-layer` SKILL.md 的 session 级细节。SKILL.md 讲「怎么设计」，这里讲「这次实际怎么落地的 + 源码勘探证据」。

## 一、核心源码勘探（为什么 pre_tool_call hook 能真拦住）

| 文件 | 证据 | 意义 |
|:--|:--|:--|
| `hermes-agent/hermes_cli/plugins.py:137` | `VALID_HOOKS` 含 `pre_tool_call` | hook 事件名合法 |
| `plugins.py:136` `_BLOCKING_EVENTS` | `{"pre_tool_call"}` | 只有它的 block 指令被下游真正采纳 |
| `agent/shell_hooks.py` | 读 config.yaml 顶层 `hooks:` 块 | 配置入口 |
| `shell_hooks.py:55` | exit 2 从 pre_tool_call hook block 工具调用 | Claude-Code 兼容阻断 |
| `gateway/run.py:11144` | 网关启动时注册 hooks | 改 config 后必须重启网关才生效 |
| `plugins.py` | `hooks_auto_accept: true` 或 `HERMES_ACCEPT_HOOKS=1` | 网关无 TTY 需要 |

**验证方法（改 hook 前先跑）**：`grep -n "pre_tool_call" hermes-agent/hermes_cli/plugins.py` + `grep -n "exit" agent/shell_hooks.py`——确认机制真实存在再动手。

## 二、本次落地产物清单（Phase 0 已完成 7/7）

| 产物 | 路径 | 测试 |
|:--|:--|:--|
| approve 补丁 | `workflow/scripts/workflow_gate.py` (+100 行) | 5/5 PASS |
| 节点映射表 | `workflow/wiki/spec/HERMES_NODE_MAP.yaml` (1165 行, 51 节点) | 字段/deps/requires 校验全过 |
| 票据脚本 | `workflow/scripts/workflow_ticket.py` | 8/8 PASS |
| 入口守卫 | `.hermes/guard/node-entry-guard.py` | 10/10 PASS |
| 16 个 persona | `workflow/wiki/personas/persona-*.md` (991 行) | 标尺可验证 |
| SOUL 草稿 | `workflow/outputs/SOUL_framework_draft.md` (130 行) | 未落盘 .hermes/ |
| hash 扩容 | `.hermes/scripts/hash-verify.sh` 10 文件 + cron */30 | ALL_OK |

## 三、抓到并修复的关键 bug

**票据目录不一致 = 闸空转**：
- ticket 写 `REPO_ROOT/guard/tickets` = `/home/ubuntu/workflow/guard/tickets`
- guard 读 `GUARD_DIR / "tickets"` = `/home/ubuntu/.hermes/guard/tickets`
- 后果：open 写了票据 guard 永远读不到 → 拦不住任何东西 → 白装
- 修复：guard 侧 `TICKETS_DIR = Path(os.environ.get("NODE_ENTRY_GUARD_TICKETS_DIR", "/home/ubuntu/workflow/guard/tickets"))`
- 连带：测试也失败 5 个（测试临时目录票据 vs guard 硬编码真实目录）→ 测试 env 补 `NODE_ENTRY_GUARD_TICKETS_DIR`

**classify 打分歧义**（影子期校准素材）：
- `classify "拆这个视频的提示词"` → 命中 `T-CONTENT.PROMPT`（文本含"提示词"三字）而非 DECONSTRUCT
- `classify "帮我分析一下这个账号的数据"` → 判 internal_interaction（可能应为 workflow）
- `classify "星广素材消耗归因大白话版"` / `classify "申请星川星广数据接口需求说明"` → 都命中 `T-ATTRIBUTION.BUSINESS`（触发词"星广"），但实际前者是 LOGIC 的对外翻译版、后者是 DATASPEC 的对外需求文档——**衍生交付/翻译版/需求说明类任务没有专属节点**，全落 BUSINESS。影子期需为「对外解释版」「接口申请」类任务补 triggers 或映射到更合适的节点
- 已登记 `wiki/spec/phase1-calibration-checklist.md`

## 四、phase1-calibration-checklist.md 内容

1. classify 关键词打分歧义（拆视频→PROMPT 而非 DECONSTRUCT）——校准 triggers 或加意图优先级
2. classify 判 internal_interaction 边界——含「分析/复盘/报告/方案」且提到具体对象 → 上取工作流态
3. 回归用例（方案 §8.4）：重放拆解事故必须 BLOCK 无票据 / open COMPOSE 上游未 close rc=2 / write_file 无执行者标注 BLOCK / 产物含 /home/ubuntu/ 走 OUTBOUND BLOCK / curl ark 未过 /execute BLOCK / 连续 20 次只读零拦截

## 五、治理决策记录

- **approve 是 L2 操作**（改门禁注册表，撤不回）——上线前需快照+dry-run+人签字，codex 实现 + CC 对抗审查
- **新 SOUL 是 L2 灵魂文件**——人签字后才落盘，草稿先到 outputs/
- **persona 是 L0**——单代理端到端，三版盲评 ≥60
- **NODE_MAP/ticket/guard 是 L1**——CC 定契约（字段语义/不变量），codex 实现，CC 复核
- 当前阶段：**Phase 1 影子期已启动**（老板已拍板两件事：核心信条承接——共情六层→persona-creative-director，成本控制→persona-render-engineer；Phase 1 挂 hook 已执行）。config.yaml 已加 hooks 块（observe，fail_closed:false）+ `hooks_auto_accept: true`，网关已重启，`guard/entry_guard_mode`=observe。下一步等影子期校准（误伤率<2%）→ Phase 2 SOUL 换血（唯一停机窗口）。

## 六、与小鹿框架层的差异（为什么不一字照搬）

| 维度 | 小鹿 | 执行者（本次） |
|:--|:--|:--|
| 节点表位置 | SOUL 正文内联 16 节点 | 外置 YAML 51 节点 |
| 轨数 | 单轨内容生产 | 五轨（含指挥/归因/决策） |
| 铁律继承 | 有 | 不继承小鹿铁律（自己的） |
| 交付方式 | 仅文字/链接/表格 | 优先原生发送视频 → 外部 URL |
| 三态「对外」定义 | 跟谁说话 | **产物会不会离开内网** |
