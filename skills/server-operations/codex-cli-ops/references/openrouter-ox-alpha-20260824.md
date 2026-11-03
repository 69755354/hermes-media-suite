# OpenRouter 接入 + Ox Alpha 实测（2026-08-24）

## OpenRouter key 配置

- key 存在 `~/.hermes/.env` 的 `OPENROUTER_API_KEY=`（sk-or-v1- 开头，剥 export 前缀）
- 验证 key：`curl https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer <key>"` → 返回 data.limit_remaining / is_free_tier
- 免费注册：openrouter.ai（国内访问不稳需代理/跳板），GitHub OAuth 绕过邮箱风控
- 可用模型数：419（2026-08-24 实测）

## Ox Alpha 实测参数（stealth/ox-alpha）

- 规格：1M 上下文 / 128K 最大输出 / 文本+图片+视频输入 / 文本输出
- 价格：$0/$0（预览期免费）
- 速度：中文任务 17.6s / 465 tokens；代码任务 23.0s / 908 tokens；推理 2.7s / 146 tokens
- 能力：DeepSWE 80%（社区 10 任务实测）> Claude Fable 5 65% > GLM-5.3/Grok 4.6 62% > GPT-5.6 Sol 52%
- 中文：长沙话地道（「你硬是蛮扎实嘞，灵泛得很咧！」+ 普通话翻译 + 释义）
- 代码：类型注解/docstring/保序去重，质量高；max_tokens 给足（800 不够会被 length 截断）
- 推理：1-50 奇数和 = 625 正确
- 注意：finish_reason=length 时 content 解析要处理（首次测试 choices[0] 可能 None，需检查 status/重试）

## 裸调 API 模板（ox_native_invoke.py 用的）

```bash
curl https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer <key>" -H "Content-Type: application/json" \
  -d '{"model":"stealth/ox-alpha","messages":[{"role":"user","content":"..."}],"max_tokens":30000}'
```

## GLM free vs 付费区别

| | glm-5.2 | glm-5.2:free |
|---|---|---|
| 价格 | prompt $0.000000966 / completion $0.000003 | $0 |
| 上下文 | 1M (1048576) | 256K (256000) |

同一模型，免费版阉割上下文到 1/4 + 限速排队。日常短任务够用，长文档/生产走付费完整版。

## 用户 Mac 经广州跳板访问国外网站（简短版）

完整见 codex-cli-ops SKILL.md「Mac 经广州跳板代理」reference（2026-08-24）。
- Mac 不能直连新加坡（22 不通），广州能直连新加坡 + OpenRouter
- 广州到 OpenRouter 1.3-1.76s（波动），新加坡 0.07s（稳但 Mac 连不上）
- 最简稳定路径：Mac `ssh -N -D 1081 ubuntu@<GZ_HOST>`（出口广州，OpenRouter 能开）
- 需要新加坡出口：`ssh -N -D 1081 -J ubuntu@<GZ_HOST> ubuntu@<SG_HOST>`
- 端口固定 1081 不换；Address already in use = 旧隧道没停干净
- 用户 Mac 公钥已授权广州机 + 新加坡机（2026-08-24）
