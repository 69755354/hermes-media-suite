# DS reasoning 开关与成本（2026-08-24 实测）

## 为什么关思考
DS flash/pro 默认开思考，`reasoning_content` 按输出价计费（3.5 倍价差档）。近 30 天 state.db 实测：flash 思考占输出 30.5%、pro 42.9%。主对话/机械调度关掉是纯赚。

## 正确改法（per-model overrides，防误伤 GLM）
```yaml
agent:
  reasoning_effort: medium              # 全局兜底，别改 none——会连 GLM 一起关
  reasoning_overrides:
    deepseek-v4-flash: none             # 主对话 → 关
    deepseek-v4-pro: none               # 降级智力活，默认别设（见下）
    deepseek-v4-flash-vision-exp: none
```
- `none`/`false`/`disabled` → `parse_reasoning_effort` 返回 `{"enabled": False}` → custom provider 发 `reasoning_effort="none"` + `extra_body.think=False`
- 设置：`hermes config set agent.reasoning_overrides.deepseek-v4-flash none`

## 关键坑
1. **`hermes config set` 警告「not a recognized config key」是 schema 校验误报**——值照样写进 YAML，运行时 `resolve_reasoning_config` 读原始值正常生效。别以为没改上。
2. **写文件≠生效，必须运行时验证**（一次抓「全局 none 误关 GLM」）：
   ```bash
   cd ~/.hermes/hermes-agent && python3 -c "
   import sys,yaml; sys.path.insert(0,'.')
   from hermes_constants import resolve_reasoning_config
   cfg=yaml.safe_load(open('/home/ubuntu/.hermes/config.yaml'))
   for m in ['deepseek-v4-flash','deepseek-v4-pro','glm-5.2']:
       print(m, resolve_reasoning_config(cfg, m))"
   # deepseek-*: {'enabled': False}  glm-5.2: {'enabled': True, 'effort': 'medium'}
   ```
3. **pro 不能一刀切关**（用户 2026-08-24 明确「pro不能关吧」）：`config.model.provider.model=deepseek-v4-pro` 挂着 codex 降级智力活（`codex_exec_gated.sh` 默认 `MODEL_ID=deepseek-v4-pro`，分镜/文案/分析/报告），思考是智力活核心价值。判断标准：DS 走主对话调度/机械 = 关；走降级智力活/深度分析 = 留。

## reasoning_effort 映射（DeepSeek 官方）
请求 `medium` 实际映射成 `high`（官方表：low/low、medium/high、high/high、xhigh/high、max/max）——主对话设 medium 实为 high 档，烧得更狠。想省要么 none 要么明确 low。

## 省钱测算
近 30 天 flash 3.18M + pro 0.52M thinking tokens 全按输出价烧。关掉省 flash×4.5~9元/M + 响应更快。估算下限 ¥21~43/30 天（成本回填不全时给范围+标注「下限」）。关掉后 3 天拉 `scripts/usage_ledger.py` 前后对比验证。
