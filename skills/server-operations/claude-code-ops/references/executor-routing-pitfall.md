# 执行器分流踩坑：用户说「用Claude」却被路由到 codex exec

## 症状

用户明确说「用Claude去改/去分析/去写」，广州机小鹿却走了 `codex exec` 而不是 `claude -p`。

## 根因（三层叠加）

### 1. codex-bridge 触发词太宽
`codex-bridge` 技能的触发词覆盖了写文案/做分析/拆解/复盘/出方案/写代码/标题/选题/口播/剧情/探店/竞品/策略/搜索爆款/合规研判——基本上所有智力活都匹配上了，动作写死 `codex exec`。

### 2. SOUL.md 硬规则把 codex 定成默认
codex-bridge 引用了一条 SOUL.md 硬指令：「创作/分析/搜索类必须先调 codex，禁止 DeepSeek 直出」——这条规则把 codex 定成了默认执行器，Claude 只是「补充执行器」。

### 3. claude-code-ops 定位太窄
触发词只有「装Claude Code/Bedrock认证/远程调用」，用途场景只列了「第二意见、架构审查」——没有写文案/分析/改稿这些日常活。

### 4. customer profile 根本没装 codex-bridge 技能
广州机 customer profile 的 skills 目录下没有 `newmedia-operations/` 目录——codex-bridge 从未同步过去。小鹿调 codex 是 GLM 模型自己的默认行为，没见过任何分流规则。

## 修复（2026-09-04 已执行）

1. **codex-bridge 加分流规则**：用户说「用Claude/cc」→走 `claude -p`；未指定→走 `codex exec`（默认）
2. **claude-code-ops 改定位**：从「补充执行器」改为「并列执行器」，触发词加了「用Claude去改/去分析/去写」
3. **同步到 customer profile**：`mkdir -p` 创建目标目录 + `cp` SKILL.md → 重启 gateway

## 同步踩坑

`soul-md-update-protocol/scripts/sync-to-customer-profile.sh` 的 KNOWN_SKILLS 列表是硬编码的，只有 4 个技能（shuziren/huoshan/soul-md-update-protocol/semantic-digital-human-workflow），新增技能不会自动加入。**soul-md-update-protocol 是 user-owned 技能，无法自动更新——用户需手动跑 `hermes curator adopt soul-md-update-protocol` 或在脚本里加新技能路径。**

## 验证方法

跟小鹿说「用Claude去分析个东西」，检查它走的是 `claude -p` 还是 `codex exec`：
```bash
# 广州机查进程
ssh -p 2222 -o ConnectTimeout=5 ubuntu@127.0.0.1 'ps aux | grep -v grep | grep -E "claude|codex" | head -5'
```