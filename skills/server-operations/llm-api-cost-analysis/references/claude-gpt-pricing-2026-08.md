# Claude/GPT 模型价格表（2026-08-24 实查）

> 用途：估算 claude/codex 直调成本时查价。**先实测模型再选价格行**——attest 硬编码不可信，本机实测是 `claude-opus-5`（见 claude-code-ops references/model-identity-verification.md 的验证法）。

## Claude 家族（Anthropic 官方/多来源一致）
| 模型 | 发布时间 | 输入 $/M | 输出 $/M | 缓存读 $/M | 备注 |
|:--|:--|--:|--:|--:|:--|
| **Opus 5** | 2026-07-24 | 5 | 25 | 0.50 | 本机 Bedrock 实测模型；快速模式 $10/$50 |
| Fable 5 | 2026 新旗舰 | 旗舰价 | 旗舰价 | — | 综合智能 ~60（第1），SWE-Bench Pro 80% |
| Sonnet 5 | 2026-06-30 | 低于 4.6 | 低于 4.6 | — | 中位主力，比 Opus 便宜 40-60% |
| Sonnet 4.6 | 2026-02-17 | 3 | 15 | — | SWE-bench 79.6% |
| Sonnet 4 | 2025-05 | 3 | 15 | — | **2026-06-15 已在 Claude API 退役** |

## GPT-5.6 家族（2026-07-09 发布，三档）
| 档位 | 定位 | 智能指数 | Coding Index | 价格 |
|:--|:--|--:|--:|:--|
| Sol | 旗舰 | ~59（第2） | 77.4（第1） | $5 / $30 |
| Terra | 日常均衡 | ~55 | 76.7 | 约为 Sol 一半 |
| Luna | 快省 | ~51 | — | 最便宜 |

## 估算提醒
- 估 claude 成本先实测模型（`CLAUDE_CODE_USE_BEDROCK=1` + `AWS_BEARER_TOKEN_BEDROCK` + `claude -p "只回复你当前的模型ID"`）
- 按 sonnet（$3/$15）估 Opus 5 实际成本会低估约 50%（2026-08-24 实测：两次派活实际 60-110 元，按 sonnet 只估出 40-80 元）
