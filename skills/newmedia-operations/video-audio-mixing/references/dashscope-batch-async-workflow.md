# DashScope 批量异步视频生成工作流

> 场景：用快乐马/wan3.0 分段出多条视频（如多镜分段），批量提交→并行轮询→下载→校验→拼接→调音量。
> 0828 实测：5段 happyhorse-1.1-r2v 720P，全部一次提交一次轮询全过。

## 一、批量提交

对每段独立 POST 创建任务，收集 task_id。提交方式见 `dashscope-video-generation` SKILL.md 第十二节 curl 样例。

```bash
ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 \
  "curl -s --connect-timeout 30 -X POST \
    'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis' \
    -H 'X-DashScope-Async: enable' \
    -H 'Authorization: Bearer \$DASHSCOPE_API_KEY' \
    -H 'Content-Type: application/json' \
    -d '{\"model\":\"happyhorse-1.1-r2v\",\"input\":{...},\"parameters\":{\"resolution\":\"720P\",\"ratio\":\"9:16\",\"duration\":N,\"watermark\":false}}'"
```

从返回 JSON 提取 `output.task_id`。

## 二、批量轮询（后台脚本模板）

把所有 task_id 存入关联数组，循环轮询直到全部 SUCCEEDED/FAILED。

```bash
#!/bin/bash
DASHSCOPE_KEY="<your-key>"

declare -A TASKS
TASKS[seg1]="task-id-1"
TASKS[seg2]="task-id-2"

declare -A URLS

for seg in "${!TASKS[@]}"; do
  TASK_ID="${TASKS[$seg]}"
  echo "=== Polling $seg task=$TASK_ID ==="
  for i in $(seq 1 40); do
    sleep 15
    result=$(ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 \
      "curl -s --connect-timeout 30 -H 'Authorization: Bearer $DASHSCOPE_KEY' \
       'https://dashscope.aliyuncs.com/api/v1/tasks/$TASK_ID'")
    status=$(echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output',{}).get('task_status','UNKNOWN'))" 2>/dev/null)
    echo "[$i] $seg: $status"
    if [ "$status" = "SUCCEEDED" ] || [ "$status" = "FAILED" ]; then
      video_url=$(echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output',{}).get('video_url',''))" 2>/dev/null)
      echo "VIDEO_URL: $video_url"
      URLS[$seg]=$video_url
      break
    fi
  done
done

echo "=== ALL DONE ==="
for seg in "${!URLS[@]}"; do
  echo "$seg: ${URLS[$seg]}"
done
```

**关键点**：
- 15秒轮询间隔，最多40次（10分钟超时）
- 5段5秒720P r2v 实测约1-2分钟内全过
- 用 `background=true` 运行轮询脚本，完成后通知

## 三、下载 + ffprobe 校验

```python
import subprocess, os, json

workdir = "/home/ubuntu/huolong_runs/segments"
os.makedirs(workdir, exist_ok=True)

segments = {"seg1": "url1", "seg2": "url2"}
for seg, url in segments.items():
    out = os.path.join(workdir, f"{seg}.mp4")
    subprocess.run(["curl", "-sL", "--connect-timeout", "30", "-o", out, url], timeout=120)
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", out],
        capture_output=True, text=True, timeout=30)
    d = json.loads(r.stdout)
    v = [s for s in d["streams"] if s["codec_type"]=="video"][0]
    a = [s for s in d["streams"] if s["codec_type"]=="audio"][0]
    print(f"{seg}: {v['width']}x{v['height']} {v['codec_name']} "
          f"{d['format']['duration']}s audio={a['codec_name']}")
```

**校验要点**：同模型同参数生成的段，codec/分辨率/fps 应完全一致。不一致则不能直接 concat copy。

## 四、拼接（同参数段用 concat demuxer + stream copy）

```bash
cat > concat_list.txt << 'EOF'
file '/path/to/seg1.mp4'
file '/path/to/seg2.mp4'
EOF

ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy merged.mp4
```

- 同 codec/同分辨率/同 fps/同采样率 → 直接 `-c copy` 不重编码
- 5段拼接是秒级操作
- 参数不一致 → 需 `-c:v libx264` 统一重编码

## 五、音量归一化（视频流不重编码）

DashScope r2v 原始音量偏低（-15~-18 LUFS，见本 skill 6.5节）。

```bash
# 先测当前响度
ffmpeg -i merged.mp4 -af "loudnorm=print_format=json" -f null - 2>&1 | tail -15

# 拉到 -14 LUFS（口播标准），只重编码音频
ffmpeg -y -i merged.mp4 \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11" \
  -c:v copy -c:a aac -b:a 128k \
  merged_vol.mp4
```

- `-c:v copy`：视频流不重编码，秒级完成
- `-c:a aac -b:a 128k`：只重编码音频
- 33.7s 720P 合并后约 11MB，无需压缩直接发飞书

## 六、交付

```bash
hermes send -t feishu:<chat_id> 'MEDIA:/path/to/merged_vol.mp4'
```

>25MB 先压 CRF28+AAC128k（见本 skill 6.8节）。
