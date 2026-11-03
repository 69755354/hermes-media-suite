# Seedream 写实人像参考知识库

> 多源交叉验证：Instagram/LinkedIn/搜狐/B站/X/Threads 等，2026-07-21 整理

## Texture Stack（去塑料感三件套）
**来源：** Instagram @manjeshyadav_design

1. **Subsurface scattering** — 皮下散射，皮肤半透明感
2. **Vellus hair** — 细小绒毛（peach fuzz），脸颊极微细节
3. **Imperfection Boost** — 瑕疵加成，打破完美

> 三件套同时写在prompt里，能直接去除 "airbrush effect"

## 各维度关键词

### 皮肤
| 目的 | 关键词 |
|:----|:-------|
| 半透明感 | subsurface scattering |
| 纹理 | visible pores, natural skin texture, detailed skin |
| 绒毛 | vellus hair, peach fuzz |
| 瑕疵 | freckles, beauty marks, slight skin imperfections |
| 油光 | natural skin glow, dewy skin, sebum |
| 细纹 | fine lines, wrinkles |

### 眼睛
| 目的 | 关键词 |
|:----|:-------|
| 虹膜 | iris texture, iris detail |
| 眼神光 | catchlight, eye reflection |
| 睫毛 | individual eyelashes, separated lashes |
| 眼白 | subtle blood vessels, natural eye white |

### 发丝
| 目的 | 关键词 |
|:----|:-------|
| 碎发 | flyaway hairs, baby hairs |
| 纹理 | hair strand texture, individual hair strands |
| 光泽 | natural hair shine |
| 毛躁 | slightly messy, natural frizz |

### 光线
| 类型 | 关键词 | 效果 |
|:----|:-------|:-----|
| 方向光 | 45° key light, directional side lighting | 最真实 |
| 窗光 | natural window light | 日常感 |
| 轮廓光 | rim light, hair light | 分离背景 |
| 硬光 | harsh side lighting | 照出纹理起伏 |

### 构图
| 技巧 | 关键词 |
|:----|:-------|
| 前景遮挡 | foreground blur, glass reflection, leaves, window frame |
| 抖动 | slight camera shake, handheld look |
| 噪点 | film grain, natural noise, sensor noise |
| 手机感 | iPhone front camera, smartphone selfie |

## 负向提示词核心词
`wax figure`, `plastic skin`, `airbrushed`, `flawless` — 四个词效果最明显

## 关键规则
1. 光线越柔皮肤越假 → 用方向光
2. 画面越干净越假 → 加前景遮挡
3. 越完美越假 → 加瑕疵
4. 垫图决定真实感上限 → 素人自拍 > 精修图
5. 关键词位置：皮肤纹理词放人物描述之后、风格词之前

## 来源
| 来源 | 内容 |
|:----|:-----|
| Instagram @manjeshyadav_design | Texture Stack 三件套 |
| LinkedIn Ferdinand Terme | 分维度提示词技巧 |
| 搜狐 AI漫剧 | 塑料感根源分析 |
| X 骑司Chase | 参考图对比实测 |
| B站 刺猬星球super-i | 垫图+光线+调色三步法 |
| Threads @addisonaithinking | 皮肤/光影/画面三技巧 |
