# SG 机 GLM 派活路径与踩坑（2026-08-30 实战）

> 适用：新加坡机 `~/.hermes/scripts/codex_glm_fallback.sh` + `~/.hermes/scripts/glm_native_invoke.py`
> 关联：`references/glm-gz-fallback-script-20260827.md`（广州机版本）

## 两条派活路径——不要搞混

| 路径 | 脚本 | 签 token | 需要 attest | 适用执行器 |
|:---|:---|:---|:---|:---|
| **codex_glm_fallback.sh** | 自己签 gate token | ✅ 自动签 | ❌ 不需要 | GLM |
| **hermes_task_dispatch.py** | 自己签 gate token | ✅ 自动签 | ❌ 需要 G07 codex producer attest | codex/claude/ds_native/ox_native |

**铁律：派 GLM 一律走 codex_glm_fallback.sh，别走 hermes_task_dispatch.py。**

G07 闸 `taskbook_attest.mode: BLOCK` 检查的是 codex producer attest 旁证文件（在项目 `guard/attest/` 目录下）。这个 attest 必须由 codex 以 exit_code=0 产出任务书时自动签的，Hermes 自己写的任务书没有这个 attest，走 hermes_task_dispatch.py 会被 BLOCK。codex_glm_fallback.sh 走的是完全独立的 gate token 机制，不经过 G07 attest 检查。

## API_URL 必须走本地代理

`glm_native_invoke.py` 第 367 行 `API_URL` 原写死阿里云 MaaS 公网地址：
```
https://ws-i44wcdhq2lfdnl07.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions
```

新加坡机访问国内 MaaS 网络不通（`Network is unreachable`，errno 101）。必须改为本地代理：
```python
API_URL = "http://127.0.0.1:18890/v1/chat/completions"
```

验证代理是否活着：
```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:18890/v1/chat/completions
# 401 = 代理活着，需要 key（正常）
# 000 = 代理挂了
ss -tlnp | grep 18890  # 确认进程在监听
```

## 同步模式 vs 异步模式

### 同步模式（默认）—— 推荐

codex_glm_fallback.sh 默认同步模式，等 GLM 跑完才返回。token 不会被提前清理。

```bash
cd /home/ubuntu/workflow && bash ~/.hermes/scripts/codex_glm_fallback.sh \
  --type 运维 \
  --project-dir /home/ubuntu/workflow/projects/<项目> \
  --user-req "任务描述" \
  "任务书全文（KV 格式）" 2>&1
```

同步模式可能跑 5-10 分钟（GLM 5.2 多轮工具循环），用 `terminal(background=true, notify=true)` 后台跑。

### 异步模式（--async）—— 有 bug 不要用

异步模式下脚本启动 GLM 子进程后立即返回 `ASYNC: <status_file>`，主脚本退出触发 `trap cleanup EXIT`，**清理函数会删除 gate token 文件**。但 GLM 子进程还在跑，等它去读 token 文件时已经被删了。

症状：`门禁校验失败: 门禁 token 文件不存在: /home/ubuntu/workflow/gate_tokens/<token_id>.json`

如果要用异步模式，需要修 codex_glm_fallback.sh 的 cleanup 函数：
```bash
# 改前
if [ -n "$TOKEN_FILE" ]; then
    rm -f "$TOKEN_FILE"
fi

# 改后：异步模式不删 token，让子进程用完自己清理
if [ "$ASYNC_MODE" -eq 0 ] && [ -n "$TOKEN_FILE" ]; then
    rm -f "$TOKEN_FILE"
fi
```

## 调用参数速查

```bash
bash ~/.hermes/scripts/codex_glm_fallback.sh \
  --type <运维|分析|文案|...> \
  --project-dir <项目绝对路径> \
  --user-req "用户原话" \
  "任务书全文"
```

- `--type`：白名单值，运维/环境/机械/校对/格式/摘要 不需要 DATA_SOURCE
- `--project-dir`：项目绝对路径
- `--user-req`：用户原话或任务描述
- 最后一个位置参数：任务书全文（KV 冒号格式或等号格式都行，脚本内部统一处理）
- **不需要**手动生成 token、不需要手动写 attest

## exit code 含义

| exit code | 含义 |
|:---|:---|
| 0 | 成功，stdout 打印 `OUTPUT: <路径>` |
| 2 | 参数错误 |
| 3 | 门禁校验失败（gate token 问题） |
| 4 | 任务书写入失败 |
| 5 | GLM 调用失败（API 错误、网络问题等） |
| 6 | GLM agent 执行异常 |

