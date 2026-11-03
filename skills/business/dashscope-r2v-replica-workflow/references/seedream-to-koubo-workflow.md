
> ⚠️ **旧口径存档（2026-09-21 前）**：本文涉及的利益点表述可能含新规禁项（无广告类／躺赚白嫖／吊打竞品／绝对免费／直接提现）。**只作历史参考，出片一律按优矩最新口径**，禁照搬。

# Seedream→口播视频生成参考（快乐马默认 / wan3.0备选）

> 2026-08-26 实测定型。适用场景：非复刻的新角色口播视频（如换人物换场景的模板变体）。

## 模型选型（0826定案）

**火龙漫剧项目默认走快乐马 (happyhorse-1.1-r2v)**，不跳 wan3.0。原因：便宜（4.5折 720P 10秒0.56元）、连续镜头不乱切、无真人检测。除非用户明确指定换 wan3.0 才换。

| 维度 | 快乐马（默认） | wan3.0（备选） |
|:---|:---|:---|
| 模型 | happyhorse-1.1-r2v | wan3.0-video |
| 单次时长 | ≤15秒 | ≤30秒 |
| fps | 24fps | 30fps |
| 分辨率 | 720P | 1080P |
| 音频 | 24kHz（prompt驱动，无audio开关） | 48kHz（audio参数控制） |
| 720P成本(折后) | 0.056元/秒 | 0.252元/秒 |
| 15秒成本 | 0.84元 | 3.78元 |
| 画面连续性 | 连续不乱切 | 会自作主张切画面 |
| 场景遵从 | 弱（白底三视图会被当日常场景） | 强 |
| prompt_extend | 无此参数 | 有（必须设false） |

## 执行步骤

### 1. codex 出 Seedream 五层提示词

派 codex 写 Seedream 5.0 文生图提示词，五层结构：
- L1 主体基础层（年龄/脸型/五官/发型/气质）
- L2 肤质妆容层（皮肤质感/毛孔/细纹/唇色写"接近肤色的自然淡裸粉仅带轻微血色不偏玫红不偏荧光"）
- L3 体态情绪穿搭层（服装/姿态/表情/配饰）
- L4 镜头光影构图层（机位/焦段/光源/构图）
- L5 场景氛围画质层（环境/色调/画质/尺寸）
- NEG 负向提示词（"无XX"格式）

codex 调用命令（codex_task.sh 不可用时）：
```bash
codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox \
  -c model_reasoning_effort=high -C /home/ubuntu/workflow "$(cat prompt.txt)" 2>&1 | tail -100
```

### 2. Seedream 5.0 生成人物参考图

```bash
# 构造 JSON payload（prompt + negative_prompt 分开字段）
cat > /tmp/payload.json << 'EOF'
{
  "model": "doubao-seedream-5-0-260128",
  "prompt": "...五层合并...",
  "negative_prompt": "...负向...",
  "size": "1440x2560",
  "n": 1,
  "watermark": false
}
EOF

# 经广州 relay 调 ARK（新加坡直连不通）
curl -sS -w "\nHTTP:%{http_code}" \
  "http://127.0.0.1:8899/upload?url=https%3A%2F%2Fark.cn-beijing.volces.com%2Fapi%2Fv3%2Fimages%2Fgenerations" \
  -H "Authorization: Bearer $ARK_API_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/payload.json
```

下载图片：OSS URL 新加坡直连不通 → SSH 到广州 curl 下载 → scp 回新加坡。
生成后必须 `vision_analyze` 自检：人物年龄/原生感/场景/无水印/无塑料感。（0826更正：vision_analyze 已配 auxiliary.vision 走 ARK doubao relay，正常返回详细图像分析，不再返空话）

### 3. 参考图传公网

```bash
scp -P 2222 image.png ubuntu@127.0.0.1:/tmp/image.png
ssh -p 2222 ubuntu@127.0.0.1 'cp /tmp/image.png /home/ubuntu/public/image.png'
# 验证
curl -s -o /dev/null -w "%{http_code}" http://<GZ_HOST>/image.png  # 200
```

### 4A. 快乐马生成口播视频（默认）

**分段**：原版39.8秒 → 分3段（15s+15s+10s，快乐马单次≤15秒）。

