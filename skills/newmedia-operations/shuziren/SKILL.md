---
name: shuziren
title: 婵镜数字人API参数参考库
description: 婵镜数字人API接口规范与克隆流程。口播分支已合并入huoshan三通道工作流。本skill仅作婵镜API参数参考库。
---

> **本文件仅作婵镜API参数参考。流程规则以 `huoshan` 为准。**
> 口播分支已合并入 huoshan 三通道工作流（探店Seedance/剧情Seedance/口播婵镜）。
> 通道选型第一问是内容类型（探店/剧情/口播），不是客户类型。
> 本 skill 不再包含节点流程、通道选型、合规规则、ffmpeg合成、字幕等内容——这些请查阅 huoshan 或 video-production。

## 婵镜API基础

**Base URL:** `https://open-api.chanjing.cc`

### 获取 access_token

```
POST /open/v1/access_token
{
  "app_id": "d01ef4c6",
  "secret_key": "[存入环境变量 CHANJING_SECRET_KEY; 注：有多个婵镜账号，如环境变量非此值则需确认用哪个账号]"
}
→ data.access_token（1天有效）
```

## 数字人克隆API

### 上传文件

```
GET /open/v1/common/create_upload_url?service=customised_person&name=video.mp4
H: access_token: $TOKEN
→ sign_url + file_id
```
用PUT方法上传到 sign_url：
```
curl -s -X PUT "$SIGN_URL" -H "Content-Type: video/mp4" --data-binary @video.mp4
```

### 提交克隆任务

**端点：** `POST /open/v1/create_customised_person`

```json
{
  "name": "名称_视频克隆_日期",
  "file_id": "上一步获取的file_id",
  "train_type": "both",
  "is_remove_bg": false,
  "error_skip": false
}
```

| 参数 | 说明 |
|:------|------|
| `train_type` | "both"（脸+声）/ "figure"（仅形象）/ "voice"（仅声音） |
| `is_remove_bg` | **默认false**（保留原视频背景）。设true会把人从背景抠出来，出片时需通过`bg.src_url`提供新背景。**必须问用户意见，不准擅自设true** |

返回 `data` = 新数字人ID（如 `"C-0aaa3b9514614df2a0f2b4296438c84f"`）

### 查询克隆进度

```
GET /open/v1/customised_person?id=数字人ID&source=0
H: access_token: $TOKEN
```

| status | 含义 |
|:-------|------|
| 0 | 初始/排查中 |
| 1 | 训练中（progress=0-100） |
| 2 | 完成 ✅ |
| 4 | 失败 ❌ |

**⚠️ status=0或空时排查顺序：** Token过期→重拿；APP_ID是否正确（多账号资产不互通）→换账号token重查；source参数（API端=0, Web端=1）

### 删除数字人/声纹

```
DELETE /open/v1/delete_customised_person?id=数字人ID
DELETE /open/v1/delete_customised_audio?id=声纹ID
```
（可能返回50000「已禁用或不存在」，正常）

### 列出数字人

```
GET /open/v1/customised_person?source=0
H: access_token: $TOKEN
```
用于确认数字人ID是否在API端存在。

## 声纹/音色API

### 列出公共音色

```
GET /open/v1/list_common_audio
H: access_token: $TOKEN
```
→ 获取 `audio_man` 音色ID列表

## 视频生成API（create_video）

**端点：** `POST /open/v1/create_video`

### 完整参数模板

```json
{
  "person": {
    "id": "数字人ID",
    "width": 1080,
    "height": 1920,
    "face_detail": true,
    "lip_sync_precision": "high",
    "blink_interval": 8,
    "head_sway": true,
    "body_breath": true,
    "face_smooth": false
  },
  "audio": {
    "tts": {
      "audio_man": "合法音色ID（list_common_audio获取）",
      "speed": 0.98,
      "pitch": 1.02,
      "emotion_enhance": true,
      "volume": 100,
      "language": "cn",
      "text": ["口播文案（纯文本，不支持SSML标签。婵镜REST API传SSML报400）"]
    },
    "type": "tts"
  },
  "motion": {
    "auto_gesture": true,
    "gesture_strength": 0.35,
    "gesture_frequency": "low"
  },
  "bg": {
    "src_url": "公网可访问的背景图URL",
    "width": 1080,
    "height": 1920
  },
  "emotion": "温和专业，日常讲解，轻微微笑",
  "model": 1,
  "source": 1,
  "screen_width": 1080,
  "screen_height": 1920
}
```

