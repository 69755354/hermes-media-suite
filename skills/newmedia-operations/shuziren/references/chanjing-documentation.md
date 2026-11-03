# 婵镜 API 文档

> 婵镜数字人视频生成API | Base URL: `https://open-api.chanjing.cc`
> 适用工作流：shuziren（数字人通道）
> 注意：与火山引擎通道（huoshan）不通用

---

## 1. 接入配置

| 参数 | 值 |
|:----|:----|
| Base URL | `https://open-api.chanjing.cc` |
| app_id | `d01ef4c6` |
| secret_key | 环境变量 `CHANJING_SECRET_KEY` |
| Token有效期 | 1天，每天首次调用需重新获取 |

---

### 认证方式

婵镜API认证使用 **`access_token` HTTP Header** 传递Token，**不是** `Authorization: Bearer`。

```
access_token: ${access_token}
```

### 获取Token

**请求：**
```
POST /open/v1/access_token
Content-Type: application/json
POST /open/v1/access_token
{
  "app_id": "d01ef4c6",
  "secret_key": "${CHANJING_SECRET_KEY}"
}
```

**响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "access_token": "xxx...xxx",
    "expire_in": 86400
  }
}
```

**注意事项：**
- Token 24小时过期，过期后需重新获取
- 建议每次任务提交前先检查Token有效性
- secret_key 从环境变量 `CHANJING_SECRET_KEY` 读取，不硬编码

---

## 2. 查询数字人克隆任务状态（customised_person）

**用途：** 查询数字人克隆训练任务的进度和结果。

### 查询单个数字人

**请求：**
```
GET /open/v1/customised_person?id={person_id}&source=0
access_token: ${access_token}
```

| 参数 | 类型 | 必填 | 说明 |
|:-----|:-----|:----|:------|
| id | string | ✅ | 数字人ID，参数名是 `id=` **不是** `person_id=` |
| source | int | ✅ | `0`=API端创建的数字人，`1`=Web端 |

**响应字段说明：**

| 字段 | 类型 | 说明 |
|:-----|:-----|:------|
| id | string | 数字人ID |
| name | string | 数字人名称（如"杨荟_视频克隆"） |
| status | int | **0=不存在/未开始, 1=进行中, 2=成功, 4=失败** |
| progress | int | 进度 0~100 |
| audio_man_id | string | 克隆训练时自动生成的音色ID |
| preview_url | string | 预览视频URL（训练完成时返回） |
| pic_url | string | 封面图URL |
| is_support_remove_bg | bool | 是否支持抠背景换场景 |
| err_reason | string | 失败原因（status=4时有值） |

**响应示例（成功）：**
```json
{
  "code": 0,
  "data": {
    "id": "C-22494d1415e14c81bf8d49187a1083b4",
    "name": "杨荟_视频克隆",
    "type": "person",
    "status": 2,
    "progress": 100,
    "audio_man_id": "C-fb658593522941d38e4d004426d49826",
    "preview_url": "https://res.chanjing.cc/chanjing/webm_resize/.../xxx.webm",
    "is_support_remove_bg": true
  }
}
```

**响应示例（空/不存在）：**
```json
{
  "code": 0,
  "data": {
    "id": "", "name": "", "status": 0,
    "progress": 0, "audio_man_id": ""
  }
}
```

### 轮询逻辑

- status=1（进行中）→ 等待5-10秒后重查
- status=2（成功）→ 取出 preview_url 给用户预览，记录 person_id 和 audio_man_id
- status=4（失败）→ 取出 err_reason 告知用户失败原因
- status=0（不存在）→ 确认数字人ID和source值是否正确

### ⚠️ 多账号坑（2026-07-14 验证）

**用户有多组婵镜APP_ID/SECRET_KEY，数字人/数字人分别在不同账号下。** 用错APP_ID查数字人ID会返回空（status=0）。

| 已知账号 | APP_ID | SECRET_KEY | 用途 |
|:--------|:-------|:-----------|:-----|
| 主账号 | `d01ef4c6` | 环境变量 | 用于数字人克隆（杨荟视频克隆在此账号下） |
| 副账号 | `d6fda3b0` | 查环境变量 | 另一组凭证 |

**查询数字人前必须先确认该数字人属于哪个APP_ID账号，用对应账号的token查询。**

---

## 3. 提交视频任务（每镜一次）

**请求：**
```
POST /open/v1/ai_creation/task/submit
Content-Type: application/json
access_token: ${access_token}

