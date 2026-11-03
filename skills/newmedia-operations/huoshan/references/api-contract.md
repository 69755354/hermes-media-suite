# API Contract: Bot → API 文案JSON · 两段架构

## 概述

当客户说「做视频」后，bot（小鹿）完成 **节点0-5**，输出以下JSON格式，POST到 `/execute` 端点触发视频生成。

### 两段分工
- **Bot域（小鹿干）：** 节点0(信息采集) → 1(用户分析) → 2(爆款拆解) → 3(选题) → **4(文案·纯台词本)** → **5(分镜脚本)**
- **API域（Helper API）：** 节点8(出提示词) → 9(合规) → 10(Seedance) → 11(ffmpeg合成) → 13(交付)

### 段1→段2复用规则
| 段1客户服务干了什么 | 段2视频工作流跳过什么 |
|:-------------------|:--------------------|
| 搜了爆款 | ✅ 跳过节点2（爆款拆解），素材直接复用 |
| 写了文案 | ✅ 文案直接当节点4底稿，加镜号/时间/情绪即可 |
| 做了分析 | ✅ 跳过节点1（用户分析），客群结论直接用 |
| 收了信息 | ✅ 节点0信息已存wiki，不重复问 |

## JSON 格式

```json
{
  "task_id": "xiyuan_20260712",
  "shop_name": "熹园知味",
  "script": [
    {
      "shot": 1,
      "time": "0-5s",
      "speaker": "店主",
      "line": "熟悉我的朋友都知道，我一直从事心理工作",
      "tone": "温暖平静，像老朋友聊天",
      "emotion": "真诚/自我介绍",
      "storyboard": "远景跟摇，门头木质青瓦暖黄灯光，店主从右侧走入镜头，平行跟摇",
      "scene": "门头"
    },
    {
      "shot": 2,
      "time": "5-10s",
      "speaker": "店主",
      "line": "看多了大家被情感纠葛困住",
      "tone": "语气渐沉，略带心疼",
      "emotion": "共情/看到痛点",
      "storyboard": "全景，庭院绿植环绕，店主缓步走过竹木茶座",
      "scene": "庭院"
    },
    {
      "shot": 3,
      "time": "10-16s",
      "speaker": "店主",
      "line": "于是就有了这家熹园知味，院里绿植环绕",
      "tone": "语速转轻快，带欣慰感",
      "emotion": "释然/展示动机",
      "storyboard": "固定中景，绿植区光影晃动，店主眼神轻抬看向庭院深处",
      "scene": "绿植区"
    },
    {
      "shot": 4,
      "time": "16-22s",
      "speaker": "店主",
      "line": "在这里喝茶，品的是茶，也是心里的那点放不下",
      "tone": "缓慢轻柔，像对自己说",
      "emotion": "内省/治愈",
      "storyboard": "中近景，茶台前店主端起茶盏闻香，低头小抿闭眼回味",
      "scene": "茶台"
    },
    {
      "shot": 5,
      "time": "22-27s",
      "speaker": "店主",
      "line": "情缘38纳福98，一杯奶茶钱换一个下午",
      "tone": "轻松随口，带点笑意",
      "emotion": "轻快/价格",
      "storyboard": "固定中景，串灯区布幔背景，店主看向镜头方向微笑",
      "scene": "串灯区"
    },
    {
      "shot": 6,
      "time": "27-32s",
      "speaker": "店主",
      "line": "珠江北路，熹园知味，有空就来坐会儿",
      "tone": "尾音自然落下，像顺口一提的邀请",
      "emotion": "温暖/邀约",
      "storyboard": "远景，门头暖光，店主转身缓步走远，镜头停留拉远",
      "scene": "门头"
    }
  ],
  "character": "店主本人，30岁女性，温暖知性，语音带温暖沙感",
  "photos": [
    "门头实景.jpg",
    "庭院实景.jpg",
    "绿植区实景.jpg",
    "茶台实景.jpg",
    "串灯区实景.jpg"
  ],
  "bgm": "Song-1",
  "style": "文艺治愈/内心独白",
  "total_words": 98,
  "target_duration": 32
}
```

## API端点

```
POST /execute
Content-Type: application/json
```

## 内部流程（API端）

收到JSON后，API内部自动执行：
1. **节点8：** DeepSeek Pro 根据剧本+人设+照片 生成6镜Seedance prompt
2. **节点9：** 合规检查（违禁词扫描）
3. **节点10：** Seedance 2.0 Mini 逐镜生成（6镜统一BASE VOICE）
4. **节点11：** ffmpeg拼接+BGM+环境音+字幕烧录
5. **返回：** 成品视频路径 + 视频URL

## 返回格式

```json
{
  "status": "ok",
  "task_id": "xiyuan_20260712",
  "video_url": "https://...",
  "final_file": "/tmp/...mp4",
  "final_size": 12345678,
  "duration": 32.1,
  "compliance": "pass"
}
```
