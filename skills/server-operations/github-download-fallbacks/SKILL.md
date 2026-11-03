---
name: github-download-fallbacks
description: git clone 卡死/超时时改用 codeload zip 下载。触发：装 GitHub skill/repo。
---

# GitHub 下载降级（大陆服务器）

本服务器直连 GitHub 的 git 协议经常卡死：clone 以 40-60 KiB/s 龟速爬行、进度停在低百分比反复刷新同一行、最后 `unexpected disconnect while reading sideband packet`。不要死等，换 zip 下载通道。

## 诊断顺序

1. 探测连通性：`curl -sI --max-time 15 https://github.com` — HTTP 200 表示通但可能慢；404/超时另查网络。
2. 查仓库大小与默认分支：
   ```bash
   curl -s https://api.github.com/repos/<owner>/<repo> | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('size'),'KB',d.get('default_branch'))"
   ```
   size 单位 KB。仓库 >10MB 时 git clone 大概率要几分钟以上，直接走 zip。
3. git clone 已启动但进度不动 → kill 掉换 zip，别等。

## 首选方案：codeload zip

```bash
curl -sL --max-time 500 -o /tmp/<repo>.zip https://codeload.github.com/<owner>/<repo>/zip/refs/heads/<branch>
unzip -q /tmp/<repo>.zip -d /tmp/extract && mv /tmp/extract/<repo>-<branch> <目标位置>
```

- 大文件放后台：terminal background=true + notify_on_complete=true，再 process wait。
- zip 内顶层目录名固定格式：`<repo>-<branch>`（如 jianying-editor-skill-main）。
- 下载前先 `rm -rf` 目标目录，避免半成品残留。
- 装完必须验证：ls 目标目录确认结构完整；若是技能，跑 skills_list 确认被识别。

## 实测数据

24.8MB 仓库 git clone 卡死在 28%（~5 分钟无进展后断连）；codeload zip 仅 6MB、后台约 1-2 分钟下完。zip 是单请求压缩包，git 是对象流，差距巨大。

## 坑

- 进度输出在同一百分比反复刷新 = 快断了，kill 换通道。
- 不要用 `--depth 1` 碰运气，直连 git 协议就是慢，换通道才是正解。
- zip 下载成功后记得清理 /tmp 下的 zip 和解压残留。
- 备选镜像（ghproxy 等）已知存在但未在本环境实测过，优先 codeload。
