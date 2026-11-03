# 主对话打包卡点 task_brief_gate（2026-08-18 落地）

> 背景：Hermes 复刻任务反复出错（复刻做成改编/14s拆段/繁体字幕/临时目录干起），根因=Hermes 打包任务书时把错误假设写进去。**执行器壳卡点（kb_gate_sg.py 挂 codex_exec_gated.sh / claude_remote_wrapper.sh）只拦执行器，DS 原生 API 直调完全绕过**。方案由 DeepSeek V4 Pro 产出，天行者审后按最小可行版落地。

## 核心设计（为什么闸在打包层）

- **执行器没错，错的是打包方 Hermes**：DS/codex 照任务书执行，任务书里写「14s拆2段」它就拆。DS 是文本生成器，任务书里没写知识库引用它不会自己去查——知识库闸的真正守门人是打包方。
- **执行层卡点对 DS 原生 API 无效**：`python3 → api.deepseek.com/chat/completions` 不经过 codex/claude 壳，kb_gate_sg.py 压根不执行。闸必须前移到 Hermes 打包层才能管住 codex/claude/DS 三通道。
- **防「假读」**：光检查 `READ_SKILL=` 标记不够（模型会写标记但不读文件），必须检查**关键约束词是否真在任务书里**（如复刻任务必须含「照原片结构」「只换人物形象」「单镜4-15s」）。

## 落地文件

| 文件 | 作用 |
|---|---|
| `/home/ubuntu/workflow/gate_config.yaml` | 六类任务（复刻/分镜/生图/出片/文案/分析）强制标记 + constraint_keywords + PRELOAD_NODES；mode: WARN/BLOCK |
| `/home/ubuntu/workflow/task_brief_gate.py` | 校验脚本：--brief <任务书> --project <项目>，输出 JSON decision PASS/BLOCK/WARN |
| `/home/ubuntu/workflow/hermes_task_dispatch.py` | 统一派活入口：先过 gate → 签发一次性 token（10 分钟）→ 传执行器 |
| `/home/ubuntu/workflow/ds_native_invoke.py` | DS 原生 API 执行器：内置 TASK_GATE_TOKEN 硬校验（无 token 拒绝，防裸调绕过） |
| codex_exec_gated.sh / claude_remote_wrapper.sh（已改） | 入口加 token 校验，`TASK_GATE_ENABLED=1` 时生效（兼容旧直调） |

## 任务书强制标记（六类，gate_config.yaml 单一事实源）

- 复刻：TASK_TYPE=复刻 + READ_SKILL=video-remake + ASSET_REF= + 约束词「照原片结构/只换人物形象/单镜4-15s/画面字幕」
- 分镜：TASK_TYPE=分镜 + READ_SKILL= + ASSET_REF= + 约束词「单镜4-15s/不拆段/台词」
- 生图：TASK_TYPE=生图 + ASSET_REF= + 约束词「参考图/角色一致」
- 出片：TASK_TYPE=出片 + READ_SKILL=seedance-2-0-mini-workflow + ASSET_REF= + 约束词「单镜4-15s/字幕」
- 文案：TASK_TYPE=文案 + DATA_SOURCE= + 约束词「原文」
- 分析：TASK_TYPE=分析 + DATA_SOURCE= + 约束词「数据来源」

## 防绕过三板斧

1. 主对话只能走 hermes_task_dispatch.py 统一入口（禁止直调底层执行器）
2. 三通道执行器都校验 TASK_GATE_TOKEN（一次性、10 分钟过期、用后标记 used），DS 原生 API 封装在 ds_native_invoke.py 内裸调被拒
3. 内容真实性校验不靠模型自报：脚本读真实 skill/踩坑记录的 REQUIREMENTS/MUST_RULES 逐条比对任务书

## 落地节奏

- 最小可行（已落地）：静态标记 + 项目目录真实性（必须含 guard/ 目录防临时目录）+ 资产存在 + PRELOAD_NODES；mode=WARN 只记日志
- 完整版（待办）：skill/踩坑记录内容比对（REQUIREMENTS/MUST_RULES 解析）、项目 guard/source_meta.json（画面字幕语言等事实元数据）、一次性 token 全量启用、与 codex_preload_manifest.py 打通
- 验证：错误任务书 → WARN+7 缺失；正确任务书 → PASS；无 token 三通道全 BLOCK exit 2

## 与小鹿对照

- 小鹿有 knowledge_gate.py（check/mark/verify 三步）+ 三重物理拦截（codex_remote.sh / codex_exec_gated.sh / claude_remote_wrapper.sh 查 guard/kb_checked.json）+ onboarding_gate.py（欢迎语物理闸）+ G_STRATEGY_BY_CODEX（智力活外包，产物标注执行者）。
- 新加坡机缺的是「主对话入口」层闸——本次 task_brief_gate 补齐。kb_gate_sg.py 的 WIKI_ROOT 写的是 /home/ubuntu/wiki，新加坡实际在 /home/ubuntu/workflow/wiki（待修）。

## 回滚

1. gate_config.yaml mode 改回 WARN 或删除
2. 执行器壳恢复备份（.bak_20260818）
3. 停用 hermes_task_dispatch.py（各通道直调仍可用，但 DS 直调绕过风险重新暴露）
