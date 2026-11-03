---
name: codex-image-vision
description: codex生图与看图操作。触发:codex生图/image_generation/比基尼被拦/看图/vision超时。
---

# codex 图像能力（生图 + 看图）2026-08-09 实测

## 生图（image_generation 工具，gpt-image-2）

### 调用
```bash
echo "<prompt>" | codex exec --skip-git-repo-check -c model_reasoning_effort=high \
  -c sandbox_mode=danger-full-access -C /home/ubuntu/workflow \
  -i <参考图可选> 2>&1 | tail -20
```
- prompt 里要求：尺寸（如 2160x3840）、输出路径（assets/xxx.png）、OUTPUT 协议、失败 BLOCKED
- codex 会自动 cp 生成图到目标路径（~/.codex/generated_images/ → 目标）
- 尺寸：在 prompt 文本里写尺寸要求（如 "Landscape 16:9 composition, save to /tmp/xxx.png"）；codex 默认出图约 1672x941
- 参考图垫图：`-i /path/ref.jpg` 锁脸（图生图模式）

### ⚠️ `--quality` 和 `--size` 不是 codex exec 的 CLI 参数（2026-09-05 实测）

`codex exec` 没有 `--quality` 和 `--size` 命令行参数。传 `--quality high --size 1920x1080` 会报 `error: unexpected argument '--quality' found`。这些参数必须写在 prompt 文本里（如 "Generate a high-quality image, 16:9 landscape composition, save to /tmp/xxx.png"），codex 会理解并在内部调用 image_generation 工具时带上参数。生图完成后 codex 会自动 cp 到 prompt 里指定的路径。

### ⚠️ 安全墙（OpenAI 比火山严很多）
- 比基尼 → sexual 拦截（input moderation）；换「泳衣」也拦（output moderation）
- 仅「高领全覆盖连体泳装」能过——泳装/贴身场景优先 Seedream
- 报错特征：`image generation failed: http 400 Bad Request ... safety_violations=[sexual] ... moderation_blocked`

### ⚠️ 质量争议（用户 2026-08-09 实测后最终定案）
- codex 出图：精修感重、摆拍感强、动态僵硬（用户原话「扭成机器人」「图很假」）——但**锁参考图脸准**
- Seedream：真实感强（胶片/抓拍感/动态自然）但锁脸弱（五官飘）
- **最终定案：codex 首选**（用户「先把codex升级成首选」），quality=high 必带；Seedream 仅简单真实感场景备选
- 复杂场景（仙侠/特效）：Seedream 会把角色画跑偏（实测画成男性），codex 稳

## 看图（vision_analyze 超时替代）

`vision_analyze`（豆包通道）在 2026-08-09 多次超时（30s+），codex 看图稳定可靠：

```bash
echo "<分析问题>" | codex exec --skip-git-repo-check -c model_reasoning_effort=high \
  -c sandbox_mode=danger-full-access -C /home/ubuntu/workflow \
  -i /path/to/image.jpg 2>&1 | tail -40
```

铁律：
- **必须 `sandbox_mode=danger-full-access`**，否则 bwrap 读不了图（`unable to locate image ... fs sandbox helper failed`）
- **prompt 用管道 stdin 传**（`echo ... |`），不能放命令行参数——`-i` 会切换 stdin 读取模式，参数方式报 `No prompt provided via stdin`
- 多图对比：`-i 图1 -i 图2` 同时喂，让 codex 逐张分析+对比表
- codex 会自动把分析报告写 md 落盘项目目录

## 与 Seedream 分工（2026-08-09 用户最终定案：**codex 首选**）
- **默认生图 → codex**（用户明确「先把codex升级成首选」），`quality=high` 必带
- Seedream 仅作备选：简单真实感场景可切；复杂场景会跑偏（实测仙侠版把角色画成男性）
- 泳装/贴身 → Seedream（codex 安全墙过不去）
- 复杂/风格化场景（仙侠/特效）→ codex 稳赢（锁脸+构图+光影全胜）

