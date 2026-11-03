# 出片链路门禁链调试：confirm_gate → G_CREATIVE_READY → G_RENDER_READY（2026-08-23 火龙实录）

> 场景：分镜+提示词包验收后出片（seedance-exact/job），被门禁链层层拦截。Claude 只读分析出三层层叠根因（报告 GATE_FIX_PLAN_claude_20260823.md 47KB 为权威源）。

## 拦截链全景（从提交到真正出片的完整关卡）

```
POST /seedance-exact/job
 → 闸0: project_dir 必须存在（fail-closed）
 → 闸1: confirm_gate node12_render（出片确认 + 产物哈希绑定）
 → TEST_RUN 入口拒绝
 → 闸2: workflow_gate G_RENDER_READY（LIGHT 豁免 / FULL 强制）
    └─ check_upstream_hashes → A_STORYBOARD 哈希须 = G_CREATIVE_READY 获批记录
 → 闸3: billing_gate precheck（无 precheck 能力时降级审计不拦）
```

## 关键判定：job 外层 status=success ≠ 出片成功

`POST /job/status` 返回 `{"status": "success", "result": {"status": "blocked", "msg": "..."}}`——**被闸拦时 job 本身算「成功完成」**，拦截信息在 `result` 字段里。查 `result.status` / `/tmp/execute_api/jobs/<job_id>/state.json`，别只看外层 status。

## 三层层叠根因（每层都要解决，修一层不能出片）

### L1：派活任务书被扫进导演意图评审（可绕过但必须修）

- `locate_creative_prompt_files`（workflow_gate.py）按 scope_guard 范围扫描：
  - `applies_to_artifacts: [A_STORYBOARD, A_PROMPT_PACKAGE]` + `filename_patterns: ["**/*prompt*.md", ...]`
  - 扫描**全项目**（os.walk），`briefs/` 下任务书文件名含 `prompt` 即命中
  - excluded 正则（接力|复盘|校验|知识库|...|bak）**不含 briefs/tasks/任务书/工单** → 任务书进评审
- `check_director_intent` 取**最新 3 个**文件（mtime 降序）逐个送评；任务书是派活工单无逐镜内容 → 四维全低分 → `action_tie high` 强制 BLOCK
- **附带缺陷：3 次评审写同一 `--out` 路径（"w" 模式），只有最后一次留存**——真产物的评审结果被覆盖丢失，当前 `导演评审报告.md` 反映的是任务书的评分，不能当分镜质量证据
- 修法：excluded 正则加 `^(?:briefs|tasks)/`（`rel_path` 由 os.path.relpath 生成已统一 `/` 分隔，锚定行首精确匹配项目根下目录，不会误伤深层含 tasks 的路径）。实测命中数 18→10，最新 3 个全变真产物。

### L2：分镜脚本过不了 check_storyboard（更严重，改标题也不够）

`check_storyboard` 双解析器全返回 0：
- `parse_storyboard_rows` 要求首列 `re.fullmatch(r"镜(?:头)?\s*\d+")`——分镜用 `S01—S08` 语义编号不匹配
- `parse_seedance_shots` 要求标题 `^##\s*镜头(\d+)\s*[｜\|].*?(\d+(?:\.\d+)?)\s*秒\s*$`——分镜标题 `## S01｜男主开场…` 不匹配

改标题后还有 5 类硬性不合格：
1. **缺四层标注**：分镜正文 `第一层/第二层/第三层/第四层` 出现 0 次（四层写在 PROMPT_PACKAGE 里，不在 A_STORYBOARD）——产物职责错位
2. **缺负面约束区**：要求字面串 `第四层：负面约束` + `NEGATIVE_LABEL_RE`（`(专属负面|通用负面|负面约束|负面词|负面)[：:]`）；分镜写 `**专属负面**：`（markdown 粗体）正则穿不过 `**`
3. **@图用途判定失败（规范与代码直接矛盾）**：`reference_has_use` 硬性要求字面串 `仅用于`；AGENTS.md 第九节要求写 `仅作人物参考/仅作场景参考`——**按规范写分镜必然被闸拦**。需人定案方向 (i) 改闸正则兼容 `仅用于|仅作`（推荐，影响面小）vs (ii) 改 AGENTS.md（两机共用源，影响大）
   - 附加缺陷：`reference_segment` 用 `re.search` 只取**全文第一个** @图N 段（本项目 @图1 出现 27 次），第一个落在表格行内 → 全局判定恒 False 并 and 连锁污染全部 7 镜
