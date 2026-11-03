#!/bin/bash
# Seedream 4.5 图生图/文生图脚本
# 用法:
#   文生图: bash seedream_gen.sh "图片描述" [尺寸]
#   图生图: bash seedream_gen.sh --ref_url "file-xxx或URL" "自定义prompt" [尺寸]
# 尺寸默认1440x2560（9:16竖屏，满足API最低368.64万像素）

SIZE="1440x2560"
REF_URL=""
PROMPT=""
USER_PROMPT=""

# 小鹿人物特征（文生图默认带上）
XIAOLU_FACE="柔和鹅蛋脸，清新杏眼深棕瞳孔，开扇双眼皮，鼻头小巧圆润，M形唇淡粉色，柔和弯眉野生眉质感，暖调浅棕色中短卷发，碎空气刘海，发尾微卷，干净温柔邻家气质"

# 基础质感前缀（文生图时自动带上）
QUALITY="轻薄自然遮瑕底妆，肤色均匀干净，无明显痘印、无明显色斑、无明显泛红，保留真实细微毛孔、自然唇纹、轻微眼角细纹和皮肤明暗层次，妆感轻薄通透，不假面，不厚重粉底，淡氛围感淡妆，门店生活化探店人像，8K高清，索尼A7M4，85mm f1.2人像镜头，室内暖柔光，浅景深虚化门店背景，富士胶片细腻颗粒，真实皮肤油脂反光，发丝通透有光泽，简约浅色上衣，松弛温柔浅笑，真人相机实拍质感，无过度精修，竖屏9:16，720*1280"

NEGATIVE="卡通，二次元，手绘，CG，蜡像，塑料假皮肤，零毛孔完美肌肤，重度美颜，惨白假肤色，大面积痘印，明显色斑，面部泛红，畸形五官，脸部不对称，多余手指，水印，文字，logo，厚重网红妆，扁平光影，僵硬表情，插画，油画，模糊低清"

# 解析参数
if [ "$1" = "--ref_url" ]; then
    REF_URL="$2"
    PROMPT="$3"
    MODE="图生图"
    if [ -n "$4" ]; then SIZE="$4"; fi
else
    USER_PROMPT="$1"
    MODE="文生图"
    if [ -n "$2" ]; then SIZE="$2"; fi
fi

# 文生图拼prompt
if [ "$MODE" = "文生图" ]; then
    if [ -n "$USER_PROMPT" ]; then
        PROMPT="${XIAOLU_FACE}，${USER_PROMPT}，${QUALITY}"
    else
        PROMPT="${XIAOLU_FACE}，${QUALITY}"
    fi
fi

if [ -z "$PROMPT" ] && [ "$MODE" = "图生图" ] && [ -z "$3" ]; then
    echo "❌ 图生图模式需要传prompt"
    echo "  bash seedream_gen.sh --ref_url \"https://xxx.jpg\" \"你的prompt\""
    exit 1
fi

KEY="${ARK_API_KEY}"
if [ -z "$KEY" ]; then
    echo "❌ ARK_API_KEY 未设置"
    exit 1
fi

echo "🎨 Seedream 4.5 $MODE | $SIZE"
echo "  参考图: ${REF_URL:-无}"
echo ""

# 构建JSON
if [ -n "$REF_URL" ]; then
    JSON=$(python3 -c "
import json
d = {
    'model': 'doubao-seedream-4-5-251128',
    'prompt': '''$PROMPT''',
    'negative_prompt': '''$NEGATIVE''',
    'image_list': ['$REF_URL'],
    'size': '$SIZE',
    'n': 1,
    'watermark': False
}
print(json.dumps(d))
")
else
    JSON=$(python3 -c "
import json
d = {
    'model': 'doubao-seedream-4-5-251128',
    'prompt': '''$PROMPT''',
    'negative_prompt': '''$NEGATIVE''',
    'size': '$SIZE',
    'n': 1,
    'watermark': False
}
print(json.dumps(d))
")
fi

RESP=$(curl -s -w "\n%{http_code}" "https://ark.cn-beijing.volces.com/api/v3/images/generations" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d "$JSON")

HTTP_CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    URL=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['url'])")
    echo "✅ 生成成功！"
    echo "$URL"
else
    echo "❌ 失败 (HTTP $HTTP_CODE)"
    echo "$BODY"
fi
