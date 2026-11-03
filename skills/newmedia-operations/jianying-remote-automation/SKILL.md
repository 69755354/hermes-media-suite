---
name: jianying-remote-automation
title: 剪映远程自动化（SSH 反向隧道 + Mac 渲染机）
description: 触发：剪映自动化/远程剪辑/Mac当渲染机。SSH隧道+Mac Web服务远程调度剪映。
version: 1.0.0
---

# 剪映远程自动化（JianYing Remote Automation）

服务器（无头 Linux）跑 Hermes 做主脑，用户 Mac 跑剪映（JianYing Pro）当渲染机，
通过 **SSH 反向隧道 + Mac 端 Web 服务** 把桌面剪辑能力暴露给服务器远程调度。

## 架构

```
Mac（剪映 + skill + Flask服务:8000） ←SSH反向隧道→ 服务器 Hermes
   │  /health 健康检查                        │ POST /run 远程执行剪辑脚本
   │  /run 在 Mac 上执行 Python 脚本          │ 生成草稿 → 剪映导出
```

## 硬限制（2026-08-06 调研确认，先读再动手）

- **jianying-editor-skill（luoluoluo22/jianying-editor-skill）自动导出只支持剪映 5.9 及以下**
  - 6.0+ 弹窗多，自动化脚本失效；装完**禁止更新**
  - macOS **不支持自动导出**（README 明确，需剪映手动导出；v1.6.0 SKILL.md 声称"全面适配 MacOS"但导出仍受限——矛盾，Mac 导出需实测）
  - CapCut 国际版 / 手机剪映不支持，只适配国内版剪映专业版桌面端
- **服务器（无头）不能直接用 skill**：生成草稿不需要剪映运行（纯 Python 写草稿 JSON），但导出必须剪映 GUI。服务器只能生成草稿 → 打包给 Mac 剪映导出
- **剪映 10.8 自带 DeepAgents**（`~/Movies/JianyingPro/User Data/DeepAgents/Skills/<ver>/jianying.agent.*`，每 agent 只有 SKILL.md）——新版剪映内置 AI 技能，**与 luoluoluo22 skill 不兼容**，无公开对外 API 文档
- **版本直连·环境事实（2026-08-07 用户纠正）**：**我们 Mac 装的是剪映 10.8**（2026-08-06 远程确认：`/Users/<MAC_USER>/Movies/JianyingPro/User Data/DeepAgents/Skills/10.8.0/`，剪映进程在跑）。**11.1 是教程/文档里的环境，不是我们实测**——「VectCut jianying_pro_10 草稿 → 剪映 11.1 客户端直连打开已测通」的结论不能套到我们 10.8 上。**VectCut jianying_pro_10 草稿能否被我们 Mac 的剪映 10.8 直连打开 = 待实测**（要么 Mac 实测：隧道+服务拉起来生成测试草稿看 10.8 能否打开；要么拉 VectCut 源码查版本常量）。10.8 的 DeepAgents 无 API 无端口=外部调用死路，仅 GUI 手动。服务器上无 VectCut/pyJianYingDraft 部署（全在 Mac 侧），服务器只当仓库；`jy_wrapper.py` 只是薄封装，核心是 `pyJianYingDraft` 库（Mac 侧装）
- **⚠️ 别把教程环境当自己环境**：引用外部「已测通」结论前，先确认测试环境是否=我们的环境（版本/系统/账号），不一致就当未验证

## 搭建步骤

### 1. SSH 密钥（Mac → 服务器，密码忘了也能配）
```bash
# Mac
ssh-keygen -t ed25519 -C "mac-jianying" -f ~/.ssh/id_ed25519   # 一路回车
cat ~/.ssh/id_ed25519.pub    # 把 ssh-ed25519 AAAA... 整行发给服务器侧
```
服务器侧把公钥追加进 `~/.ssh/authorized_keys`（chmod 600 / .ssh 700）。
验证：`ssh ubuntu@<IP> "echo ok"`。

### 2. Mac 端服务（templates/jianying-web.py）
Flask 服务，两个接口：
- `GET /health` — 健康检查（返回 skill 路径是否存在、剪映草稿目录）
- `POST /run` — `{"script": "python代码"}` 在 skill 环境下执行（PYTHONPATH 指向 skill，cwd=skill 根目录），返回 stdout/stderr

```bash
pip3 install flask
nohup python3 ~/jianying-web.py > /tmp/jy-web.log 2>&1 &   # 默认 skill 根目录 ~/.agent/skills/jianying-editor，可 JY_SKILL_ROOT 覆盖
```

### 3. 反向隧道（关键：服务+隧道两个进程都要跑）
```bash
nohup ssh -R 8000:localhost:8000 -N ubuntu@<服务器IP> > /tmp/jy-tunnel.log 2>&1 &
```
- 两个命令都后台（`nohup`），Mac 不能开多窗口也不怕
- 服务器验证：`curl http://127.0.0.1:8000/health`

### 4. 远程调用（服务器侧）
```python
import json, urllib.request
resp = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/run",
    data=json.dumps({"script": "print('hi')"}).encode(),
    headers={"Content-Type": "application/json"}, timeout=60).read())
```

## 隧道排障（反复踩的坑）

| 症状 | 根因 | 处理 |
|:---|:---|:---|
| `Warning: remote port forwarding failed for listen port 8000` | 旧隧道占着服务器 8000 | 服务器 `sudo lsof -i :8000` 找 sshd PID 杀掉；Mac `pkill -f "ssh -R 8000"` 后重建 |
| curl 超时（连上但无响应） | 隧道在但 Mac 服务没跑，或隧道"半死"（CLOSE_WAIT 一堆） | 查 `cat /tmp/jy-web.log` 有没有 `Running on`；隧道半死→杀服务器 sshd 隧道会话 + Mac 重建 |
| /health 通但 /run 超时 | Mac 端脚本执行慢/挂起 | 先测极简脚本区分执行问题 vs 转发问题 |
| 服务 `Running on 8000` 但 health 不通 | 隧道断（窗口关/进程死） | 重跑隧道命令；确认隧道日志无报错 |

## 调研备忘（references/）

- `references/ecosystem-research.md` — VectCutAPI / jianying-editor-skill / 剪映 DeepAgents 调研结论
- `templates/jianying-web.py` — Mac 端 Flask 服务模板（可直接复制部署）

## Pitfalls

- **别让用户在 Mac 终端反复手输命令**——能用 `/run` 远程执行就不麻烦用户；用户找不到文件时用 `/run` 列目录
- **公钥 ≠ 指纹**：让用户发 `cat ~/.ssh/id_ed25519.pub` 的输出（`ssh-ed25519 AAAA...` 开头），不是 ssh-keygen 显示的 `SHA256:...` 指纹行
- **隧道和服务是两个进程**：只起一个 = curl 超时，用户困惑"我开了啊"
- **多次 nohup 隧道**会在服务器堆僵尸 sshd（半死转发）——重建前先清干净
