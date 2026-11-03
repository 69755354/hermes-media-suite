# GLM-5.2 免费 vs 付费 vs 官方 key：经济账与坑（2026-08-24 实测）

用户问「免费glm5.2有什么问题」「他为什么要key」「需要消耗key的钱吗」后逐层理清。

## 一句话结论
GLM 官方所有 API 都要 key（注册开放平台才有），没有「免 key」入口。
- OpenRouter `glm-5.2:free` = 免你 key，吃公共池 → 429 + 256K + 排队（不烧钱包）
- 智谱官方付费 API = 自己 key + 充值烧余额（约 28元/M 输出）
- 智谱官方赠送额度 = 注册送的免费 token / free 模型，不充值可用，用光即停

## 免费版 `glm-5.2:free` 实测问题（2026-08-24，新加坡机）
1. **429 限流**：连测 3 次，第 1/3 次直接 `429 rate-limited upstream`（共享池），仅第 2 次重试通过。OpenRouter 提示「add your own provider key to accumulate rate limits」。生产用=随时卡壳。
2. **256K 阉割**：免费版上下文砍到 256K（付费完整版 1M），限速 + 高峰期排队。
3. **reasoning 吃空预算**：`max_tokens=200` → 200 全被 thinking 吃掉 → `content=None` 空回复（与 DS flash reasoning 坑同源）。

## 定价对比（OpenRouter 实测拉取 /models）
| 档位 | 输入 | 输出 | 上下文 | 备注 |
|------|------|------|--------|------|
| glm-5.2 付费 | $0.97/M | $3.04/M ≈ 22元/M | 1M | 完整无阉割 |
| glm-5.2:free | $0 | $0 | 256K | 限流+排队 |
| DS flash | 1.5-3元/M | 4.5-9元/M | 1M | 并发2500直连 |

## key 机制（OpenAI-compatible API 标准）
- key = 身份凭证，识别调用者/记账/限流/鉴权
- 无效 key → `401` / 智谱 `code:1000 身份验证失败`
- 本机 `custom_glm` provider 的 key（`34e34c...`）已失效（code:1000），付费路已断；GLM 实际只有 `glm-5.2:free` 一个可用（免费但受限）选项

## 决策建议
- 白嫖要 GLM 质量：注册智谱开放平台拿赠送额度/free 模型是正路（避开 OpenRouter 429）
- 当生产降级通道：免费档不可靠（429），需修好官方付费 key 才谈得上 1M+不排队
- codex 挂时降级顺序仍优先 `stealth/ox-alpha`（免费）再 DS，GLM free 只适合低频率零散任务