{
  "ref_resources": [
    {"url": "角色图URL", "file_type": "image"},
    {"url": "场景图URL", "file_type": "image"}
  ],
  "ref_prompt": "节点8输出的完整prompt",
  "creation_type": 4,
  "aspect_ratio": "9:16",
  "clarity": 720,
  "video_duration": 5,
  "model_code": "seedance-2.0-lite-mini"
}
```

**参数说明：**

| 参数 | 类型 | 必填 | 说明 |
|:-----|:-----|:----|:------|
| ref_resources | array | ✅ | 参考图URL列表，最多支持多图（全能参考多图模式） |
| ref_resources[].url | string | ✅ | 图片的公网可访问URL |
| ref_resources[].file_type | string | ✅ | 固定为 `"image"` |
| ref_prompt | string | ✅ | 节点8输出的完整prompt，直接复用，不自编简版 |
| creation_type | int | ✅ | 固定为 `4` |
| aspect_ratio | string | ✅ | `"9:16"`（竖屏） |
| clarity | int | ✅ | `720` 或 `1080` |
| video_duration | int | ✅ | 每镜秒数（根据分镜定时长） |
| model_code | string | ✅ | `"seedance-2.0-lite-mini"` |

**响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": "uuid-string"
}
```

> ⚠️ 注意：submit返回的 `data` 字段是 **字符串（UUID）**，不是对象。不是 `data.unique_id`。提交成功后立即用该UUID调用查询接口获取结果。

---

## 4. 查询任务结果

**请求：**
```
GET /open/v1/ai_creation/task?unique_id={uuid}
access_token: ${access_token}
```

**响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "unique_id": "uuid-string",
    "progress_desc": "Success",
    "output_url": [
      "https://cdn.chanjing.cc/video/xxx.mp4"
    ]
  }
}
```

**progress_desc 状态流转：**
```
Queued → Ready → Generating → Success
                    ↓
                   Error
```

| 状态 | 说明 | 操作 |
|:----|:-----|:-----|
| Queued | 排队中 | 等待5秒后重查 |
| Ready | 就绪待处理 | 等待5秒后重查 |
| Generating | 生成中 | 等待5秒后重查 |
| Success | 生成完成 | 取出 output_url[0] 下载视频 |
| Error | 生成失败 | 重试提交（上限5次） |

---

## 5. 数字人通道特殊规则

| 规则 | 说明 |
|:----|:------|
| ✅ 写实人物图直传 | 婵镜不拦截写实人物图，无需彩绘绕真人检测 |
| ✅ 公网URL传图 | 所有参考图必须上传至公网可访问URL，不支持base64 |
| ✅ 支持duration | 每镜可独立控制时长 |
| ✅ 每镜独立提交 | 每镜一个任务，拿到output_url后再跑下一镜 |
| ✅ prompt直接写写实 | prompt直接写「照片级写实，无CG感」，不写「从彩绘还原」 |
| ⚠️ 重试上限 | 每镜重试不超过5次 |

---

## 6. 参考图URL管理

| 图类型 | 来源 | 上传方式 |
|:------|:-----|:---------|
| 🧑 角色图 | 节点6 Seedream生成 | uguu.se / COS |
| 🏪 门头实景 | 用户提供 | uguu.se / COS |
| 🛋️ 店内实景 | 用户提供 | uguu.se / COS |

---

## 7. 常见错误处理

| 错误 | 原因 | 处理 |
|:----|:-----|:-----|
| Token过期 | 超过24小时未刷新 | 重新获取access_token |
| 任务超时 | 生成超过60秒无结果 | 重试查询最多10次，每次间隔5秒 |
| 视频质量不达标 | 画面崩坏/嘴形不对 | 调整duration或重试 |
| 参考图URL失效 | 临时URL过期 | 重新上传至稳定CDN |
| 权限错误 | secret_key/app_id不匹配 | 检查环境变量配置 |
