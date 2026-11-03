# HappyHorse / Wan3.0 提示词实测勘误

> 来源：用户提供三块实测数据（2026-08-25），与官方文档交叉核对
> 官方文档：
> - HappyHorse-R2V：https://help.aliyun.com/zh/model-studio/happyhorse-reference-to-video-api-reference
> - HappyHorse-I2V：https://help.aliyun.com/zh/model-studio/happyhorse-image-to-video-api-reference
> - Wan3.0：https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference

## 一、参考图引用语法（关键勘误）

### HappyHorse R2V：`[Image 1]` 标记
- prompt 中用 `[Image 1]`、`[Image 2]` 指代 media 数组中对应位置的参考图像
- 顺序与 media 数组顺序一致
- 使用时需指明参考图中的具体对象，如 `[Image 1]中身着红色旗袍的女性`
- 官方示例：
  ```
  "prompt": "[Image 1]中身着红色旗袍的女性，镜头先以侧面中景勾勒旗袍修身剪裁...展开[Image 2]中的折扇的同时，[Image 3]中的流苏耳坠..."
  ```

### Wan3.0：`图1` / `视频1` 标记
- prompt 中用 `图1`、`图2` 指代 reference_image（图和视频分别计数）
- prompt 中用 `视频1`、`视频2` 指代 reference_video
- 官方示例：
  ```
  "prompt": "视频1抱着图3，在图4的椅子上弹奏一支舒缓的乡村民谣，并说道：\"今天的阳光真好。\"图1手中拿着图2，路过视频1..."
  ```

### ⚠️ 与 Seedance 完全不同
- Seedance（火山）用 `@图1` `@图2` — **火山专属语法，阿里不识别**
- 阿里用 `[Image 1]`（HappyHorse）或 `图1`（Wan3.0）
- **不能混用**

## 二、R2V vs I2V 本质区别（文档不会写，实测得出）

| 维度 | R2V（参考生视频） | I2V（图生视频） |
|:---|:---|:---|
| 图片角色 | **角色参考**（不锁首帧） | **视频第一帧**（首帧） |
| 锁人物全程 | 不保证 | 不保证（只是起点） |
| 参考图数量 | HappyHorse 1-9张 | HappyHorse 仅1张 |
| Wan3.0参考素材 | 最多10张图+5视频+5音频 | first_frame 最多1张 |
| 用途 | 多角色/多素材融合 | 从一张图开始生成视频 |

**关键理解**：I2V的图片是视频的第一帧，但模型可以自由演化后续画面，不会全程锁定人物外观。R2V的图片是角色参考，模型参考其外观特征但不以它为首帧。

## 三、提示词坑（实测得出，文档不写）

### 1. SD权重语法完全无效
- `(面部:1.3)` `(xxx:1.2)` 等 Stable Diffusion 权重语法 → **完全无效**
- 模型不会加权，当成普通文本处理
- 偶发画面出现乱字

### 2. 英文双引号极易生成画面字幕
- `"台词"` 用英文双引号包裹的内容 → **极易把引号内文字渲染到画面上**
- 如需写台词，用自然语言描述：`人物说：xxx` 或中文引号

### 3. 大括号不触发语音
- `{对白}` 不会触发语音生成，大括号是**普通字符**
- 这是 Seedance 火山专属语法，阿里两个模型不识别
- 台词写法：用自然语言 `人物说：xxx`

### 4. 负向提示词效果弱
- HappyHorse 无 negative_prompt 参数
- Wan3.0 文档未提供 negative_prompt 字段
- 禁止条件优先写在正向提示词末尾，效果更好

### 5. 不能上传外部音频驱动口型
- 两个模型都不能上传外部 wav 音频文件驱动口型
- 只能依赖模型内部生成语音
- Wan3.0 `reference_audio` 类型是参考音频（音色参考），不是口型驱动

## 四、HappyHorse R2V 官方 curl 样例

