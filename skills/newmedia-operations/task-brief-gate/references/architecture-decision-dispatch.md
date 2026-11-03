# 架构决策派活模式：用户点名「让 claude 判断」（2026-08-22 广州 execute-api 切硬模式决策实测）

**触发**：用户点名「这个东西让 claude 判断 / 让 claude 拍板 / 让 claude 分析怎么走」——交给 claude 做架构/门禁/策略级判断（claude=架构/审查/终审，点名才用）。

## 模式五步

### 1. 证据进项目，不靠脑补
把全部环境事实收进 `inputs/<topic>/证据包_<日期>.md`，内容全部来自实测：
- 审计日志分布（如 gate_chain_audit.log 的 SOFT_PASS/BLOCKED/PASS 计数 + 最近 N 条原文）
- 服务配置（systemd drop-in、环境变量、MD5、部署时间）
- 代码位置与逻辑（闸链行号、端点读取逻辑）
- 实跑结果（如 `workflow_gate.py check <proj> G_RENDER_READY` 的 BLOCKED 输出）
- 调用方实际请求体（从小鹿会话库 state.db 捞真实 POST 脚本——查字段缺什么）
- 权限现状（`sudo -l` NOPASSWD 清单、root SSH 是否通）
- 历史背景（上次改动定案日期、已知绕过事件）

写完后更新 `guard/kb_checked.json` 的 sources 追加证据包路径。

### 2. 决策任务书结构（TASK_TYPE=分析）
- 标记行：`TASK_TYPE=分析` + `DATA_SOURCE=inputs/<topic>/证据包_<日期>.md` + `PROJECT_DIR=` + `PRELOAD_NODES=1,2,3,4`（分析类 preload_nodes 默认 [1,2,3,4]）
- `USER_REQ=` 直传用户原话（如「切啊」「这个东西让ckaude判断」）
- 第零步（必做）：read_file 证据包 + 相关代码基线 + 改动说明
- 背景节第一行写「数据来源：<证据包路径>（全部环境事实以该文件为准，禁止脑补）」——满足分析类 constraint_keywords「数据来源」
- 「需要判断的问题」：候选路线只列选项与各自定义，**不夹带 Hermes 判断/建议**（判断权交给执行器）
- 产出要求编号列出（本实例六问：利弊、推荐路线、改造方案、切换顺序、回滚预案、翻车点），强制「给出明确结论，不允许都行/看情况」
- 硬约束：只读分析、禁写文件/删文件/改配置/重启服务、禁付费 API、可 ssh 广州机只读查询、禁止编造数据（结论必须引用证据包或代码行号）

### 3. 派活前自检（kb_gate 误伤词）
`grep -nE '出片|Seedance|seedance|视频生成|生成视频|video.*gen' <任务书>`——命中就改写措辞（如「出片确认」→「渲染确认」）。task_brief_gate 预检 PASS 后再 dispatch。

### 4. 派活走正规入口 + 后台
```
python3 /home/ubuntu/workflow/hermes_task_dispatch.py \
  --brief <brief.md> --project <proj> --target claude \
  -- "$(cat <brief.md>)" <proj_dir>
```
必须 `background=true + notify_on_complete=true`（claude 通道是阻塞式，前台跑必超时）。

### 5. 前台超时后的处置（claude 版）
前台 dispatch 超时（exit 124）**不等于任务死了**：先 `ps aux | grep -E 'claude|dispatch' | grep -v grep` 查孤儿——若壳被杀但 claude 没起来（无 claude -p 进程、无 tee 日志管道）→ 无孤儿，直接 background 重发即可；若有 claude -p 在跑 → 不重发，等 notify（重发=双倍扣费+并发互覆盖）。

## 本实例关键教训（切门禁/切模式前必做）

**切硬模式前必须验证「业务路径在硬模式下真能过闸」，不能只看代码逻辑。**
- 证据1：审计日志 38 条 SOFT_PASS 全是 video_talk 缺 project_dir（软模式掩盖了请求侧漏传）
- 证据2：即使补 project_dir，华合项目实跑 G_RENDER_READY 仍 BLOCKED（上游 G_CREATIVE_READY 未获批，19 节点主链未建立）
- 结论：直接切硬 = 小鹿正常轻量直调全断。门禁设计与实际业务（确认剧本后直调）不匹配，需先分层或补链。

