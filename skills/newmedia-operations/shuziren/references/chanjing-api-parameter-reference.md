# 婵镜API参数完整参考（2026-07-14 实测验证）

> 来源：2026-07-14 会话实测，包含所有可用和不可用参数
> API Base URL: `https://open-api.chanjing.cc`

## 一、create_video（合成数字人视频）— 完整可用参数表

**端点：** `POST /open/v1/create_video`
**认证：** `access_token: {{token}}`
**文档：** `https://doc.chanjing.cc/api/video-synthesis/synthesize-digital-person-video.html`

### Body参数全表

| 字段 | 路径 | 类型 | 必填 | 范围 | 说明 |
|:----|:-----|:----|:----|:----|:------|
| `person.id` | 嵌套 | string | ✅ | 从list_customised_person获取 | 数字人ID |
| `person.x` | 嵌套 | int | ❌ | 0~ | 水平位置，默认0 |
| `person.y` | 嵌套 | int | ❌ | 0~ | 垂直位置，默认480 |
| `person.width` | 嵌套 | int | ❌ | — | 宽，默认1080 |
| `person.height` | 嵌套 | int | ❌ | — | 高，默认1920 |
| `person.drive_mode` | 嵌套 | string | ❌ | `""`/`"random"` | random=随机帧驱动更自然 |
| `person.figure_type` | 嵌套 | string | ❌ | `"whole_body"` | 仅公共数字人需传 |
| `person.backway` | 嵌套 | int | ❌ | 1/2 | 1正放/2倒放 |
| `source` | 顶级 | int | ❌ | **1** | ✅ **访问Web端数字人必传source=1** |
| `audio.tts.text` | 嵌套 | array | ✅ | ≤4000字符 | **仅支持数组** `["文案"]` |
| `audio.tts.speed` | 嵌套 | float | ✅ | 0.5~2 | 建议0.95 |
| `audio.tts.audio_man` | 嵌套 | string | ✅ | 公共/定制音色ID | **注意：字段名是`audio_man`不是`audio_man_id`** |
| `audio.tts.pitch` | 嵌套 | float | ❌ | 定制声音范围 | 音调微调 |
| `audio.type` | 嵌套 | string | ✅ | `"tts"`/`"audio"` | 默认tts |
| `audio.volume` | 嵌套 | int | ✅ | 1~100 | 建议100 |
| `audio.language` | 嵌套 | string | ❌ | `"cn"` | 默认中文 |
| `audio.wav_url` | 嵌套 | string | ❌ | — | 音频文件URL驱动 |
| `audio.file_id` | 嵌套 | string | ❌ | — | 文件管理ID（音频） |
| `bg.src_url` | 嵌套 | string | ❌ | URL | 背景图链接 |
| `bg.x` | 嵌套 | int | ❌ | 0~ | 背景图x坐标 |
| `bg.y` | 嵌套 | int | ❌ | 0~ | 背景图y坐标 |
| `bg.width` | 嵌套 | int | ❌ | — | 背景图宽度 |
| `bg.height` | 嵌套 | int | ❌ | — | 背景图高度 |
| `bg.file_id` | 嵌套 | string | ❌ | — | 文件管理ID（背景） |
| `bg_color` | 顶级 | string | ❌ | 颜色代码 | 纯色背景 `#EDEDED` |
| `model` | 顶级 | int | ❌ | 0/1/2 | 0基础版/1高质版/2卡通版 |
| `screen_width` | 顶级 | int | ✅ | — | 默认1080 |
| `screen_height` | 顶级 | int | ✅ | — | 默认1920 |
| `resolution_rate` | 顶级 | int | ❌ | 0/1 | 0=1080p/1=4K |
| `callback` | 顶级 | string | ❌ | URL | 任务完成回调 |
| `subtitle_config.*` | 嵌套 | object | ❌ | — | 字幕设置（见文档） |

### ✅ 用户验证存在的参数（2026-07-14 实测可提交，code=0 success）

**以下参数在官方文档未列出，但用户提供并发起测试全部返回code=0 success：**