```bash
curl --location 'https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis' \
-H 'X-DashScope-Async: enable' \
-H "Authorization: Bearer $DASHSCOPE_API_KEY" \
-H 'Content-Type: application/json' \
-d '{
  "model": "happyhorse-1.1-r2v",
  "input": {
    "prompt": "[Image 1]中身着红色旗袍的女性，镜头先以侧面中景勾勒旗袍修身剪裁与S型曲线，随即切换至低角度仰拍，捕捉她轻抬玉手展开[Image 2]中的折扇的同时，[Image 3]中的流苏耳坠随头部转动轻盈摆动的细节，最后推近至面部特写。",
    "media": [
      {"type": "reference_image", "url": "https://xxx/girl.jpg"},
      {"type": "reference_image", "url": "https://xxx/fan.jpg"},
      {"type": "reference_image", "url": "https://xxx/earrings.jpg"}
    ]
  },
  "parameters": {
    "resolution": "720P",
    "ratio": "16:9",
    "duration": 5
  }
}'
```

## 五、Wan3.0 官方 curl 样例（参考生视频）

```bash
curl --location 'https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis' \
-H 'X-DashScope-Async: enable' \
-H "Authorization: Bearer $DASHSCOPE_API_KEY" \
-H 'Content-Type: application/json' \
-d '{
  "model": "wan3.0-video",
  "input": {
    "prompt": "视频1抱着图3，在图4的椅子上弹奏一支舒缓的乡村民谣，并说道：今天的阳光真好。图1手中拿着图2，路过视频1，把手中的图2放到视频1旁边的桌子上，并说道：真好听，能不能再唱一遍。",
    "media": [
      {"type": "reference_image", "url": "https://xxx/girl.jpg"},
      {"type": "reference_video", "url": "https://xxx/role2.mp4"},
      {"type": "reference_image", "url": "https://xxx/object3.png"},
      {"type": "reference_image", "url": "https://xxx/object4.png"},
      {"type": "reference_image", "url": "https://xxx/background5.png"}
    ]
  },
  "parameters": {
    "resolution": "480P",
    "ratio": "adaptive",
    "duration": 5,
    "prompt_extend": true
  }
}'
```

## 六、Wan3.0 全参数速查

| 参数 | 说明 | 默认值 |
|:---|:---|:---|
| resolution | 480P/720P/1080P | 1080P |
| ratio | adaptive/16:9/9:16/1:1/3:4/4:3/4:5/5:4/9:21/21:9 | adaptive |
| duration | [2,30]整数；有视频输入时总时长≤30s；-1=智能时长 | 5 |
| audio | true/false 输出是否含音频 | true |
| prompt_extend | true/false 智能改写prompt | true |
| watermark | true/false 水印 | false |
| seed | [0,2147483647] 随机种子 | 随机 |

## 七、HappyHorse 全参数速查

### R2V
| 参数 | 说明 | 默认值 |
|:---|:---|:---|
| resolution | 480P/720P/1080P | 1080P |
| ratio | 16:9/9:16/3:4/4:3/4:5/5:4/1:1/9:21/21:9 | 16:9 |
| duration | [3,15]整数 | 5 |
| watermark | true/false（文案"Happy Horse"） | true |
| seed | [0,2147483647] | 随机 |

### I2V
| 参数 | 说明 | 默认值 |
|:---|:---|:---|
| resolution | 480P/720P/1080P | 1080P |
| duration | [3,15]整数 | 5 |
| watermark | true/false | true |
| seed | [0,2147483647] | 随机 |
| 注意 | I2V 无 ratio 参数（跟随首帧图比例） | — |

> ⚠️ **快乐马全系列无 `audio` 参数，但输出默认含音频**（0825 实测：i2v/r2v 出片均带 aac 24kHz 音轨，台词用 `人物说：xxx` 触发模型内部生成语音）。旧文档「无声」说法错误，已勘误。

## 八、计费（用户实测数据）

- R2V/I2V 同价，只看分辨率和输出时长
- 参考图数量不加价
- 720P = 0.9元/秒，1080P = 1.2元/秒
- HappyHorse 4.5折 / wan3.0 6折（折扣需核对官方价格页）
