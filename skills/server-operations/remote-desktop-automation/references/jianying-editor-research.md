# 剪映自动化调研（2026-08-06 实测结论）

## 三条路对比

| 方案 | 可行性 | 说明 |
|:---|:---|:---|
| 剪映 10.8 DeepAgents 外部调用 | ❌ 死路 | 无 API 无端口（lsof 验证 0 监听） |
| 剪映 10.8 GUI 手动用 | ✅ 能用 | 剪映里点"智能粗剪/剪口播/BGM 对齐"，人在电脑前操作 |
| 降级 5.9 + jianying-editor-skill | ⚠️ 唯一全自动 | 装旧版剪映 + skill，服务器远程全自动（功能旧） |
| ffmpeg（现状） | ✅ 已全自动 | 字幕/BGM/卖点卡都行，无剪映炫特效 |

## jianying-editor-skill（luoluoluo22/jianying-editor-skill）

- 2666★，MIT，活跃维护（2026-06-12 更新：MacOS 全面适配、v5.9+ 草稿架构）
- 能力：写文案/AI 配音/字幕（打字机动画）/自动配乐/特效转场/关键帧/**自动导出 MP4**（1080P-4K）
- 还有：录屏+智能变焦、网页动效转视频、影视解说、复合片段
- **硬要求**：Windows + 剪映专业版 **5.9 或更低**（6.0+ 弹窗干扰自动化脚本）；Mac 只能生成草稿、不能自动导出
- 使用链：桌面机装 AI agent（Claude Code/Cursor/Trae/Antigravity，或桌面机本地 Hermes——SKILL.md 标准格式兼容）→ 克隆 skill 到其 skills 目录 → 自然语言指挥
- 核心 API（确定性，生成脚本后执行）：`JyProject(...)`、`add_media_safe(...)`、`add_cloud_media/add_cloud_music`、`add_text_simple/add_narrated_subtitles`、`save()`
- Mac 草稿目录：`~/Movies/JianyingPro Drafts/`；环境变量 `JY_PROJECTS_ROOT` 可改
- 检查草稿：`python <SKILL_ROOT>/scripts/draft_inspector.py list --limit 20`

## 剪映 10.8 DeepAgents（无 API 实证）

- 路径：`~/Movies/JianyingPro/User Data/DeepAgents/Skills/10.8.0/`
- 内含 skill.md 描述：智能粗剪（roughcut）、智能剪口播（去水词/停顿/重复）、BGM 对齐、高光提取、素材理解、脚本生成
- 但 `lsof -iTCP -sTCP:LISTEN` 显示剪映（VideoFusion-macOS）**0 个监听端口**——纯 GUI 内置功能，无对外 API/CLI
- 结论：外部程序无法调用剪映 DeepAgents

## 剪映 5.9 下载源（Mac）

- 夸克网盘（skill 官方）：https://pan.quark.cn/s/81566e9c6e08
- 吾爱破解（Mac 5.9.0，验证过）：https://pan.baidu.com/s/1eSJTg44HA6QTkqyVJkQ0sA 提取码 3s7w
- B站视频（Mac 5.9，智能字幕免费）：https://pan.baidu.com/s/1WW1O4hBOkcWHZi8ADvmRSw 提取码 8888
- Windows 官方 CDN 直链（模式参考）：https://lf3-package.vlabstatic.com/obj/faceu-packages/Jianying_5_9_0_11632_jianyingpro_0_creatortool.exe
- 装完**必须禁止自动更新**（否则升回新版本破坏自动化）

## VectCutAPI（备选，绕不开剪映客户端）

- sun-guannan/VectCutAPI（2138★）：云端编排 + **本地剪映执行**——注册/使用仍要求电脑端剪映
- 本地部署生成剪映草稿（pyJianYingDraft 写 JSON，不需要剪映运行）；**导出必须剪映客户端**（服务器无 GUI 装不了）
- 结论：对无头服务器不友好，不接