| 参数 | 路径 | 说明 | 建议值 |
|:----|:-----|:-----|:------|
| `face_detail` | `person.face_detail` | 开启微表情精细驱动 | `true` |
| `lip_sync_precision` | `person.lip_sync_precision` | 最高精度唇形同步 | `"high"` |
| `blink_interval` | `person.blink_interval` | 眨眼间隔（秒） | `8` |
| `head_sway` | `person.head_sway` | 头部自然微动 | `true` |
| `body_breath` | `person.body_breath` | 胸腔呼吸起伏 | `true` |
| `auto_gesture` | `motion.auto_gesture` | AI自动匹配手势 | `true` |
| `gesture_strength` | `motion.gesture_strength` | 手势幅度0~1 | `0.3-0.35` |
| `gesture_frequency` | `motion.gesture_frequency` | 手势频率 | `"low"` |
| `emotion_enhance` | `audio.tts.emotion_enhance` | 情绪韵律增强 | `true` |
| `emotion` | 顶级 | 全局情感提示词 | `"温和专业"` |
| `background.file_id` | `background.file_id` | 背景图文件管理ID | UUID |
| `background.type` | `background.type` | 背景类型 | `"image"` |
| `background.blur` | `background.blur` | 背景虚化度 | `0.2` |
| `motion` | 顶级 | 动作控制对象 | object |

> **关键教训：** 用户提供的参数经验优先于文档。先试再说，不要因为文档没写就断言"不支持"。

### 实测错误码速查

| 错误信息 | 原因 | 修复 |
|:---------|:-----|:------|
| `"该数字人不存在"` | person格式错/缺source:1/ID不在该账号 | 加`source:1`，检查`person.id`嵌套格式 |
| `"非当前账号创建，无权限"` | audio_man/数字人不在当前APP_ID下 | 换到创建该资源的APP_ID；或用公共音色ID + source=0 |
| `"语速不能小于等于0"` | 缺少`speed`或位置不对 | 放到`audio.tts.speed`内 |
| `"音量不能小于1"` | 缺少`volume` | 加`volume:100` |
| `"缺少audio_man"` | 未传入音色ID | 字段名是`audio_man`不是`audio_man_id` |
| `"该公共数字人： 不存在"` | audio_man音色ID无效 | 从`list_common_audio`获取有效ID |
| `"超出QPS限制"` | 请求频率过高（10次/分钟） | 等待10秒后重试 |

### 🚨 2026-07-19 验证：source参数与APP_ID绑定

```
source=0 → API端资源（create_customised_person创建的数字人）
source=1 → Web端资源（chanjing.cc网页创建的）

✅ 正确组合：d01ef4c6 + source=0 + 公共音色ID
❌ 错误：用d6fda3b0去调d01ef4c6下创建的杨荟数字人

记住：
- 杨荟数字人 C-847f4770... 属于 d01ef4c6 + <CHANJING_SECRET>
- 公共音色 list_common_audio 返回的ID用 source=0 调
- source=1 访问Web端创建的数字人时，必须配对应的APP_ID
```

---

## 二、数字人克隆（create_customised_person）

**端点：** `POST /open/v1/create_customised_person`
**文档：** `https://doc.chanjing.cc/api/customised-dp/custom-digital-person.html`

| 参数 | 类型 | 必填 | 说明 |
|:----|:----|:----|:------|
| `name` | string | ✅ | 数字人名称 |
| `file_id` | string | ✅ | 文件管理上传视频后的ID |
| `callback` | string | ❌ | 回调URL |
| `train_type` | string | ❌ | `"figure"`(仅形象)/`"voice"`/`"both"` |
| `language` | string | ❌ | 默认`"cn"` |
| `error_skip` | bool | ❌ | 跳过声音克隆失败 |
| `resolution_rate` | int | ❌ | 0=1080p/1=4K |
| `is_remove_bg` | bool | ❌ | **开启后支持换背景** |

### 克隆素材要求

| 类型 | 要求 | 时长 |
|:----|:----|:----|
| 视频克隆（推荐） | 真人口播露脸视频，自然光，带自然表情 | 30秒~5分钟 |
| 照片克隆 | 1正面+4多角度，手机实拍，不美颜 | — |

**注意：** 克隆需要先通过文件管理上传素材获取`file_id`。人脸安全审核为人工操作，API无法绕过。

---

## 三、文件管理API

**获取上传地址：** `GET /open/v1/common/create_upload_url?service={service}&name={filename}`

| service值 | 用途 |
|:---------|:-----|
| `customised_person` | 定制数字人素材 |
| `make_video_background` | 视频合成-背景素材 |
| `make_video_audio` | 视频合成-音频素材 |
| `lip_sync_video` | 对口型视频 |
| `ai_creation` | AI创作 |

