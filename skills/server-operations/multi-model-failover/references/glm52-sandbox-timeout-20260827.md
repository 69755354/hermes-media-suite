# GLM 5.2 沙箱 300s 超时 + codex_glm_fallback.sh token 自动生成（2026-08-27 实测）

## 症状 1：GLM 超时，stdout/stderr 全空

`codex_glm_fallback.sh` 调 `glm_native_invoke.py` 执行机械类任务（wan3.0 出片），300 秒后进程被 SIGTERM 杀掉。临时文件 `/tmp/codex_glm_stdout_*.json` 和 `/tmp/codex_glm_stderr_*.log` 大小都是 0。

## 根因 1：GLM 作为 agent 浪费时间探测 API 端点

relay 日志（`journalctl | grep relay`）显示 GLM 在 300 秒内没干正事，一直在探测 API 端点像 Ollama 服务器：

```
23:34:19  POST /chat/completions → 200  (正常调了一次)
23:34:48  GET /api/v1/models → 404      ← Ollama 接口
23:34:48  GET /api/tags → 404           ← Ollama 接口
23:34:48  GET /props → 404              ← Ollama 接口
23:34:48  GET /version → 404            ← Ollama 接口
23:34:49  POST /api/show → 404          ← Ollama 接口
23:34:50  GET /models → 200             ← 终于找到对的
23:34:50-52  GET /props /version → 404  ← 还在试
23:34:59  POST /chat/completions → 200  ← 最后又调了一次
```

systemd 日志确认：`execute_code timed out after 300.01s (limit 300s) with 0 tool calls`

**关键判据：** 0 tool calls = GLM 一直在"探索"没开始干活。API 本身是通的（直接 ping 0.7s 返回 200）。

## 诊断方法（GLM 超时排查顺序）

1. 查 GZ sandbox 进程：`ssh -p 2222 ubuntu@127.0.0.1 "ps aux | grep sandbox | grep -v grep"` — 不在 = 被杀
2. 查临时文件：`ls -lt /tmp/codex_glm_*` — stdout/stderr 0 字节 = 被杀时没输出
3. **查 relay 日志**（关键证据）：`ssh -p 2222 ubuntu@127.0.0.1 "journalctl --since '5 min ago' --no-pager | grep relay"` — 大量 GET `/props`/`/version`/`/api/tags`→404 = GLM 在瞎探测
4. **测 API 本身**：直接 ping `chat/completions` 端点 — 0.7s 返回 200 = API 没挂

## 处置

- API 通 + stdout/stderr 空 + 0 tool calls = 沙箱超时，不是 API 故障
- 重试可能就过（GLM 有时正常有时抽风）
- 治本：调大沙箱超时（300s → 600s+），或任务书写死"直接执行命令，不要探测 API"
- 与 reasoning token 坑的区别：reasoning 坑是 API 返回 200 但 content 空（`finish_reason=length`）；沙箱超时是进程被杀、什么都没返回

## 症状 2：codex_glm_fallback.sh 自动生成 gate token

`codex_glm_fallback.sh`（广州机 `~/.hermes/scripts/`）自己生成 TASK_GATE_TOKEN，不需要手动设置环境变量：

1. 接收 `--type`/`--project-dir`/`--user-req`/`--out` + prompt
2. 写任务书到 `/tmp/codex_glm_brief_xxx.md`（**冒号 KV 格式**，不是等号）
3. 自己用 `uuid.uuid4().hex` 生成 token，写 JSON 到 `gate_tokens/` 目录
4. `TASK_GATE_TOKEN=$TOKEN python3 glm_native_invoke.py` 调 GLM
5. 成功输出 `OUTPUT: <路径>`，失败 exit 5（GLM_FAIL）

**脚本名叫 codex_glm_fallback 但没有 codex 回退逻辑** — GLM 挂了就 exit 5，不会自动切 codex。自动切 codex 的逻辑在上层（Hermes dispatch 或调用方判断 exit code）。

## 任务书格式要求

codex_glm_fallback.sh 写的任务书用冒号 KV 格式：
```
TASK_TYPE: 机械
USER_REQ: 执行wan3.0首尾帧出片
PROJECT_DIR: /home/ubuntu/workflow/projects/huangjin
PRELOAD_NODES: 1,2,3,4,5
DATA_SOURCE: 用户提供
```

注意：等号格式（`TASK_TYPE=xxx`）会导致 glm_native_invoke.py 的 `parse_task_book` 解析不到必填字段，rc=2。

## 症状 3：GLM-5.2 飞书 session 不外包智力活（2026-08-27 实锤）

飞书 session 收到「这个和夜店颜值版的对比」（分析类任务），GLM-5.2 没调 delegate_task、没调 codex/SSH，自己 terminal 下视频→抽帧→vision_analyze 逐帧看画面。35 次 API 调用 38 分钟没回话，上下文 11 万 token。

**根因：DELEGATE 分支在 observe 模式。** `entry_guard_policy.yaml` 中 `branch_modes.DELEGATE: observe`——guard 的 INTELLECT_WORDS（"分析"命中了）正确识别这是智力活该外包，但 observe 模式只写 audit jsonl 不拦截。GLM-5.2 作为推理模型自己判断要不要遵守 SOUL.md 的「智力活外包」软规则，它选择了不遵守。

**与症状 1 的区别：** 症状 1 是 GLM 被沙箱超时杀（执行层问题）；症状 3 是 GLM 压根没调外包（调度层问题）。两个问题叠加 = GLM 既不外包又自己干到超时。

**诊断方法：**
1. grep agent log 确认零次 delegate/codex/SSH 调用：`grep '<session_id>.*delegate\|<session_id>.*codex\|<session_id>.*ssh.*114' ~/.hermes/logs/agent.log`
2. cat guard policy 确认 DELEGATE 模式：`cat ~/.hermes/guard/entry_guard_policy.yaml | grep DELEGATE`
3. grep audit jsonl 确认 guard 识别了但放行：`grep '<session_id>' ~/.hermes/guard/entry_guard_audit.jsonl`

**修复方向：** 把 `branch_modes.DELEGATE` 从 `observe` 改为 `enforce`（需先验证 7 天误伤率，见 agent-framework-layer 踩坑 26）。

## 关键路径

- `codex_glm_fallback.sh`: `/home/ubuntu/.hermes/scripts/codex_glm_fallback.sh`（广州机）
- `glm_native_invoke.py`: `/home/ubuntu/.hermes/scripts/glm_native_invoke.py`（广州机）
- gate tokens: `/home/ubuntu/workflow/gate_tokens/`（广州机）
- 临时文件: `/tmp/codex_glm_brief_*.md`、`/tmp/codex_glm_stdout_*.json`、`/tmp/codex_glm_stderr_*.log`
- glm_native_invoke.py 的 `MAX_TOKENS` 已从 8192 改为 16384（2026-08-27）
- glm_native_invoke.py 的 `extract_content()` 已加 reasoning_content 回退
- `entry_guard_policy.yaml`: `~/.hermes/guard/entry_guard_policy.yaml` 或 `/home/ubuntu/workflow/guard/entry_guard_policy.yaml`
