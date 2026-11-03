# DeepSeek 思考模式（reasoning_effort）控制链路 — 2026-08-24 源码+官方文档实测

## 症状
用户问「主会话不需要开思考模式吧」→ 查证确认：主对话一直开着思考模式，每轮烧 reasoning tokens（成本大头），而主会话（调度/传话/机械操作/质检）用不上深度思考。

## 完整链路（改配置前先理解）
1. config.yaml `agent.reasoning_effort: medium`（当前值）→ `hermes_constants.py:parse_reasoning_effort()` → `{"enabled": True, "effort": "medium"}`
2. → DeepSeek provider（`plugins/model-providers/deepseek/__init__.py`）→ `extra_body.thinking.type="enabled"` + 顶层 `reasoning_effort=medium`
3. **⚠️ DeepSeek 官方映射表：`medium` 会映射成 `high`** —— 等于拿 high 档思考强度跑主对话
4. **思考模式不支持 temperature/top_p/presence_penalty/frequency_penalty**（官方文档确认，设了不报错但不生效）

## 真正关掉

### ⚠️ 先分清两种改法（2026-08-24 实测踩坑）

**❌ 全局改会误伤非 DS 模型：** `hermes config set agent.reasoning_effort none` 设的是**全局兜底**，`resolve_reasoning_config()` 对**任何**模型都返回 `{"enabled": False}`——实测 glm-5.2（custom_glm）也被关思考。custom provider 对所有 custom 端点发 `think=False` + `reasoning_effort="none"`，GLM 是 codex 挂掉时的备选，不该被误伤。

**✅ 精准改法：per-model overrides（2026-08-24 已落地）**
```yaml
agent:
  reasoning_effort: medium                 # 全局兜底保持原状，防误伤其他模型
  reasoning_overrides:
    deepseek-v4-flash: none                # 主对话模型 → 关思考
    deepseek-v4-pro: none                  # 深度分析模型 → 关思考
    deepseek-v4-flash-vision-exp: none     # 看图模型 → 关思考
```
写入命令（`hermes config set` 能存 dict key，虽提示 not recognized 但照常写入）：
```bash
hermes config set agent.reasoning_effort medium                                # 先恢复全局（若已误设 none）
hermes config set agent.reasoning_overrides.deepseek-v4-flash none
hermes config set agent.reasoning_overrides.deepseek-v4-pro none
hermes config set agent.reasoning_overrides.deepseek-v4-flash-vision-exp none
```

### ✅ 运行时验证（别只看 config 文本，跑真实解析函数）
```bash
cd ~/.hermes/hermes-agent && python3 -c "
import sys, yaml
sys.path.insert(0, '.')
from hermes_constants import resolve_reasoning_config
cfg = yaml.safe_load(open('/home/ubuntu/.hermes/config.yaml'))
for m in ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-v4-flash-vision-exp', 'glm-5.2']:
    print(m, resolve_reasoning_config(cfg, m))
"
# 期望：DS 全系 {'enabled': False}；glm-5.2 {'enabled': True, 'effort': 'medium'}
```
- 生效需 `/new` 或重启 gateway（agent 段配置）
- 影响：所有走主对话的会话（微信/飞书/CLI/cron）；**不影响** codex/claude 独立执行器
- 别关场景：策略分析/深度推理类任务；主对话偶尔需要思考可用 `/reasoning` 临时开

### 解析优先级（hermes_constants.py:1099 `resolve_reasoning_config` 源码确认）
1. `agent.reasoning_overrides.<model>`（spelling-tolerant，per-model）→ 命中即返回
2. 全局 `agent.reasoning_effort`（原始值直传，YAML 布尔 false 不会被 `or ""` 吞掉）
3. 都空 → None → provider 默认（DeepSeek 服务端默认思考开 + high）

## 验证命令
```bash
cd ~/.hermes/hermes-agent && venv/bin/python -m hermes_cli.main config get agent.reasoning_effort
grep -n "reasoning_effort" ~/.hermes/config.yaml
```

## DeepSeek 官方定价页（api-docs.deepseek.com/zh-cn/quick_start/pricing，2026-08-24 实测）
- DS flash：输入 1.5/3.0 元/M（空闲/高峰，缓存未命中），输出 4.5/9.0 元/M，上下文 1M、输出最大 384K、并发 2500
- DS pro：输入 4.5/9.0，输出 13.5/27.0
- 对比 glm-5.2 付费（OpenRouter）：输出 $3.04/M ≈ 22 元/M，**GLM 输出贵约 3 倍**

## 上下文「实际能用多少」
Hermes 主会话受 `compression.threshold: 0.12` 限制（config.yaml 实测）——到模型窗口 12%（≈12 万 token）就压缩归档，**永远不会真塞满 1M**。这是防爆上下文+省钱的设计，不是模型虚标。
