# 婵镜API端点发现记录（2026-07-14 会话验证）

> 基础URL: `https://open-api.chanjing.cc`
> 文档: `https://doc.chanjing.cc`
> 关键突破：`source: 1` 参数解决Web/API不互通问题

## 认证

```bash
TOKEN=$(curl -s https://open-api.chanjing.cc/open/v1/access_token \
  -H "Content-Type:application/json" \
  -d "{\"app_id\":\"$APP_ID\",\"secret_key\":\"$SECRET_KEY\"}" | jq -r '.data.access_token')
```

## 数字人管理

| 操作 | 方法 | 端点 | 说明 |
|:----|:----|:-----|:------|
| 克隆提交 | POST | `/open/v1/create_customised_person` | 需先上传视频拿file_id |
| 拉取列表 | POST | `/open/v1/list_customised_person` | `{"source":1}`取Web端创建 |
| 拉取详情 | GET | `/open/v1/customised_person?id=xxx&source=1` | |
| 删除 | POST | `/open/v1/delete_customised_person` | `{"id":"xxx"}` |

### 核心坑：Web和API数字人不互通

用户声明：「Web页面和API的模型资产没有做数据打通」。Web端创建的DH在API端返回"该数字人不存在"。解决办法：**必须加 source:1 参数**或在API端重新克隆。

## 视频合成 - 数字人口播（主路径）

**端点：** `POST /open/v1/create_video`

### 标准请求体

```json
{
  "person": {"id": "C-xxx数字人ID", "width": 1080, "height": 1920},
  "audio": {
    "tts": {"text": ["口播文案"], "speed": 0.95, "audio_man": "音色ID"},
    "type": "tts", "volume": 100
  },
  "screen_width": 1080, "screen_height": 1920,
  "source": 1
}
```

**关键发现：**
- `person.id` 是嵌套字段（不是顶级`person_id`）
- `source: 1` 必须加 否则返回"该数字人不存在"
- `audio_man` 参数名是audio_man不是audio_man_id
- `text` 是数组格式，不支持字符串

### 可选参数

**model 高精度口型：** model:1（高质版lip-sync pro，2蝉豆/秒）

**bg 背景图：** 须先上传文件到婵镜
```json
{"bg": {"src_url": "公网URL", "width": 1080, "height": 1920}}
```
注意：width/height必须传，否则报错

**SSML停顿：** ❌ **REST API不支持**（返回400）。改用纯文本+标点控节奏：逗号=短停，句号=中停，换行+省略号=长停。详见 shuziren SKILL.md「SSML转纯文本铁律」章节。

### 查询视频状态

```bash
GET /open/v1/video?id={task_id}&source=1
# status: 10=处理中, 30=完成
# progress: 0-100
# video_url: 下载链接
```

### 实测错误码速查

| 错误 | 原因 | 修复 |
|:-----|:-----|:------|
| 该数字人不存在 | 缺source:1或person格式错 | 加source:1+检查person.id |
| 语速不能<=0 | speed缺失 | 放到audio.tts.speed |
| 音量不能<1 | volume缺失 | 加volume:100 |
| 缺少audio_man | audio_man字段缺失 | 参数名是audio_man |
| 该公共数字人： 不存在 | audio_man音色ID无效 | 从list_common_audio获取 |
| 背景图片宽度不能小于1 | bg缺width/height | 加bg.width和bg.height |
| 超出QPS限制 | 频率过高 | 等待10秒后重试 |

## 声音/音色

**端点：** `GET /open/v1/list_common_audio?page=1&size=50`

### 推荐女声

| 名称 | ID | 场景 |
|:----|:---|:-----|
| 知性女声 | `C-CASE-776889bb5e494074bb4beb4307c56059` | 心理/咨询/深度内容 |
| 情感女声 | `C-CASE-c81abd10266f47ee9173046e4fdd2dc5` | 情感故事 |
| 科普女声 | `c4fcaa1d58334917898149213e156d15` | 知识科普 |
| 带货小芸 | `f9248f3b1b42447fb9282829321cfcf2` | 通用/带货 |

## 文件管理

**获取上传地址：** `GET /open/v1/common/create_upload_url?service=make_video_background&name=bg.jpg`

上传步骤：
1. 获取sign_url和full_path
2. PUT上传文件到sign_url
3. 使用full_path作为bg.src_url

## Hermes MCP配置

结论：婵镜MCP始终403，推荐用原生API。尝试过headers和env两种认证方式均失败。
