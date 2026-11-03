# 批量多段提交 + 统一轮询模板

> 0827 实测：火龙通用口播 HH-3/4/5 三段一次性提交、一个后台进程轮询全部出片。

## 场景

同一个人、同一参考图、多段台词独立生成（如口播 5 段分段出片、多镜分镜出片）。逐段提交→逐段等→逐段下载太慢。

## 提交阶段

### 1. 每段提示词写本地文件

```bash
cat > /tmp/hh3_prompt.txt << 'PROMPT_EOF'
[Image 1]中的人物保持坐姿...人物说：它的选集页从第1集一直排到第62集...
PROMPT_EOF
```

### 2. scp 到广州机

```bash
for seg in hh3 hh4 hh5; do
  scp -P 2222 -o ConnectTimeout=10 -o BatchMode=yes /tmp/${seg}_prompt.txt ubuntu@127.0.0.1:/tmp/${seg}_prompt.txt
done
```

### 3. 循环提交，拿 task_id

```bash
DASHSCOPE_KEY=$(grep DASHSCOPE_API_KEY ~/.hermes/.env | cut -d'=' -f2)
REF_IMG="http://<GZ_HOST>/huolong_ref_spirit.png"

for seg in hh3:8 hh4:9 hh5:5; do
  name=$(echo $seg | cut -d: -f1)
  dur=$(echo $seg | cut -d: -f2)
  echo "=== Submitting $name (duration=$dur) ==="
  ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 "python3 -c \"
import json, urllib.request
prompt = open('/tmp/${name}_prompt.txt', 'r').read().strip()
body = {
    'model': 'happyhorse-1.1-r2v',
    'input': {
        'prompt': prompt,
        'media': [{'type': 'reference_image', 'url': '${REF_IMG}'}]
    },
    'parameters': {'resolution': '720P', 'ratio': '9:16', 'duration': ${dur}, 'watermark': False}
}
data = json.dumps(body, ensure_ascii=False).encode('utf-8')
req = urllib.request.Request(
    'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis',
    data=data,
    headers={
        'Authorization': 'Bearer ${DASHSCOPE_KEY}',
        'Content-Type': 'application/json',
        'X-DashScope-Async': 'enable'
    }
)
resp = urllib.request.urlopen(req, timeout=30)
print(json.loads(resp.read()))
\""
  echo ""
done
```

## 轮询阶段（后台一个进程轮询所有 task_id）

用 bash 关联数组存 `段名=task_id`，循环逐段轮询直到全部 SUCCEEDED/FAILED。用 `terminal(background=True, notify_on_complete=True)` 让出片后自动通知。

```bash
DASHSCOPE_KEY=$(grep DASHSCOPE_API_KEY ~/.hermes/.env | cut -d'=' -f2)

declare -A TASKS
TASKS[hh3]="6889b389-3bef-4206-b63d-babd9ae44933"
TASKS[hh4]="db5c6862-ea3a-4e0e-81ae-53fb95e71f48"
TASKS[hh5]="2746744b-1e2c-46e6-b9c6-2f4c1333059a"

for seg in hh3 hh4 hh5; do
  TASK_ID="${TASKS[$seg]}"
  echo "=== Polling $seg task=$TASK_ID ==="
  for i in $(seq 1 40); do
    sleep 15
    result=$(ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 "curl -s --connect-timeout 30 -H 'Authorization: Bearer $DASHSCOPE_KEY' 'https://dashscope.aliyuncs.com/api/v1/tasks/$TASK_ID'")
    status=$(echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output',{}).get('task_status','UNKNOWN'))" 2>/dev/null)
    echo "[$i] $seg: $status"
    if [ "$status" = "SUCCEEDED" ] || [ "$status" = "FAILED" ]; then
      echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); o=d.get('output',{}); print('STATUS:', o.get('task_status')); print('VIDEO_URL:', o.get('video_url','')); print('ERRORS:', o.get('errors',''))" 2>/dev/null
      break
    fi
  done
  echo ""
done

echo "=== ALL DONE ==="
```

## 下载 + 验证阶段

全部出片后统一下载、ffprobe 验时长、whisper 转写验台词完整性和语速。

```bash
cd /home/ubuntu/workflow/projects/huolong_general_template_v1

# 下载
curl -sL --connect-timeout 30 "$VIDEO_URL" -o scenes/hh3_general_v1.mp4

# ffprobe 时长 + 分辨率
ffprobe -v quiet -show_entries format=duration -show_entries stream=width,height -of csv=p=0 scenes/hh3_general_v1.mp4

# whisper 转写验台词 + 语速
ffmpeg -y -i scenes/hh3_general_v1.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 /tmp/check.wav 2>/dev/null
python3 -c "
from faster_whisper import WhisperModel
m = WhisperModel('small', device='cpu', compute_type='int8')
segs, _ = m.transcribe('/tmp/check.wav', language='zh', beam_size=3)
for s in segs:
    print(f'[{s.start:.1f}s-{s.end:.1f}s] {s.text}')
total = ''.join(s.text for s in segs).replace(' ','').replace('，','').replace('。','')
dur = max(s.end for s in segs) if segs else 0
if dur > 0:
    print(f'字数: {len(total)}, 时长: {dur:.1f}s, 语速: {len(total)/dur:.1f}字/秒')
" 2>/dev/null
```

## 注意事项

- DashScope 并发限制：同时提交 3 个任务没触发限流，但更多段建议分批
- 轮询间隔 15 秒足够（快乐马 720P 通常 1-2 分钟出片）
- `notify_on_complete=True` 必须加——轮询脚本跑完自动通知，不用手动 poll
- 提示词里的占位符（`{终集数}``{剧名}`）必须在提交前替换成真实值
- 语速加速指令（0827定案）每段都要写：「整段台词不停顿一口气说完，句与句之间不换气不隔开，像连珠炮一样紧凑分享，语速偏快，吐字清晰」
- duration 比原片对应段缩 1 秒（如原片 HH-1=10s→给 9s）
