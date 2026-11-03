# ARK API 文生图/图生图（Seedream 4.5）完整指南

> 最后更新: 2026-07-21
> 本技能管理的脚本: `scripts/seedream_gen.sh`（文生图/图生图二合一）
> 源对话: 飞书小鹿工作流重写 + Seedream prompt三轮调优

---

## 一、API 端点

```
POST https://ark.cn-beijing.volces.com/api/v3/images/generations
```

## 二、可用模型

| 模型 ID | 状态 | 价格 | 说明 |
|:--------|:----:|:----:|:------|
| `doubao-seedream-4-5-251128` | ✅ 主力 | 0.22元/张 | 写实人像首选，质感优于5.0 |
| `doubao-seedream-5-0-260128` | ✅ 可用 | 0.22元/张 | 更清晰但更AI（太光滑太对称） |
| `doubao-seedream-5-0-pro-260628` | ❌ 未开通 | - | 需火山引擎控制台手动开通 |

**4.5 vs 5.0 选择：** 5.0 太假（皮肤过于光滑、五官过于对称），4.5 更有真人实拍感。默认用 4.5。

## 三、参数白名单

| 参数 | 必填 | 说明 |
|:-----|:----:|:------|
| `model` | ✅ | 模型ID |
| `prompt` | ✅ | 正向提示词 |
| `negative_prompt` | ❌ | 负向提示词（强烈建议传） |
| `image_list` | ❌ | 参考图URL数组，最多14张，支持 `file-xxx` ID 和公网URL |
| `size` | ✅ | 必须 ≥3,686,400 像素（如 1440x2560 / 1920x1920） |
| `n` | ❌ | 每次1张，多张可能被拒 |
| `watermark` | ❌ | **必须传 `false`**，否则图片带水印 |

### 尺寸约束

API 要求最小 3,686,400 像素。常用合规尺寸：

| 比例 | 宽 | 高 | 像素 | 说明 |
|:----:|:--:|:--:|:-----:|:------|
| 9:16 | 1440 | 2560 | 3,686,400 | 默认竖屏，刚好达标 |
| 1:1 | 1920 | 1920 | 3,686,400 | 正方形，刚好达标 |
| 9:16 | 1080 | 1920 | 2,073,600 | ❌ 不达标 |
| 16:9 | 2560 | 1440 | 3,686,400 | 横屏 |

## 四、文生图（无参考图）

### 用法（通过脚本）

```bash
bash /home/ubuntu/.hermes/scripts/seedream_gen.sh "描述" [尺寸]
bash /home/ubuntu/.hermes/scripts/seedream_gen.sh  # 默认出小鹿形象
```

### 完整正向提示词模板

拼接规则：`{小鹿人物特征}，{用户自定义描述（可选）}，{质感描述}`

**小鹿人物特征（固定）：**
```
柔和鹅蛋脸，清新杏眼深棕瞳孔，开扇双眼皮，鼻头小巧圆润，M形唇淡粉色，柔和弯眉野生眉质感，暖调浅棕色中短卷发，碎空气刘海，发尾微卷，干净温柔邻家气质
```

**质感描述（固定）：**
```
轻薄自然遮瑕底妆，肤色均匀干净，无明显痘印、无明显色斑、无明显泛红，保留真实细微毛孔、自然唇纹、轻微眼角细纹和皮肤明暗层次，妆感轻薄通透，不假面，不厚重粉底，淡氛围感淡妆，门店生活化探店人像，8K高清，索尼A7M4，85mm f1.2人像镜头，室内暖柔光，浅景深虚化门店背景，富士胶片细腻颗粒，真实皮肤油脂反光，发丝通透有光泽，简约浅色上衣，松弛温柔浅笑，真人相机实拍质感，无过度精修，竖屏9:16，720*1280
```

### 负向提示词（固定，脚本自动带）

```
卡通，二次元，手绘，CG，蜡像，塑料假皮肤，零毛孔完美肌肤，重度美颜，惨白假肤色，大面积痘印，明显色斑，面部泛红，畸形五官，脸部不对称，多余手指，水印，文字，logo，厚重网红妆，扁平光影，僵硬表情，插画，油画，模糊低清
```

## 五、图生图（带参考图）

### 流程

```
本地图片 → ARK文件上传（拿file-xxx ID） → image_list传参 → Seedream生成
```

### 步骤一：上传参考图到ARK

```bash
FILE_ID=$(curl -s "https://ark.cn-beijing.volces.com/api/v3/files" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -F "file=@/path/to/image.jpg" \
  -F "purpose=user_data" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "FILE_ID: $FILE_ID"
```

