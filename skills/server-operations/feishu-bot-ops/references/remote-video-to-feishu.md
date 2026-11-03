# 远程生成视频发飞书工作流（2026-08-27 实测）

## 场景

通过 SSH 在广州机跑 `dashscope_video.py`（快乐马/wan3.0 等 DashScope 视频生成），视频输出路径是**广州机本地路径**（如 `/home/ubuntu/workflow/projects/happyhorse_output/xxx.mp4`），新加坡机不存在该文件。

## 正确流程（3 步）

### 1. 从 SSH 输出提取 OSS 直链

dashscope_video.py 成功后输出包含：
```
[INFO] 视频URL: https://dashscope-xxx.oss-accelerate.aliyuncs.com/...mp4?Expires=...&OSSAccessKeyId=...&Signature=...
[OK] 下载完成: /home/ubuntu/workflow/projects/happyhorse_output/xxx.mp4 (3.0MB)
```

**广州机的下载完成路径在新加坡机不存在。** 用 OSS 直链下载到本机。

### 2. 下载到本机

```python
import urllib.request
urllib.request.urlretrieve(oss_url, '/tmp/视频名.mp4')
```

或 bash:
```bash
curl -o /tmp/视频名.mp4 "https://dashscope-xxx.oss-accelerate.aliyuncs.com/...mp4?Expires=..."
```

### 3. 用 feishu_send_video.py 发到群

```bash
python3 <skill_dir>/scripts/feishu_send_video.py /tmp/xxx.mp4 <chat_id> <文件名> chat_id
```

- 第 4 参数 `chat_id` = receive_id_type=chat_id（群发）
- 不填第 4 参数 = 默认 open_id（私聊 DM）

群发示例（素材群）：
```bash
python3 scripts/feishu_send_video.py /tmp/huolong_v20.mp4 <MATERIAL_GROUP_CHAT_ID> huolong_v20.mp4 chat_id
```

## 踩坑

### 坑1：curl 一行命令发飞书被 hardline 拦
`curl -X POST ... -d '{"receive_id":"oc_xxx",...}'` 这种超长 inline payload 触发 security-middleware 的 "oversized/unparseable inline command payload" 拦截。**不要用 curl 一行发飞书消息**，用脚本。

### 坑2：内联 Python 重新发明轮子
用 `execute_code` 写完整 Python（读 .env → get_token → upload → send）能跑通，但已有 `feishu_send_video.py` 脚本封装好了这些逻辑。**直接调脚本**，不重新写。

### 坑3：飞书凭证在 .env 不在 config.yaml
凭证路径：`~/.hermes/.env` 的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（纯字符串无 secret_ 前缀）。不在 `config.yaml` 的 `platforms.feishu` 下（那里只有 enabled/notification/typing 等非凭证配置）。脚本 `load_env()` 已处理。

## 飞书凭证位置（两机不同）

- **新加坡机（default profile）**：`~/.hermes/.env` → `FEISHU_APP_ID=cli_aaf4227734381bc1` + `FEISHU_APP_SECRET=...`
- **广州机（customer profile = 小鹿）**：`~/.hermes/profiles/customer/.env` → `FEISHU_APP_ID=cli_aad9fec111389cdc` + `FEISHU_APP_SECRET=...`

open_id 是 per-app 的，跨机不通用。
