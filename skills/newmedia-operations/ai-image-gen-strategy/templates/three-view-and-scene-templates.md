# 角色三视图 + 场景图 codex 提示词模板（2026-08-25 火龙V20实测全过）

> 6张图（3角色三视图+3场景图）codex并行生成，全部通过vision自检：性别正确、排版正确、写实非CG、无畸形。
> 模板提取为通用结构，替换角色/场景描述即可复用。

## 一、角色三视图模板（codex文生图）

### 关键成功要素（缺一不可）
1. **显式写性别**：`adult Chinese FEMALE` / `adult Chinese MALE`（不写性别→可能跑偏）
2. **显式写排版**：`Left one-third is a facial close-up portrait (head to collarbone). Right two-thirds shows THREE full-body views standing side by side: front view | three-quarter side view | back view. All three full-body figures are equal height, feet aligned on the same baseline.`
3. **显式写风格**：`Photorealistic, NOT 3D, NOT CG, NOT anime, NOT illustration, NOT cartoon`
4. **显式写尺寸**：`Image size: 2560x1440 pixels, 16:9 horizontal aspect ratio`
5. **显式写背景**：`Pure white seamless background, no text, no watermark, no logo`
6. **多角色区分**：`This character must look DIFFERENT from any other male character - distinct face, hair, and clothing`
7. **皮肤质感**：`natural skin texture with visible pores, NOT plastic, NOT smooth CG skin, subsurface scattering`
8. **一致性锁定**：`Same person, same clothing, same hair, same accessories across all four views`

### 模板（替换{{}}部分）

```
Generate a three-view character reference sheet image. EXACT specifications:
- Image size: 2560x1440 pixels, 16:9 horizontal aspect ratio
- Layout: Left one-third is a facial close-up portrait (head to collarbone, showing detailed facial features). Right two-thirds shows THREE full-body views standing side by side: front view | three-quarter side view | back view. All three full-body figures are equal height, feet aligned on the same baseline.
- Pure white seamless background, no text, no watermark, no logo
- Character: {{AGE}}-year-old adult Chinese {{GENDER}}. Photorealistic, NOT 3D, NOT CG, NOT anime, NOT illustration, NOT cartoon.
- Face: {{FACE_DESCRIPTION}}
- Hair: {{HAIR_DESCRIPTION}}
- Body: {{BODY_DESCRIPTION}}
- Clothing: {{CLOTHING_DESCRIPTION}}
- Skin: natural skin texture with visible pores, NOT plastic, NOT smooth CG skin, subsurface scattering
- Same person, same clothing, same hair, same accessories across all four views
{{MULTI_CHARACTER_NOTE}}
- Save the generated image to: {{OUTPUT_PATH}}
- On success output: OUTPUT: {{OUTPUT_PATH}}
- On failure output: BLOCKED: <reason>
```

### 实测变量示例

**女性角色（25岁）：**
- FACE: oval face, clear defined jawline, brown eyes with slight upward tilt, high nose bridge, full natural lips, matte red lipstick
- HAIR: dark brown long wavy hair, 7:3 parting, one side tucked behind ear
- BODY: slender balanced adult female figure, standing upright, natural posture
- CLOTHING: black velvet slim-fit long-sleeve dress, asymmetric square neckline showing collarbone moderately, hemline 8cm above knee, black opaque stockings, silver strappy high heels, small geometric earrings

**男性角色B（26岁）：**
- FACE: square narrow face, clear jawline, thick eyebrows, dark brown eyes, high straight nose bridge, clean shaven no beard
- HAIR: black short hair, faded sides, top styled back with slight wet texture
- BODY: 185cm height, broad shoulders, lean muscular build with training definition, not excessive muscle
- CLOTHING: deep peacock blue silk long-sleeve shirt, collar with one button undone, black high-waist trousers, black leather boots, silver thin chain necklace and minimalist wristwatch
- MULTI_CHARACTER_NOTE: (none for first character)

**男性角色C（28岁，与B区分）：**
- FACE: long diamond-shaped face, narrow double eyelids, straight nose, clear lip line, very light short stubble on chin
- HAIR: cold black short textured hair, natural forehead texture, NOT slicked back, piecey fringe
- BODY: 183cm height, lean inverted triangle build, defined shoulder and arm lines
- CLOTHING: black subtle shimmer suit jacket, charcoal gray crew-neck tee underneath, black straight trousers, shiny leather loafers, dark metal rings
- MULTI_CHARACTER_NOTE: This character must look significantly DIFFERENT from Character B - different face shape, different hairstyle, different clothing color