4. **情绪描述不足**：`emotion_categories` 要求部位词+动作词同短句共现，动作词表 ACTION_RE 为 18 词闭集（抬升|抬起|轻收|…），不含 `招呼/站起/讲解/前倾/后移` 等常用写法
5. **S01 单镜时长超口播上限**：全文含「口播」→ is_talking_head=True → 上限 10s；S01 = 10.050s 超 0.050s

### L3：G_CREATIVE_READY 记录已被 BLOCK 副作用清零

- `blocked()` 调 `record_gate(..., "BLOCKED")`，record_gate 对非 ALLOWED/SKIPPED 状态写 `status: null` + 所有 artifact_hashes 置 null——**原 ALLOWED 记录被销毁**
- 后果：下次 G_RENDER_READY 报错从「哈希不符」变「上游门未获批」，必须先让 G_CREATIVE_READY 重新 ALLOWED
- LIGHT 豁免通道已关（`/etc/hermes/render_authorized.list` 被清空「豁免全部取消」）= FULL 强制 G_RENDER_READY

## judge 无响应：不是拦截原因，是静默放行缺陷

- `judge()` 返回 None → main 返回 rc=2；`check_director_intent` 对 rc=2 只打 stderr WARN + continue（**不拦截**）——API 故障 = 该文件评审被跳过 = 放行
- 本次 BLOCK 恰恰来自一次成功的 judge 调用（返回完整四维分数 + high issue）
- 确定性盲区：`content[:12000]` 截断，24782 字符分镜只有 48.4% 被评审（S05—S08 从未被看过）——评审通过结论对后半片不成立

## 人工审批路径（方案 A）vs 根治路径（方案 B）

- **方案 A（立即出片）**：人 approve 两道门（G_CREATIVE_READY + G_RENDER_READY）。`approved_record_is_current` 在任何检查函数前返回 ALLOWED——approve 记录满足 status=ALLOWED + approval_by/approved_at 存在 + produces 哈希匹配即跳过 check_director_intent/check_storyboard。**必须由人执行**（AGENTS.md 铁律 7：人工门只能由人批准，Claude/Hermes 不得代批）。命令：`workflow_gate.py approve <proj> <gate_id> --by "<人>" --evidence <证据文件>`。前置：A_STORYBOARD 一个字节不改（改动同时打掉 confirm 闸 artifact_sha 与 approve 记录哈希）；证据文件须存在且非空。
- **方案 B（根治）**：改闸代码让自动路径通过。改动面：excluded 正则加 briefs/tasks + 解析器兼容 S01 语义编号 + reference_has_use 兼容「仅作」+ 报告分文件留存 + reference_segment 遍历 + judge 模型名读 config + 截断修复。**workflow_gate.py 两份（/opt/hermes/gates/ 与 /home/ubuntu/workflow/scripts/）md5 相同但独立 inode，root:root 0444，无同步脚本，须 root 同时改两处**——codex 容器无权改生产文件，只产补丁到 staging 由人部署。

## 执行纪律沉淀

- 出片被拦先查 `gate_chain_audit.log`（`/home/ubuntu/.hermes/guard/gate_chain_audit.log`）看真实拦截点，别从错误信息猜
- confirm_gate 确认绑定产物 = 单向棘轮：一旦绑定 artifact_sha 不可退回无绑定；旧确认（无 sha）带产物 check 必拦
- 改分镜脚本 = confirm 闸失效需重新确认；改 A_STORYBOARD = G_CREATIVE_READY 哈希不符需重新获批——**出片前产物冻结是硬约束**
- 用户问「还有哪里有问题的」= 一次性挖全链路（闸0→闸3 + 产物哈希 + 三视图 + 人工门）再汇报，别挤牙膏
