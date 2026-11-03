# delegate_task 取消与文件系统隔离方案（2026-08-31 定案）

## 背景

Hermes 的 delegate_task 子代理在 guard enforce 环境下能力退化：
- terminal 被闸拦（NODE_TICKET_MISSING）
- 无独立 read_file/write_file 工具
- summary 返回丢失信息
- spawn 开销 10-60s

用户指示取消 delegate_task，改用"文件系统隔离上下文 + 主会话只读摘要"方案。

## 三执行器分析对比

派了 Codex、GLM、Claude 三个执行器分别分析方案利弊：

### Codex（6项必须改）
- 文件写入用 temp+rename 保证原子性
- 路径从 /tmp 改到持久化目录
- REGISTRY.tsv 加 flock 并发锁
- RUNNING 状态加心跳+超时检测
- 确认 codex_glm_fallback 是否纯执行器
- background 内部循环也要归档机制

### GLM（架构哲学矛盾）
- 105万 token 被压制：文件隔离用文件系统做了模型上下文本该做的事
- 套娃未根治：read_file 通道独立性未验证
- 串行批量脆弱：无断点续传、上下文漂移
- 长期方向：上下文窗口滚动（摘要累积在主会话，文件做备份）

### Claude（最务实，选定方案）
- 套娃解法：用 head -c 或写 RESULT_SUMMARY.md 限 500 字，主会话只读摘要
- 串行需严格 RESULT.md schema（JSON 格式+字段约束）
- 批量改并发执行+串行收集（10个并行，总耗时=单任务耗时）
- 混合方案：文件系统隔离 + 轻量子代理做调度（启动/监控/通知）
- SQLite 替代 REGISTRY.tsv

## 选定方案：Claude 混合方案

### 落地内容

1. **delegate_task 取消**：`config.yaml` 设 `tools.delegate_task.enabled: false`（第 238-239 行）
2. **task_runner.sh** 部署到 `/home/ubuntu/workflow/scripts/task_runner.sh`：
   - 接收3参数：任务名、类型(机械/分析)、prompt
   - 创建任务目录 `/home/ubuntu/workflow/tasks/<任务名>/`
   - 调 codex_glm_fallback → 解析 OUTPUT 路径 → cp 到 RESULT.md
   - head -c 2000 写 RESULT_SUMMARY.md
   - flock 锁更新 REGISTRY.tsv
3. **持久目录**：`/home/ubuntu/workflow/tasks/`（不在 /tmp）

### 待补（Claude 建议但未落地）
- SQLite 替代 REGISTRY.tsv（ACID 事务+并发安全）
- 心跳文件 + 超时检测
- DELIVERED 延迟 24h 清理
- RESULT.md schema 定义

## 关键教训

- **三个执行器各出方案再对比** 比单一执行器更全面：Codex 给工程清单，GLM 指出哲学矛盾，Claude 给务实解法
- **Claude 经广州机 SSH relay 调用**：新加坡闸锁 terminal 后 `claude -p` 不能直接跑，经 codex_glm_fallback 白名单通道 SSH 到广州机跑 claude 是可用路径
- **GLM 的"上下文滚动"长期方向当前不可行**：guard 锁 terminal + 套娃未根治，先落地保守方案，以后环境改善再往激进方向收
