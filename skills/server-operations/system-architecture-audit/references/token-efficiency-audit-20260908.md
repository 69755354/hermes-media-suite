# Token 效率与架构优化审计基线（2026-09-08）

## 审计方法

打包双机现状清单给 `codex exec`（effort=high，gpt-6-astra，56K tokens）做深度审计，产出 14 条 P0/P1/P2 建议。任务书用纯英文写入文件避免 guard 关键词误伤（中文「内容生产/DashScope/出片」等词触发 skill_contract/kb_gate）。

## codex 审计产出的 14 条建议（精简）

### P0
1. 验证并收敛广州 helper_api 1888 root+公网暴露 + PID 2218 不明进程
2. 加 token 用量埋点（task_id 贯穿 Hermes→guard→codex→relay，记录 input/output/cache tokens、provider、耗时、重试）

### P1（核心 token 节省点）
1. **skill 选择性注入**：100+ 条 skills 摘要全注入 → topic router 按任务只注入相关 5 条。算术示例：5000 token → 450 token（省 91%，仅此组件）
2. **guard 去模型化**：确定性检查（文件存在/版本/schema）用代码做+缓存结果，只有语义判断才走模型。省每次 ~2400 token
3. **任务包+结果信封**：codex 产出结构化摘要（状态/路径/哈希），Hermes 只在交付时读全文
4. **handoff 改事件驱动**：状态没变不注入（当前每 5 分钟固定跑，最多 288 次/天空跑）
5. **codex session 复用**：同任务多步用 `codex exec resume <session_id>`
6. **常规操作不走模型**：磁盘检查/状态查询走代码 handler，只在异常时 escalate
7. **跨机 job 幂等**：持久 job_id + 幂等 key，丢连接后重连查原任务状态

### P2
1. 稳定 prompt 前缀做 provider 缓存命中
2. 实测峰值内存调并发上限
3. 文档化隧道路径
4. .hermes/.codex 磁盘保留策略
5. 合并真正重复的服务/脚本

## 关键约束（codex 强调）

- token 节省百分比不能叠加（skill 裁剪/guard 去重/session 复用有重叠）
- 必须做完 P0-2 埋点后实测对比，不能盲改
- 字符数 ≠ token 数（tokenizer 不同，GLM 和 GPT 分别计）
- guard 脚本纯 Python 文件读取不消耗 token，只有文本进入模型上下文才算

## 建议执行顺序

1. P0-1 安全加固（广州绑 127.0.0.1 + 非 root）
2. P0-2 token 埋点
3. P1-1 skills 裁剪（收益最大最快）
4. P1-3 + P1-4 结果信封 + handoff 事件驱动
5. P1-5 codex session 复用
