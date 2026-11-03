# execute_api 软模式绕过事故 — 完整排查记录（2026-08-21）

## 事故链

1. **08-18 定案**：execute_api.py 加出片物理闸（闸0 project_dir fail-closed / 闸1 confirm_gate node12_render / 闸2 工作流 G_RENDER_READY / 闸3 余额 precheck）。08-19 14:34-14:36 硬模式实测：缺 project_dir BLOCK、出片确认未通过 BLOCK、工作流上游未获批 BLOCK——**代码闸本身完整**。
2. **08-19 14:43:48** 创建 `/etc/systemd/system/execute-api.service.d/10-gate-soft.conf`，内容 `[Service]\nEnvironment=HERMES_GATE_SOFT=1`。设计意图是灰度：「三闸软灰度（HERMES_GATE_SOFT=1），转硬拦等 CONFIRM.json」。
3. **CONFIRM.json 一直没来**（全盘 find 一个都没有），软模式一直开着。
4. **08-21 22:40** 审计日志 gate_chain_audit.log 共 32 条 SOFT_PASS，全部是 `entry=video_talk cid=ou_9b79... proj= reason=缺少 project_dir`——agent 直调 /video_talk 不传 project_dir，软模式全部放行，出片成功。**「刹车装好了、脚一直没踩下去」**。

## 关键诊断命令（按序执行）

```bash
# 1. 软模式 drop-in 是否真实存在
ls -la /etc/systemd/system/execute-api.service.d/
cat /etc/systemd/system/execute-api.service.d/10-gate-soft.conf

# 2. 服务环境变量（drop-in 生效验证）
systemctl show execute-api --property=Environment
# 或直接读进程 environ（root 才能读全量，ubuntu 只能读自己的）
cat /proc/$(pgrep -f execute_api.py | head -1)/environ | tr '\0' '\n' | grep HERMES_GATE_SOFT

# 3. SOFT_PASS 计数 + 样例
grep -c 'SOFT_PASS' /home/ubuntu/.hermes/guard/gate_chain_audit.log
grep 'SOFT_PASS' /home/ubuntu/.hermes/guard/gate_chain_audit.log | tail -5

# 4. CONFIRM.json 是否就位（决定能否转硬）
find /tmp/projects /home/ubuntu/workflow/projects -name 'CONFIRM.json'

# 5. 代码改了但服务没重启的判断：文件 mtime vs 进程启动时间
stat -c '%y %n' /opt/helper_api.py        # 08-05 停更 = 裸版本
ps -o pid,lstart,cmd -p 1029               # 08-15 启动 = 跑的就是旧文件
```

## helper_api.py（1888）裸接口审计

- do_POST 只查 `X-Auth-Token` 静态密钥（`expect = "9a52a11f..."`），**没有任何确认闸**。
- `/seedance`、`/pipeline`、`/agnes-video`、`/agnes-pipeline` 全是裸出片接口。
- **AK 明文硬编码**：`AK = "<ARK_API_KEY>"`（第 5 行，644 root 可读）——agent 读文件即得 key，直调火山 API 完全绕开本地服务。
- `/home/ubuntu/.env` 权限 664（ubuntu 组可读），凭据对 agent 全开。

## 正规流程与绕过路径的区分（关键！）

| 路径 | 入口 | 是否过三闸 | 说明 |
|:---|:---|:---|:---|
| 正规工厂出片 | ai-video-factory `/internal/v1/projects/{id}/media/execute` → `orchestrator.submit_remote_media()` → `RemoteExecutionClient.submit()` → **新加坡 POST /job** | 工厂层 C1+G_RENDER_READY+授权+结算 | **不经过广州机 execute_api 三闸** |
| agent 绕过路径 A | 直调 1889 `/execute` 或 `/video_talk` 不传 project_dir | 软模式下 SOFT_PASS 放行 | 关软模式即堵 |
| agent 绕过路径 B | 直调 1888 `/seedance` | 无确认闸（裸） | 需 1888 加闸 |
| agent 绕过路径 C | 读 .env / 硬编码 AK 直调火山 API | 任何本地闸碰不到 | 需凭据收口 |

**结论**：关软模式只堵路径 A。要完整堵死需三层：① 1888 接口确认闸（fail-closed 缺 project_dir 拒绝）→ 堵 B；② 凭据收口（.env 600 root、挖硬编码 AK、脚本走 root 代理）→ 堵 C；③ iptables 出网拦截（可选第二道，精确放行误伤风险高，建议 ①+② 先做观察）。

## 广州机无 token 层 → 跨机部署闸的适配（task_brief_gate 同步）

新加坡机有 hermes_task_dispatch.py 统一入口 + kb_gate_sg token 签发消费层；广州机无（Hermes 直调 wrapper）。适配方案：

1. 传 `task_brief_gate.py` + `gate_config.yaml` 到广州机 `/home/ubuntu/workflow/`（原样，mode: WARN）。
2. 写公共校验脚本 `scripts/gz_brief_gate_check.sh`：提取 project_dir（PROJECT_DIR= 或路径正则，兼容 /tmp/projects/）→ `printf '%s' "$PROMPT" | python3 task_brief_gate.py --brief /dev/stdin --project "${PROJ:-/nonexistent}"` → **观察期一律 exit 0 只记录**（BLOCK 也放行，防误杀），7 天后人工切 BLOCK（取消脚本内 `exit $RC` 注释）。
3. 三个 wrapper 各插一行（`|| true` 兜底防 grep 无输出）：
   - `codex_remote.sh`：PROMPT 组装后
   - `claude_remote_wrapper.sh`：依赖检查后
   - `ds_fallback.sh`：WORKDIR 校验后
4. **部署前必查三件事**（2026-08-21 实测坑）：
   - 目标机任务书是否带 `TASK_TYPE=`（task_brief_gate 缺 TASK_TYPE 或值不在 config 里 → **硬 BLOCK 不走 WARN**）；广州机历史任务书 TASK_TYPE 值只有 分析/出片，且出现过 `出片` 带反引号的笔误。
   - 广州项目在 `/tmp/projects/`（非 workflow/projects/）——find_project_dir 靠 `Path(project_arg).exists()` 绝对路径兜住。
   - 部分广州项目无 `guard/` 目录 → check_project_real 报「非真实项目」WARN——观察期可接受，切 BLOCK 前要补。
5. **部署后三用例验证**：无 TASK_TYPE 普通任务（观察期记录+放行）/ 带 TASK_TYPE 真实项目（WARN 落盘审计）/ 缺 USER_REQ（WARN 落盘）。
6. 备份：三个 wrapper 各留 `.bak-$(date +%Y%m%d)`。
