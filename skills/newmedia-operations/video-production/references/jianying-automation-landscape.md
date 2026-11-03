# 剪映自动化方案盘点（2026-08-06 调研）

> 目标：服务器（无头 Linux）自动化操作 Mac 上的剪映专业版。本文件是三条路线的调研结论，避免重复踩坑。

## 路线对比

| 方案 | 版本要求 | 自动导出 | 服务器可用 | 结论 |
|:---|:---|:---|:---|:---|
| VectCutAPI `jianying_pro_10` | 剪映 10.x 草稿格式，11.1 能打开 | ❌ 要剪映客户端手动导出 | ✅ 草稿生成可在服务器跑 | **✅ 推荐（不降级）** |
| luoluoluo22/jianying-editor-skill | 剪映 5.9 或更低 | ✅（Windows 全自动；Mac 不支持自动导出） | ❌ 要本地剪映 | ⚠️ 降级路线，唯一全自动 |
| 剪映 11.1 DeepAgents | 内置 | GUI 内点 | ❌ 无 API | ❌ 外部调不了 |

## VectCutAPI（sun-guannan/VectCutAPI，2138★，MIT，活跃）

- 官方支持三种草稿格式：`draft_profile: capcut_legacy / jianying_legacy / jianying_pro_10`
  （config.json.example 注释：`jianying_pro_10 for Jianying Pro 10.x`）
- 草稿模板齐全：`template/`（draft_info.json、draft_meta_info.json、draft_content.json 等）+ `pyJianYingDraft/` Python 库
- **pyJianYingDraft 是草稿生成器不是迁移器**——能生成新草稿，不能读 V4R 老草稿提取数据。V4R 迁移要开发。
- 云端 API（vectcut.com / 流光剪辑）：注册流程第一步就是「安装客户端」（剪映电脑端），云端编排 + 本地执行——**不是纯云端**，服务器用不了。
- 部署要求：Python 3.10+、剪映或 CapCut 国际版、FFmpeg。本地服务 `python capcut_server.py`（端口 9001）+ MCP `mcp_server.py`。

## luoluoluo22/jianying-editor-skill（2666★，MIT）

- 给 AI agent（Claude Code/Cursor/Trae/Antigravity；Codex 未列但 SKILL.md 格式兼容）用的剪映自动化 skill。
- **自动导出深度依赖剪映 5.9 或更低**（6.0+ 弹窗干扰自动化脚本），装完禁止更新。
- Windows 完整支持；macOS 实验性（草稿/录屏可用，**自动导出不支持**，手动点）。
- 6/12 更新声称「全面适配 MacOS + v5.9+ 架构」——与 README「Mac 不支持自动导出」有出入，实测为准。
- 5.9 安装包下载源（Mac 版）：夸克网盘（skill README）、百度网盘 `pan.baidu.com/s/1eSJTg44HA6QTkqyVJkQ0sA` pwd `3s7w`（吾爱破解）、`pan.baidu.com/s/1WW1O4hBOkcWHZi8ADvmRSw` pwd `8888`（B站 BV1tw4m1a72c）。

## 剪映 11.1 DeepAgents（GUI 内置）

- skills 目录：`~/Movies/JianyingPro/User Data/DeepAgents/Skills/10.8.0/`，每个 agent 只有一个 `skill.md` 描述文件：
  - jianying.agent.roughcut（智能粗剪）、speaker_local_agent（智能剪口播）、highlight_local_agent（高光提取）、material_understanding_local_agent（素材理解）、script_local_agent（脚本生成）、align_bgm_with_video_local_agent（BGM 对齐）
- **无对外 API**：剪映进程（VideoFusion-macOS）实测 **0 个监听端口**，外部程序调不了，只能在剪映 GUI 里点。

## V4R 老草稿迁移

- V4R = 剪映草稿内部 schema 版本（老格式）。老草稿 → 新版草稿（jianying_pro_10）需要：读老 draft_content.json → 提取画面/音频/字幕/BGM/时间点 → 映射到新格式重建。
- 剪映 6.0+ draft_content.json 有**加密机制**（gist renezander030/521e6c6e8590a2a6e917009d9313bc55）——迁移前先验证老草稿 JSON 是明文还是加密，决定迁移工具怎么写。
- 迁移开发量评估：先拿一个真实 V4R 草稿路径，远程看 JSON 结构再估。

## Mac 远程链路（已搭建，可用）

- Mac 公钥已加服务器 authorized_keys（`ssh-keygen -t ed25519` + 公钥追加，免密码）。
- Mac 端 `jianying-web.py`（Flask）：`GET /health` + `POST /run`（在 skill 环境下执行任意 Python 脚本，返回 stdout/stderr）。
- 隧道：`nohup ssh -R 8000:localhost:8000 -N ubuntu@<GZ_HOST> &`，服务器访问 `http://127.0.0.1:8000` 即达 Mac。
- 服务器公网 IP：<GZ_HOST>。
