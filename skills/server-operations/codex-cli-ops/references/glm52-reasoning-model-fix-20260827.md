# GLM 5.2 推理模型空输出修复（2026-08-27 实战）

> 适用：广州机 `glm_native_invoke.py`（GLM 5.2 执行壳）
> 同类问题：DS V4 也有完全相同的 reasoning_content 吃光 max_tokens 问题，见 SKILL.md 排查表 `finish_reason: length + content 为空` 条目

## 症状

GLM 跑完返回空 content，exit code=5（输出文件不存在或为空），日志显示"响应 content 摘要: (空)"。API 本身通（key 有效、HTTP 200），但 `finish_reason=length`。

## 根因

GLM 5.2 是推理模型（reasoning model），每次调用先在 `reasoning_content` 字段里做思考，然后才输出 `content`。

1. **max_tokens 太小**：`max_tokens=8192` 时推理 token + 输出 token 共享额度，长任务书（>3000 字）推理就吃光额度，`content` 返回空
2. **脚本只读 content**：`extract_content()` 只读 `msg["content"]`，不读 `msg["reasoning_content"]`——如果模型把分析写在推理里、content 是空的，脚本拿到空字符串

## 修复（已部署到广州机 glm_native_invoke.py 2026-08-27）

### 修复1：max_tokens 8192 → 16384

```python
# call_glm_api() 函数内
"max_tokens": 16384,  # 原 8192
```

### 修复2：extract_content 增加 reasoning_content fallback

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

## 验证方法

```python
# 直接测试 API 返回结构
import urllib.request, json
data = json.dumps({
    "model": "glm-5.2",
    "messages": [{"role": "user", "content": "说一个字"}],
    "max_tokens": 50
}).encode()
# 看返回 JSON：如果 finish_reason=length 且 content="" 但 reasoning_content 有内容
# = max_tokens 不够（推理吃光额度）
```

## 通用教训

推理模型（reasoning model）的 `reasoning_content` / `reasoning_tokens` 会吃 `max_tokens` 预算。已知有此行为的模型：
- **GLM 5.2**（阿里云百炼）— reasoning_content 字段，max_tokens 需要 ≥16384
- **DeepSeek V4**（api.deepseek.com）— reasoning_content 字段，max_tokens 需要 ≥30000
- 诊断特征：`finish_reason=length` + `content=""` + `usage.completion_tokens_details.reasoning_tokens ≈ max_tokens`
