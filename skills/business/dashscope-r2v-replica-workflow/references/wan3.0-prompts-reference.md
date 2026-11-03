# wan3.0 + HappyHorse 官方提示词参考库

> 来源：阿里云百炼文档 2026-08-26 更新版
> 文档地址：
> - wan3.0: https://www.alibabacloud.com/help/zh/model-studio/wan3-video-generation-guide
> - HappyHorse API参考: https://www.alibabacloud.com/help/zh/model-studio/happyhorse-api-reference/
> - HappyHorse 文生视频: https://www.alibabacloud.com/help/zh/model-studio/happyhorse-text-to-video-api-reference
> - HappyHorse 参考生视频: https://www.alibabacloud.com/help/zh/model-studio/happyhorse-reference-to-video-api-reference
> - 完整本地副本：`wiki/assets/dashscope/wan3.0-prompts-reference.md`

## wan3.0 模型概览

wan3.0-video / wan3.0-video-prime 是 All-in-One 视频生成模型，无需切换模型名称即可覆盖全部任务类型。模型根据 `input.media` 中的 `type` 字段和提示词意图自动路由。

### 核心能力

| 能力 | 触发方式 | 关键参数 |
|:---|:---|:---|
| 文生视频 | 仅传入 prompt，不传 media | resolution/ratio/duration/-1智能时长 |
| 首帧生视频 | type=first_frame | ratio=adaptive |
| 首尾帧生视频 | type=first_frame + last_frame | ratio=adaptive |
| 全模态参考 | type=reference_image/reference_video/reference_audio | 最多20个素材 |
| 文件/网页生视频 | type=file / link | 各限1个，互斥 |
| 视频编辑 | type=reference_video + 编辑意图词 | ratio=adaptive, duration=-1 |
| 视频延长 | type=reference_video + 延长意图词 | ratio=adaptive, 总时长≤30s |

### 输入素材限制

| type | 说明 | 限制 |
|:---|:---|:---|
| first_frame | 首帧图像 | 最多1张 |
| last_frame | 尾帧图像 | 最多1张 |
| reference_image | 参考图像 | 最多10张，单张≤20MB |
| reference_video | 参考视频 | 最多5段，总时长≤15s，单文件≤100MB |
| reference_audio | 参考音频 | 最多5段，总时长≤15s，单文件≤15MB |
| file | 文档(docx/xlsx/pptx/pdf/txt/md) | 最多1个，与link互斥 |
| link | 公开网页 | 最多1个，与file互斥 |

> reference_xx/file/link 与 first_frame/last_frame 互斥，不能混用。

### 输出参数

| 参数 | 默认值 | 可选值 |
|:---|:---|:---|
| resolution | 1080P | 480P / 720P / 1080P |
| ratio | adaptive | 16:9 / 4:3 / 1:1 / 3:4 / 9:16 / adaptive |
| duration | -1(智能,默认5s) | 2-30秒 / -1 |
| prompt_extend | - | true / false |
| audio | 开 | true / false |

### API 端点（新加坡地域，业务空间专属域名）

```
POST https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis
Header: X-DashScope-Async: enable
Header: Authorization: Bearer $DASHSCOPE_API_KEY
Header: Content-Type: application/json

GET https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api/v1/tasks/{task_id}
```

> 注意：新加坡直连被墙，需SSH到广州机执行curl。见 `aliyun-dashscope-ops` skill。

## 官方示例提示词索引

### 文生视频

| # | 提示词 | 时长 | 格式 |
|:---|:---|:---|:---|
| 1 | 毛绒宇宙冒险 | 20s | 单镜头描述 |
| 2 | 女牛仔给马加草 | 30s | 分镜格式(0-8s/8-16s/16-24s/24-30s) |
| 3 | 暗黑奇幻3D动画 | 30s | 单镜头+配音描述 |

### 图生视频

| # | 提示词 | 时长 | 格式 |
|:---|:---|:---|:---|
| 4 | 水墨竹林刀客(首帧) | 20s | 分镜格式(0:00-0:03等) |
| 5 | 西湖水神西子(首尾帧) | 15s | 一镜到底+配音+音效 |

### 全模态参考

| # | 提示词 | 时长 | 素材 |
|:---|:---|:---|:---|
| 6 | 角色替换+音色提取+口型驱动 | 15s | 图+视频+音频 |
| 7 | 多角色多物品交互 | 5s | 5张图+1视频 |

### 参考文件

| # | 提示词 | 时长 | 素材 |
|:---|:---|:---|:---|
| 8 | 智能眼镜产品广告 | 10s | PPT文件 |
| 9 | 跨境电商GMV数据可视化 | 22s | Excel文件(4片段) |

### 视频编辑

| # | 提示词 | 操作 |
|:---|:---|:---|
| 10 | 转黏土风格 | 风格转换 |
| 11 | 改英文台词 | 台词编辑 |
| 12 | 换帽子换衣服(3张参考图) | 参考编辑 |

### 视频延长

| # | 提示词 | 时长 | 方向 |
|:---|:---|:---|:---|
| 13 | 面包师烤面包 | - | 向后延长 |
| 14 | 华尔兹舞会 | 15s | 向前延长 |
| 15 | 雪林女孩 | 5s | 双向延长 |

