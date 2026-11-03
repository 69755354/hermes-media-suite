# DS 原生 API 直调绕过执行层卡点（2026-08-18 实测确认 + 已落地）

## 背景

codex 额度用尽（`You've hit your usage limit`）后降级到 DS。老板追问：「执行层卡点是针对 codex 的，那换成 ds 还有用吗？」

## 结论：没用，完全绕过

- `kb_gate_sg.py`（知识库卡点 + Seedance skill 卡点）只挂在两个执行器壳上：
  - `codex_exec_gated.sh`
  - `claude_remote_wrapper.sh`
- DS 原生 API 直调路径：`python3 → https://api.deepseek.com/v1/chat/completions`——**根本不经过这两个壳**，`kb_gate_sg.py` 不会执行。
- 所以执行层卡点对 DS 原生 API 通道完全免疫。

## 更本质的结论

DS 是文本生成器，**任务书写什么它做什么**。知识库引用、红果规则、复刻定义全靠打包方（Hermes）写进任务书——DS 不会自己查知识库、不会自己读 skill。

**知识库闸的真正守门人是主对话层（Hermes 打包前），不是执行器壳。**

## 正确落点

物理闸必须放在**打包入口**：
- Hermes 接「复刻/分镜/内容生产」类任务时先跑卡点
- 没读对应 skill + 没查项目现状 → BLOCK 不许派活
- 这样同时管住 codex/claude/DS 三条通道，换执行器不会失效

## 附带发现：新加坡机 WIKI_ROOT 路径

- 小鹿广州机：`knowledge_gate.py` 里 `WIKI_ROOT = "/home/ubuntu/wiki"`
- 新加坡机：`kb_gate_sg.py` 里也写的是 `/home/ubuntu/wiki`，但实际知识库在 `/home/ubuntu/workflow/wiki`
- 照抄小鹿脚本时注意两机路径不同，否则读到空目录、卡点形同虚设

## ✅ 已落地（2026-08-18 会话内完成，天行者审后执行）

老板最终定性：「问题就出在你派任务的时候乱写」——卡点拦的不只是「执行器没读知识库」，而是**任务书本身缺关键约束**（如复刻任务书缺 `CONSTRAINT=照原片结构` / `CONSTRAINT=不拆段` / `READ_SKILL=video-remake`）。执行器照错误任务书执行不会纠错。

**方案来源**：DeepSeek V4 Pro 分析（`/home/ubuntu/workflow/outputs/主对话打包卡点方案_pro.md`），老板审后按最小可行版落地。

**落地文件**：
| 文件 | 作用 |
|---|---|
| `/home/ubuntu/workflow/gate_config.yaml` | 六类任务（复刻/分镜/生图/出片/文案/分析）强制标记清单 + 关键约束词 + PRELOAD_NODES |
| `/home/ubuntu/workflow/task_brief_gate.py` | 打包卡点：校验任务书标记/约束词/项目目录真实性/资产存在/PRELOAD_NODES |
| `/home/ubuntu/workflow/hermes_task_dispatch.py` | 统一派活入口：先过 gate → 签发一次性 token（10分钟）→ 传执行器 |
| `/home/ubuntu/workflow/ds_native_invoke.py` | DS 原生 API 执行器（内置 TASK_GATE_TOKEN 硬校验，防 DS 直调绕过） |
| `~/.hermes/scripts/codex_exec_gated.sh`（改） | 加 token 校验（TASK_GATE_ENABLED=1 时生效），备份 .bak_20260818 |
| `workflow/scripts/claude_remote_wrapper.sh`（改） | 同上，备份 .bak_20260818 |

**当前状态**：gate_config mode=WARN（只记审计日志不阻断）；执行器 token 校验靠 TASK_GATE_ENABLED=1 触发。稳定后切 BLOCK + 三通道强制走统一入口。

**验证结果**（全过）：错误任务书 → WARN+7 条缺失原因；正确任务书 → PASS；codex 壳无 token → BLOCK exit 2；ds_native 无 token 直调 → BLOCK exit 2；有 token → 通过校验。

**派活铁律（未来必守）**：
1. 内容生产任务必须走 `hermes_task_dispatch.py --brief <任务书> --project <项目> --target <codex|claude|ds_native>`，禁止直调底层执行器/裸 python 调 DS
2. 任务书必须带强制标记（复刻：TASK_TYPE=复刻 + READ_SKILL=video-remake + ASSET_REF + 「照原片结构/只换人物形象/单镜4-15s/画面字幕」；分镜：单镜4-15s/不拆段；出片：READ_SKILL=seedance-2-0-mini-workflow）
3. 光写标记不够，关键约束词必须真在任务书里（防假读）
4. 项目必须有 guard/ 目录（防临时目录从零干起）
5. 打包前先读管辖 skill（复刻→video-remake；分镜/出片→seedance+红果踩坑），规则写进任务书

落地记录：`/home/ubuntu/workflow/outputs/主对话打包卡点_落地记录_20260818.md`

**回滚**：gate_config mode 改回 WARN/删除；执行器壳恢复 `.bak_20260818`；停用 hermes_task_dispatch.py。
