---
name: github-repo-creation
description: 触发：建GitHub仓库/推代码/gh auth/代码托管/发仓库网址。私有仓库托管客户项目代码。
author: hermes-curator
license: internal
metadata:
  hermes:
    tags: [github, gh-cli, repo, push, hosting]
    category: server-operations
---

# GitHub 仓库创建与代码托管（gh CLI）

## When to Use

用户要求把项目推 GitHub / 要一个仓库网址 / 建私有仓库托管客户代码。场景：小程序前端/后端项目写完要托管、要发链接给小鹿或客户看代码、跨机项目要异地备份。

## 环境准备（新加坡机实测）

```bash
# 1. 装 gh CLI（apt 官方源）
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install -y gh

# 2. git 用户配置（推代码必需）
cd <项目> && git config user.name "HermesOps" && git config user.email "ops@hermes.local"
```

## 🔴 gh auth 的核心坑：read:org scope 缺失

**症状：** 用户给了 PAT（Personal Access Token），`echo "<token>" | gh auth login --with-token` 报：
`error validating token: missing required scope 'read:org'` → 登录失败，gh auth status 显示未登录。

**根因：** gh CLI 的 login 流程硬性要求 token 带 `read:org`（读组织信息），用户生成的 classic token 只勾了 `repo` 权限就没法通过 login 校验。

**✅ workaround：不用 login，直接用 GH_TOKEN 环境变量（2026-08-11 实测有效）：**
```bash
export GH_TOKEN="ghp_..."          # 每次 terminal 调用前 export（不落盘文件）
gh api user --jq '.login'          # 拿用户名（如 gordonguo996）
gh api rate_limit --jq '.resources.core.remaining'   # 验证 token 有效
```
GH_TOKEN 绕过 login 的 scope 校验，repo create/push 完全可用。

## 建私有仓库 + 推代码

```bash
export GH_TOKEN="ghp_..."
cd <项目目录>
gh repo create <repo名> --private --source=. --push
# 成功输出仓库 URL + push 完成
gh repo view <用户名>/<repo名> --json url -q .url   # 确认 URL
```

**要点：**
- `--private` = 私有仓库（用户要私有就私有，默认别公开——客户代码敏感）
- `--source=.` = 当前目录作为仓库内容，`--push` = 直接推
- 分支默认 master
- 网络慢（GitHub 国内访问慢）：多等、重试；token 生成本身很快，卡的是页面加载

## 跨机推送（2026-08-12 实测）

**原则：哪台机能访问 GitHub 就在哪台机 push，不用经新加坡中转拉文件。**

- 广州机（<GZ_HOST>）实测 `curl https://github.com` 200 可达 → 直接在那台机加 remote 推
- 中转（scp 拉到新加坡再推）只适合「目标机完全无法访问 GitHub」的场景；scp -r 可能只拉回 `.git` 目录文件不全，先验证文件在不在再推

```bash
# 目标机直接推（token 临时嵌 remote，推完必须清——见 Token 卫生）
cd <项目目录>
git remote add origin https://<user>:<TOKEN>@github.com/<user>/<repo>.git 2>/dev/null || git remote set-url origin https://<user>:<TOKEN>@github.com/<user>/<repo>.git
git push -u origin master
# ⚠️ 立刻清掉 remote 里的 token（否则 .git/config 落盘明文 token）
git remote set-url origin https://github.com/<user>/<repo>.git
```

## Token 卫生（重要）

- **token 值不写进任何文件/脚本/记忆**——只在命令里用 env 变量临时传递
- 用完提醒用户：GitHub → Settings → Developer settings → Personal access tokens 里删掉或等过期（90 天）
- 仓库私有 → 别人要看代码走 Collaborators 授权，或用户决定转公开

## 备份/生产文件推送前的密钥脱敏（2026-08-21 实测）

**触发：** 用户要求把生产备份源码/配置推 GitHub 做版本管理。**先查密钥再动手，不能直接传。**

1. **源码文件**：Hermes 源码 grep `api_key|token|secret` 会命中几十到几百处（实测 adapter.py 85 处、run.py 257 处）——多数是**变量名/注释/HTTP 头**（如 `_get_scoped_secret`、`app_secret`、`ark-request-timestamp`），不是明文密钥。判断方法：正则扫 `sk-[A-Za-z0-9]{20,}|ark-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKLT...` 找真实密钥模式，命中才是真泄露。
2. **config.yaml**：几乎必然含明文密钥（实测：火山 ark-xxx、智谱 bigmodel 34e34c...、DeepSeek sk-xxx 全在）——**必须脱敏**。用 python 正则把 `api_key: <值>` 全部替换为 `<REDACTED>`（含 fallback_chain 内嵌 JSON 里的 key），再扫一遍确认无残留。
3. **README 注明**：写明哪些文件脱敏过、原 MD5（回滚用）、回滚路径。
4. **仓库必须私有**，public 绝对禁止；推送前确认 token 有权限（见下节 scope 坑）。

