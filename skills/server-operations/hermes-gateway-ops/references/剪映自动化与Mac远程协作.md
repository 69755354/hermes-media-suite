# 剪映自动化与 Mac 远程协作（2026-08-06）

服务器 Hermes 与用户 Mac 上剪映协作的方案调研 + 已落地部分。⚠️ 状态标注：SSH 密钥/隧道已验证 ✅；Web 服务联调未完成 ⏳（用户端操作卡在文件创建，待续）。

## 剪映自动化工具选型（外部调研结论，2026-08-06 查证）

| 工具 | 平台要求 | 能力 | 状态 |
|:---|:---|:---|:---|
| **luoluoluo22/jianying-editor-skill**（2666★，MIT） | **Windows + 剪映 5.9 或更低**（Mac 实验性：自动导出不支持） | 文案/配音/字幕/特效/录屏/自动导出 MP4，自然语言全流程 | 最主流，2026-06-12 刚更新「MacOS 全面适配」但 README 未同步（两处矛盾，导出要实测） |
| **VectCutAPI**（sun-guannan，2138★） | 本地部署：Python3.10+ + FFmpeg + **剪映/CapCut 客户端**（无头服务器不可）；云端：注册 vectcut.com 拿 key，但 Apifox 文档流程「安装客户端」在获取 key 之前——**不是纯云端**，仍要本地剪映执行 | 草稿管理/字幕/特效/关键帧/云端渲染（名义） | 服务器无头跑不了；云端也要本地客户端，自动化价值低 |
| ffmpeg（现状） | 服务器直接可用 | 拼接/字幕烧录/BGM/卖点卡 | ✅ 已全自动，效果朴素 |

**结论：** 服务器要全自动出片 = ffmpeg；要剪映级效果（转场/字幕动画）= 必须用户在 Windows/Mac 机器上装剪映 5.9 + 上述 skill。VectCut 云端名不副实（注册仍要电脑端）。

## jianying-editor-skill 关键约束（用户想用时对照）

- **剪映必须 5.9 或更低**（6.0+ 弹窗干扰自动化；官方提供 5.9 夸克网盘链接，装完禁止更新）
- Mac：草稿生成/字幕/配音可用，**自动导出不支持**（手动剪映里导出）——「自动 80% + 手动导出 10 秒」
- 安装：`git clone https://github.com/luoluoluo22/jianying-editor-skill.git <agent的skills目录>/jianying-editor`（Hermes/Claude Code/Cursor/Codex 均可，SKILL.md 标准格式）
- 核心 API（生成脚本用）：`JyProject(...)`、`add_media_safe(...)`、`add_cloud_music(...)`、`add_text_simple(...)` / `add_narrated_subtitles(...)`、`save()`；Mac 草稿根目录 `~/Movies/JianyingPro Drafts/`；环境变量 `JY_PROJECTS_ROOT` 可覆盖

## SSH 反向隧道方案（已验证 ✅：密钥 + 隧道）

目标：服务器 Hermes 远程操作 Mac 剪映（Mac 当「渲染机」）。

**① Mac 生成密钥（已验证流程）：**
```bash
mkdir -p ~/.ssh
ssh-keygen -t ed25519 -C "mac-jianying" -f ~/.ssh/id_ed25519   # 一路回车
cat ~/.ssh/id_ed25519.pub    # 公钥内容发给服务器侧，追加到 ~/.ssh/authorized_keys（chmod 600）
```
- **⚠️ 用户分不清公钥 vs 指纹**：ssh-keygen 输出里的 `SHA256:...` 是指纹不是公钥；公钥必须以 `ssh-ed25519 AAAA...` 开头（`cat ~/.ssh/id_ed25519.pub` 的输出）
- 服务器公钥追加后：`ssh ubuntu@<IP> "echo 通了"` 验证

**② 反向隧道（已验证 ✅：服务器 8000 可达）：**
```bash
ssh -R 8000:localhost:8000 -N ubuntu@<GZ_HOST>   # Mac 上挂住，窗口别关
```
服务器侧 `socket.connect(("127.0.0.1", 8000))` 成功 = 隧道通。

**③ Mac 端 Web 服务（⏳ 未联调）：**
- 脚本：`/home/ubuntu/scripts/mac_remote/jianying-web.py`（服务器侧备份）
- 功能：`GET /health` + `POST /run {"script": "python代码"}`（在 skill 环境执行，PYTHONPATH 指向 skill 根，返回 stdout/stderr）
- Mac 启动：`pip3 install flask && python3 ~/jianying-web.py`（默认 skill 路径 `~/.agent/skills/jianying-editor`，其他路径用 `JY_SKILL_ROOT=...` 指定）
- 后续：服务器 POST localhost:8000/run 传剪辑脚本 → Mac 生成剪映草稿 → 手动导出（Mac 版）或 auto_exporter（Windows 5.9）

## 给用户 Mac 终端指令的教训（2026-08-06 反复卡）

用户终端操作 Mac 时连续踩坑：scp 加了端口参数（报 `connect_to localhost port 8000: failed`）、把指纹当公钥发、nano/TextEdit 粘贴文件截断（文件只剩一半）。**给非程序员用户的 Mac 指令原则：**
- 命令**原样复制**，明确「不要加任何参数/不要改」
- scp 默认走 22 端口，**绝不加 -P 端口**（隧道 8000 是另一回事，别混）
- 文件传输优先 scp 拉取（一键），其次才让用户手动粘贴（易截断）
- 每步让用户回报输出/报错，逐步推进，别一次给 4 条命令
- 用户对「复制 cat 命令的输出」理解差——明确说「以 ssh-ed25519 开头的那一行」

## 服务器公网 IP（SSH/隧道用）

`<GZ_HOST>`（腾讯云 VM-0-11-ubuntu，内网 10.1.0.11）
