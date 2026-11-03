# Execute API 服务部署参考

> 2026-07-12 会话建成 | systemd服务 | 端口 1889

## 服务信息

| 项目 | 值 |
|:----|:----|
| 服务名 | `execute-api.service` |
| 端口 | **1889**（不是 1888） |
| 脚本路径 | `/home/ubuntu/execute_api.py` |
| systemd | `/etc/systemd/system/execute-api.service` |
| 开机自启 | ✅ enabled |
| 状态控制 | `sudo systemctl [start/stop/restart] execute-api` |
| 日志 | `sudo journalctl -u execute-api --no-pager -n 30` |

## 调用方式

```bash
curl -X POST localhost:1889/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "xiyuan",
    "文案": "完整6镜文案+人设",
    "照片": ["/path/门头.jpg", "/path/店内.jpg"]
  }'
```

**超时注意：** 全流程需 3-5 分钟（Seedance 逐镜6次×~30s），curl 的 `--max-time` 至少设 300 秒。

## 内部流程

```
输入：文案+照片
  ↓ 节点5：分镜脚本（DeepSeek Flash）～3s
  ↓ 节点6：角色参考图（Seedream）～8s
  ↓ 节点7：素材汇总 + base64 预处理
  ↓ 节点8：出提示词（DeepSeek Pro）～3s
  ↓ 节点9：合规检查
  ↓ 节点10：Seedance 逐镜生成（6镜×~30s）～180s
  ↓ 节点11：ffmpeg 合成+BGM+字幕
  ↓ 节点12：视频检验
  ↓ 节点13：交付成品
输出：{"status":"ok", "video":"/path/to/final.mp4"}
```

## 架构关系

```
Bot域（小鹿）                      API域（execute-api:1889）
  节点0→1→2→3→4→5                     节点8→9→10→11→12→13
       ↓ POST /execute                     ↓
  剧本JSON ──────────────────→  成品视频 ✅
```

## 🚨 重要发现：subprocess.run curl 在后台进程会挂

**现象：** `subprocess.run(["curl", ...], capture_output=True)` 在 systemd / terminal(background=true) 环境中会**永久挂起**，curl 不返回。

**根因：** 后台进程缺少 PTY 时，curl 的 stdout/stderr pipe 处理可能死锁。

**正确做法：用 Python 原生 `urllib.request` 代替 subprocess curl**
```python
import urllib.request, json

def http_request(url, data=None, method="POST", timeout=30):
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer " + API_KEY}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())
```

下载文件也一样，用 `urllib.request.urlopen` 替代 `subprocess.run(["curl", "-o", ...])`。