## 批量并行生图（2026-08-25 实测）

需要一次出多张图（如3角色三视图+3场景图=6张）时，**并行跑 codex 比 串行快 3-5 倍**：

```bash
#!/bin/bash
# 每个图一个 codex exec 进程，用 & 后台启动，最后 wait
echo "<prompt_A>" | codex exec ... 2>&1 | tail -5 &
echo "<prompt_B>" | codex exec ... 2>&1 | tail -5 &
echo "<prompt_C>" | codex exec ... 2>&1 | tail -5 &
wait
```

要点：
- 每个 codex exec 用 `&` 后台启动，`wait` 等全部完成
- 每个进程独立的 `tail -5` 捕获 OUTPUT 路径
- 6 张图并行约 6 分钟完成（vs 串行约 25 分钟）
- codex 会自动把知识库引用+质检报告写 md 落盘项目目录（副产物，不影响主任务）
- **不要担心并发冲突**：每个 codex exec 是独立进程，各自的 sandbox 和输出路径互不干扰
- 可用模板：`templates/batch-image-gen.sh`

## 批量看图（6+ 张一次性 inspection，2026-08-25 实测）

`vision_analyze` 不仅能超时，还能**静默失败**：返回 `"success": true` 但实际没看到图（"I don't see any image attached"）——不是报错，是空结果。**不能只看 success 字段，必须检查 analysis 内容有没有实际描述。**

批量看图的可靠方案：**一个 codex exec 喂 6 张图，一次出全部质检报告**：

```bash
echo "For EACH image, answer: 1) gender correct? 2) layout correct? 3) photorealistic? 4) deformities? 5) describe clothing/hair." \
  | codex exec --skip-git-repo-check -c model_reasoning_effort=high \
    -c sandbox_mode=danger-full-access -C /home/ubuntu/workflow \
    -i img1.png -i img2.png -i img3.png -i img4.png -i img5.png -i img6.png 2>&1 | tail -80
```

要点：
- codex 逐张按顺序分析，输出结构化 per-image 报告
- 同时会自动落盘 qc/xxx_inspection.md（codex 副产物行为）
- 比 vision_analyze 逐张调（每次可能超时/空结果）快得多且可靠
- 6 张图一次约 82K tokens、2 分钟内完成

## 角色三视图 prompt 模板（2026-08-25 火龙 V20 实测定稿）

codex 文生图出三视图时，prompt 必须显式写以下要素，否则会跑偏：

1. **尺寸+比例**：`2560x1440 pixels, 16:9 horizontal aspect ratio`
2. **排版**：`Left one-third is a facial close-up portrait (head to collarbone). Right two-thirds shows THREE full-body views standing side by side: front view | three-quarter side view | back view. All three full-body figures are equal height, feet aligned on the same baseline.`
3. **性别显式写**：`adult Chinese FEMALE` / `adult Chinese MALE`（不写会被参考图干扰或默认出女性）
4. **风格显式写**：`Photorealistic, NOT 3D, NOT CG, NOT anime, NOT illustration, NOT cartoon`
5. **皮肤质感**：`natural skin texture with visible pores, NOT plastic, NOT smooth CG skin`
6. **多人区分**：多角色时每个 prompt 末尾写 `This character must look DIFFERENT from any other male character - distinct face, hair, and clothing`
7. **纯白背景**：`Pure white seamless background, no text, no watermark, no logo`
8. **输出协议**：`Save the generated image to: <绝对路径>` + `OUTPUT: <路径>` + `On failure output: BLOCKED: <reason>`

实测 6 张图（3角色+3场景）全部一次通过，无跑偏。

## 关联
- codex-bridge（任务分发总桥）
- seedream-image-generation（Seedream 工作流）
- singapore-guangzhou-relay（ARK 中转通道）
- dashscope-video-generation（视频生成，角色三视图是 r2v 的 @图1 前置资产）
