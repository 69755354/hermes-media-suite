---
name: openrouter-ops
title: OpenRouter 模型通道接入与免费模型
description: OpenRouter 接入/免费模型/ox alpha。触发：对接GPT、免费模型、GLM免费版。
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [openrouter, models, free, ox-alpha, glm]
    related_skills: [codex-cli-ops, network-relay-ops]
---

# OpenRouter 通道与免费模型

## When to Use

- 用户问「能不能对接 GPT」「OpenRouter 怎么接」「有没有免费模型」「ox alpha 是什么」
- 需要免费备用模型通道（DeepSeek 涨价/codex 额度尽时的降级选项）
- 配置/测试 OpenRouter 上的模型（ox-alpha、glm-5.2:free 等）

## 接入事实（2026-08-24 实测）

### Key 配置

```bash
# key 存 .env（sk-or- 开头）
echo 'OPENROUTER_API_KEY=sk-or-xxx' >> ~/.hermes/.env
chmod 600 ~/.hermes/.env

# 验证 key 有效（返回 data.label / usage=0 = 有效）
curl -s https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $KEY"
```

### 模型列表查询（419 个模型，免费的一堆）

```bash
curl -s "https://openrouter.ai/api/v1/models" -H "Authorization: Bearer $KEY" | python3 -c "
import json,sys
for m in json.load(sys.stdin)['data']:
    if 'free' in m['id'].lower() or 'stealth' in m['id'].lower():
        print(m['id'], m.get('pricing',{}).get('prompt'), m.get('context_length'))
"
```

### 调用模板（chat/completions 直调）

```python
requests.post("https://openrouter.ai/api/v1/chat/completions",
  headers={"Authorization": f"Bearer {KEY}"},
  json={"model": "stealth/ox-alpha",
        "messages": [{"role":"user","content": prompt}],
        "max_tokens": 500})
```

- ⚠️ **reasoning 模型响应结构**：`choices[0].message.content` 可能为 None（reasoning_tokens 吃预算）——解析时先 `msg.get("content")` 判空，别直接下标
- **finish_reason=length** 常见：max_tokens 给不够模型想继续写（ox-alpha 输出能力强，代码任务 800 token 被截断正常）

### 配成 Hermes 别名（随时 /model 切换）

```bash
hermes config set model.aliases.ox openrouter/stealth/ox-alpha
# 或 model.aliases.glmfree openrouter/z-ai/glm-5.2:free
```

## Ox Alpha（stealth/ox-alpha）实测结论（2026-08-24）

- **匿名 stealth 模型**，OpenRouter 2026-08-20 上线，完全免费（prompt=0/completion=0），预览期随时可能变/下线
- 1M 上下文、128K 输出、文本+图片+视频输入（拒音频）
- 代码强：DeepSWE 编程题 80% 通过（超 Claude Fable 5 的 65%、GPT-5.6 Sol 的 52%）
- 实测三连：中文地道（长沙话+翻译正确）、代码规范（类型注解/docstring/保序去重）、推理准（1-50 奇数和=625）
- **短板：慢**（15-23s/次），适合深度任务，不适合日常聊天
- **归属未知**（全网猜智谱/混元/Gemini，无实锤）——stealth 模型回答「我是谁」不可信

## 免费模型清单（OpenRouter :free 档）

- `stealth/ox-alpha` — 代码/推理强，免费
- `z-ai/glm-5.2:free` — 智谱 GLM 5.2 免费版
- `google/gemma-4` 系列、`nvidia/nemotron` 系列、`cohere/north-mini-code`、`openrouter/free`（自动路由）等一堆

### ⚠️ :free 档的坑（glm-5.2 vs glm-5.2:free 对比实测）

| | 付费版 | :free 版 |
|:---|:---|:---|
| 价格 | 正常计费 | $0 |
| 上下文 | 完整（glm-5.2 = 1M） | **砍到 256K** |
| 速度 | 正常 | 限速 + 高峰期排队 |

同一模型，免费档 = 阉割版（上下文砍 1/4 + 限速）。日常短任务够用，长上下文/生产任务用付费完整版。GLM 只有 glm-5.2:free 一个免费档，其余全收费（glm-4.5-air 接近白送但非 0）。

### ⚠️ glm-5.2:free 实测补充（2026-08-24，替换 DS flash 评估）

- **429 是常态不是偶发**：连测 3 次 2 次 429（`upstream_provider_shared_pool` 共享池限流）——测试/调用必须带重试循环（2-3 次、间隔 3s），一次成功不代表通道可用
- **reasoning 模型吃 max_tokens 坑**：glm-5.2 默认思考模式，`max_tokens=200` 时 200 全被 `reasoning_tokens` 吃掉 → `content=None` + `finish_reason=length`（空回复）。**测试/调用必须给足 max_tokens（≥800）**，解析先判 `msg.get("content")` 空
- **替换主对话结论（实测对比）**：GLM 5.2 付费版 prompt $0.97/M / completion $3.04/M（OpenRouter per-token 价格 ×1M 换算）≈ 输出 22 元/M，是 DS flash（输出 4.5-9 元/M，峰谷）约 3 倍；免费档 256K + 限速 + 429 → **不能当生产主对话**。适用仅限：codex 挂掉的降级备选、单次高质量创作任务。主对话维持 DS flash 不动

**GLM key 经济账（为什么 GLM 要 key / 免费不免费，2026-08-24 用户澄清）**：官方所有 API 都要 key（注册开放平台，无免key入口），免费的是 OpenRouter 中转（免你 key 但吃公共池 429）；官方赠送额度用光即停、不充值扣不了钱。完整对比见 `references/glm-key-economics-20260824.md`。

## 网络注意（新加坡机实测）

- 新加坡机直连 openrouter.ai：0.07-0.14s，通
- 广州机直连：1.3-1.8s，通但会波动（国内到国外线路时通时断）
- 走新加坡 SOCKS 出口反而慢（多一跳 8.5s）——就近原则：广州机能直连就直连，别绕新加坡

## 关联

- **阿里云百炼 MaaS 部署 GLM 接入**（不是智谱！`sk-ws-` key + `maas.aliyuncs.com` 网关）：完整流程、hermes config set 写法、新加坡直连被挡走广州 relay、MaaS 网关查不了余额 —— 见 `references/aliyun-maas-glm-20260824.md`
- codex-cli-ops（codex 通道/额度降级）：codex 额度尽时除了 DS FLASH 顶班，Ox Alpha 是免费新选项
- hermes-agent references/providers-and-models.md（Hermes 内置 provider 表）
