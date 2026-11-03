---
name: remote-desktop-automation
title: 远程桌面 GUI 自动化（SSH 反向隧道 + 桌面端 HTTP 服务）
description: 远程控制桌面机跑剪映等GUI应用。SSH反向隧道+桌面端/run服务，服务器远程执行脚本。
---

# 远程桌面 GUI 自动化

## 适用场景

服务器是无头 Linux（没有 GUI），但某些工作必须桌面机完成（剪映渲染/导出、桌面软件操作）。
思路：**桌面机当"执行器"，开一个 HTTP 服务暴露 /run 接口（在本地执行任意 Python），服务器通过 SSH 反向隧道远程调用**。

```
桌面机(Mac/Win: 剪映+服务:8000) ←SSH反向隧道→ 服务器(Hermes)
   /run 执行 Python 脚本                  调度任务、POST 脚本
```

## 架构（三层）

1. **桌面端服务**（templates/jianying-web.py）：
   - Flask 监听 127.0.0.1:8000
   - `GET /health`：健康检查 + skill 目录/草稿目录探测
   - `POST /run`：接收 `{"script": "python代码"}`，在 SKILL_ROOT 环境下 subprocess 执行，返回 stdout/stderr
   - `JY_SKILL_ROOT` 环境变量指定 skill 根目录（默认 `~/.agent/skills/jianying-editor`）——**注意：/run 会强制检查该目录存在，目录不存在返回 500**（指向任意存在的目录即可绕过，如剪映 DeepAgents 目录）

2. **SSH 反向隧道**（桌面机执行）：
   ```bash
   ssh -R 8000:localhost:8000 -N ubuntu@<服务器IP>
   ```
   - 服务器访问 `127.0.0.1:8000` 即转发到桌面机
   - 桌面机需先配好到服务器的 SSH 密钥（`ssh-keygen -t ed25519` → 公钥发服务器加 authorized_keys）

3. **服务器调度**：HTTP POST 脚本到 `http://127.0.0.1:8000/run`

## 关键坑（全部踩过）

### SSH 密钥配置
- 用户发来"公钥"实际是终端显示的**指纹图/指纹行**（SHA256:...）——真公钥要 `cat ~/.ssh/id_ed25519.pub` 的输出（以 `ssh-ed25519 AAAA...` 开头）
- 用户忘了服务器密码：直接让用户发公钥，服务器端追加到 `authorized_keys`（chmod 600，.ssh 700），绕开密码
- 服务器公网 IP：`curl ifconfig.me` 或腾讯云 metadata

### 隧道反复失败的根因（重点）
- **症状**：服务器 `127.0.0.1:8000` 能连（socket connect 成功）但 HTTP 请求超时；桌面端跑隧道报 `remote port forwarding failed for listen port 8000`
- **根因**：服务器上残留旧隧道（sshd 进程占着 8000 的 LISTEN），新隧道绑定失败；或旧隧道半死（CLOSE_WAIT 一堆）转发不出数据
- **修复**：
  ```bash
  # 服务器：杀掉占用 8000 的隧道 sshd
  sudo lsof -i :8000 | grep LISTEN | awk '{print $2}' | sort -u | xargs sudo kill
  # 桌面机：杀旧隧道进程，重来
  pkill -f "ssh -R 8000"
  ```
- **多隧道进程打架**：桌面机多次执行 ssh -R 会残留多个进程，全部 pkill 后重建

### 桌面机只能开一个窗口
- 用 nohup 全后台：服务 + 隧道都 `nohup ... > /tmp/xxx.log 2>&1 &`
- 检查：`cat /tmp/jy-web.log`（应有 Running on）、`cat /tmp/jy-tunnel.log`（应为空，有 warning 就是端口冲突）

## 剪映案例（2026-08-06 实测结论）

完整调研见 `references/jianying-editor-research.md`。关键结论：
- **luoluoluo22/jianying-editor-skill**（2666★，MIT）：唯一支持**自动导出 MP4** 的剪映自动化 skill，但硬要求 **Windows + 剪映 5.9 或更低**（6.0+ 弹窗干扰自动化）；Mac 只能生成草稿不能自动导出
- **剪映 10.8 DeepAgents**：GUI 内置 AI 剪辑（智能粗剪/剪口播/BGM 对齐），**无对外 API 无监听端口**，外部调不了
- 服务器（无头 Linux）无法直接跑剪映自动化（没有剪映）；远程控制必须桌面机当执行器
- 剪映 5.9 下载源见 reference（百度网盘直链）

## 验证清单

1. 桌面机起服务 → `curl 127.0.0.1:8000/health` 桌面机本地通
2. 桌面机建隧道 → 服务器 `curl 127.0.0.1:8000/health` 通
3. `/run` 执行极简脚本（`print("hello")`）→ 返回 ok
4. `/run` 执行真实剪辑脚本（skill API）→ 生成草稿 → 桌面机剪映打开验证

## 相关文件

- `templates/jianying-web.py` — 桌面端 Flask 服务模板（复制到桌面机跑）
- `references/jianying-editor-research.md` — 剪映自动化调研结论 + 下载源
