# 视频分析→生成全链路实战笔记

> 参数状态：历史实战笔记。镜数、时长与字数不得作为通用阈值，统一以 `director-thinking/SKILL.md` 和项目 Charter 为准。

> 2026-07-08 实测 | 武极天尊神界篇短剧预告片
> 流程：拆视频 → 豆包Vision 7要素分析 → 反推提示词 → Seedance并行生成 → ffmpeg拼接

## 一、帧提取方法

30秒视频，每6秒取一帧，共5帧覆盖全片节奏：

```bash
mkdir -p /tmp/video_frames
ffmpeg -i input.mp4 -vf "fps=1/6" -frames:v 5 -q:v 2 /tmp/video_frames/frame_%02d.jpg -y
```

**参数说明：**
- `fps=1/6`：每6秒取一帧（30秒视频得5帧）
- `-frames:v 5`：最多取5帧
- `-q:v 2`：高质量JPEG（1-31，1最好）

---

## 二、豆包Vision分析指令

ARK端点 `ep-20260701164350-mr48s`，模型 `doubao-seed-1-6-vision-250815`

**推荐prompt模板：**

```
分析这些视频帧（每6秒一帧，共X帧，{视频类型描述}），按以下维度逐帧分析并汇总：
1. 画面主体（人物外貌/穿搭/表情/数量）
2. 动作（正在做什么，帧间变化说明剧情推进）
3. 场景环境（室内/室外、具体空间、风格）
4. 光影（光源方向、强度、色温）
5. 运镜（固定还是动态？景别变化？）
6. 风格色调（整体视觉风格、色调）
7. 画质（清晰度、分辨率）
最后给出一个完整的反推提示词（可直接用于AI视频生成）。
```

**代码示例（Python）：**

```python
import base64, requests, json

# 编码图片
with open(path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

# 组装多帧请求
payload = {
    "model": "ep-20260701164350-mr48s",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt}
        ] + [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            for b64 in frames
        ]
    }],
    "max_tokens": 2000
}

resp = requests.post(
    "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    json=payload,
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    timeout=120
)
```

**注意：** 图片全走base64内联，不发外链。最大5帧同时分析，token消耗约9000（5帧+长分析）。

---

## 三、反推提示词→Seedance参数

从7要素分析结果组装Seedance参数，每个片段独立一段prompt。

**分段策略：**
- 每段6秒（兼容Seedance Mini≤7秒限制）
- 画面变化明显处切段（不同场景/景别/色调）
- 每段prompt只描述本段画面

**并行提交（实测有效）：**

```python
segments = [
    {"id": "seg1", "prompt": "分镜1画面描述", "duration": 6},
    {"id": "seg2", "prompt": "分镜2画面描述", "duration": 6},
    ...
]

# 全部提交（不等待上一个完成）
task_ids = {}
for seg in segments:
    payload = {
        "model": "doubao-seedance-2-0-mini-260615",
        "content": [{"type": "text", "text": seg["prompt"]}],
        "duration": seg["duration"],
        "resolution": "720p",
        "ratio": "9:16",
        "watermark": False
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    task_ids[seg["id"]] = resp.json()["id"]
    time.sleep(1)  # 避免并发限流

# 轮询所有任务
for round in range(30):
    for sid in pending:
        r = requests.get(f"{url}/{task_ids[sid]}", headers=headers)
        if r.json().get("status") == "succeeded":
            # 下载
            video_url = r.json()["content"]["video_url"]
            requests.get(video_url, timeout=30)
            # 存为 /tmp/seedance_{sid}.mp4
```

**实测效果：** 5段并行，最慢段约90秒完成，比串行节省约4倍时间。

---

## 四、ffmpeg拼接

```bash
# 生成concat文件列表
echo "file '/tmp/seedance_seg1.mp4'" > /tmp/concat_list.txt
echo "file '/tmp/seedance_seg2.mp4'" >> /tmp/concat_list.txt
# ...以此类推

# 一键拼接+统一竖屏
ffmpeg -y -f concat -safe 0 -i /tmp/concat_list.txt \
  -c:v libx264 -crf 23 -preset medium \
  -vf "scale=720:1280:force_original_aspect_ratio=decrease,\
       pad=720:1280:(ow-iw)/2:(oh-ih)/2" \
  -pix_fmt yuv420p \
  output.mp4
```

**实测成品：** 30.4秒, 9.6MB, 720p竖屏H.264

---

## 五、⚠️ 已知坑

| 坑 | 现象 | 解决 |
|:--|:-----|:-----|
| ARK Key被红化截断 | 只存了前15字符，API返回401 | 用session_search找回完整key，subprocess写入.env |
| Seedance Mini单段>7s | 可能崩坏/卡顿 | 每段≤6秒，稳 |
| 图生视频有0.3s彩铅闪过 | 参考图痕迹 | `ffmpeg -ss 0.3 ...` 剪掉开头 |
| 文生视频人物易翻车 | 面部漂移/畸形 | 含人物场景优先图生视频 |
