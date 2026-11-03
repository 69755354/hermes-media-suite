# GLM 内容审核拦截 data_inspection_failed（2026-09-06 实测）

## 症状

用户看到飞书/微信持续弹出：
```
⚠️ The model provider failed after retries. I kept raw provider details out of chat; check gateway logs for diagnostics.
```

看起来像网络问题或 relay 挂了，但实际不是。

## 根因

GLM 5.2 的**内容审核**（content moderation）判定会话上下文中存在敏感内容，返回 HTTP 400 拒绝请求。

错误日志（`~/.hermes/logs/errors.log`）中的关键字段：
```json
{
  "error": {
    "code": "data_inspection_failed",
    "message": "Input text data may contain inappropriate content."
  }
}
```

- HTTP 状态码：**400**（BadRequestError）
- 错误类型：`openai.BadRequestError`
- **不可重试** — Hermes gateway 重试机制无效，因为问题不在网络/速率/余额，而在内容本身
- provider: `custom`，base_url: `http://127.0.0.1:18890/v1`，model: `glm-5.2`

## 与其他 GLM 故障的区别

| 故障类型 | HTTP | 可重试 | 根因 | 修复 |
|---|---|---|---|---|
| relay 挂了 | 无响应 | 是（重启 relay） | systemd 进程死 | `systemctl --user restart glm-aliyun-proxy.service` |
| key 失效 | 401 | 否 | API key 过期/吊销 | 换新 key |
| 余额不足 | 402 | 否 | 账户没钱 | 充值 |
| 限流 | 429 | 是（退避） | 速率超限 | 等待/降并发 |
| 推理 token 吃光 | 200 | — | max_tokens 太小 | 调大 max_tokens |
| **内容审核拦截** | **400** | **否** | **上下文含敏感内容** | **开新会话** |

## 诊断步骤

1. **查 errors.log**：`grep -i "data_inspection\|inappropriate\|BadRequest" ~/.hermes/logs/errors.log`
2. **确认 HTTP 400**：如果看到 `BadRequestError` + `data_inspection_failed` = 内容审核，不是网络问题
3. **不要重试**：400 是非可重试错误，重试只会反复触发审核，烧 token
4. **不要改 relay/key**：relay 和 key 都正常，问题在上下文内容

## 修复

**唯一有效修复：开新会话。**

- 内容审核拦截的是**当前会话上下文**（conversation history）中的某些内容
- 新会话不带被拦截的上下文，正常工作
- 旧会话无法恢复——即使清空 errors.log 也没用，因为上下文仍在 gateway 的会话管理中
- 如果需要恢复旧会话的工作进度：读 handoff 归档文件（`~/.hermes/archives/handoff_*.json`）提取关键状态

## 对用户的话术

用户看到的是 "model provider failed after retries"。解释时：
- 不暴露原始错误码/API 细节（铁律五：保密纪律）
- 用白话说："GLM 内容审核拦了之前会话的某些内容，不是网络问题，新会话正常"
- 不需要用户做任何操作——新会话自动恢复

## handoff 归档文件恢复

旧会话被审核拦截后，handoff 归档文件可能字段为空：
- 路径：`~/.hermes/archives/handoff_<session_id>.json`
- `recent_conversation`/`last_user_message`/`recent_20_messages` 等字段可能为空
- 但文件本身存在，`session_id`/`generated_at` 等元数据可用
- 如果字段为空，只能从项目目录的文件系统状态（runs/outputs/verdict.json 等）恢复工作进度

## 触发条件推测

本次拦截发生在头条产线工作会话中。可能触发审核的内容：
- 文章主题涉及裁员/年龄歧视/职场困境等社会敏感话题
- 长上下文积累后，某些片段组合触发了审核阈值
- GLM 审核标准比 DS/Claude 更严格（中国合规要求）

**注意**：这不是确定结论，是推测。不要因此规避此类话题——审核拦截是低概率事件，正常生产不受影响。