## 二、场景图模板（codex文生图）

### 关键成功要素
1. **显式写尺寸+比例**：`Image size: 1440x2560 pixels, 9:16 vertical aspect ratio`
2. **空间结构描述**：左中右后方位明确
3. **光线描述**：主光+辅光+轮廓光分别写
4. **禁止项**：`NO people, NO readable text, NO Chinese characters, NO logos`
5. **UI留白区**：`Right side: clean vertical area reserved for UI overlay` / `Center: clean vertical area (55-65 percent of frame) reserved for UI overlay`

### 模板

```
Generate a vertical scene image. EXACT specifications:
- Image size: 1440x2560 pixels, 9:16 vertical aspect ratio
- Scene: {{SCENE_DESCRIPTION}}
{{SPATIAL_DETAILS}}
- Lighting: {{LIGHTING_DESCRIPTION}}
- NO people, NO readable text, NO Chinese characters, NO logos{{ADDITIONAL_NEGATIVES}}
- Style: photorealistic, cinematic, {{STYLE_QUALIFIER}}
- Save the generated image to: {{OUTPUT_PATH}}
- On success output: OUTPUT: {{OUTPUT_PATH}}
- On failure output: BLOCKED: <reason>
```

### 实测变量示例（夜店三场景）

**N1 吧台卡座：**
- SCENE: High-end urban nightclub, semi-enclosed bar booth area
- SPATIAL: Left-center: a dark red velvet high-back single chair. Center: clear walkway for a person to walk toward camera. Right-rear: curved smoked glass bar counter. Background: pink-red and blue-purple neon geometric light strips. Floor: black mirror stone with weak reflection only.
- LIGHTING: warm soft light on face area, blue-purple and pink-red rim light from behind
- STYLE: premium nightclub aesthetic, NOT cheap KTV

**N2 VIP走廊：**
- SCENE: VIP corridor in a high-end urban nightclub
- SPATIAL: Center: short walkway leading toward camera. Both sides: smoked glass panels and thin metal lines. Overhead: purple-blue rectangular light strips creating depth perspective. Right side: clean vertical area reserved for UI overlay (no objects, no text). Floor: dark polished stone.
- LIGHTING: purple-blue ambient
- STYLE: premium nightclub aesthetic

**N3 DJ台：**
- SCENE: DJ booth side-front area in a high-end urban nightclub
- SPATIAL: Background: blurred DJ console silhouette and purple-blue light strips. Empty dance floor, no people. Center: clean vertical area (55-65 percent of frame) reserved for UI overlay. Left side: reserved for character standing position. Lower-left: reserved for CTA area.
- LIGHTING: purple-blue ambient with slight brightness breathing effect on light strips
- STYLE: premium nightclub aesthetic
- ADDITIONAL_NEGATIVES: NO DJ Person

## 三、并行生成脚本结构

```bash
#!/bin/bash
set -u
OUTDIR=/path/to/output

# 角色A
echo "<prompt A>" | codex exec --skip-git-repo-check -c model_reasoning_effort=high \
  -c sandbox_mode=danger-full-access -C /path/to/workflow 2>&1 | tail -5 &

# 角色B
echo "<prompt B>" | codex exec --skip-git-repo-check -c model_reasoning_effort=high \
  -c sandbox_mode=danger-full-access -C /path/to/workflow 2>&1 | tail -5 &

# 场景图...
echo "<prompt N1>" | codex exec ... &

echo "=== All jobs launched, waiting... ==="
wait
echo "=== All jobs done ==="
ls -lh ${OUTDIR}/*.png 2>&1
```

关键点：
- `&` 后台并行 + `wait` 等全部完成
- 每个codex用 `echo "prompt" | codex exec ...` 管道传prompt
- `-c model_reasoning_effort=high` 出图质量更好
- `-c sandbox_mode=danger-full-access` 必须（否则读写不了图）
- `2>&1 | tail -5` 只取结尾OUTPUT行

## 四、批量vision自检（codex多图看图）

```bash
echo "For EACH image, answer: gender? layout correct? photorealistic? deformities?" | \
codex exec --skip-git-repo-check -c model_reasoning_effort=high \
  -c sandbox_mode=danger-full-access -C /path/to/workflow \
  -i img1.png -i img2.png -i img3.png -i img4.png -i img5.png -i img6.png 2>&1 | tail -80
```

关键点：
- 最多6张图一次喂给codex（-i img1 -i img2 ... -i img6）
- prompt用管道stdin传
- codex自动生成质检报告md落盘
- vision_analyze对本地PNG可能全部失败（"no image attached"），codex看图是可靠替代
