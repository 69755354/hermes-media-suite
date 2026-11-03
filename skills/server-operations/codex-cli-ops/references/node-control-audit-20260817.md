# 两机节点控制审计（2026-08-17 codex 全量审计）

> 审计对象：小鹿（广州机 <GZ_HOST>，profile customer）vs 新加坡机（<SG_HOST>，主 Hermes）
> 审计报告原件：`outputs/xiaolu_guangzhou_vs_singapore_node_control_audit_20260817.md`
> 用途：修门禁/卡点前先读这份，避免重复审计；修复后回填状态。

## 核心结论

两机物理控制「未闭环」——每个卡点都有旁路。看似有闸，实际可绕过。

## P0 漏洞（可被绕过或无拦截）

| # | 漏洞 | 影响 |
|:--|:--|:--|
| P0-01 | 广州 `0.0.0.0:1889` /execute 无认证 | 任何人可触发付费接口（DS/Seedream/Seedance/合成） |
| P0-02 | execute/helper API 不调用任何门禁 | 全旁路 |
| P0-03 | Codex 沙箱没挂 `workflow/AGENTS.md` + `.hermes/skills` | 强制加载链物理不可达（Hermes 派活漏规则的根因之一） |
| P0-04 | 合规门漏扫与 fail-crash（data_source_gate 第一份文件后 return；空集合 TypeError） | 极限词文案 ALLOWED |
| P0-05 | 门禁授权/完整性契约未闭合（无 token 可 approve、已批门不复算上游 hash、CLIENT_COPY 整门 SKIP） | 批准可伪造 |
| P0-06 | G_STRATEGY_BY_CODEX 不证明执行者（文本头/非空文件都可伪造） | 通道真实性无证明 |
| P0-07 | **广州生产主通道是 DS**（`/home/ubuntu/execute_api.py` 直接 deepseek_call，分镜/提示词/用户分析全走 deepseek-chat） | 违反「DS 仅容灾」，无 DS_DEGRADED 隔离 |
| P0-08 | 真人写实直传无物理拦截（不验图片内容/provenance；seedance-exact 接受任意存在图片） | 绕检可绕过 |
| P0-09 | 门禁 split-brain（广州至少两份 workflow_gate.py + 新加坡一份，哈希全不同；registry/spec 也不同） | 同一 gate 不同语义 |
| P0-10 | 广州 helper /pipeline 先 Seedance+合成后才查合规，且合规失败不改顶层成功状态 | 违规交付 + 浪费付费 |

## P1（只有软规则，无可靠物理卡点）

- P1-01 customer gateway cwd 无 AGENTS（规则源不注入）
- P1-02 skill 预读是自证（`_预读_*.md` 只需出现文件名+要点字样，不证明真读了）
- P1-03 出片通道选择是提示词逻辑（探店/剧情→Seedance、口播→婵镜没有类型化 API/状态机）
- P1-04 彩铅绕检是文本规则（G_RENDER_READY 查文字关键词，不查真实图片）
- P1-05 DS 降级前置条件是注释（ds_fallback.sh 不读健康检查事件）
- P1-06 部分合规风险只告警不拦截

## P2（有卡点但可跳过）

- P2-01 `SKIP_KB_GATE=1` 是 prompt 内自声明（无身份/票据/有效期）
- P2-02 无项目路径即 KB fail-open（「写一篇餐饮口播文案」两机都 rc=0）
- P2-03 KB flag 可手工伪造（只查 checked truthy，不绑定 task/node/artifact/hash）
- P2-04 新加坡出片 marker（READ_SKILL=...）提前 return 0 且跳过 KB 检查
- P2-05 项目级豁免文件（`_自备文案.flag` 等）无人类批准签名
- P2-06 entry route 可整门 SKIP（CLIENT_COPY 输出 SKIPPED 未查红线）

## 修复方向（审计给的 8 条验收标准）

1. 任一内容入口缺项目/task/有效 gate ticket → provider 调用前拒绝
2. 删除/伪造 READ_SKILL、_预读.md、checked:true 不能获得放行
3. 修改上游 artifact → 已有 ticket/批准立即失效
4. 每份候选文案逐文件扫描；空集合稳定 BLOCKED
5. DS 无健康故障票据只能产出 degraded artifact，不能进正式 gate
6. 真人写实参考图直传 Seedance 必须拒绝；只有带完整 provenance 的绕检资产可进生成
7. 广州/新加坡门禁和 registry/spec/skill manifest 哈希一致
8. 负向测试覆盖每个 API/wrapper/入口/skip 条件；CI 全绿再恢复付费生成

## 修复风险分析（改错会断服）

| 修复项 | 风险 | 原因 |
|:--|:--|:--|
| 广州 1889 加认证 | 🔴 高 | 现有调用方（小鹿 gateway/脚本）没带 token，加了全断 |
| execute/helper 接门禁 | 🔴 高 | 合法调用也可能被拦，生产全停 |
| Codex 沙箱挂 skills | 🟡 中 | 挂载路径/权限错 → codex 读不到或读错；要重启沙箱 |
| DS 禁主通道 | 🟡 中 | 广州现在分镜/提示词全靠 DS，禁了全停（需 codex 顶上） |
| 真人写实直传拦截 | 🟡 中 | 图像检查逻辑新写，误判会拦正常出片 |
| 门禁哈希统一 | 🟡 中 | 三份合并可能引 bug，要同步部署+重启 |
| 先合规后出片 | 🟢 低 | 只调顺序，但要重启广州服务 |
| 负向测试 | 🟢 低 | 只加测试 |

**原则：分批修（先低风险后高风险）；每改一个先备份+测试+可回滚；广州在跑客户，不能弄挂。**

## 实测证据（关键复现）

- 广州 `POST 127.0.0.1:1889/ping` 无认证 HTTP 200，监听 0.0.0.0:1889
- 新加坡 execute 无认证 HTTP 200，但监听 127.0.0.1:1889（外部攻击面小）
- 无项目路径「写一篇餐饮口播文案」→ 两机 KB gate 均 rc=0（fail-open 实锤）
- 新加坡：项目无 KB flag + 出片 + READ_SKILL → rc=0（提前放行实锤）
