# 2026-08-09 安全加固会话完整记录（P0 全部 + P1 提速）

## P0-5 反向隧道守护（双端）

- 广州机侧：autossh + systemd（tunnel-sg.service），断线 3s 自动重连
- 新加坡机侧：tunnel_watchdog.py systemd 服务，60s 探测 8899，3 连败写 /tmp/tunnel_degraded
- 坑：systemd ExecStart 里 key 路径不能用 ~（profile home 解析错），必须绝对路径

## P1 提速落地清单

1. **Job API**（execute_job_manager.py）：/job 提交立即返回 job_id，/job/status 查进度，/job/cancel 取消；状态落盘 /tmp/execute_api/jobs/ 防重启丢失
2. **节点并行**：node5/6/9（分镜/角色图/合规）只依赖文案 → ThreadPoolExecutor(3) 并行
3. **Seedance 2 并发**：node10 逐镜 max_workers=2（等待型，内存友好）
4. **codex session 复用**：codex_task.sh 按项目目录存 session id，同项目 resume
   - 坑：codex_task.sh 在 background=true 下输出空日志（stdin 管道丢 prompt）→ 后台大任务用直接 flock 形式
5. **埋点**：log() 记每节点 dur_s，result 带 timings + total_s
6. **media outbox**（media_outbox.py）：send_document 失败入队 /tmp/media_outbox/，后台 60s 重试
7. **SPEC 解析修复**：WORKFLOW_SPEC.yaml 第 4 行 update_note 后残留无 key 的 `ffmpeg: 1` 导致 YAML 报 mapping values not allowed → 删除后 18 节点全解析

## 断链清理（codex 审计发现 24 项）

- customer profile 路径（迁移后不存在）→ 改主 skills 实际路径
- deepseek-thinking-config skill 不存在 → guard 引用清零，参数并入 huoshan
- assets/characters 目录不存在 → 建立 + 归档 xiaolu_sheet.jpg
- agnes-compose 方法存在但路由表缺分支 → 补 elif
- guard 裸命令 review_gate.py 不在 PATH → 改绝对路径
- api-contract.md 过时（script/photos vs 文案/照片）→ 标注
- 合理保留：跨 profile 同步说明、Hindsight/CDP/n8n 功能描述（非执行必读）
