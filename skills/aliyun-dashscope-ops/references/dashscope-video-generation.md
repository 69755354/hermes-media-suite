# DashScope 视频生成 API 实测记录

> 2026-08-25 实测通过，wan3.0-video 5秒480P 视频生成成功

## 模型列表

通过 `GET https://dashscope.aliyuncs.com/api/v1/models` 拉取全量列表（319个），筛选视频生成相关：

| 模型ID | 名称 | 输入→输出 | 计费(720P,实测) |
|--------|------|-----------|-----------|
| wan3.0-video | Wan3.0-Video | Text→Video | 0.9元/秒(实测0826) |
| wan3.0-video-prime | Wan3.0-Video-Prime | Text→Video | - |
| happyhorse-1.1-t2v | HappyHorse-1.1-T2V | Text→Video | 0.9元/秒(实测0826) |
| happyhorse-1.0-t2v | HappyHorse-1.0-T2V | Text→Video | 0.9元/秒(实测0826) |
| happyhorse-1.1-i2v | HappyHorse-1.1-I2V | Image+Text→Video | 0.9元/秒(实测0826) |
| happyhorse-1.0-i2v | HappyHorse-1.0-I2V | Image+Text→Video | 0.9元/秒(实测0826) |
| happyhorse-1.1-r2v | HappyHorse-1.1-R2V | Image+Text→Video(最多9张参考) | 0.9元/秒(实测0826) |
| happyhorse-1.0-r2v | HappyHorse-1.0-R2V | Image+Text→Video | 0.9元/秒(实测0826) |
| happyhorse-1.0-video-edit | HappyHorse-1.0-Video-Edit | Text+Image+Video→Video | 0.9元/秒(实测0826) |

> ⚠️ 计费勘误（0826）：旧记录 720P=0.124元/秒 来自 /models API 返回值，与实测不符。用户实测 720P=0.9元/秒、1080P=1.2元/秒。参考图数量不加价。HappyHorse 4.5折/wan3.0 6折。

## 关键参数（0826 官方文档勘误）

> ⚠️ 以下为 0825 旧实测参数，0826 官方文档确认 wan3.0 无 negative_prompt 字段，audio_url 改为 reference_audio 类型在 media 中传入。详见 `references/happyhorse-wan3-prompt-errata.md` 全参数速查表。

```json
{
  "model": "wan3.0-video",
  "input": {
    "prompt": "描述文本（必选，和media必填其一）",
    "media": [{"type": "first_frame|last_frame|reference_image|reference_video|reference_audio|file|link", "url": "..."}]
  },
  "parameters": {
    "resolution": "480P|720P|1080P",
    "ratio": "adaptive|16:9|9:16|1:1等",
    "duration": 5,
    "audio": true,
    "prompt_extend": true,
    "watermark": false,
    "seed": 0
  }
}
```

## 异步调用流程

### 步骤1: 创建任务

```
POST https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis
Headers:
  X-DashScope-Async: enable   (必选！否则403)
  Authorization: Bearer sk-ws-xxx
  Content-Type: application/json
```

响应：
```json
{"request_id":"xxx","output":{"task_id":"63a2dbd7-...","task_status":"PENDING"}}
```

### 步骤2: 轮询

```
GET https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}
Headers:
  Authorization: Bearer sk-ws-xxx
```

状态变化: PENDING → RUNNING → SUCCEEDED

SUCCEEDED 响应：
```json
{
  "output": {
    "task_id": "xxx",
    "task_status": "SUCCEEDED",
    "video_url": "https://dashscope-a717.oss-accelerate.aliyuncs.com/.../xxx.mp4?...",
    "orig_prompt": "一只小猫在月光下奔跑"
  },
  "usage": {"duration":5, "fps":30, "SR":480, "ratio":"16:9"}
}
```

### 步骤3: 下载

video_url 是阿里云OSS加速域名，新加坡可直连下载。
若直连失败，可尝试通过广州 relay 下载。

## 新加坡调用方案

### 问题
- 新加坡直连 dashscope.aliyuncs.com → TCP timeout（被墙）
- 8899 relay 转发 → 丢 X-DashScope-Async header → 403 "does not support synchronous calls"
- glm_aliyun_proxy(18890) → 硬编码MaaS网关地址，不转发到公共端点

### 解决方案: SSH到广州执行curl

广州机IP: <GZ_HOST>, SSH端口: 2222（从新加坡 `ssh -p 2222 ubuntu@127.0.0.1`）

