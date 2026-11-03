# ARK File Upload + Seedream 图生图

## Upload image to ARK

```bash
curl -s "https://ark.cn-beijing.volces.com/api/v3/files" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -F "file=@/path/to/image.jpg" \
  -F "purpose=user_data"
# Returns: {"object":"file","id":"file-xxx","purpose":"user_data","status":"processing"}
# Wait a moment, then check: GET /api/v3/files/file-xxx → status:"active"
```

Requirements:
- `purpose` must be `user_data` or `agent` (not `image_gen`)
- File ID format: `file-20260721...`
- Status becomes `active` after short processing delay

## Use file ID in Seedream image_list

```bash
bash seedream_gen.sh --ref_url "file-xxx" "参照这张图生成..."
```

The `file-xxx` ID works directly in `image_list` — no need for public URL.

## Image format constraints

- Min total pixels: 3,686,400 (e.g. 1920x1920 or 1440x2560)
- Default 9:16: 1440x2560 (exactly meets minimum)
- `watermark: false` must be passed explicitly

## 文生图 vs 图生图

| Mode | When | Prompt | image_list |
|:-----|:-----|:-------|:-----------|
| 文生图 | No reference image | User description + 小鹿特征 + quality prefix | Omit |
| 图生图 | User provides reference image | Custom prompt | Image URL or file ID |

## Quality prompts

**文生图正向（自动拼接）：**
小鹿特征 + 用户描述 + 8K质感描述（佳能R6/50mm f1.4/柯达金200）

**图生图正向（用户自定义）：**
根据参考图内容写，包含「严格1:1复刻参考图人物五官轮廓...」等还原词

**负向提示词（通用）：**
卡通，动漫，二次元，手绘，CG，3D渲染，蜡像，塑料假皮肤...（完整列表在seedream_gen.sh）

## 常用尺寸

- 1440x2560 (9:16, 3.69MP, 刚好满足最低要求)
- 1920x1920 (正方形, 3.69MP)
- 720x1280 ❌ 像素不够