## GLM 达到最大轮次无产出（任务书不够指令式）

GLM 5.2 默认最大 10 轮工具循环。如果任务书写得偏「描述性」（说「改 fetch_material_for 用摘要组装 material」但没给具体行号、没说删哪些约束），GLM 会把所有轮次花在 grep/read 理解现有架构上，一轮都没改就到 max rounds，输出 `(达到最大轮次，无最终答案)`。

**解法：任务书要指令式，给死改什么：**
- 明确写「删掉第 X-Y 行的硬约束：'不用豆包 Snippet 拼凑'」
- 明确写「第 X 行改为：<具体代码>」
- 明确写「砍掉：site_selectors 检查、robots 检查、fetcher.get_text 调用」
- 不要只写方向性描述（「用摘要选题不抓全文」），要写具体操作

**看 GLM 执行日志确认它卡在哪：**
```bash
ls -lt /home/ubuntu/workflow/glm_exec_*.log | head -3
tail -80 /home/ubuntu/workflow/glm_exec_<最新>.log
# 看 Round 1-10 每轮的 tool_calls，确认它在 grep 什么
```

## 502 relay 超时：偶发 vs 连续

本地代理 18890 转发到阿里云 MaaS 偶尔超时（`HTTPError 502: relay error: The read operation timed out`）。代理本身活着（`curl` 返回 401 = 正常），key 也对（用真实 key 测试能返回内容）。

**单次 502 = 偶发**，重跑一次通常就行。

**连续两次 502 = relay 通道或 key 实际不可用**（2026-08-30 实测：relay 代理活着但到 MaaS 的转发链路断；2026-08-31 实测：relay + 广州→智谱网络都通，但 GLM key 过期，智谱返回 401 "令牌已过期"，relay 把 401 包装成 502 timeout）。**连续 502 必须先测 key 再降级**，不要直接降级（key 过期时降级 codex 也白跑，只换一个故障换一个）。诊断路径见 `references/glm-502-diagnosis-20260831.md`。降级路径：
```bash
codex exec --skip-git-repo-check -c model_reasoning_effort=high \
  "$(cat /tmp/prompt.md)" > /tmp/output.md 2>&1
```
从 gateway 内部直接 `codex exec` 裸调（codex_exec_gated.sh 从 gateway 内部调用会被 pre_tool_call guard 挡，且需要 docker 权限+gate token；hermes_task_dispatch.py 需要 G07 attest）。裸调代价：失去 kb_gate 校验+并发槽+审计，仅适合非内容生产类分析任务。

验证代理+key 端到端可用：
```bash
GLM_KEY=$(python3 -c "import yaml; cfg=yaml.safe_load(open('/home/ubuntu/.hermes/config.yaml')); print(cfg['providers']['custom_glm']['api_key'])")
curl -s -m 60 -X POST http://127.0.0.1:18890/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GLM_KEY" \
  -d '{"model":"glm-5.2","messages":[{"role":"user","content":"说一个字"}],"max_tokens":10}' 2>&1 | head -5
# 返回 choices 内容 = 代理+key 都通
```

## 排查速查

| 症状 | 原因 | 解法 |
|:---|:---|:---|
| `Network is unreachable` (errno 101) | API_URL 指向公网 MaaS，新加坡不通 | 改 API_URL 为 `http://127.0.0.1:18890/v1/chat/completions` |
| `门禁 token 文件不存在` | 异步模式 token 被提前清理 | 用同步模式，或修 cleanup 函数 |
| `G07 ATTEST_NOT_FOUND` | 走了 hermes_task_dispatch.py 派 GLM | 改用 codex_glm_fallback.sh |
| `GLM_FAIL: GLM 5.2 本地调用失败 (rc=6)` | GLM agent 执行中出错 | 看 stderr 日志 `/tmp/codex_glm_stderr_*.log` |
| `HTTPError 502: relay error: read timed out` | 代理转发 MaaS 超时。单次=偶发，连续两次=relay链路实际断 | 单次：重跑。连续两次：不重试，降级 codex exec 裸调（见上节） |
| `(达到最大轮次，无最终答案)` | 任务书不够指令式，GLM 全部轮次花在理解代码 | 任务书写具体行号+明确删/改/砍哪些代码 |
| 旧进程报 Network unreachable | 改了 API_URL 前派出去的旧进程 | kill 旧进程，重派新的 |
