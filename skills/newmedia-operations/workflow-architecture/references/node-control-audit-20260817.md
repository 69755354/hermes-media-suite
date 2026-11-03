# 节点控制审计：小鹿（广州）vs 新加坡（2026-08-17 codex 审计实录）

审计产出：`workflow/outputs/xiaolu_guangzhou_vs_singapore_node_control_audit_20260817.md`
触发场景：出片任务漏带绕检规则被老板批「是Hermes绕过规则还是codex」→ 全面审计两机每个节点控制是否形成不可绕过的物理闭环。

## 一句话结论

**两机的内容控制都「未闭环」**——看似有卡点（kb_checked.json / READ_SKILL 标记 / workflow_gate），实际都能被绕过。纸面规则无卡点 = 摆设（老板核心哲学）。

## ⚠️ 广州生产主通道实锤 = DS，不是 codex（2026-08-17 实测）

- 老板记忆「广州不是都调 codex 吗」与实际不符。
- 实锤：广州生产脚本 `/home/ubuntu/execute_api.py`（PID 从 8-15 常驻）**全脚本 deepseek_call / deepseek-chat**，grep codex 无结果。
- `.hermes/scripts/node1_analysis.py`（节点1 用户分析）也直接 deepseek-chat——但未查到生产调用方（疑似旧脚本）。
- **结论：广州生产主通道 = DS（deepseek-chat），违反「DS 仅容灾」铁律**；分镜/提示词/用户分析全由 DS 生成。
- 修复方向未定案（切换 codex 有跑不动的风险，先记着）。

## P0 漏洞清单（10 条，摘要）

| # | 漏洞 | 要点 |
|:--|:--|:--|
| P0-01 | 广州 1889 无认证 | `/execute` 无 token 可触发 DS/Seedream/Seedance/合成/交付；监听 0.0.0.0 |
| P0-02 | API 全旁路 | execute/helper API 不调用 KB/skill preload/workflow_gate/客户确认门/红线 |
| P0-03 | **codex 主通道读不到强制 skill** | `codex_sandbox.sh` 未挂载 `workflow/AGENTS.md` 和 `.hermes/skills` → AGENTS.md 强制加载链物理不可达（**本次漏规则根因**） |
| P0-04 | 合规门漏扫/fail-crash | data_source_gate 第一份文件后返回；空集合 TypeError |
| P0-05 | 门禁授权契约未闭合 | 无 check token 可 approve、已批门不复算上游 hash、并发写损坏 state |
| P0-06 | G_STRATEGY_BY_CODEX 不证明执行者 | 广州验可伪造文本头；新加坡只验非空文件 |
| P0-07 | 广州 DS 当生产主通道 | 违反「DS 仅容灾」，见上节实锤 |
| P0-08 | **真人写实直传无物理拦截** | 出片 API 不查图像内容/参考图 provenance；seedance-exact 接受任意存在图片 |
| P0-09 | 门禁 split-brain | 广州至少两份 workflow_gate.py（927/1027 行）+ 新加坡 1094 行，哈希全不同；registry/spec 也不同 |
| P0-10 | 广州 helper 先出片后查合规 | /pipeline 在 Seedance+合成后才查合规，违规交付+浪费付费 |

## P1/P2 摘要

- P1：customer gateway cwd 无 AGENTS（规则源未注入）；skill 预读 `_预读_*.md` 自证可伪造；出片通道选择=提示词逻辑（无 API 枚举/拒绝分支）；彩铅绕检只查文字记录不查图；DS 降级前置条件是注释无健康证明。
- P2：`SKIP_KB_GATE=1` prompt 内自声明；无项目路径 KB fail-open；KB flag 手工可伪造；**`READ_SKILL=seedance-2-0-mini-workflow` 文本标记可伪造**（写字符串即 rc=0，不验真实读文件）；`_自备文案.flag` 等豁免无人工批准签名；CLIENT_COPY 整门 SKIP。

## 修复方向（审计给的 8 条，未实施）

1. 任一内容入口缺项目/task/有效 gate ticket 均在 provider 调用前拒绝
2. 删除/伪造 `READ_SKILL`、`_预读.md`、`checked:true` 不能获得放行
3. 修改任一上游 artifact 后已有 ticket/批准立即失效
4. 每份候选文案逐文件扫描；空集合稳定 BLOCKED 不异常退出
5. DS 无健康故障票据只能产出 degraded artifact，且不进正式 gate
6. 真人写实参考图直提 Seedance 必须拒绝；只有带完整 provenance 的合格绕检资产可进生成
7. 两机门禁/registry/spec/skill manifest 哈希一致，无 profile 私有旧副本
8. 负向测试覆盖每个 API/wrapper/入口类型和 skip 条件；CI 全绿后再恢复付费生成

## 修复风险评估（2026-08-17 Hermes 分析，老板问「改这个有什么风险」）

- 加认证/接门禁（1/2/4）：**改可能让现有调用全断**——广州调用方没带 token、API 现在全靠旁路才能跑。生产停摆风险最高。
- 合并门禁/改沙箱（3/6/7）：可能引入新 bug + 要重启服务。
- 加检查（5/8）：新逻辑可能误判，相对可控。
- 建议分批：先低风险（先合规后出片、负向测试）→ 中风险（沙箱挂 skills、直传拦截）→ 高风险（加认证/切 codex 主通道），每改一个备份+测试+可回滚。
