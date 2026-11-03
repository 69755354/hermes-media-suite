# Hermes 全机盘点（system audit）命令集

2026-08-09 实战整理。触发：用户问「检查配置」「梳理整个 Hermes」「看下家底」。分区块并行跑，一次摸完再汇报。

## 区块一：版本与进程

```bash
cat ~/.hermes/hermes-agent/version.json 2>/dev/null || git -C ~/.hermes/hermes-agent describe --tags 2>/dev/null
ps aux | grep -E "hermes|helper|uvicorn|n8n" | grep -v grep | awk '{printf "%s %s %s %s\n", $2, $3, $4, $11" "$12" "$13}' | head -15
```

## 区块二：配置与密钥

```bash
# 主配置（read_file 读 ~/.hermes/config.yaml）
# 密钥文件
ls ~/.hermes/.env && wc -l ~/.hermes/.env
# tavily 残留检查（2026-08-09 tavily 已停用）
grep -n -i tavily ~/.hermes/config.yaml ~/.hermes/.env
```

## 区块三：脚本/守卫/平台

```bash
ls ~/.hermes/scripts/      # 50+ 脚本：权限闸/评审闸/数据源闸/生图/搜索
ls ~/.hermes/guard/        # 哈希校验 + security-middleware + render_locks
ls ~/.hermes/platforms/    # 平台适配（pairing 等）
ls ~/.hermes/plugins/      # 插件（lightclawbot 微信等）
```

## 区块四：工作流（Codex 侧）

```bash
ls ~/workflow/             # AGENTS.md + projects/scripts/skills/wiki
find ~/workflow/wiki -maxdepth 2 -type d
grep -E "^node" ~/workflow/wiki/spec/WORKFLOW_SPEC.yaml | head -20   # SPEC 节点数
ls ~/workflow/projects/    # ⚠️ 空目录 = 还没正式跑项目，注意
```

## 区块五：技能体系

```bash
ls ~/.hermes/skills/       # 顶级技能目录（newmedia-operations/thinking/server-operations 等）
```

## 区块六：记忆与 cron

```bash
cat ~/.hermes/memories/MEMORY.md   # 我的笔记
cat ~/.hermes/memories/USER.md     # 用户档案
ls ~/.hermes/cron/                 # executions.db/output/ticker 心跳
```

## 区块七：资源与状态

```bash
df -h / && free -h                 # 磁盘/内存
cat ~/.hermes/gateway_state.json   # gateway 状态
cat ~/.hermes/gateway.pid          # gateway PID
cat ~/.hermes/channel_directory.json  # 平台通道
```

## 本机身份确认（跨机迁移防 SSH 回自己）

```bash
hostname && curl -s --max-time 5 ifconfig.me   # 例：VM-0-11-ubuntu / <SG_HOST> = 新加坡机
```
记忆铁律：本机=新加坡机 <SG_HOST>，广州机 <GZ_HOST> 是另一台。汇报前先验身份。

## 汇报结构（微信短分条）

物理层（机器/IP/内存/磁盘）→ 核心进程 → 大脑（模型）→ 技能体系 → 安全防线 → 工作流 → 平台 → 记忆 → cron → ⚠️注意点（配置冲突/内存紧张/空目录等）。