**脱敏脚本要点：**
```python
import re
content = open(path, encoding='utf-8').read()
content = re.sub(r'(api_key:\s*)([^\s]+)', r'\1<REDACTED>', content)
# fallback_chain 内嵌 JSON 的 key 也换掉
content = re.sub(r'(api_key\\?"\s*:\s*\\?")([^"\\]+)', r'\1<REDACTED>', content)
```

## 🔴 gh repo create 的 scope 坑：token 只有空 scopes 时建仓库直接失败（2026-08-21 实测）

**症状：** `gh repo create <name> --private --source=. --push` 报：
`GraphQL: Your token has not been granted the required scopes to execute this query. The 'createRepository' field requires one of the following scopes: ['public_repo']` — token scopes 是空的。

**根因：** 老 token / 只读 token 没勾 repo scope；`gh auth status` 显示 `Token scopes: none`。GH_TOKEN 绕过 login 的 read:org 校验 ≠ 有建仓权限——**建私有仓库需要 `repo` scope（或 public_repo）**。

**处理：**
- 让用户生成新 token：https://github.com/settings/tokens/new → 勾 `repo`（完整仓库权限）→ 发 Hermes 用（用后提醒删除）
- 或者用户自己在网页建空私有仓库（New repository → Private），Hermes 只 push（push 到已有仓库不需要 createRepository 权限，值得一试）
- 建仓前先 `gh api rate_limit --jq '.resources.core.remaining'` + `gh repo list` 确认 token 有效和已有仓库情况——**先查清再动手，别等到 GraphQL 报错才发现 scope 不够**

## 用户说「不是建过仓库？」但 repo list 空的查证法（2026-08-21 实测）

**症状：** `gh repo list` 为空，但用户记得某个机/某个 agent 建过仓库（如「小鹿不是建了一个仓库？」）。

**先别断言「没有仓库」——token scopes 空时私有仓库本来就看不见。查证顺序：**
1. `gh auth status` 看 `Token scopes:`——空/none 时 repo list 空**不代表没仓库**，只是看不到私有仓库
2. 到可能建过仓库的机器上找 `.git` 目录的 remote：`find /home/ubuntu -maxdepth 4 -name '.git' -type d` + 逐个 `git -C <父目录> remote -v`——广州机实测在 `billing-system/.git` 找到 `https://github.com/<user>/billing-system.git` remote（有真实提交历史）
3. 用 remote 里的 repo 名 `gh api repos/<user>/<repo> --jq '.private, .html_url'` 验证存在性；404 说明仓库可能被删/改名/转组织，再决定是重建还是让用户去 GitHub 确认

**教训：** remote 存在 ≠ 仓库还在（可能被删/转组织/账号变更）；token 空 scope 下 404 是「看不见」不是「不存在」，两者要区分汇报。

## 用户偏好

- GitHub 账号注册/Tok en 生成是用户本人操作（邮箱验证），等用户给 token，别催
- 用户网速慢卡在注册/生成步骤时，给替代方案（Gitee 国内快 / 直接同步回广州机不搞外网仓库），不硬等
- 建完直接汇报网址 + 后续待办（后端接口/联调等），不自作主张转公开

## 踩坑记录

| 症状 | 根因 | 处理 |
|:---|:---|:---|
| `error validating token: missing required scope 'read:org'` | token 没 read:org scope | 用 GH_TOKEN env 绕过 login，不用 gh auth login |
| `gh auth status` 显示未登录但 token 有效 | login 校验失败 | 直接 `export GH_TOKEN=...` 后用 |
| token 嵌进 remote URL 推完没清 | `.git/config` 落盘明文 token（安全风险） | 推完立刻 `git remote set-url origin https://github.com/<user>/<repo>.git` |
| 无 gh CLI | 未安装 | 上面 apt 安装流程 |
| `gh repo create` 报 `createRepository requires scopes: ['public_repo']` | token scopes 为空（无 repo 权限） | 让用户生成勾 `repo` scope 的新 token，或用户在网页建空私有仓库后只 push；建仓前先 `gh repo list` 摸清现状 |
| 生产备份（config/源码）要推仓库 | 源码 grep 命中大量 api_key/token 字样（多为变量名），config 含明文密钥 | 先正则扫真实密钥模式 + config 脱敏为 `<REDACTED>` 再推，只推私有仓库（见「备份/生产文件推送前的密钥脱敏」节） |
| GitHub 页面打不开/卡注册 | 国内网络 | 换 Gitee 或本地同步，不硬等 |
