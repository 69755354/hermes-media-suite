---
name: server-migration
title: 服务器迁移与跨机数据搬运
description: 触发：迁移服务器/跨机拷数据/问SSH信息/对比目录。铁律：先确认本机身份，防SSH回自己。
version: 1.0
---

# 服务器迁移 / 跨机数据搬运

**触发：** 用户说「广州机的SSH是什么」「把A机数据迁到B机」「两台机目录对比」「拷目录过去」「rsync同步」。

## 🚨 铁律 0：第一步永远先确认「我是不是那台机器」（2026-08-09 事故）

用户提任何「某台机器」时，**先验证本机身份再搜任何连接信息**：

```
hostname                          # 本机名
curl -s --max-time 10 ifconfig.me # 公网 IP（备选 ipinfo.io/ip）
ip -4 addr show                   # 内网 IP + docker 网段
```

**为什么：** 本机 SSH 到自己的公网 IP 完全能通（密钥认证），且目录结构、文件、md5 全部一模一样——极易被当成「另一台内容一致的机器」，然后煞有介事地对比半天、甚至编出迁移方案。

**事故实录（2026-08-09）：** 用户问「广州机的 SSH 地址/端口/用户名/迁移目录/目标目录」。我翻 wiki 部署文档拿到 <GZ_HOST>，SSH 上去发现 home 结构跟本机一模一样（backup_20260804/deliverables/assets/wiki/.hermes 全在），还输出「两台机内容一致」的分析。用户骂「你特么就是广州几」——一查 hostname=VM-0-11-ubuntu、ifconfig.me=<GZ_HOST>，**本机就是广州机**。白忙 3 轮 + 差点给错误迁移方案。

**识别「SSH 回自己」的信号：** 远程 home 目录结构/文件清单/时间戳与本机高度重合、md5 全一致 → 高度疑似自己，先 `hostname` + 公网 IP 验证。

## 连接信息核实（只读探测，不跑业务）

```
① 端口测试：timeout 8 bash -c 'echo > /dev/tcp/<IP>/22'  # 免费，不耗API
② 免密探测：ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=8 \
     -i ~/.ssh/id_ed25519 ubuntu@<IP> "whoami; hostname"
③ 用户名顺序：先 ubuntu（腾讯云/阿里云 Ubuntu 默认），再 root；root 通常拒密钥登
④ 文档先查：wiki/spec、backup_*/skills 里的部署记录（如 n8n-deploy-china 文档）
   ⚠️ 文档连接信息可能过时/废弃——以实测为准（n8n 2026-07-05 已废弃，广州机无 ~/n8n，别按旧文档找）
```

## 迁移前盘点

```
① du -sh 各候选目录（wiki/.hermes/deliverables/assets/项目文件/backup_*）排序
② 看源机最新 mtime：还有近几天的新文件 = 源机仍在产数据，先确认增量边界
③ 目标目录映射：目标机结构未知就直说问用户，别猜（猜错=迁错地方）
④ docker 容器：数据卷迁移是另一回事（n8n/searxng/astrbot/gewe），先确认目标机装没装 docker
```

## 执行与验证

```
rsync -av --dry-run <src>/ <dst>/   # 先出差异清单，用户过目再动手
md5sum 两边文件对比                  # 关键文件校验一致性
```

## 坑

- **废弃部署不迁**：skill 标注「已废弃」的服务（如 obsolete webhook skill）别按旧文档迁移，先确认线上是否还在用。
- **known_hosts 是 hash 的**：`cut -d' ' -f1 known_hosts` 看不出 IP，别靠它确认机器清单。
- **别拿「远程文件一样」当结论**：先排除「那就是我自己」再谈内容对比。
