---
name: semantic-digital-human-workflow
title: 语义驱动数字人口播工作流
description: 把“数字人生成”从单纯视频合成升级为“文案语义驱动的口播表演系统”。用户文案→语义拆分→动作编排→标点控节奏（替代SSML）→婵镜参数生成→视频生成。
---

<!-- CANONICAL-RULINGS-BEGIN -->
> ⚠️ **本文件与视频线统一口径冲突的地方，一律以统一口径为准（用户 2026-10-01 逐条拍板），旧写法作废。**
> 统一口径单一事实源：`.hermes/skills/newmedia-operations/huolong-replica-template/references/current-rulings-20261001.md`
> 摘要：段时长＝字数÷5.5（不提速）；句数不限、只看语言逻辑；双人段必须互相说；画面/人物/禁止事项照旧写，只有配音部分不写段首段尾语速；画幅听用户当次要求（默认竖屏 720×1280，双人优先横屏）；LOGO 念到 CTA 时淡入保持 1.5 秒；默认只用快乐马出片，婵镜/Seedance/探店线用户点名才用；成片响度 -14 LUFS；BGM 0.25；CRF 18／aac 128k／24fps；实念率底线 90%；参考片＝过审基准，照抄不退稿。
<!-- CANONICAL-RULINGS-END -->


## 核心原则

> ⚠️ 通道限制（统一口径⑫）：默认出片只走快乐马 happyhorse-1.1-r2v；本婵镜流程**仅在用户明确点名婵镜数字人时**才用，不自行选择，也不在产出物里提工具名。

数字人不应该机械复刻参考视频动作，而应该根据当前文案内容**动态生成对应表情、手势和节奏**。

## 五步流程

```
用户文案 → ①语义拆分 → ②动作编排 → ③标点控节奏 → ④婵镜参数生成 → ⑤视频生成
```

---

## ① 语义拆分

不要一整段直接丢给生成接口。先拆成语义单元：

| 语义类型 | 示例 |
|:--------|:-----|
| 开场问候 | 大家好，欢迎来到我们的展厅。 |
| 卖点介绍 | 今天我带大家看一款核心产品。 |
| 重点强调 | 它的第一个优势是效率更高。 |
| 对比说明 | 第二个优势是使用更简单。 |
| 案例证明 | 第三个优势是成本更低。 |
| 行动引导 | 如果你也想提升效率，可以重点了解一下。 |

**铁律：** 每句≤15字，拆成独立的语义单元。

---

## ② 动作编排

给每一句加动作标签，输出结构化JSON：

```json
[
  {
    "text": "大家好，欢迎来到我们的展厅。",
    "action": "微笑点头，轻微抬手示意",
    "emotion": "亲和自然",
    "gesture": "轻幅度开放手势"
  },
  {
    "text": "今天我带大家看一款核心产品。",
    "action": "身体微微转向产品方向",
    "emotion": "专业介绍",
    "gesture": "指向画面侧方"
  }
]
```

**字段说明：**
| 字段 | 说明 | 可选值 |
|:----|:-----|:-------|
| text | 口播文案（≤15字） | 短句 |
| action | 身体动作描述 | 微笑点头/身体前倾/偏头/抬手/轻叹等 |
| emotion | 情绪状态 | 亲和自然/专业自信/心疼共情/理性剖析/释然希望等 |
| gesture | 手势幅度 | 低幅度/轻幅度/自然手势/强调手势 |

---

## ③ 标点控节奏（替代SSML）

**⚠️ 婵镜REST API不支持SSML标签（400报错），改用纯文本+标点控制停顿和语气。**

**替换规则（直接套用）：**
- `<break time="0.2-0.3s"/>` → `，`
- `<break time="0.4-0.5s"/>` → `。`
- `<break time="1s"/>` → `\n……`
- `<emphasis>` → ` 关键词！`

**转换示例：**