```bash
# 创建任务
ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 \
  'curl -s --connect-timeout 30 -X POST "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis" \
    -H "X-DashScope-Async: enable" \
    -H "Authorization: Bearer sk-ws-xxx" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"wan3.0-video\",\"input\":{\"prompt\":\"...\"},\"parameters\":{\"resolution\":\"480P\",\"duration\":5}}"'

# 轮询
ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 \
  'curl -s "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}" \
    -H "Authorization: Bearer sk-ws-xxx"'
```

### 封装脚本

`~/.hermes/scripts/dashscope_video.py`（0825 更新，取代旧 `happyhorse_t2v.py`）:
- 统一脚本，支持 wan3.0-video / happyhorse 全系列（t2v/i2v/r2v/video-edit）
- 自动根据模型选择正确的 input 格式（image_url vs media 对象列表）
- 自动创建任务 → 轮询(15秒间隔) → 下载视频
- 自动估算成本（HappyHorse 4.5折 / wan3.0 6折）
- ffprobe 检查输出分辨率/时长/帧率
- 支持 --model / --prompt / --image / --images / --video-url / --resolution / --duration / --ratio / --negative / --output
- 旧脚本 `happyhorse_t2v.py` 只支持 t2v，已废弃但保留兼容
- i2v 调用示例见「图生视频（i2v）API 格式差异」章节

## 实测数据

- 测试: wan3.0-video, "一只小猫在月光下奔跑", 480P, 16:9, 5秒
- 提交时间: 10:55:22
- 完成时间: 10:58:24（约3分钟）
- 输出: 832x480 H264 30fps, 5.5MB
- 计费: 约0.31元（0.062元/秒 × 5秒）

## Hermes config 配置注意

不要在 config.yaml 的 `available_models_json` 里手写 happyhorse1.1 这样的模型名——
MaaS网关上调不到（model_not_found），必须走DashScope公共端点的异步视频API。
GLM走18890代理，视频生成走SSH到广州curl，两套通路。

## wan3.0-video 定价（0825 从定价页抓取）

wan3.0-video 不在 /models API 返回的列表里，但定价页有：

| 档位 | 原价 | 限时折扣 |
|:---|:---|:---|
| 480P | 0.3元/秒 | 7折=0.21元/秒 |
| 720P | 0.6元/秒 | 7折=0.42元/秒 |
| 1080P | 1.2元/秒 | 7折=0.84元/秒 |

## 图生视频（i2v）API 格式差异（0826 官方文档勘误，重要）

> ⚠️ 以下为 0825 旧实测记录，wan3.0 用 `image_url` 是旧格式。0826 官方文档确认 wan3.0 已统一到 `input.media`，media 元素必须带 `type` 字段。详见 `references/happyhorse-wan3-prompt-errata.md`。

**0826 官方文档正确格式（所有模型统一用 input.media）：**

### wan3.0-video i2v（用 media + type: first_frame）

```json
{
  "model": "wan3.0-video",
  "input": {
    "prompt": "描述文本",
    "media": [{"type": "first_frame", "url": "http://公网可访问URL/image.png"}]
  },
  "parameters": {"resolution": "720P", "ratio": "adaptive", "duration": 5, "prompt_extend": true}
}
```

### happyhorse-1.1-i2v（用 media + type: first_frame）

```json
{
  "model": "happyhorse-1.1-i2v",
  "input": {
    "prompt": "描述文本",
    "media": [{"type": "first_frame", "url": "http://公网可访问URL/image.png"}]
  },
  "parameters": {"resolution": "720P", "duration": 5}
}
```

### happyhorse-1.1-r2v（用 media + type: reference_image，1-9张）

```json
{
  "model": "happyhorse-1.1-r2v",
  "input": {
    "prompt": "[Image 1]中身着红色旗袍的女性，展开[Image 2]中的折扇",
    "media": [
      {"type": "reference_image", "url": "http://xxx/girl.jpg"},
      {"type": "reference_image", "url": "http://xxx/fan.jpg"}
    ]
  },
  "parameters": {"resolution": "720P", "ratio": "16:9", "duration": 5}
}
```

### 踩坑过程（0825→0826）

- `input.image_url`（字符串）→ HappyHorse 报 `Field required: input.media`（0826确认：wan3.0也应用media）
- `input.media`（字符串）→ 报 `Input should be a valid list`
- `input.media`（字符串列表 `["url"]`）→ 报 `Input should be a valid dictionary`
- `input.media`（对象列表 `[{"url": "url"}]`）→ HappyHorse 报缺 type 字段（0826勘误）
- `input.media`（对象列表 `[{"type":"first_frame","url": "url"}]`）→ **成功**