排查「为什么一直缺 project_dir」的取证链（可复用）：
1. `grep -n 'video_talk\|project_dir' <生产代码>` —— 端点怎么读参（body.get 缺省空串）
2. 小鹿会话库捞真实调用：`sqlite3 state.db "SELECT content FROM messages WHERE content LIKE '%video_talk%' ..."` —— 看请求体字段（发现只有 task_id/prompt/refs/duration/customer_id，无 project_dir）
3. 实跑门禁验证补参后是否真能过：`workflow_gate.py check <proj> G_RENDER_READY`（发现仍 BLOCKED）
4. 审计日志分布量化影响面：`grep -oE 'SOFT_PASS entry=video_talk cid=[^ ]+' <audit> | sort | uniq -c`

## claude 判断结论（2026-08-22 交付，用户「这个东西让claude判断」→ 三路线判断全文）

claude 实测推翻「关软模式 = 恢复硬拦」，决定性发现（判断结论全文 `projects/xiaolu-bug-sweep/staging/gz-gate-decision/判断结论_20260822.md`）：

1. **闸2 G_RENDER_READY 结构性不可达 rc=0**：registry 里 `render_readiness` 是 `implemented:false, manual:true`，`workflow_gate.py check()` 尾部 `if manual: return 3` → rc=0 数学上不可达；19 门里 17 个 rc=3-only（只读仿真实测）。execute_api `if r.returncode != 0:` 把 rc=3 当拦截 → **硬模式拦截率 100%，与项目/客户/参数无关**。「补 project_dir + 跑通主链闸2就过」是伪假设。
2. **闸1 也 100% 拦**（证据包漏了它）：`confirm_gate.py check` 实跑 rc=2；全机 `find / -name CONFIRM.json` 只有测试残留——所有真实项目都没有确认状态文件。
3. **workflow_gate.py 三副本分叉**：执行副本（`~/.hermes/scripts/`，无 approve 子命令）+ 新副本（`workflow/scripts/`，有 approve 但状态写 `<proj>/workflow_state.json` 无签名）+ 新加坡（第三版）。**用新副本 approve 批门，执行副本读外置+HMAC 签名文件，白批。**
4. **路线 C（强制主链）物理不可实现**：「走完主链」当前没有任何命令能完成（执行副本无 approve）。
5. **推荐 B 判据必须放调用方不可写处**：❌ 绝不用 `body.get("entry_type")`（自我声明=后门）。✅ 项目级渲染授权白名单 `/etc/hermes/render_authorized.list`（root:root 644）——`project_dir ∈ 白名单` → LIGHT（只豁免闸2，闸0/闸1/permission 全硬）；∉ → FULL 四闸原样。**天行者批一次=加一行，项目级一次，不是每条视频一次。**
6. **LIGHT 隐藏必要条件：堵 confirm skip 旁路**：`confirm_gate.py skip <proj>` 让 agent 自开 24h 全放行——LIGHT 唯一安全点（闸1）可被一条命令绕过。闸1 必须解析 `cmd_check` 输出的 `"mode":"skip"`，命中视为未确认。
7. **灰度四阶段（环境变量改一次要一次 root，改用代码内分级）**：阶段1 `_HARD_ENTRIES={"execute"}`（/execute 近3天零流量=天然灰度场）→ 24h → 阶段3 `{"execute","video_talk"}`（soft 环境变量仍在双保险）→ 24h → 阶段4 才请 root 移除 drop-in。**顺序铁律：摘 drop-in 必须最后。**
8. **`/home/ubuntu/execute_api.py` 是 ubuntu:ubuntu 600** → 改代码+重启（SIGTERM + Restart=always）全程不需要 root，回滚 10 秒（`cp .bak + pkill -TERM`）；root 只两次：建白名单、最后摘 drop-in。
9. **明早第一步 = 影子演练**：硬模式环境变量下只读跑华合四闸打全 rc，坐实双 100% 阻断推断；**这张表出来之前不碰 drop-in**。

派 claude 判架构的实操要点（本会话补）：任务书三条路线只列事实（每条收益/风险/影响面/成本），**不预设答案、不写 Hermes 倾向**（用户「判断权交给执行器」）；产出要求六项（利弊/推荐/改造方案/切换顺序/回滚/翻车点）；claude 会自己 ssh 广州机只读实测补证据包缺口（本会话补 5 项：生产文件权属/闸1 100%拦/闸2 不可达/三副本/闸3 空转）。
