---
name: chanjing-digital-human-quirks
description: Use when 婵镜数字人出片排查眼神偏/声音爆/换音色.
category: newmedia-operations
---

# 婵镜数字人出片缺陷排查与修复

本skill收录婵镜数字人出片后常见缺陷的检测方法与修复方案。参数API参考见 `shuziren` skill。

## 1. 眼神偏（不看镜头）

**现象：** 用户反馈「数字人老是看边上」。

**检测方法：**
1. 抽帧：`ffmpeg -i video.mp4 -vf 'fps=1/5' -q:v 2 /tmp/frame_%03d.jpg -y`
2. 逐帧 `vision_analyze`，问题：「这个数字人的眼睛在看哪里？是在看镜头正前方还是偏向左/右？有没有斜视？」
3. 多帧对比：4帧中3帧偏 = 训练素材缺陷，不是API参数问题

**原因：** 克隆训练素材本身眼神偏，API参数无法修正。

**解决：** 换数字人，或重新克隆用正对镜头的训练素材。

## 2. 声音爆（峰值满幅）

**现象：** 用户反馈「声音有点爆」。

**检测方法：**
```bash
ffmpeg -i video.mp4 -af 'volumedetect' -f null - 2>&1 | grep -E 'mean_volume|max_volume'
```
- max_volume = 0.0 dB → 满幅爆音
- 正常应在 -1.0 ~ -3.0 dB

**原因：** `volume=100`（满格）+ 公共音色可能叠加导致峰值顶满。

**修复：**
- 出片前：降 `volume` 到 80-90
- 出片后：`ffmpeg -i video.mp4 -af loudnorm=I=-16:TP=-1.5 -c:v copy -c:a aac video_fixed.mp4`

## 3. 数字人自带音色 vs 公共音色

**查自带音色：**
```
GET /open/v1/customised_person?source=1
→ data.audio_man_id
```

**使用：** 把 `audio_man_id` 值填入 `audio.tts.audio_man`，替代公共音色。

| 类型 | 获取方式 | 特点 |
|:----|:--------|:-----|
| 自带音色 | 数字人详情 `audio_man_id` | 克隆时train_type=both自带，声音更贴合 |
| 公共音色 | `GET /open/v1/list_common_audio` | 通用音色如带货小芸，可能与数字人不搭 |

**建议：** 优先用自带音色，声音更自然，爆音概率更低。

## 4. 数字人权限不通

**现象：** `code=50000, msg=非当前账号创建，无权限`

**原因：** 数字人不在当前 app_id 账号下（多账号资产不互通）。

**排查：**
- source=0 查API端数字人，source=1 查Web端数字人
- 不同 app_id 下的数字人互不可见

## 5. 飞书发视频失败

**现象：** `Feishu file upload missing file_key`

**原因：** 不是文件太大，是飞书上传API瞬断或返回异常。

**修复：**
- 方法1：重试 `hermes send --to feishu "描述 MEDIA:/path/to/video.mp4"`
- 方法2：ffmpeg压缩到25MB以下再发 `ffmpeg -i input.mp4 -crf 28 -c:a aac -b:a 128k output.mp4`
- 方法3：走 codex_glm_fallback.sh 派执行器发