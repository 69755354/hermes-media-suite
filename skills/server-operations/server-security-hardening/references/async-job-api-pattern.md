# 持久化 Job API 模式（2026-08-09 execute_api 提速改造）

把同步 HTTP 长任务（如 `/execute` 跑 28-56 分钟视频流水线）改成异步持久化 Job 的核心模式。
提交立即返回 job_id，后台线程执行，可查进度/取消，进程重启不丢（状态落盘）。

## 核心结构（execute_job_manager.py）

```python
JOB_DIR = "/tmp/execute_api/jobs"      # 状态落盘目录
JOBS = {}                               # job_id -> state dict
LOCK = threading.Lock()

def create_job(body) -> dict:
    job_id = uuid.uuid4().hex[:16]
    state = {"id": job_id, "status": "queued", "created_at": time.time(),
             "progress": [], "result": None, "error": None, "body": body}
    JOBS[job_id] = state
    _persist(job_id, state)             # 立即落盘，防进程重启丢失
    return {"job_id": job_id, "status": "queued"}

def run_job_async(job_id, pipeline_fn, body):
    def worker():
        # 状态 queued -> running；pipeline_fn(body, progress_logger) 执行
        # 成功 -> success + result；异常 -> failed + error
    threading.Thread(target=worker, daemon=True).start()
```

## 接入 HTTP Handler 的路由（execute_api.py）

```python
elif self.path == "/job":
    j = create_job(body)
    run_job_async(j["job_id"], run_pipeline, body)
    result = j
elif self.path == "/job/status":
    result = get_job(body.get("job_id", "")) or {"error": "not found"}
    if "error" in result: status = 404
elif self.path == "/job/cancel":
    result = cancel_job(body.get("job_id", ""))
```

## pipeline 函数改造（支持进度回调 + 埋点）

```python
def run_pipeline(body, _log_cb=None):
    prog = []
    _node_t0 = {}
    def log(n, m):
        now = time.time()
        if n not in _node_t0: _node_t0[n] = now
        dur = round(now - _node_t0.get(n, now), 1)
        prog.append({"node": n, "msg": m, "dur_s": dur})   # 埋点
        if _log_cb: _log_cb(n, m)
    ...
    result["timings"] = {p["node"]: p.get("dur_s") for p in prog}  # p50/p95 数据基础
    result["total_s"] = round(time.time() - _t0, 1)
```

## 关键点

- **daemon=True 线程**：不阻塞 HTTP 响应，请求立即返回 job_id
- **状态落盘**：每步 progress 更新都 _persist，进程重启后 get_job 从磁盘恢复
- **并发控制**：Job 线程内跑 pipeline 时，pipeline 内部的 ffmpeg/codex 调用仍要 flock 锁（见 server-security-hardening 第6节）
- **进度日志结构**：`{"node": "5", "msg": "分镜：6镜", "dur_s": 12.3}`——埋点数据累积后可算 p50/p95

## 并行化依赖分析（视频流水线示例）

- 节点5(分镜)/6(角色图)/9(合规) 只依赖文案 → ThreadPoolExecutor(max_workers=3) 并行
- 节点10(Seedance逐镜) 6 镜互相独立 → max_workers=2 并发（防广州 relay/Seedance 限流，达标再升3）
- 串行 12-24 分钟 → 2 并发预计 4-8 分钟