```xml
<!-- ❌ SSML（报400） -->
<prosody rate="0.95" pitch="1.02">大家好，欢迎来到我们的展厅。</prosody>
<break time="0.4s"/>今天我给大家介绍这款产品。
<break time="0.3s"/>它有三个核心优势。
<break time="0.3s"/>第一，<emphasis level="moderate">效率更高</emphasis>。

<!-- ✅ 纯文本（无报错） -->
大家好，欢迎来到我们的展厅。
今天我给大家介绍这款产品，它有三个核心优势。
第一， 效率更高！
第二，使用更简单。
第三，成本更低。
```

**规则：**
- 句间停顿 → 句号
- 短停顿 → 逗号
- 重点词 → 前后加空格+感叹号
- 情绪转折/长停顿 → 句号+换行+省略号……

**完整替换表见 shuziren skill 的「SSML转纯文本铁律」章节。**

---

## ④ 婵镜参数生成

### 通用模板

```json
{
  "person": {
    "id": "数字人ID",
    "lip_sync_precision": "high",
    "face_detail": true,
    "face_smooth": false,
    "blink_interval": 8,
    "head_sway": true,
    "body_breath": true
  },
  "audio": {
    "tts": {
      "audio_man": "音色ID",
      "speed": 1.0,
      "pitch": 1.02,
      "emotion_enhance": true,
      "text": ["口播文案（纯文本，无SSML标签）"]
    },
    "type": "tts",
    "volume": 100
  },
  "motion": {
    "auto_gesture": true,
    "gesture_strength": 0.2,
    "gesture_frequency": "low",
    "head_sway": true,
    "body_breath": true
  },
  "emotion": "表演基调描述（开场→中间→结尾的情绪变化）",
  "screen_width": 720,
  "screen_height": 1280,
  "source": 1
}
```

### 关键参数对照表

| 参数 | 位置 | 说明 |
|:----|:-----|:------|
| `lip_sync_precision` | person | 口型精度，固定`"high"` |
| `face_detail` | person | 微表情，`true` |
| `face_smooth` | person | 塑料脸，`false` |
| `blink_interval` | person | 眨眼间隔，8秒 |
| `head_sway` | person | 头部自然摆动，`true` |
| `body_breath` | person | 身体呼吸感，`true` |
| `speed` | audio.tts | 语速，固定 1.0（段时长＝字数÷5.5 向上取整，不调语速） |
| `pitch` | audio.tts | 音调，1.02（微暖） |
| `emotion_enhance` | audio.tts | 情绪增强，`true` |
| `audio_man` | audio.tts | 音色ID，`list_common_audio`获取 |
| `volume` | audio | 音量，放audio层级不是audio.tts内 |
| `auto_gesture` | motion | 自动手势，`true` |
| `gesture_strength` | motion | 手势幅度，口播0.2-0.35，不超过0.45 |
| `gesture_frequency` | motion | 手势频率，`"low"`（专业口播）/ `"medium"`（直播） |
| `emotion` | 顶级 | 表演基调，写完整描述 |
| `source` | 顶级 | Web数字人访问必须`1` |

### gesture_strength 选值

| 人设类型 | gesture_strength | gesture_frequency |
|:---------|:----------------|:------------------|
| 心理咨询师/专家 | 0.2 | low |
| 专业口播/商务 | 0.25-0.3 | low |
| 探店博主/带货 | 0.35 | medium |
| 主播/促销 | 0.4 | medium |
| ❌ 超过0.45 | — | — |

---

## ⑤ 视频生成

0. 前提：用户已明确点名用婵镜；画幅按用户当次要求（横版 1280×720／竖版 720×1280；没说就默认竖屏，双人段优先横版）
1. 结构化脚本 → 婵镜参数 → 调 `create_video` API
2. 出片前必须问「要跑不？」
3. 出片后交付视频链接

---

## 已知限制

婵镜 API **不是**真正的「语义动作编排系统」。它可以做到：
- ✅ 根据文案自动匹配一些手势
- ✅ 控制动作强度和频率
- ✅ 控制表情基调和口型精度
- ✅ 控制语速和情绪增强

但它**做不到**像专业动画软件那样：
- ❌ 每一句精确指定抬手角度
- ❌ 精确指向左侧/右侧
- ❌ 精确控制微笑幅度
- ❌ 精确控制眼神方向和转身时机

所以不能只靠API参数，必须靠**文案结构 + 动作提示 + emotion字段描述**来弥补。
