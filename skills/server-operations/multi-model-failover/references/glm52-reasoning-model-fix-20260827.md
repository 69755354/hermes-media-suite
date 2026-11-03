# GLM 5.2 推理模型 token 坑与修复（2026-08-27 实测）

## 症状

`glm_native_invoke.py` 调 GLM 5.2（阿里云百炼 MaaS）执行分析任务，API 返回 200 但 `content` 字段为空字符串，`finish_reason=length`，最终落盘 0 字节文件，脚本 exit 5。

## 根因

GLM 5.2 是**推理模型**（和 DS V4 flash/pro 一样），每次调用先在 `reasoning_content` 里做思考，再在 `content` 里输出正文。两个问题叠加：

1. **`max_tokens=8192` 太小**：推理 token + 输出 token 共用额度。任务书 5700 字，推理可能要几千 token，8192 不够推理 + 输出，`finish_reason=length` 直接截断。
2. **`extract_content()` 只读 `msg["content"]`**：如果模型在推理阶段 token 耗尽、`content` 是空的，脚本拿到空字符串，判定"最终答案为空"，直接 exit 5。

API 响应体结构：
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "reasoning_content": "1. **分析请求：**\n    *",  // 推理内容在这
      "content": ""                                          // 正文为空
    },
    "finish_reason": "length"
  }],
  "usage": {
    "completion_tokens": 11,
    "completion_tokens_details": {"reasoning_tokens": 10}
  }
}
```

## 修复（已部署到广州机 glm_native_invoke.py）

### 修改 1：max_tokens 8192 → 16384

```python
# call_glm_api() 函数内
"max_tokens": 16384,  # 原 8192
```

### 修改 2：extract_content() 增加 reasoning_content 回退

```python
def extract_content(resp: dict) -> str:
    """从响应中提取文本内容（GLM 5.2 是推理模型，content 为空时回退到 reasoning_content）"""
    choices = resp.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    if content:
        return content
    # GLM 5.2 推理模型：content 为空时，reasoning_content 可能含分析结果
    reasoning = msg.get("reasoning_content") or ""
    return reasoning
```

## 验证结果

修复后用同样的 5700 字任务书（对比修正报告分析），GLM 5.2 **2 轮就出活**：
- Round 1：推理 + `write_file` 写报告（11688 字符）到项目目录
- Round 2：确认完成，返回摘要

## 任务书优化：预塞数据省轮次

之前让 GLM 自己 `read_file` 读 4 份文件 + 10 个维度分析，25 轮不够用。改为**把所有必要数据直接塞任务书里**，GLM 不用读文件直接干分析 + 写报告，2 轮就够。

任务书结构：
```
TASK_TYPE: 分析
PROJECT_DIR: <项目目录>
OUTPUT: <输出路径>
USER_REQ: <任务描述+全部数据内嵌+对比维度+报告格式要求>
```

## SSH heredoc 变量不展开的坑

通过 `ssh ... "TOKEN=$(...) cat <<EOF ...${TOKEN}... EOF"` 生成 gate token 时，heredoc 里的 `${TOKEN}` 不展开，导致 token 文件名和环境变量不一致。

**正确做法**：用 `python3 -c` 生成 token 文件，避免 shell heredoc 变量展开问题：

```bash
ssh -p 2222 ubuntu@127.0.0.1 'python3 -c "
import uuid, json, time, os, hashlib
brief_path = \"/tmp/brief.md\"
sha = hashlib.sha256(open(brief_path,\"rb\").read()).hexdigest()
token = uuid.uuid4().hex
os.makedirs(\"/home/ubuntu/workflow/gate_tokens\", exist_ok=True)
with open(f\"/home/ubuntu/workflow/gate_tokens/{token}.json\", \"w\") as f:
    json.dump({\"token_id\": token, \"brief_sha256\": sha, \"issued_at\": int(time.time()), \"expires_at\": int(time.time())+600, \"used\": False}, f)
os.chmod(f\"/home/ubuntu/workflow/gate_tokens/{token}.json\", 0o600)
print(token)
"'
```

## 与 DS V4 推理 token 坑的对比

| 维度 | DS V4 flash/pro | GLM 5.2 |
|---|---|---|
| 推理字段 | `reasoning_content` | `reasoning_content` |
| 默认开推理 | 是 | 是 |
| content 为空 | reasoning 吃光 max_tokens | 同 |
| 修复方向 | max_tokens≥30000 + thinking:False | max_tokens 16384 + content→reasoning 回退 |
| 推理可关 | `chat_template_kwargs: {'thinking': False}`（未完全关） | **不可关**（见下方 0827 实测） |

## GLM 5.2 思考不可关闭（2026-08-27 实测）

通过本机 relay（`127.0.0.1:18890`）直接发 API 请求测试 `enable_thinking` 参数：

```bash
curl -s -X POST http://127.0.0.1:18890/v1/chat/completions \
  -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"glm-5.2","messages":[{"role":"user","content":"1+1=?"}],"max_tokens":100,"enable_thinking":true}'
```

**结果：**
- `content`: "1 + 1 = 2"（最终回答）
- `reasoning_content`: 完整推理过程（4 步分析）
- `usage`: prompt=16, completion=93, **reasoning_tokens=84**

一个 `1+1=?` 就烧了 84 个 reasoning token。传或不传 `enable_thinking`，GLM 5.2 都会思考——**思考是默认开启且不可关闭的**。

**与 DS V4 的关键区别：** DS V4 可以通过 `chat_template_kwargs: {'thinking': False}` 部分抑制推理（reasoning_tokens 仍存在但大幅减少）；GLM 5.2 没有等效参数，思考是模型固有行为。

**成本影响：** 每次 GLM 5.2 API 调用都在为思考付 token。广州 GLM 壳的 `extract_content()` 在 `content` 非空时直接返回，`reasoning_content` 被丢弃——思考结果没被利用但 token 已付费。

**利用思考内容的潜在改进方向（未落地）：**
- 修改 `extract_content()` 在 `content` 非空时也保留 `reasoning_content`（拼在 content 后面或独立字段返回）
- 让 GLM 壳的 system prompt 引导模型把思考结论写进 `content`（减少 reasoning 浪费）
- 主会话（Hermes gateway）侧：GLM 5.2 返回的 `reasoning_content` 已通过 relay 透传给 gateway，但 gateway 是否利用了 reasoning 取决于 Hermes 内部逻辑

**本机 relay 架构：** `glm_aliyun_proxy.py` 是纯透传代理（body 原封不动转发），不修改任何参数。Hermes config 里配什么参数就传什么。relay 的 `_log_usage()` 已记录 `reasoning_tokens` 字段用于对账。

## 注意

- `glm_native_invoke.py` 在广州机 `~/.hermes/scripts/` 下，是用户创建的脚本，不是 curator 管理的
- `glm-gz-shell` skill 是 user-owned，不能自动 patch，需用户手动更新
- 修改已备份原文件（`.bak.<timestamp>`）
- `glm-gz-shell` SKILL.md 里写的 `max_tokens: 8192` 已过期，实际代码已改为 16384