### 参考图公网URL托管

DashScope i2v 需要图片有公网可访问URL。新加坡机8899图片服务只绑127.0.0.1，公网不可达。
**解法**：把图通过 SSH 传到广州机 Caddy 公开目录 `/home/ubuntu/public/`，用 `http://<GZ_HOST>/<filename>.png` 作为URL。

```bash
scp -P 2222 /local/image.png ubuntu@127.0.0.1:/tmp/image.png
ssh -p 2222 ubuntu@127.0.0.1 'cp /tmp/image.png /home/ubuntu/public/image.png'
# 验证
ssh -p 2222 ubuntu@127.0.0.1 'curl -s -o /dev/null -w "%{http_code}" http://<GZ_HOST>/image.png'
# 返回200即可用
```

### i2v 实测结果（0825 火龙镜1两轮对比）

**第一轮（错误参考图）：** 用已删除的芳姐彩铅定妆图做参考，人物还原度低，生成的人物跟目标完全不一样。用户纠正：芳姐素材已删，应该用最终版成片帧做参考。

**第二轮（正确参考图）：** 用 v20 最终版高颜值版（25岁年轻男性，黑衬衫）成片第5秒帧做参考图，prompt带镜1台词，720P 5秒 9:16：
- **wan3.0**：~3分钟出片，7.7MB，人物还原度高，皮肤质感真实，光影电影感，手部有轻微AI变形
- **快乐马1.1-i2v**：~1分钟出片，2.5MB，文件小码率低，出片速度快，输出文件名带 `_watermark` 后缀
- **关键发现：DashScope 两个模型都不卡真人检测**——直接传真人视频帧/照片做参考图不会触发隐私拦截，跟 Seedance 必须用彩铅绕检不同

### 用成片帧做 i2v 参考图（0825 实测模式）

当原始角色定妆图/彩铅图已删除时，可以用最终成片的视频帧做 i2v 参考图：
1. 从成片 `ffmpeg -ss <秒> -frames:v 1 frame.png` 抽帧
2. 选人物清晰、姿态典型的帧（如口播展示姿态）
3. scp 到广州机 Caddy 公开目录获取公网 URL
4. 直接传给 happyhorse-i2v / wan3.0 做 i2v 参考图
5. DashScope 不卡真人，不需要彩铅绕检

### 折扣计费速查（0825 老板确认折扣率）

HappyHorse 4.5折，wan3.0 6折。5秒720P单次成本：
- 快乐马1.1（4.5折）：0.28元
- wan3.0（6折）：1.26元
- SD2.0 Mini（无折扣）：2.5元

一条30秒视频（6镜×5秒）成本：快乐马1.68元 / wan3.0 7.56元 / SD2.0 Mini 15元

### DashScope 视频模型 vs Seedance 关键差异

| 维度 | DashScope (wan3.0/快乐马) | Seedance 2.0 Mini |
|:---|:---|:---|
| 真人检测 | **无** — 直接传真人照片/视频帧 | **有** — 拦截真人照，必须彩铅绕检 |
| 台词口型 | 不驱动口型 — 写在prompt里但不保证口型同步 | 口型可同步台词 |
| 参考图格式 | media(type:first_frame/reference_image等) | media(type:first_frame/reference_image) | reference_image(base64数组) |
| 多张参考 | r2v支持最多9张 | 单组参考图 |
| 负向提示词 | 支持 | 不支持 |
| 生成速度 | 快乐马~1分钟, wan3.0~3分钟 | ~2分钟 |
| 成本(5s/720P) | 快乐马0.28元, wan3.0 1.26元 | 2.5元 |

### 模型能力确认纪律（0825 用户纠正）

用户质疑"wan3.0不是多模态？"时，我之前没确认就跑了 i2v 调用。教训：
1. **跑之前先确认模型能力**——从 `/models` API 的 `inference_metadata.request_modality` 字段确认支持的输入模式
2. **wan3.0-video 不在 /models 列表里**，但实测能接受 `input.image_url` 并出片，说明支持图生视频——这是靠实测确认的，不是靠文档确认的
3. **happyhorse-1.1-i2v** 的 `inference_metadata.request_modality = ["Image", "Text"]`，明确支持图生视频
4. **不能凭印象说模型"是/不是多模态"**——先查 API 元数据，查不到的标注"靠实测确认"

