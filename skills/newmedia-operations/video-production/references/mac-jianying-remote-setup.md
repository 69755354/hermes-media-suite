# Mac 远程剪映自动化搭建记录（2026-08-06）

> 目标：服务器 Hermes 远程操作用户 Mac 上的剪映（jianying-editor-skill）。
> 架构：`服务器 Hermes ↔ SSH反向隧道 ↔ Mac Flask Web服务(jianying-web.py) ↔ Mac剪映+skill`

## 架构图

```
Mac (剪映5.9 + jianying-editor-skill + jianying-web.py:8000)
   │  ssh -R 8000:localhost:8000 -N ubuntu@<GZ_HOST>  (反向隧道，Mac主动连服务器)
   ▼
服务器 127.0.0.1:8000  ← Hermes curl/urllib 访问
```

关键：**隧道是 Mac 主动连服务器**（服务器不需要知道 Mac IP）；隧道建立后服务器 `127.0.0.1:8000` 即 Mac 的 `127.0.0.1:8000`。

## 环境事实

- 服务器：腾讯云 `<GZ_HOST>`，用户 `ubuntu`，SSH 22 开放，PasswordAuthentication yes
- Mac 用户名：`<MAC_USER>`；Mac 上 skill 路径：`~/.agent/skills/jianying-editor`（默认路径）
- Mac 剪映草稿目录：`~/Movies/JianyingPro Drafts/`
- jianying-editor-skill（luoluoluo22/jianying-editor-skill）核心 API：`JyProject()`、`add_media_safe()`、`add_cloud_music()`、`add_text_simple()`、`add_narrated_subtitles()`、`save()`
- Mac 端 Python：`/Library/Developer/CommandLineTools/usr/bin/python3`（3.9），flask 已装

## 搭建步骤（已完成部分）

### 1. Mac SSH 密钥
```bash
mkdir -p ~/.ssh
ssh-keygen -t ed25519 -C "mac-jianying" -f ~/.ssh/id_ed25519   # 一路回车
cat ~/.ssh/id_ed25519.pub   # 公钥整行发给服务器侧，追加到 /home/ubuntu/.ssh/authorized_keys
```
- 服务器侧追加后：`chmod 600 authorized_keys && chmod 700 ~/.ssh`（权限松 SSH 会拒）
- 验证：`ssh ubuntu@<GZ_HOST> "echo 通了"`
- **用户公钥陷阱**：`ssh-keygen` 终端输出的 `SHA256:xxx` 是指纹不是公钥；公钥必须 `cat ~/.ssh/id_ed25519.pub` 取（`ssh-ed25519 AAAA...` 开头）

### 2. Mac 端 Web 服务（jianying-web.py）
- 源码：`/home/ubuntu/scripts/mac_remote/jianying-web.py`（服务器上有备份）
- 接口：
  - `GET /health`：返回 skill_root / drafts_root / skill_exists
  - `POST /run`：`{"script": "python代码"}` → 写 /tmp/jy_run_script.py → skill 环境下执行 → 返回 stdout/stderr
- Mac 启动：
```bash
pip3 install flask
JY_SKILL_ROOT="<skill实际路径>" nohup python3 ~/jianying-web.py > /tmp/jy-web.log 2>&1 &
```
- 注意：flask 脚本在 `~/Library/Python/3.9/bin` 不在 PATH（警告无害，python import flask 正常）

### 3. SSH 反向隧道（单窗口方案）
```bash
nohup ssh -R 8000:localhost:8000 -N ubuntu@<GZ_HOST> > /tmp/jy-tunnel.log 2>&1 &
```
- `nohup` = 关窗口不断；两个服务都用 nohup 后台，一个窗口搞定
- 验证隧道：服务器 `ss -tln | grep 8000`（有 LISTEN = 隧道在）

## 排障

### 症状：服务器 curl 127.0.0.1:8000 超时（Connected 但 0 bytes）
排查链：
1. `ss -tlnp | grep 8000` → 8000 监听在（隧道建立）但转发不通
2. Mac `cat /tmp/jy-web.log` → 服务有没有真起来（`Running on http://127.0.0.1:8000`）
3. Mac `cat /tmp/jy-tunnel.log` → **`Warning: remote port forwarding failed for listen port 8000`** = 服务器 8000 被旧隧道会话占用，新隧道绑定失败
4. 服务器 `sudo lsof -i :8000` → 找到 `sshd pid=XXXX`（旧隧道对应 sshd，一堆 CLOSE_WAIT 死连接）
5. `kill <pid>` 释放端口（确认 ssh 主服务不受影响：`systemctl is-active ssh`）
6. Mac 重跑隧道命令 → 重测

### 其他已知坑
- 用户"不能开两个窗口" → 服务+隧道都用 `nohup ... &` 后台，单窗口
- `ssh -R` 绑定失败时旧 sshd 进程可能残留（CLOSE_WAIT 堆积），必须服务器侧 kill
- 草稿素材路径：草稿引用的素材是 Mac 本地路径，服务器生成草稿时素材路径要写成 Mac 路径（`/Users/<MAC_USER>/...`）才能被剪映识别

## 未完成/待验证
- Mac 自动导出（auto_exporter）是否可用——README 说不支持 Mac 导出，实测为准
- 剪映版本确认（必须 5.9 或更低）
- 联调 POST /run 真正生成草稿
