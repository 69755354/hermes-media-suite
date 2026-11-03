# 模型身份实测与成本估算（2026-08-24 实锤）

> 背景：本会话一度按 attest 硬编码 `claude-sonnet-4` 下结论「我们在用 sonnet-4」，用户质疑「你确定我们用的 sonnet？」后实测翻案——**实际是 `claude-opus-5`**。本文是验证方法与成本口径。

## 实锤结论
- 本机 Bedrock wrapper 实际模型 = **`claude-opus-5`**（Claude Opus 5，2026-07-24 发布）
- 证据：① `~/.claude/debug/*.txt` 里 `model=us.anthropic.claude-opus-5` + `[API REQUEST] /model/us.anthropic.claude-opus-5/invoke-with-response-stream`；② 模拟 wrapper 认证实测自报
- **attest 硬编码 `claude-sonnet-4` 是假记录**（write_attest.sh 部署时写死的字符串）——attest 模型字段不可信

## 模型验证法（按可信度排序）
1. **实测自报（最硬，几毛钱）**：
```bash
CLAUDE_CODE_USE_BEDROCK=1 \
AWS_REGION="$(cat ~/.hermes/claude_bedrock_region 2>/dev/null || echo us-east-1)" \
AWS_BEARER_TOKEN_BEDROCK="$(cat ~/.hermes/claude_bedrock_key)" \
claude -p "只回复你当前的模型ID" --output-format text
```
2. **debug 日志（免费）**：`grep -o "model=[a-zA-Z0-9.\-]*" ~/.claude/debug/*.txt` → 看 `us.anthropic.claude-*`
3. session jsonl 通常**无** model/usage 字段（Bedrock 不落）——不要靠 jsonl 找模型
4. **不要**用 attest 字符串 / 「无配置=默认」推断（本会话即被 attest 带偏）

## 认证三件套（wrapper 等效环境）
```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-east-1
export AWS_BEARER_TOKEN_BEDROCK="$(cat ~/.hermes/claude_bedrock_key)"   # ABSK 开头原样 key
```
裸 `claude -p` 不带这三件套会报 `Not logged in`——那是没配 Bedrock 环境，不是模型问题。

## 成本估算（Opus 5 定价，多来源一致）
| 项 | 价格 |
|:--|:--|
| 输入 | $5 / 百万 token |
| 输出 | $25 / 百万 token |
| 缓存读 | $0.50 / 百万 token |
| 快速模式 | $10 / $50（本机未用） |

**估 claude 成本前先实测模型**：按 sonnet（$3/$15）估会把 Opus 5 的实际成本低估约 50%（本会话实例：两次派活实际约 60-110 元，按 sonnet 估只有 40-80 元）。

## 参考
- claude-code-ops 主文件「成本与轮数机制」节：轮数统计/固定注入/省钱抓手
- llm-api-cost-analysis 0.2 节：无 usage 记录时的估算方法
