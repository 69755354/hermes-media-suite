# 指向：执行器协作知识（2026-08-12）

本文件是索引指针，完整内容在 **codex-cli-ops skill** 的 references/ 下（同一 curator 维护，避免重复存储）：

## DS 容灾降级全方案 → codex-cli-ops `references/ds-fallback-plan.md`

cc（Claude）/codex 挂掉时用 DeepSeek 顶班的完整方案，2026-08-12 实测落地：

- **一句话：DS 顶不了「审查」，顶得了「执行」；DS 能验证，不能发现**
- 实测通道：DS 顶 cc 位 = claude 壳 + `https://api.deepseek.com/anthropic` + `deepseek-v4-pro`；DS 顶 codex 位 = codex 壳 + `https://api.deepseek.com/v1` + `wire_api=responses` + `deepseek-v4-flash`（**codex 壳只能用 flash**）
- 两个坑：① `CLAUDE_CODE_USE_BEDROCK=1` 劫持路由，要 `env -u` 清掉；② 健康检查三层里**只有 L3（端到端改坏函数+跑测试）失败才算 DOWN**——L1/L2 环境/鉴权问题别降级，L3' 限流等重试别降级
- 降级矩阵：codex 挂时**让 CC 端到端做完**（不是 DS 顶 codex）；都挂时内容生产几乎无损（本来就跑 DS），写代码降级（分支+单文件+测试兜底），架构审查**冻结排队不降级**
- 硬红线（禁止降级）：门禁状态机/skills 树删除（Git 外不可回滚）/主干 push/数据迁移/安全边界/客户方案定稿——输出 `BLOCKED_NEEDS_PRIMARY:<原因>`
- 落地：`scripts/agent_health_check.sh` + `scripts/ds_fallback.sh` 已在 workflow git

## 双执行器交叉互评 + 分工定稿 → codex-cli-ops `references/agent-division-and-cross-review.md`

- 交叉互评流程：用户原话打包分别问两边 → 互发对方评 → 追问依据（A/B/C/D 分级）→ 原话汇总；**不加 Hermes 判断**
- 分工定稿：路由轴 = **可逆性×事实不确定度**（非项目大小）；单一 owner；五方角色 CC/codex/DS/Hermes/**人（唯一持久记忆+唯一不可逆授权）**
- 「CC 更会审查、Codex 更会实现」仍是假设，用数据验证前不成立

## 审查维度工具（workflow 侧已落地）

`scripts/mutation_test.py` / `artifact_lifecycle.py` / `change_cost_map.py` / `cold_start_test.py` / `stress_test.py`（commit 8fccec0）——Claude 自述 5 个未用维度已工具化（突变注入⭐/产物生命周期/变更成本地图/冷启动路径/演化压力测试），详见 `references/review-dimensions.md`。