**payload 结构**：
```json
{
  "model": "happyhorse-1.1-r2v",
  "input": {
    "prompt": "[Image 1]中的中年女性坐在自家客厅沙发上，身体正对镜头，双手自然放在膝上，目光直视镜头。9:16竖屏，一个连续物理镜头，不切画面，不跳镜。中近景，胸口以上构图，固定机位。配音与音效：一位45岁左右中文女声，音色平和自然，语速适中，吐字清晰，不过快。人物说：台词整段。人物表情自然，说话时嘴型与中文人声自然同步。画面专属负面：换脸、五官漂移、仿真3D感、CG塑料感、插画感；手部畸形、多指少指、肢体穿模；突然站起、离开座位、切画面、跳镜、口型错位、多余的话、乱语。",
    "media": [{"type": "reference_image", "url": "http://<GZ_HOST>/image.png"}]
  },
  "parameters": {
    "resolution": "720P",
    "ratio": "9:16",
    "duration": 15,
    "watermark": false
  }
}
```

**提交**（SSH到广州执行curl）：
```bash
# 先把payload写到广州本地文件，再curl -d @file（禁在SSH命令里heredoc/变量插值传JSON）
scp -P 2222 /tmp/payload_part1.json ubuntu@127.0.0.1:/tmp/
ssh -p 2222 ubuntu@127.0.0.1 \
  "curl -s --connect-timeout 30 -X POST 'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis' \
    -H 'X-DashScope-Async: enable' \
    -H 'Authorization: Bearer $DASHSCOPE_API_KEY' \
    -H 'Content-Type: application/json' \
    -d @/tmp/payload_part1.json"
```

**轮询**（15秒间隔，720P/15s 约需1-2分钟）：
```bash
ssh -p 2222 ubuntu@127.0.0.1 \
  "curl -s -X GET 'https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}' \
    -H 'Authorization: Bearer $DASHSCOPE_API_KEY'"
# status: PENDING → RUNNING → SUCCEEDED (拿 video_url) / FAILED
```

**下载视频**：OSS URL 新加坡直连不通 → 广州 curl 下载 → scp 回新加坡。

**快乐马成本（4.5折）**：720P 15s=0.84元/段，3段共约2.24元。

### 4B. wan3.0 生成口播视频（备选，用户明确指定时用）

**分段**：原版39.8秒 → 分2段各20秒（wan3.0 单次≤30秒）。

**payload 结构**：
```json
{
  "model": "wan3.0-video",
  "input": {
    "prompt": "图1中的中年女性坐在家中客厅沙发上，身穿浅灰蓝色棉质圆领长袖上衣，面对镜头。配音与音效：图1中的中年女性用自然的中文普通话说道：台词整段。语速适中，吐字清晰。无背景音乐。",
    "media": [{"type": "reference_image", "url": "http://<GZ_HOST>/image.png"}]
  },
  "parameters": {
    "resolution": "1080P",
    "ratio": "9:16",
    "duration": 20,
    "audio": true,
    "prompt_extend": false,
    "watermark": false
  }
}
```

**wan3.0 成本（6折）**：1080P 20s=14.4元/段，2段共约28.8元。比快乐马贵13倍。

### 5. ffmpeg 合成

数字人视频 + App 录屏 + 字幕 ASS + BGM + Logo + CTA → 参见 `references/v19-compose-reference.md` 和后期合成四铁律。

## 台词写法铁律（不分模型）

- **整段写**：不拆时码，一个"人物说："后面接全部台词
- **语速描述**：写"语速适中，吐字清晰，不过快"，禁标数值
- **分段台词核对**：每个shot的提交prompt台词必须与分镜分配的台词逐句核对一致
- **卖点词不降级**：原片怎么写就怎么写，合规处理由人决定不由AI自作主张
- **用户已说文案不变=不再追问**：用户明确说"文案口播不变"后，不再逐词追问是否保留风险词——用户说了就是定了

## 注意事项

- 快乐马无 audio/prompt_extend 参数，声音纯靠 prompt 驱动
- wan3.0 prompt_extend 必须 false，否则精确台词和锁定描述被改写
- 两个任务可并行提交：独立 task_id，各自轮询
- 大文件传输用后台：70MB 文件 scp 超过 execute_code 300s 超时
- SSH传JSON payload会被shell转义破坏：必须先写到广州本地文件再curl -d @file
