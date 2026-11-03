# 内存升级（实例变配）前后准备与验证（2026-08-14 实测）

场景：云厂商把实例从 2GB 升到 4GB（变配），升级会**重启实例**，网关断一次，正在跑的后台任务（codex/claude）全部中断。

## 升级前准备（用户说「我要升级了」之后做）

1. **备份关键数据**（tar 打包，防变配意外）：
```bash
mkdir -p /home/ubuntu/backup
BK="/home/ubuntu/backup/hermes_pre_upgrade_$(date +%Y%m%d_%H%M%S).tar.gz"
tar czf "$BK" -C /home/ubuntu .hermes/state.db .hermes/config.yaml .hermes/SOUL.md .hermes/.env .hermes/skills workflow/outputs workflow/wiki workflow/projects 2>/dev/null
```

2. **确认 gateway 自启**（systemd enabled，升级重启后自动恢复）：
```bash
hermes gateway status   # Active: active (running) + Loaded: enabled 即 OK
```
- 注意是**用户级** systemd：`systemctl --user status hermes-gateway`，系统级 `systemctl list-unit-files | grep hermes` 查不到是正常的
- gateway 启动命令：`<venv>/bin/python -m hermes_cli.main gateway run`

3. **记录正在跑的后台任务 + prompt 路径**，升级后重跑。

## 🔴 /tmp 在实例重启后会被清空（2026-08-14 实测）

升级重启后 `/tmp` 里所有文件消失——**凡是还要重跑的任务 prompt，必须存持久目录**（如 `/home/ubuntu/workflow/prompts/`），别放 /tmp。本次 claude 评审 prompt 放 /tmp 被清，报 `No such file or directory`，只能重写重跑。

## 升级后验证清单（按序执行）

1. 内存生效：`free -h`，total 应从 1.9Gi 升到 3.6Gi+；`available` 充足
2. gateway 自动恢复：`hermes gateway status` → active (running)；`cat ~/.hermes/gateway_state.json` → feishu/weixin 均 connected
3. swap 保留：`swapon --show`——**swapfile 重启后不会自动启用**，需要手动 `sudo swapon /swapfile2`（除非写了 fstab）；`.env`/config 改动在重启后自动生效（如模型切换）
4. 平台连接确认 + 观察 FTS 卡顿警告（`grep "FTS write corruption" ~/.hermes/logs/gateway.log`）是否随内存增大消失
5. 重跑被打断的后台任务（先重写 /tmp 里的 prompt，或从 workflow/prompts/ 读）

## 内存容量经验值（2GB → 3.6GB 实测对比）

| 内存 | 能否并行重任务 | 依据 |
|:--|:--|:--|
| 1.9G（旧） | ❌ 必须 flock 串行 | gateway ~400MB + codex ~230MB + claude ~240MB + node 们 ~150MB + 系统 ~400MB ≈ 1.5GB 峰值，逼近爆、触发 swap 卡死 |
| 3.6G（升后） | ✅ 并行上限 **4 个**（5 个排队） | 系统+网关 ~900MB，每个重任务（codex/claude+node）~450MB：3个=2.2GB 占60%安全；4个=2.7GB 占72% 还有~1GB 余量可行；5个=3.15GB 余量见底危险 |

升级后派任务可去掉 flock 串行限制，直接并行（任务间有依赖的仍需排队）。**用户拍板（2026-08-14）：同一时间最多 4 个重任务，第 5 个主动排队。**
