# 广州 execute-api 门禁链 + 出片记账（2026-08-22 部署实录）

## 门禁链（_gate_chain，execute_api.py）

- **闸0/闸1**：建档+权限+配额、出片确认（node12_render）——本次未改
- **闸2 G_RENDER_READY**：`workflow_gate.py check <project_dir> G_RENDER_READY`
  - 软模式（HERMES_GATE_SOFT=1）：`_verdict()` 写 SOFT_PASS 返回 None → 继续闸3 → 放行
  - 硬模式：任何非零退出（含链缺失/上游未获批/项目未纳入 registry）→ 拦截
  - 2026-08-21 定案：删除原「链缺失（`_chain_absent` 关键词匹配"上游门/未获批/不存在/未纳入/registry"）放行」旁路——链未建立/上游未批本身就是 G_RENDER_READY 未通过，不能再由错误文本关键词构成旁路
- **闸3 billing precheck**：`billing_gate.py precheck --customer-id X --type video`
  - rc==2 → 余额不足拦截；其他非零 → BILLING_DEGRADED 容灾放行（billing 抖动不打断已获准出片）
  - 硬模式 + 输出含 NOOP_MODE /「无 check 子命令」→ 追加 `WARN BILLING_GATE_NOT_ENABLED`（暴露 billing 仍是空实现）；软模式不写
  - 注意：billing_gate.py 无 check 子命令且 NOOP_MODE=True——billing 闸实际是空实现，余额安全靠 confirm/workflow/permission 三闸
- 审计日志：`/home/ubuntu/.hermes/guard/gate_chain_audit.log`；PASS 行 = entry/cid/proj
- 软模式开关只认环境变量 `HERMES_GATE_SOFT=1`（systemd drop-in 写入）

## 出片记账（_record_video_cost，改动3）

- 位置：execute_api.py 常量区 + 103-186 行；`seedance()` 成功后调用；`/execute` 与 `/video_talk` 两通道都接
- 默认库：`/home/ubuntu/wiki/shop-info/costs.db`；可用 `HERMES_COSTS_DB` 或函数 `db_path` 参数指向测试库
- 表结构与 cost_meter.py 的 costs 表一致（CREATE TABLE IF NOT EXISTS + idx_costs_status；status CHECK 枚举 reserved/committed/charged/void）
- **幂等**：request_hash = SHA256(customer_id+task_id+piece_id+provider+model+provider_task_id+request_content+duration+ref_count)，UNIQUE + INSERT OR IGNORE——同一 provider task 重放不重复入账
- 成本估算（2026-08-21 实测口径）：无参考资源 1,520,000 微厘（1.52元），有参考资源 1,700,000（1.70元）；model=doubao-seedance-2-0-mini-260615；provider：ARK 直调=ark，婵镜通道=volcengine；status=charged；estimated_micro_cny == cost_micro_cny
- 容错：`_record_video_cost_safe()` 包装——记账失败写 `WARN COST_RECORD_FAILED` 审计，不丢已生成的视频 URL（防客户端重试二次付费）
- piece_id：`/execute` 为 task_id:shot:<镜号>；`/video_talk` 为 task_id

## 部署实录（2026-08-22 01:25-01:26）

- 生产旧版 MD5 `bff1c12a79ac45646181b9d0a4bdd3ef` == inputs/gz-execute-codex/execute_api.py 基线（codex 改前核对，防被别人改过）
- 部署后 MD5 `be1546ad5686f6f69c443db21bf12884`（广州 == staging/gz-execute）
- 备份：`.bak-20260821-precodex`（codex 改前）、`.bak-20260822-predeploy`（部署前）
- 重启：`kill -TERM 1787177` → systemd 自动拉起新 PID 2781205；软模式 env `HERMES_GATE_SOFT=1` 保留；1889 根路径 GET 返回 501（正常，非 GET 端点）
- 重启前 10 分钟无请求日志（journalctl --since '10 min ago'），确认无任务被打断

## 独立验收四步（部署前，不信 codex 自报）

1. `python3 -m py_compile <staging>` 
2. `diff -u <基线> <staging> | grep '^@@'` 看改动块分布 + diff 行内函数名直方图——抓改动说明没提的新函数/新分支
3. 真实逻辑测试（零付费）：importlib 加载 staging 模块直接调函数，测试库用临时路径隔离；本会话实测幂等（同参数连写两次行数仍 1）、字段、分支值全过
4. 部署前 MD5 核对生产 == 基线 → 备份 → scp → 远端验证 → 重启 → 验证