- `purpose` 必须为 `user_data` 或 `agent`，否则报错
- 返回的 `file-xxx` ID 可直接填入 `image_list` 数组
- 文件有效期约7天，过期后需重新上传

### 步骤二：调Seedream图生图

```bash
# 通过脚本
bash /home/ubuntu/.hermes/scripts/seedream_gen.sh \
  --ref_url "file-20260721130211-wv9ml" \
  "参照参考图，严格1:1复刻人物五官轮廓..."

# 或直调API
curl -s "https://ark.cn-beijing.volces.com/api/v3/images/generations" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seedream-4-5-251128",
    "prompt": "参照参考图，严格1:1复刻人物五官轮廓...",
    "negative_prompt": "卡通，二次元，手绘...",
    "image_list": ["file-20260721130211-wv9ml"],
    "size": "1440x2560",
    "n": 1,
    "watermark": false
  }'
```

### 图生图正向提示词模板

```
严格1:1复刻参考图人物五官轮廓、脸型、眉眼、鼻型、唇形、原生肤色、发型样式，原生真人线下实拍原图，8K超清，佳能R6 Mark2相机，50mm f1.4定焦人像镜头，室内门店柔和暖调漫射光，无生硬阴影，皮肤保留细微毛孔、皮下红血丝、自然面部肌理、轻微眼角细纹、原生唇纹，不磨皮、无美颜滤镜，发丝根根分明带自然通透光泽，衣物面料自带真实褶皱与布料纹理，人物松弛自然浅笑，浅景深虚化门店背景，自然原生色彩，柯达金200胶片颗粒质感，真实人类皮肤油脂反光，瞳孔清晰可见虹膜纹理、根根分明睫毛，环境漫反射光影，轻微原生相机噪点，自然面部骨骼起伏，无人工修饰痕迹，竖屏9:16，720*1280
```

**⚠️ 坑：prompt中避免使用"小鹿"二字** — 会被AI理解为动物生成一头鹿。改用"参考图人物"。

## 六、seedream_gen.sh 脚本

路径：`/home/ubuntu/.hermes/scripts/seedream_gen.sh`

```bash
# 文生图
bash seedream_gen.sh                    # 出小鹿默认形象照
bash seedream_gen.sh "穿红色连衣裙"      # 小鹿特征+描述+质感
bash seedream_gen.sh "描述" "1920x1920" # 自定义尺寸

# 图生图（先上传参考图拿file ID）
bash seedream_gen.sh --ref_url "file-xxx" "参照参考图，生成..."
```

脚本内置：小鹿特征（XIAOLU_FACE）、质感描述（QUALITY）、负向提示词（NEGATIVE），文生图自动拼接。

## 七、ARK文件上传（解决无公网URL问题）

客户发到飞书/微信的参考图没有公网URL时，先用 ARK 文件上传：

```bash
# 完整链路
FILE_ID=$(curl -s "https://ark.cn-beijing.volces.com/api/v3/files" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -F "file=@参考图.jpg" \
  -F "purpose=user_data" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

RESP=$(curl -s "https://ark.cn-beijing.volces.com/api/v3/images/generations" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"doubao-seedream-4-5-251128\",
    \"prompt\": \"参照参考图保留五官发型，正面微笑半身自拍...\",
    \"negative_prompt\": \"卡通，二次元，手绘...\",
    \"image_list\": [\"$FILE_ID\"],
    \"size\": \"1440x2560\",
    \"n\": 1,
    \"watermark\": false
  }")

URL=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['url'])")
curl -o result.jpg "$URL"
```

## 八、真实感要点（2026-07-21 研究结论）

B站「焚决！一招教你去除人物AI味」（刺猬星球super-i）核心逻辑：

1. **AI假不是因为细节不够，是因为太完美了**
2. **垫图要用真实生活照** — 不要用商拍图/精修图
3. **光线要有方向、要不均匀** — 加轮廓光和发丝光，小的不完整才是真实感来源
4. **写实prompt误区：**
   - 「无毛孔、零瑕疵」→「保留真实毛孔、细微雀斑、皮肤纹理」
   - 「均匀柔光」→「侧上方自然光，产生真实高光和阴影变化」
   - 「专业摄影设备」→「手机前置自拍感」反而更真实

## 九、常见踩坑

1. `watermark` 不传默认 true → 每次显式传 false
2. 720x1280 不够 → 最小 1440x2560（9:16）
3. prompt 超 100 字会丢失重点
4. "小鹿"在prompt中被理解为动物 → 用"参考图人物"
5. 图生图传 `image` 无效 → 正确参数是 `image_list`
6. 国际图床不可用 → 用 ARK 文件上传代替
7. 5.0 比 4.5 更假 → 默认用 4.5
