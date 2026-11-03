# 剪映自动化生态调研（2026-08-06）

> ⚠️ **我们自己的 Mac 是剪映 10.8**（2026-08-06 远程确认：/Users/<MAC_USER>/Movies/JianyingPro/User Data/DeepAgents/Skills/10.8.0/）。**教程/文档里测通的「剪映 11.1 + VectCut jianying_pro_10」是别人的环境，不是我们实测**——任何「已测通」结论落地前必须区分「别人的环境」vs「我们的环境」；版本不同，草稿版本号（jianying_pro_10）能否被客户端直连打开要重新验证，不能拿教程结论套。

结论速查 + 细节。三个项目容易混淆，先分清：

| 项目 | 作者 | 定位 | 关键限制 |
|:---|:---|:---|:---|
| **jianying-editor-skill** | luoluoluo22（2666★） | 给 AI agent 用的剪映自动化 skill（SKILL.md + Python API） | 剪映 **5.9 及以下**；Mac 不支持自动导出 |
| **VectCutAPI**（流光剪辑） | sun-guannan（2138★，Python） | 剪映/CapCut 自动化 API（HTTP 服务 / MCP / 云端） | 本地模式产草稿要剪映导入；云端要注册 |
| **剪映内置 DeepAgents** | 字节（剪映 10.8+ 自带） | 新版剪映内置 AI 技能 | 无公开 API；与 luoluoluo22 skill 不兼容 |

## jianying-editor-skill（luoluoluo22/jianying-editor-skill）

- GitHub: https://github.com/luoluoluo22/jianying-editor-skill（MIT，2026-01 创建，活跃维护）
- 能力：写文案 → AI 配音 → 字幕（打字机动画）→ 自动配乐 → 特效/转场/滤镜 → 自动导出 MP4（1080P-4K）；录屏+智能变焦、网页动效转视频、影视解说、关键帧、复合片段
- 支持的 AI 编辑器：Antigravity / Trae / Claude Code / Cursor（**Codex 未在官方列表，但 SKILL.md 是标准格式，Codex 理论上可加载**）
- **平台状态**：
  - Windows：完整支持（含自动导出），推荐环境
  - macOS：实验性，**自动导出不支持**（需剪映手动导出）；v1.6.0（2026-04-19）做了 Apple Silicon/Intel 路径解析 + avfoundation 录屏适配，README 仍写"自动导出不支持 macOS"——两处矛盾，Mac 导出需实测
  - CapCut 国际版/手机：不支持
- **版本硬限制**：自动导出只支持剪映专业版 **5.9 及以下**（6.0+ 弹窗干扰脚本）；提供 5.9 夸克网盘下载，装完禁止更新
- 安装：PowerShell 一键 `irm is.gd/rpb65M | iex` 或 git clone 到 `.claude/skills/` `.trae/skills/` `.agent/skills/` 等
- 核心 API：`JyProject`、`add_media_safe`、`add_narrated_subtitles`、`add_text_simple`、`save()`；Mac 草稿目录 `~/Movies/JianyingPro Drafts/`
- 服务器无头环境：只能生成草稿（纯 Python 写 JSON），导出必须剪映 GUI

## VectCutAPI（sun-guannan/VectCutAPI，流光剪辑）

- GitHub: https://github.com/sun-guannan/VectCutAPI（Python，MIT）
- 能力：草稿管理、视频处理、音频编辑、图像处理、文本/字幕、特效引擎、贴纸、关键帧、媒体分析（35+ HTTP 接口 + 11 MCP 工具）
- 本地部署：`git clone` + `pip install -r requirements.txt` + `python capcut_server.py`（端口 9001）或 `python mcp_server.py`
- 系统要求：Python 3.10+ / **剪映或 CapCut 国际版** / FFmpeg——本地模式产**剪映草稿**（导入剪映二次编辑/导出），**服务器无头不能本地渲染**
- 云端（www.vectcut.com / jianyingapi.apifox.cn）：注册 → API Key → 云渲染出片（高并发/弹性扩容/AI配音/数字人）；**但文档流程第一步就是"安装客户端"**——云端也依赖本地剪映客户端配合（云端编排 + 本地执行模式），不是纯云端
- 注意：README 宣称"cloud-based"但实际注册/使用要求装剪映桌面端（用户实测：注册要下载电脑端）

## 剪映 10.8 内置 DeepAgents

- 路径：`~/Movies/JianyingPro/User Data/DeepAgents/Skills/<version>/`
- 结构：`jianying.agent.roughcut` / `speaker_local_agent` / `highlight_local_agent` / `material_understanding_local_agent` / `script_local_agent` / `align_bgm_with_video_local_agent`，每个目录只有 `SKILL.md`
- 判断：这是新版剪映内置 AI 技能（DeepAgents 是通用 agent 框架名，剪映借名），**没有公开对外 API**；搜索无结果。如果要用新版剪映自动化，需要探索剪映自身的 AI 接口（待调研），不能指望 luoluoluo22 skill

## 落地建议（对 Hermes 工作流）

1. 剪映版本 5.9 → 用 luoluoluo22 skill（最成熟，能自动导出）
2. 剪映 10.8+ → 别用 luoluoluo22 skill（版本超限）；查剪映内置 AI 能力或降级 5.9
3. 服务器自动化剪辑 → ffmpeg（已验证全自动：拼接/字幕/BGM/卖点卡）；剪映 skill 只在"客户要可编辑工程文件"或"要剪映级特效"时才值得引入