> 完整提示词文本见 `wiki/assets/dashscope/wan3.0-prompts-reference.md`

## 提示词写法规律

### 分镜格式特征
- 每镜头 4-6 秒，时间戳标注格式 `(0:00 - 0:03)` 或 `[0-3秒]`
- 单镜头要素：运镜 + 画面 + 动作 + 细节 + 氛围
- 多镜头叙事支持最长 30 秒

### 提示词结构模板
1. **全局设定**：风格/质感/色彩/场景/角色描述
2. **配音与音效**：BGM描述 + 台词 + 语速 + 音效
3. **分镜描述**：时间戳 + 运镜 + 画面 + 动作 + 细节
4. **风格说明**：保持参考图风格一致

### 多模态素材指代规则
- `图1`/`图片1` → input.media 数组第1个 reference_image
- `视频1` → 第1个 reference_video
- `音频1` → 第1个 reference_audio
- 三类互不冲突，分别计数

### 语速控制方式（wan3.0 专属）
wan3.0 没有独立语速API参数，语速通过提示词自然语言描述：
- "语速缓慢，带轻微回响，余韵悠长"
- "语速约2.5词/秒，像在季度会上做presentation的语气——专业但不冰冷，有节奏感，关键数字处微微加重"
- 台词节奏、语速、语气全靠 prompt 文字描述

> HappyHorse 不支持有声视频，没有语速控制。

### 编辑/延长触发词
- 编辑：`编辑视频`/`去掉`/`替换`/`改成`
- 延长：`延长`/`延续`/`续写`/`向前延长`/`向后延长`

### 有声视频（wan3.0 专属）
- 默认开启（原生生成人声台词、BGM、音效）
- 提示词中直接写台词（含引号），模型自动生成配音
- `audio=false` 可关闭

## HappyHorse（快乐马）官方文档要点

### 模型ID

| 模型 | 能力 |
|:---|:---|
| happyhorse-1.1-t2v | 文生视频 |
| happyhorse-1.1-r2v | 参考生视频(多张参考图) |
| happyhorse-1.0-t2v | 文生视频(旧版) |
| happyhorse-1.0-r2v | 参考生视频(旧版) |

### 快乐马 vs wan3.0 关键区别

| 对比项 | HappyHorse 1.1 | wan3.0 |
|:---|:---|:---|
| 有声视频 | ❌ 不支持 | ✅ 原生台词+BGM+音效 |
| 台词/语速控制 | ❌ 无 | ✅ 自然语言描述 |
| 参考素材 | 仅图片(1-9张) | 图+视频+音频+文档+网页(最多20个) |
| 最大时长 | 5秒(官方示例) | 30秒 |
| 视频编辑 | 有独立接口 | All-in-One |
| 素材指代 | `[Image 1]` | `图1`/`视频1`/`音频1` |
| 水印 | 默认带(需watermark=false关) | 默认不带 |

### 快乐马官方示例提示词

**文生视频（t2v）：**
```
一座由硬纸板和瓶盖搭建的微型城市，在夜晚焕发出生机。一列硬纸板火车缓缓驶过，小灯点缀其间，照亮前路。
```

**参考生视频（r2v，3张参考图）：**
```
[Image 1]中身着红色旗袍的女性，镜头先以侧面中景勾勒旗袍修身剪裁与S型曲线，随即切换至低角度仰拍，捕捉她轻抬玉手展开[Image 2]中的折扇的同时，[Image 3]中的流苏耳坠随头部转动轻盈摆动的细节，最后推近至面部特写，定格在她指尖轻点扇骨、眼波流转间的含蓄风情，多视角全方位展现东方韵味。
```

### 快乐马 r2v 参数

| 参数 | 说明 | 默认值 |
|:---|:---|:---|
| resolution | 480P/720P/1080P | 1080P |
| ratio | 16:9/9:16/3:4/4:3/4:5/5:4/1:1/9:21/21:9 | 16:9 |
| duration | [3,15]整数 | 5 |
| watermark | true/false | true |
| seed | [0,2147483647] | 随机 |

## 抓取技巧

### help.aliyun.com 页面抓取方法

阿里云文档页面 `help.aliyun.com` 全JS渲染，直接 curl 或 jina reader 抓不到正文内容。

**方法：用 browser_navigate + browser_console(JS提取正文)**
1. `browser_navigate` 到文档URL
2. `browser_console` 执行：先点击展开折叠框（`details, summary, [class*="expand"]...`），再获取 `article.innerText` 或 `main.innerText`
3. 折叠框内容需先点击展开才能获取——文档中标注"完整提示词见表格下方折叠框"的内容，需要点击展开后才在 innerText 中出现

### 业务空间专属域名（0826官方新增）

阿里云百炼推荐从旧域名迁移到业务空间专属域名：
- 华北2（北京）：`https://dashscope.aliyuncs.com` → `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`
- 新加坡：`https://dashscope-intl.aliyuncs.com` → `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com`

`{WorkspaceId}` 在百炼控制台业务空间详情页面查看。旧域名仍可正常使用。
