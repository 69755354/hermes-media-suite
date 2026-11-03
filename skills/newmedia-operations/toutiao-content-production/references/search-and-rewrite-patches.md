### 豆包搜索 Global→Custom 版切换 + hotlist 用摘要选题（2026-08-30 定案）

**问题链**：豆包搜索 Global 版（`global_search`）免费额度 500 次/月耗尽 → 报 10406。用户账号已开 Custom 版（`web_search`）按量后付费，余额通用。但代码里 endpoint 和请求/响应格式都是 Global 版的。

**改动**：
1. **config.yaml**：endpoint 从 `search_api/global_search` 改为 `search_api/web_search`
2. **modules/search.py**：请求体改为 `{"Query": query, "SearchType": "web", "Count": N, "Filter": {"NeedUrl": True}}`；响应解析从 `Result.Documents` 改为 `Result.WebResults`；返回值增加 `snippet/summary/site_name/publish_time` 字段
3. **hotlist.py `fetch_material_for()`**：砍掉抓网页流程（site_selectors/robots/fetcher.get_text/extract_body），改为直接用 web_search 返回的 `Summary`（优先）或 `Snippet` 作为 `raw_text` 组装 material.json。不达标（< min_body_chars）跳到下一个 doc
4. **hotlist.py 硬约束更新**：删除「不用豆包 Snippet 拼凑」「取不到正文不产 material」旧约束（那是 Global 版时期写的，Custom 版返回的 Summary 是真实报道摘要）

**用户定方向**：「搜索热点就是选题，你要把全文搞过来干嘛？」——不需要抓全文，用搜索返回的摘要组装 material 就够了，LLM 自己会写文章。

### hotlist 资格门容错修复（2026-08-30 codex 实施）
hotlist.py 资格门曾因热榜 API 返回字段缺失（age_hours/author_followers/article_reads 不在热榜数据里）全拦 50 条。修复：资格门对热榜 API 不返回的字段做容错（缺失告警不拦，已有且不达标的仍拦），50 条→38 条 eligible。`--dry-run` 能选出至少 1 条选题，rc=0。

### 回炉稿跳过去味环节 bug（2026-08-30 实测发现，已派 codex 修复）

**问题**：格式门回炉重写后，`[④⑤拟人化]` 环节被跳过——日志明确输出「回炉稿不再过拟人化/去味改写，直接进⑥标题→⑥.5配图→⑦检测」。导致：
1. 回炉重写的稿子完全没去过 AI 味
2. 多轮回炉叠加，AI 味可能越来越高（r1=7.98 → r2=8.14）
3. 格式门3轮回炉都是同一个问题（加粗段不够），说明重写时没有针对格式门失败原因做定向修复

**根因**：产线设计是先拟人化去味→再检测。但如果格式门没过要回炉重写，重写后的稿子直接跳过去味环节拿去检测。DS 因 AI 味本身就偏高，跳过去味后接近或超过阈值；GLM 因 AI 味本身很低（3.45），即使跳过也不会超阈，所以没暴露这个问题。

**修复方向（已派 codex）**：① 回炉稿重新过拟人化→去AI味→标题→配图→检测（不回大纲）；② 格式回炉 prompt 应明确告知「上一稿加粗 X/N 段，要求 ≥70% 段有加粗，请在每段开头加粗关键词」；③ 兜底加粗逻辑提前触发，减少无意义回炉轮次。

### 去AI味相似度死锁 + 格式回炉路径去味阻断修复（2026-08-30）

**三连发 bug，根因全在 ⑤去味 逻辑和 pipeline 对去味失败的处置：**

1. **deai_rule_card 相似度死锁（humanize.py）**：GLM AI味=0.0（已干净），候选通过全部质量门（accepted=True），但相似度 0.99>0.9 且 score_after>=score_before → needs_fallback=True → effective=False。分数已0.0不可能再降，旧逻辑死锁。**修复**：needs_fallback 增加 `AND score_after > ai_score_max` 条件——分数已低于阈值时不因高相似度触发 fallback。修复位置 L314-316 + L337-338。
2. **格式回炉路径去味失败丢弃加粗修复（pipeline.py）**：bold 兜底成功补到 14/19（过线），format_rehumanize_context 被设 → continue → ④⑤重跑 → ⑤失败 → 立即 return rc=3，加粗修复被丢弃。**修复**：格式回炉路径下 ⑤失败时不退出，保留格式修复文本+补加粗，继续走⑥→⑦。
3. **普通路径去味失败阻断全链（pipeline.py）**：r1 ⑤候选因三段式回归被拒（accepted=False），effective=False → 立即 return rc=3，⑥/⑥.5/⑦ 全没跑。但 AI味=3.18 远低于阈值 8.4。**修复**：普通路径 ⑤失败时检查去味前 v1 文本 AI味，已≤阈值则跳过去味用 v1 继续。只有 AI味仍超阈值才 rc=3。

**验证**：离线 112 项断言全过 + 真实数据重放（旧 effective=False → 新 True）+ 实跑 verdict=PASS（AI味6.92/原创97.23%/编造0/格式PASS/配图3/3）。详见 `references/deai-similarity-deadlock-fix-20260830.md`。

**三条教训**：① 相似度判据不能独立于分数上下文，分数已达标时高相似度是合理不是失败；② 去味失败≠文章不合格，pipeline 应检查去味前是否已达标；③ 格式回炉路径的⑤去味对低AI味模型必然失败，必须做特殊处理。

### GLM 通道接入产线（2026-08-30 codex 实施）
config.yaml 新增 GLM 通道配置：`provider: glm` / `model: glm-5.2` / `base_url` 走本地代理 / `key_env: GLM_API_KEY` / `key_ref: ~/.hermes/config/glm.key`。llm.py 按 alias 路由 DS/GLM。pipeline.py `--model glm` 可用。DS 通道保留可切换。

**⚠️ GLM key 配置坑**：codex 写的 base_url 是 `https://open.bigmodel.cn/api/paas/v4/chat/completions`（智谱直连），但 Hermes 的 GLM key 是走本地代理 18890 的，直连会 401。必须改成 `http://127.0.0.1:18890/v1/chat/completions`。GLM key 写到 `~/.hermes/config/glm.key`（从 Hermes config `providers.custom_glm.api_key` 提取）。

**⚠️ DS key 配置坑**：产线 `config.yaml` 里 DS 通道的 `hermes_key_path: model.api_key` 指向 Hermes config 的 `model.api_key`——这是 GLM 的 key 不是 DS 的。DS key 在 Hermes config 的 `providers.custom_custom.api_key`，需提取写到 `~/.hermes/config/deepseek.key`，并通过环境变量 `DEEPSEEK_API_KEY` 传入（`DEEPSEEK_API_KEY=$(cat ~/.hermes/config/deepseek.key) python3 pipeline.py ... --model pro`）。不设环境变量会 401（用了 GLM key 去调 DS API）。

