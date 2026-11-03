# Seedream出场景图 + 换脸锁定身份 (绕过API图生图锁不住特征问题的方案)

> 适用场景：需要锁定角色的面部特征，但Seedream API裸调靠垫图锁不住
> 核心逻辑：Seedream只负责出场景/构图/穿搭，不负责锁脸；锁脸交给独立的换脸模块

---

## 为什么需要这个方案

ARK API 图生图无法可靠锁定参考图的五官特征（已验证4+次），而豆包App有内置面部保护所以能锁住。

```
Seedream 文生图 → 出场景图（人脸不对没关系）
  ↓
换脸模块 → 把目标人脸贴上去
  ↓
输出最终图
```

## 方案对比

| 方案 | 费用 | 效果 | 门槛 |
|:----|:-----|:-----|:-----|
| 豆包App直接生成 | 免费 | ⭐⭐⭐⭐⭐ | 最低，推荐 |
| FaceFusion本地部署 | 免费（需GPU） | ⭐⭐⭐⭐⭐ | 需本地部署 |
| InsightFace | 免费 | ⭐⭐⭐⭐ | 模型下载慢 |
| 火山引擎FaceSwap API | ~0.004元/次 | ⭐⭐⭐⭐ | 需单独Key |
| 阿里云人脸融合 | 按次计费 | ⭐⭐⭐⭐ | 需单独Key |

## 方案A：InsightFace（效果最好，推荐）

```bash
python3 -m venv /path/to/venv/faceswap
source /path/to/venv/faceswap/bin/activate
pip install insightface opencv-python onnxruntime

python3 scripts/faceswap.py \
  /path/to/reference_face.jpg \
  /path/to/target_image.jpg \
  /path/to/output.jpg
```

注意：首次运行会从 GitHub 下载约 280MB 的模型文件。中国服务器下载极慢（实测2小时+超时）。

## 方案B：OpenCV简易版（无需额外模型，效果一般）

注意：OpenCV 5.0 已将 CascadeClassifier 移出主命名空间。需要手动下载xml文件。

## 方案C：FaceFusion（社区最主流）

- GitHub 28.4k+ Stars
- 3.8版本，持续更新
- 90%真实感，比insightface好
- 需要GPU(N卡)最佳，CPU也能跑

## 完整流程

1. Seedream 文生图 → 出场景图（不管人像，自由发挥）
2. 换脸 → 将参考图人脸替换到场景图上
3. 输出最终图

优势：Seedream负责构图/光线/背景质量，换脸负责身份锁定，各取所长。
