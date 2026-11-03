---
name: github-repo-install
description: 从 GitHub 装仓库/技能，git clone 卡死时改用 codeload zip 下载。
---

# GitHub 仓库安装（本服务器网络环境）

## 症状：git clone 直连 GitHub 卡死

本服务器到 github.com 的 git 协议通道不稳定，大仓库 clone 常卡死：

- 卡在 `Receiving objects` ~28% 不动，速度 40-60 KiB/s
- 报 `fetch-pack: unexpected disconnect while reading sideband packet`
- 超时退出后目标目录可能根本没建成（ls 直接报错）
- 实测 jianying-editor-skill（git 仓库 24.8MB）：git clone 卡 5 分钟停在 28% → 杀掉换 zip 几秒搞定

## 首选方案：codeload zip 下载（稳定快速）

### 1. 查仓库大小和默认分支（api.github.com 通常可通）

```bash
curl -s https://api.github.com/repos/<owner>/<repo> | python3 -c "import json,sys; d=json.load(sys.stdin); print('size:', d.get('size'), 'KB; branch:', d.get('default_branch'))"
```

### 2. 下载 zip（大仓库用后台跑 + notify_on_complete）

```bash
curl -sL --max-time 500 -o /tmp/<repo>.zip https://codeload.github.com/<owner>/<repo>/zip/refs/heads/<branch>
```

### 3. 解压安装

```bash
cd /tmp && unzip -q <repo>.zip -d extract && ls extract/
mv extract/<repo>-<branch> <目标路径>
rm -rf extract /tmp/<repo>.zip
```

## 装成 Hermes 技能后的验证

- `skills_list` / `hermes skills list` 能看到技能名
- read_file 读 SKILL.md 确认 frontmatter（name/description）解析正常
- 目录结构完整（docs/rules/scripts 等按需核对）

## 坑

- 下载完 `ls -la` 看 zip 体积是否合理：README 级仓库的 zip 只有几 MB，比 git 仓库体积小很多，别用 git 仓库大小当预期
- raw.githubusercontent.com 本环境会 301 回 github.com，不是可用下载源，直接用 codeload
- 换方案前先 kill 掉卡死的 clone 进程，避免残留半成品目录
- 大 zip 用 background=true 跑，别前台等超时
