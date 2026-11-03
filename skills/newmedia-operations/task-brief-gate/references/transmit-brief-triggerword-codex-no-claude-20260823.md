# 传话书触发词变体 + codex 容器无 claude key（2026-08-23 reverse-video-prompt 融合分析打包实录）

## 场景

用户定案「reverse-video-prompt 是补缺不是替代，闭环：抽帧+豆包反推 → 出片 → 对比诊断 → 迭代 prompt → 沉淀规则」，要求派 claude 做融合分析。Hermes 写传话书（briefs/pack-merge-analysis-20260823.md）后 dispatch codex 打包任务书。

## 坑 1：传话书 USER_REQ 用户原话含「出片」字样 = SKILL_CONTRACT 误判（新变体）

- **现象**：dispatch 报 `SKILL_CONTRACT:WARN L1: TASK_TYPE=分析 与出片意图不匹配（应为 出片）` + `BLOCKED: 出片任务缺少 seedance-2-0-mini-workflow skill 加载标记`，DISPATCH_EXIT=1。
- **根因**：kb_gate 全文扫描传话书，USER_REQ 里用户原话「抽帧+豆包反推 → 出片 → 对比诊断」含「出片」两字——**连 Hermes 写的传话书也会被扫**，不是只有 codex 打包的任务书才受触发词约束。
- **修法（实测通过）**：保留 `TASK_TYPE=分析`，只补一行 `READ_SKILL=seedance-2-0-mini-workflow` 即过（L1 WARN 放行，KB 硬拦解除）。**用户原话一字不改**——不要为了过卡点改写用户原话，也不要改 TASK_TYPE=出片（传话书不是出片任务，改了就是假读）。
- **自检**：dispatch 前 `python3 ~/.hermes/scripts/kb_gate_sg.py -f <brief>` 期望 PASS/RC=0；报 L1 WARN 不拦，缺 READ_SKILL 才 BLOCK。

## 坑 2：codex 容器没有 claude/Bedrock key（正常，不是失败）

- **现象**：codex 打包完任务书，报告里写「当前环境没有 Claude/dispatcher 执行入口/缺 Bedrock key (/home/ubuntu/.hermes/claude_bedrock_key)，Claude 分析报告尚未生成」。
- **解读**：这是**容器能力边界**，不是任务失败。codex 容器不挂 claude CLI/Bedrock 凭据；claude 派单走宿主机 wrapper（`hermes_task_dispatch.py --target claude`，claude_remote_wrapper.sh 跑宿主机）。
- **正确处理**：任务书已生成即可继续——用宿主机 dispatch 派 claude 执行同一份任务书，不用重打包、不用让 codex 补跑。完整链路：codex 打包任务书（容器内）→ Hermes 宿主机 dispatch claude（wrapper 宿主机）→ claude 出报告。

## 本会话产物路径

- 传话书：`reverse_prompt_merge/briefs/pack-merge-analysis-20260823.md`（含 READ_SKILL 修正）
- codex 打包任务书：`reverse_prompt_merge/staging/CLAUDE_MERGE_ANALYSIS_TASK_BOOK_20260823.md`（自审 PASS，SHA-256 `4b448bb1…`）
- claude 融合分析：`reverse_prompt_merge/staging/CLAUDE_MERGE_ANALYSIS_REPORT*`（分析 reverse-video-prompt 与 video-remake/video-reproduction/video-reverse-engineering/huoshan/seedance 系 skill 的融合方案）

## 关联

- 主 SKILL.md「区分 L1 WARN 与 KB BLOCK」pitfall 的**传话书变体**：分析类任务书/传话书正文含 Seedance/出片词时，TASK_TYPE=分析 的 L1 不匹配只是 WARN 不阻断，真正 BLOCK 的是缺 READ_SKILL=seedance-2-0-mini-workflow。
- 蒸馏产物：`reverse_prompt_merge/raw/SKILL.md`（Reverse Video Prompt 主 skill）、`prompt-framework.md`（61KB 反推框架）、`iteration-workflow.md`（复刻反馈迭代流）——后续融合分析/落地时引用。