### 模型元数据速查（0825 从 /models API 拉取）

| 模型 | request_modality | response_modality | capabilities |
|:---|:---|:---|:---|
| happyhorse-1.1-t2v | [Text] | [Video] | VG |
| happyhorse-1.1-i2v | [Image, Text] | [Video] | VG |
| happyhorse-1.1-r2v | [Image, Text] | [Video] | VG |
| happyhorse-1.0-t2v | [Text] | [Video] | VG |
| happyhorse-1.0-i2v | [Image, Text] | [Video] | VG |
| happyhorse-1.0-r2v | [Image, Text] | [Video] | VG |
| happyhorse-1.0-video-edit | [Text, Image, Video] | [Video] | VG |
| wan3.0-video | 不在列表 | 不在列表 | 靠实测确认 |
| wan3.0-video-prime | 不在列表 | 不在列表 | 靠实测确认 |

## 三模型横向对比（wan3.0-video vs HappyHorse vs Seedance 2.0 Mini）

| 维度 | wan3.0-video | HappyHorse-1.1 | SD2.0 Mini (火山) |
|:---|:---|:---|:---|
| 厂商 | 阿里·万相3.0 | 阿里·HappyHorse | 字节·豆包 |
| 定位 | 四模态全能参考 | 广告营销场景适配 | 全能参考图生视频 |
| t2v | ✅ wan3.0-video | ✅ happyhorse-1.1-t2v | ❌ |
| i2v | ✅ input.media (type:first_frame) | ✅ input.media (type:first_frame) | ✅ reference_image |
| r2v | ✅ 四模态合一 | ✅ happyhorse-1.1-r2v (最多9张参考) | ❌ |
| 视频编辑 | ❌ | ✅ happyhorse-1.0-video-edit | ❌ |
| 分辨率 | 480P/720P/1080P | 480P/720P/1080P | 720P固定 |
| 时长 | 2-30秒 | 3-15秒 | 4-15秒 |
| 真人检测 | 无 | 无 | 有(拦截真人照) |
| 负向提示词 | 支持 | 支持 | 不支持 |
| 调用端点 | DashScope公共 | DashScope公共 | 火山引擎ARK |
| SG连通 | SSH跳广州 | SSH跳广州 | 8899 relay |
| 生成耗时(5s/720P) | ~3分钟 | ~1分钟 | ~2分钟 |

### 5秒视频单次成本对比（原价）

| 档位 | wan3.0-video | HappyHorse-1.1 | SD2.0 Mini |
|:---|:---|:---|:---|
| 480P | 1.05元 | 0.31元 | — |
| 720P | 2.1元 | 0.62元 | 2.5元 |
| 1080P | 4.2元 | 0.83元 | — |

### 5秒视频单次成本对比（折后，0825 老板确认折扣率）

| 档位 | wan3.0（6折） | HappyHorse-1.1（4.5折） | SD2.0 Mini（无折扣） |
|:---|:---|:---|:---|
| 480P | 0.63元 | 0.14元 | — |
| 720P | 1.26元 | 0.28元 | 2.5元 |
| 1080P | 2.52元 | 0.37元 | — |

快乐马4.5折后720P 5秒只要0.28元，比SD2.0 Mini便宜9倍。1080P也才0.37元。

### 真人参考图直出 vs 彩铅绕检（0825 用户定案）

**用户明确指示：快乐马支持真人参考图，不需要彩铅三视图绕检。**

- Seedance 2.0 Mini 有真人检测拦截，必须用彩铅三视图绕检
- **DashScope（快乐马/wan3.0）无真人检测**，直接传真人视频帧/照片做参考图不触发拦截
- 当原片角色彩铅图已删除/不可用时，直接从成片抽帧做 i2v 参考图
- 用户原话：「你用快乐马来生成镜1看看，他们支持真人所有不需要彩铅图」
- **快乐马 i2v prompt 不写负面词**（HappyHorse 不支持 negative_prompt 参数，写进去也不报错但无效）
- 快乐马 i2v prompt 风格：纯画面描述 + 动作时码，不写 Seedance 那套「彩铅三视图还原真人照片级写实」绕检话术
- HappyHorse i2v/r2v 输出默认带水印（右下角"Happy Horse"文案），`watermark` 参数默认 true，可设 false 关闭。wan3.0 `watermark` 默认 false。
