# 去AI味相似度死锁 + 格式回炉路径去味阻断修复（2026-08-30）

## 问题链

三连发 bug，根因全在 ⑤去味 的 needs_fallback 逻辑和 pipeline 对去味失败的处置。

### Bug 1: deai_rule_card 相似度死锁（humanize.py）

**现象**：GLM AI味=0.0（已经干净），deai 候选通过全部质量门（accepted=True），但相似度 0.99>0.9 且 score_after>=score_before → needs_fallback=True → effective=False。

**根因**：`needs_fallback = (not accepted) OR (sim > threshold AND score_after >= score_before)`。当分数已0.0不可能再降，但旧逻辑仍因高相似度触发 fallback，fallback 也无法改善 → effective=False → pipeline rc=3。

**修复**：needs_fallback 增加 `AND score_after > ai_score_max` 条件——分数已低于阈值时，高相似度只说明原文已够好，不应触发 fallback。

```python
# 旧逻辑（死锁）
needs_fallback = (not audit["accepted"]
                  or (sim > similarity_threshold
                      and audit["score_after"] >= audit["score_before"]))

# 新逻辑（修复）
needs_fallback = (not audit["accepted"]
                  or (sim > similarity_threshold
                      and audit["score_after"] >= audit["score_before"]
                      and audit["score_after"] > ai_score_max))
```

修复位置：humanize.py L314-316（主候选）+ L337-338（fallback 候选循环内）

### Bug 2: 格式回炉路径去味失败丢弃加粗修复（pipeline.py）

**现象**：bold_per_para_fallback 成功补到 14/19（73.7%>=70%），format_rehumanize_context 被设置 → continue 回到循环顶部 → ④⑤重跑 → ⑤去味失败 → pipeline 直接 return rc=3，加粗修复被丢弃。

**根因**：format_rehumanize 路径强制重走 ④⑤，但 ⑤去味 对 GLM（AI味已达标）无法产生 effective=True 的候选 → pipeline L646-657 立即 return rc=3。

**修复**：格式回炉路径下 ⑤去味 失败时不立即退出，保留格式修复后的文本（humanize_input_text），补一次 bold_per_para_fallback，继续走⑥→⑦。

### Bug 3: 普通路径去味失败阻断全链（pipeline.py）

**现象**：r1 第一轮 ⑤去味 候选因三段式回归（3→5）被拒（accepted=False），effective=False → pipeline 立即 return rc=3，⑥标题/⑥.5配图/⑦检测 全没跑。

**根因**：pipeline 对 ⑤去味 失败的唯一处置是 return rc=3，不管 AI味是否已达标。GLM AI味=3.18 远低于阈值 8.4，去味失败不应阻断整条链。

**修复**：普通路径 ⑤去味 失败时，检查去味前（v1）文本的 AI味。若已≤阈值，跳过去味用 v1 文本继续走⑥→⑦。只有 AI味仍超阈值才走人工复核。

```python
# 修复后逻辑
if not human_v2["effective"]:
    if format_rehumanize_context:
        # 格式回炉路径：保留格式修复文本，跳过去味
        article_text = humanize_input_text
        bold_fixed, post_bold = bold_per_para_fallback(article_text)
        # ...继续走⑥→⑦
    else:
        # 普通路径：检查 AI味是否已达标
        pre_deai_score, _ = detect_mod.ai_score(human_v1["text"])
        if pre_deai_score <= ai_score_max:
            article_text = human_v1["text"]
            # ...继续走⑥→⑦
        else:
            # AI味仍超阈值 → 人工复核
            return 3
```

## 验证

- 离线测试：4 套测试全过（test_rewrite_loop 54项 / test_deai_quality_gate 26项 / test_ai_score_density 11项 / test_fabrication 21项 = 112项 0失败）
- 真实数据重放：用 humanized_v2_r3.json 实际数据验证，旧逻辑 effective=False → 新逻辑 effective=True
- 实跑验证：daily_auto.sh glm 完整链跑通，verdict=PASS（AI味6.92/原创97.23%/编造0/格式PASS/配图3/3）

## 教训

1. **相似度判据不能独立于分数上下文**：高相似度+分数未改善 在分数已达标时是合理行为（原文已够好），不是失败。相似度 fallback 应加 `score > threshold` 前置条件。
2. **去味失败不等于文章不合格**：当 AI味已低于阈值，去味只是锦上添花。pipeline 应检查去味前文本是否已达标，而非一律 rc=3。
3. **格式回炉路径的 ⑤去味 是高风险节点**：格式回炉强制重走 ④⑤，但 ⑤ 对低 AI味模型（GLM）必然失败 → 丢失格式修复。必须对格式回炉路径做特殊处理。