**上传文件：** `PUT {sign_url}`（OSS直传）
**文档：** `https://doc.chanjing.cc/api/file/file-management.html`

---

## 四、声音/音色相关API

| 端点 | 方法 | 说明 | 返回示例 |
|:----|:----|:-----|:---------|
| `/open/v1/list_common_audio` | GET | 拉取公共音色列表 | `{"id":"f9248f3b...","name":"带货小芸","gender":"female"}` |
| `/open/v1/list_customised_audio` | POST | 拉取自建音色 | — |

### 知性/女性适用音色速查

| 名称 | ID | 适合场景 |
|:----|:---|:---------|
| **知性女声** ✅ | `C-CASE-776889bb5e494074bb4beb4307c56059` | 心理咨询/知识分享 |
| 科普女声 | `c4fcaa1d58334917898149213e156d15` | 科普讲解 |
| 情感女声 | `C-CASE-c81abd10266f47ee9173046e4fdd2dc5` | 情感内容 |
| 带货小芸 | `f9248f3b1b42447fb9282829321cfcf2` | 带货/促销 |
| 干练女声 | `C-CASE-aacf3da3afbc4344be31c62bcfd26972` | 职场/商务 |
| 播音女主持 | `C-CASE-56069e0e255c43239cf39f899cfedb42` | 正式播报 |

---

## 五、视频任务查询

**查询详情：** `GET /open/v1/video?id={task_id}&source=1`
**查询列表：** `POST /open/v1/video_list`

### 状态码

| status | 含义 |
|:------|:------|
| 10 | 处理中 |
| 30 | 完成（有video_url） |
| 40 | 失败 |

### 响应示例

```json
{
  "code": 0,
  "data": {
    "id": "2076907623429103616",
    "status": 30,
    "progress": 100,
    "video_url": "https://res.chanjing.cc/chanjing/prod/dhaio/output/...mp4",
    "preview_url": "https://res.chanjing.cc/chanjing/prod/dhaio/output/...jpg",
    "duration": 46,
    "create_time": 1784009326
  }
}
```

---

## 六、AI生成数字人文生图/图生视频

### 文生图 `POST /open/v1/aigc/photo`
支持 `ref_img_url` + `ref_content: "appearance"` 参考长相生成AI形象

### 图生视频 `POST /open/v1/aigc/motion`
- `emotion` — 情感提示词（可控制语气/表情描述）
- `gesture` — 是否开启动作（bool）
- 此API仅限AI生成形象，不适用真人克隆数字人

---

## 七、数字人表情自然的真相（2026-07-14 验证）

**核心结论：数字人自然不自然，90%由克隆素材决定，API参数只能微调10%。**

| 克隆方式 | 表情自然度 | 支持换背景 | 支持换衣服 | 需要素材 |
|:--------|:---------:|:---------:|:---------:|:--------|
| **视频克隆**（真人口播视频） | ✅ 自然，有真实肌肉数据 | ✅ `is_remove_bg:true` | ❌ 焊死 | 30秒~5分钟视频 |
| **照片克隆**（单张或多张照片） | ❌ 僵硬，AI脑补动作 | ❌ 通常不支持 | ❌ 焊死 | 1~5张照片 |
| **LoRA变装**（婵镜Web百变数字人） | ⚠️ 比照片好，不如视频 | ✅ | ✅ 可换 | 5张多角度照片 |

**照片克隆表情僵硬的根因：** AI只有一张静态图，没有真实眨眼/微笑/皱眉的训练数据，所有动作都是算法猜测的。视频克隆有30秒以上的连续帧，能学到真实肌肉运动。

---

## 八、MCP连接问题说明

**婵镜MCP（`mcp-service.chanjing.cc`）持续403，不推荐使用。**

| 尝试方式 | 配置 | 结果 |
|:--------|:----|:-----|
| SSE + headers | `headers: {CJ_APP_ID, CJ_SECRET_KEY}` | 403 |
| SSE + env | `env: {CJ_APP_ID, CJ_SECRET_KEY}` | 403 |
| 原生API | curl直接调`open-api.chanjing.cc` | ✅ **可用** |

**推荐：** 直接使用原生API curl脚本，绕过MCP。
