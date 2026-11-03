# 派活被拦的四个固定模式（2026-09-23 实测）

派活失败几乎都不是任务本身出错，而是**入口闸**拦的。收到「任务未完成」先按这四条对号，再改任务书重派。

## 1 TASK_TYPE 与客户原话意图不一致（最高频）
- 现象：`BLOCKED: L1: TASK_TYPE=分镜/文案/机械 与出片意图不匹配（应为 出片）`
- 原因：入口按 `USER_REQ` 的原话做意图分类。原话要「生成/出片/出几条片」→ 意图就是 **出片**，写别的类型一律拒。
- 修法：TASK_TYPE 直接写 **出片**；台词本/分镜/提示词包作为**该任务书里的第一步**让执行器产出，不另拆任务类型。
- 反例：把「免费看剧 3 条」拆成 `TASK_TYPE=文案` 的任务 → 必挂。

## 2 知识库标记过期
- 现象：`KB_GATE:BLOCKED <项目> 知识库未查询！`
- 原因：`guard/kb_checked.json` 记录的任一知识库文件在标记 ts **之后**被改过（改了规则/skill 文档就会触发），闸按 `mtime > ts` 判失效。
- 修法：真读一遍相关文档，再覆盖写 `guard/kb_checked.json`（`ts` 用当前时间、`read_files` 保留真实存在的绝对路径、补齐该任务类型要求的 skill `SKILL.md` 路径），然后本地跑 `python3 /home/ubuntu/.hermes/scripts/kb_gate_sg.py -f <brief>` 确认 `KB_GATE:PASS`。

## 3 同一 request-id 重提被去重
- 现象：重派后打印「已受理」，但状态目录里的文件时间戳没变、状态还是旧的 failed。
- 原因：队列按 request-id 去重，只认首次受理记录。
- 修法：卡点修好后换新后缀重派（`-chupian2`、`-r2`）；不要指望同号重提会重新入队。

## 4 marker 与 gate_config 冲突
- 现象：`marker conflicts with config: READ_SKILL=...`
- 原因：写错了该任务类型要求的 `READ_SKILL` 取值（例如分镜要求 `director-thinking,video-production` 却带了 `hyperframes`）。
- 修法：取值照 `gate_config.yaml` 对应任务类型的 markers 原样抄；`出片` = `READ_SKILL=seedance-2-0-mini-workflow,hyperframes`。

## 派活前的 30 秒自检
1. `TASK_TYPE` 是否等于客户原话的意图（要出片就写出片）
2. 项目内有 `assets/`（非空）与名字含 script/storyboard/prompt 的上游产物
3. `kb_gate_sg.py -f <brief>` → `KB_GATE:PASS`
4. `preflight_rules.py --task-type <类型> --project <项目>` → `PREFLIGHT: PASS`
5. 任务号后缀是新的（不是已挂的那次）