### 参数详解

| 参数 | 路径 | 必填 | 说明 |
|:----|:----|:----|:------|
| `person.id` | 嵌套 | ✅ | 数字人ID，嵌套在person对象中 |
| `source` | 顶级 | ✅ | 访问Web数字人必须设为1 |
| `text` | `audio.tts.text` | ✅ | 数组格式 `["文案"]`，不支持字符串 |
| `speed` | `audio.tts.speed` | ✅ | 范围0.5~2，建议0.95-1.0 |
| `audio_man` | `audio.tts.audio_man` | ✅ | 参数名是`audio_man`非`audio_man_id` |
| `type` | `audio.type` | ✅ | 固定值 `"tts"` |
| `volume` | `audio.volume` | ✅ | 范围1~100，建议100。**必须放audio层级，不能放audio.tts内部** |
| `screen_width` | 顶级 | ✅ | 竖屏1080 |
| `screen_height` | 顶级 | ✅ | 竖屏1920 |
| `person.face_detail` | 嵌套 | 可选 | 面部细节增强 |
| `person.lip_sync_precision` | 嵌套 | 可选 | 唇形同步精度，建议"high" |
| `person.blink_interval` | 嵌套 | 可选 | 眨眼间隔，建议8 |
| `person.head_sway` | 嵌套 | 可选 | 头部微摆 |
| `person.body_breath` | 嵌套 | 可选 | 身体呼吸感 |
| `person.face_smooth` | 嵌套 | 可选 | 面部平滑，建议false |
| `audio.tts.pitch` | 嵌套 | 可选 | 音调微调，1.02=微暖 |
| `audio.tts.emotion_enhance` | 嵌套 | 可选 | 情绪增强，true=TTS自动抓关键词加重 |
| `motion.gesture_strength` | 嵌套 | 可选 | 手势幅度，0.35=日常/0.2=心理咨询 |
| `motion.gesture_frequency` | 嵌套 | 可选 | "low"/"medium"/"high" |
| `bg.src_url` | 嵌套 | 可选 | 背景图公网URL（**不要用background.file_id，实测不生效**） |
| `emotion` | 顶级 | 可选 | 情绪描述文字 |
| `model` | 顶级 | 可选 | 固定1 |

### 已知坑

| ❌ 错误 | ✅ 正确 |
|:--------|:--------|
| 数字人C-d开头ID填audio_man | 分开查list_common_audio获取音色ID |
| 手势幅度>0.6 | gesture_strength=0.35（日常）/0.2（心理） |
| 关lip_sync_precision | 必须high |
| TTS语速>1.15 | speed=0.95-1.0 |
| 照片克隆想有自然表情 | ❌ 不可能，必须视频克隆 |
| 不相信用户提供的参数去查文档说"不支持" | ❌ 用户经验优先于文档，先试再说 |
| SSML标签嵌入文案（`<break>`等） | ❌ REST API不支持，返回400。文案必须纯文本+标点控节奏 |
| background.file_id 传背景 | ❌ 不生效，改用 `bg.src_url` |
| volume放audio.tts内 | ❌ 返回"音量不能小于1"，volume放audio层级 |
| 克隆预览无声 | ✅ preview_url是webm无声版，要听声音需出测试视频 |

### 错误码速查

| 错误信息 | 原因 | 修复 |
|:---------|:-----|:------|
| `该数字人不存在` | person格式错/缺source:1/ID不在当前账号 | 加`source:1`，检查`person.id`格式 |
| `语速不能小于等于0` | 缺少 `speed` 参数，或 speed 不在 `audio.tts` 内部 | 放到`audio.tts.speed` |
| `音量不能小于1` | 缺少 `volume` 参数 | 加`volume:100` |
| `缺少audio_man` | 未传入 `audio_man` 音色ID | 参数名是`audio_man`不是`audio_man_id` |
| `该公共数字人： 不存在` | audio_man 音色ID 无效 | 从`list_common_audio`获取有效ID |
| `超出QPS限制` | 请求频率过高 | 等待10秒后重试 |
| `该文件还未完成上传，请稍后` | PUT上传后OSS同步未完成 | 等待15-20秒后再提交 |

### SSML转纯文本铁律

