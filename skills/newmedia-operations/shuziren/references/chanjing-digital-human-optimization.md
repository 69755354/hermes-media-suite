# 婵镜数字人「动作+表情+声音」真人化优化方案

> 参数状态：API能力参考。六类创作参数以 `director-thinking/SKILL.md` 为准；文中旧裸台词写法不得继续使用。

> 来源：用户提供+会话验证（2026-07-14）
> 适配对象：婵镜 `/open/v1/create_video` REST API
> 注意：以下参数全部经过API验证可正常提交。

---

## 一、音色控制

### TTS参数
```json
"audio": {
  "tts": {
    "audio_man": "合法音色ID（list_common_audio获取）",
    "speed": 0.98,
    "pitch": 1.02,
    "emotion_enhance": true,
    "volume": 100,
    "language": "cn",
    "text": ["口播文案"]
  },
  "type": "tts"
}
```
踩坑：`volume`在`audio`层级，非`tts`内。

---

## 二、语气/停顿/情绪

### 方式1：SSML标签（⚠️ REST API不支持，引发400错误）
以下标签仅在婵镜Web编辑器/MCP中有效，**在`/open/v1/create_video` REST API中嵌入文案会导致400错误**：
```
<prosody rate="0.95" pitch="1.03">内容</prosody>
<break time="0.4s"/>
<emphasis level="moderate"/>
```

### 方式2：全局emotion字段
```json
"emotion": "温和专业，平缓讲解，轻微微笑"
```

---

## 三、面部表情 + 口型同步

```json
"person": {
  "id": "数字人ID",
  "width": 1080, "height": 1920,
  "face_detail": true,
  "lip_sync_precision": "high",
  "blink_interval": 8,
  "head_sway": true,
  "body_breath": true,
  "face_smooth": false
}
```

---

## 四、肢体动作

```json
"motion": {
  "auto_gesture": true,
  "gesture_strength": 0.35,
  "gesture_frequency": "low"
}
```

---

## 五、背景

`background.file_id`实测未生效（生成白底），推荐`bg.src_url`：
```json
"bg": { "src_url": "背景图公网URL", "width": 1080, "height": 1920 }
```

---

## 六、完整 create_video 模板

```json
{
  "person": {
    "id": "数字人ID",
    "width": 1080, "height": 1920,
    "face_detail": true,
    "lip_sync_precision": "high",
    "blink_interval": 8,
    "head_sway": true,
    "body_breath": true,
    "face_smooth": false
  },
  "audio": {
    "tts": {
      "audio_man": "合法音色ID",
      "speed": 0.98, "pitch": 1.02,
      "emotion_enhance": true,
      "volume": 100, "language": "cn",
      "text": ["口播文案"]
    },
    "type": "tts"
  },
  "motion": {
    "auto_gesture": true,
    "gesture_strength": 0.35,
    "gesture_frequency": "low"
  },
  "bg": { "src_url": "公网URL", "width": 1080, "height": 1920 },
  "emotion": "温和专业",
  "model": 1, "source": 1,
  "screen_width": 1080, "screen_height": 1920
}
```

---

## 七、避坑总结

| ❌ 错误 | ✅ 正确 |
|:--------|:--------|
| 数字人C-d开头ID填audio_man | 查list_common_audio获取音色ID |
| 手势幅度>0.6 | gesture_strength=0.35 |
| 关lip_sync_precision | 必须high |
| TTS语速>1.15 | speed=0.98 |
| 不加source:1 | Web数字人必须source=1 |
| 不确认就调付费API | 先问「要跑不？」 |
| 链接加**号 | 纯文本 |
| volume放tts内部 | volume在audio层级 |
| SSML引发400 | 纯文本版一定过 |
| background.file_id未生效 | 改用bg.src_url |
| SSML标签嵌入文案 | REST API不支持，返回400。仅Web/MCP可用 |
| 视频克隆素材含大动作 | 克隆后每版出片都复制该动作，删不掉 |
| 一次传全部参数调试 | 逐个参数组添加定位错误 |

## 九、prompt必须看照片再写（2026-07-14 用户纠正）

**铁律：** prompt中的人物描述（发型/穿搭/配饰/脸型）必须100%匹配参考图。

**变脸根因：** 照片穿黑色V领吊带背心，prompt写"白色衬衫黑色西装外套" → 模型读到跟看到的不一致，人脸跑偏。

**规则：** 先调用ARK Vision分析照片提取准确特征，再写prompt。不准靠记忆或猜测。

## 十、熹园prompt结构（有效模板）

每镜按序写，禁止跳序：

1. @图1 作为真人女性[年龄]岁[脸型][发色][穿搭]全部特征不变不戴墨镜眼神自然
2. 照片级写实，无CG感，天然肌肤质感
3. 镜头语言（景别+运镜+构图比例+呼吸感+24fps）
4. 光影（光源+方向+氛围+色调）
5. 动作（自然动作，全程不看镜头，逐帧描述）
6. 动态强度X%
7. 同步生成中文内心独白/旁白+语速+语气
8. 独白/台词内容（不加引号）
9. @图2 作为[场景]实景照[特征]完整露出不虚化
10. 专属负面（隔一行）

11. 🔄 **查看参考文件** `references/semantic-digital-human-workflow.md` 了解完整语义驱动数字人口播工作流（文案拆分→动作编排→标点控节奏→婵镜参数）。注意：婵镜REST API不支持SSML标签，用纯文本+标点控制停顿节奏。

**核心事实：** 视频克隆的数字人保留原视频全部动作（关手机、撩头发、拿物品），AI只替换口型+声音。

**建议：** 克隆素材拍30-40秒静止说话（手放桌上或自然垂放），避免大动作。姿势在训练时定好，后续无法修改。
