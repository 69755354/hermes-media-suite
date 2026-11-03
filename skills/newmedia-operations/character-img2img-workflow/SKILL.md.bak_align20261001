---
name: character-img2img-workflow
description: 给固定角色出场景图/自拍/换装图时使用，参考图锁脸+场景变量prompt。
---

<!-- CANONICAL-RULINGS-BEGIN -->
> ⚠️ **本文件与视频线统一口径冲突的地方，一律以统一口径为准（用户 2026-10-01 逐条拍板），旧写法作废。**
> 统一口径单一事实源：`.hermes/skills/newmedia-operations/huolong-replica-template/references/current-rulings-20261001.md`
> 摘要：段时长＝字数÷5.5（不提速）；句数不限、只看语言逻辑；双人段必须互相说；画面/人物/禁止事项照旧写，只有配音部分不写段首段尾语速；画幅听用户当次要求（默认竖屏 720×1280，双人优先横屏）；LOGO 念到 CTA 时淡入保持 1.5 秒；默认只用快乐马出片，婵镜/Seedance/探店线用户点名才用；成片响度 -14 LUFS；BGM 0.25；CRF 18／aac 128k／24fps；实念率底线 90%；参考片＝过审基准，照抄不退稿。
<!-- CANONICAL-RULINGS-END -->


# 固定角色垫图生图工作流（Seedream 图生图）

> 触发：用户要求给已有角色出图（换场景/换穿搭/自拍/清凉版），需要保持同一张脸。
> 实测验证：2026-08-05。上游定稿文件：`wiki/concepts/xiaolu-final-prompt.md`（小鹿最终版提示词）、`wiki/concepts/xiaolu-character-sheet.md`（角色四视图设定稿）、`wiki/concepts/img2img-template.md`（图生图标准模板）。

## 核心原则

1. **图生图不写五官外貌文字**——面部完全靠参考图锁定。写了五官描述反而容易串味/漂移。
2. **参考图用最终定稿设定稿**，不用近期衍生图。用户明确纠正过："拿最原始的形象图做参考"。
3. **场景必须写具体**，禁止"干净浅色背景"类素底描述（用户反馈"没有背景啊"）。

## 参考图选择（小鹿）

- ✅ **最终定稿参考图 = `/home/ubuntu/assets/characters/xiaolu_sheet.jpg`**（纯白背景多角度展示图，按最终版提示词生成）
- ❌ `seedance-fixed-character/小鹿_探店形象.png`（旧版18-22岁韩系甜妹，已废弃）
- ❌ 7/29 批次衍生图（`xiaolu_selfie.jpg` 曾被改成御姐风、`xiaolu_bikini_sunset.jpg`）

## 完整调用流程

### 1. 压缩参考图
大图 base64 会撑爆 curl 命令行，先缩小：
```bash
ffmpeg -y -i <参考图> -vf "scale=864:-1" -q:v 3 /tmp/ref_sheet_final.jpg
```

### 2. ARK File API 上传拿 file ID
```bash
curl -s -X POST "https://ark.cn-beijing.volces.com/api/v3/files" \
  -H "Authorization: Bearer <ARK_API_KEY>" \
  -F "file=@/tmp/ref_sheet_final.jpg" -F "purpose=user_data" \
  -o /tmp/upload.json -w "HTTP:%{http_code}\n" --max-time 45
```
- 成功返回 `{"id": "file-2026xxxxxxxx", "status": "processing"}`
- **⚠️ 上传端点间歇性 HTTP:000**：有时第1次就通，有时连试6次全挂。重试模式：for 循环 3-6 次 + sleep 3-5s，`-w "%{http_code}"` 判 200 才 break。注意 images/generations 和 chat/completions 端点不受影响，只有 /files 偶发。
- 每次生成前重新上传，不复用旧 file ID（有时效）。

### 3. 调 images/generations 垫图
```json
{
  "model": "doubao-seedream-5-0-260128",
  "prompt": "…",
  "image_list": ["file-2026xxxxxxxx"],
  "size": "1728x2304",
  "n": 1
}
```
- **⚠️ size 下限 3,686,400 像素**：`1024x1536` 报 InvalidParameter，`1728x2304` 可行。
- 大 JSON 用 `--data @/tmp/req.json`，不要内联 -d（会 Argument list too long）。

### 4. 下载结果
用 Python urllib + UA header 下载。不要用 xargs 截断 URL——签名 URL 截断会 NoSuchKey。

## Prompt 模板（img2img-template.md 规则）

```
年轻东亚女性,原生均匀肤色，自然皮肤质感，杜绝过度腮红，无面部大面积泛红色块,
生活化纪实摄影，胶片轻微颗粒，相机直出原图，无重度美颜磨皮，保留皮肤自然肌理，
拒绝过度精致广告写真质感,{frame_setting},{camera_rule},{light_setting},
{lens_param},{expression_emotion},{clothes_info},{scene_environment}
```
- 穿搭固定（小鹿最终版）：白色蕾丝边细吊带方领内搭，浅底色碎花A字短裙，裸色细带高跟凉鞋，细项链与小巧耳钉
- 负向 A 包常驻：塑料肌肤，CG，动漫，3D渲染，五官扭曲，面部畸形，肢体残缺，超高饱和度，僵硬人脸，数字人塑胶感，画面出现文字、水印
- 负向 B 包按需：俯拍，仰拍，极端高机位/低机位，不自然蹲姿，肢体严重扭曲，极致背景虚化，生硬强烈硬阴影，浓重橘暖色调，厚重蜜桃腮红
- 兜底加强版（仅人脸漂移时）：末尾追加"保持参考图人物面部五官、脸型基础特征不变"

## 场景描述写法

- ❌ "干净浅色背景" / "纯色背景" → 无场景素底图
- ✅ 具体场景：夏日海边沙滩+碧蓝海面+金色阳光+海风吹动发丝

## 老版纯文生图端点（不锁脸，仅当无参考图时）

- `POST localhost:1888/seedream`（文生图）仍可用，但不锁脸，同角色连续出图会漂移
- 服务起不来时：`sudo python3 -m py_compile /opt/helper_api.py` 查语法错误；服务因读 `/root/.helper_keys` 崩溃时确认 systemd User=root

## 已排雷

- ❌ 用旧版形象图当参考（用户纠正过）
- ❌ prompt 写五官外貌描述（应该靠参考图锁脸）
- ❌ 素底场景描述（应该写具体场景）
- ❌ 内联 -d 传大 JSON / 复用旧 file ID / xargs 截断下载 URL