**婵镜REST API `create_video` 不支持任何SSML标签** — 传了返回400。仅在Web编辑器/MCP可用。

**替代方案：纯文本 + 标点断句控节奏。**

| SSML标签 | 替换为 | 说明 |
|:---------|:------|:-----|
| `<break time="200ms"/>` | `，` | 短停顿→逗号 |
| `<break time="0.3s"/>` | `，` | 同上 |
| `<break time="400ms"/>` | `。` | 中等停顿→句号 |
| `<break time="0.5s"/>` | `。` 或 `\n……` | 长停顿→句号+换行 |
| `<break time="1s"/>` | `\n……` | 情绪留白→换行+省略号 |
| `<emphasis level="moderate">关键词</emphasis>` | ` 关键词！` | 关键词前后加空格+感叹号，婵镜TTS自动加重 |

### 参数调试方法论

**不要一次性传全部参数。逐个添加定位错误参数：**

```bash
# 第一步：极简参数验证数字人可用
{"person":{"id":"ID","width":1080,"height":1920},
 "audio":{"tts":{"text":["测试"],"speed":1,"audio_man":"音色ID"},"type":"tts","volume":100},
 "screen_width":1080,"screen_height":1920}

# 第二步：逐个添加参数组，每加一组单独提交验证
```

**关键教训：** 用户提供的参数经验优先于文档。先试再说，不要因为文档没写就断言"不支持"。

## 视频克隆行为特征

- 视频克隆的数字人**保留原视频的全部动作**（关手机、撩头发、喝水等），AI只替换口型同步和声音
- 参数无法删除或修改原视频中的具体动作
- 仅能通过 `motion.gesture_strength` 控制AI新增手势的幅度
- **理想克隆素材：** 30-40秒，手放桌上或自然垂放，只说话不动手。不要使用带关手机、撩头发、拿物品等大动作的视频

## Web与API资产不互通

- Web端（chanjing.cc GUI）创建的图片数字人 → API端 `create_video` 返回「该数字人不存在」
- API端（`list_customised_person`）看到的数字人ID → 同端 `create_video` 可用
- **唯一解：通过API端提交克隆任务（`create_customised_person`）**
- 判断方法：收到数字人ID后先 `list_customised_person` 确认该ID出现在API端列表中

## 数字人克隆照片要求

| # | 类型 | 要求 |
|:-:|:----|:-----|
| 1 | 正面标准照 | 平视镜头、自然微笑、露额头耳朵下巴 |
| 2 | 45°左侧脸 | 头微左转，捕捉侧脸骨骼 |
| 3 | 45°右侧脸 | 头微右转，补齐另侧 |
| 4 | 大笑表情照 | 露齿笑，训练唇形肌肉 |
| 5 | 平静严肃照 | 无笑容，平衡表情跨度 |

**拍摄规范：** 室内柔光、关闭美颜、无遮挡、白墙背景、半身大头照
**AI生图不能替代真人实拍照片用于克隆。**

## 背景图选型指南

- 实景背景 > AI生成背景（观众一眼识别假背景）
- 背景要有景深感，不要纯色平涂
- 背景色跟穿搭不打架
- `bg.src_url` 传图，不要用 `background.file_id`
- 详见 `references/chanjing-background-guidelines.md`

## MCP说明（已废弃）

> **结论：MCP连接始终失败（403），推荐放弃MCP，使用原生API（curl脚本）。**

| 尝试 | 配置 | 结果 |
|:----|:-----|:-----|
| headers认证（旧） | `mcp_servers.chanjing.headers` + `mcp.chanjing.cc/mcp` | 403 |
| env认证（新） | `mcp.servers.chanjing.env` + `open-api.chanjing.cc/mcp` | 403 |

## 参考文档

- 婵镜API文档：`references/chanjing-documentation.md`
- 婵镜数字人/声纹删除：`references/chanjing-deletion-api.md`
- 婵镜背景图指南：`references/chanjing-background-guidelines.md`
- 婵镜数字人优化方案：`references/chanjing-digital-human-optimization.md`
- 婵镜凭证管理：`references/chanjing-credential-management.md`
- 婵镜API发现：`references/chanjing-api-discovery.md`
- 婵镜status=0排查：`references/chanjing-troubleshooting-status-0.md`
- 婵镜API参数参考：`references/chanjing-api-parameter-reference.md`
