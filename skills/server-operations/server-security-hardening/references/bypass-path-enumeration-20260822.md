# 出片确认闸物理防绕 — 绕过路径穷举与落地修正（2026-08-22 claude 独立判断）

来源：广州 execute_api 出片确认闸加固论证（小鹿自述「我改不了」被实测推翻后，claude 独立判断）。核心结论：**原三层方案（chmod 444 + 删 sudoers ALL + 哈希 watchdog）方向对但防错地方，且缺四条 P0 中任何一条仍可绕**。

## 决定性发现（★ = 推翻方案前提）

1. **★ B0 软模式让闸自失效**：`10-gate-soft.conf`（systemd drop-in）写 `HERMES_GATE_SOFT=1`，staging 版 `_HARD_ENTRIES = set()` → `soft = (env=="1" and entry not in _HARD_ENTRIES)` 恒真 → `_verdict()` 恒 `return None`（放行）。**攻击者不用改任何文件，闸自己就是关的**。部署前必须：删 drop-in + daemon-reload，且 `_HARD_ENTRIES` 填 `{"execute","video_talk"}`。
2. **★ B2 chmod 444 不防 unlink**：POSIX 删除文件取决于**父目录**写权限，与文件自身权限无关。`/home/ubuntu`、`.hermes/scripts` 都对 ubuntu 可写 → root 的 444 文件照样 `mv` 掉换同名文件。**必须把闸文件迁到 root 属主目录（如 `/opt/hermes/gates/` root:root 755），只 chmod 不迁目录 = 白做**。
3. **★ B3 真正的 root 通路是密码残留**：live `.env` 已摘（08-19），但 `SUDO_PASSWORD` 明文仍在 ubuntu 可读位置：`.env.bak-weixin-off-20260809`、`profiles/customer/.env.bak_20260806`、两个 state.db（`strings` 可捞）。有密码 + `(ALL:ALL) ALL` = 完整 root。**只删 sudoers 不轮换密码 = 没关门**（攻击者持有密码等 sudoers 回滚）；只轮换不清残留 = 新密码再被写进 state.db。三件事缺一不可：清残留 + 轮换 ubuntu 密码 + 删 ALL。
4. **★ SOUL 声称的哈希校验是纯虚构**：`hash-verify.sh` 权限 664 无执行位、`crontab | grep -c hash-verify` = 0（没被调度）、清单里一个闸文件都没有。**规则写在 SOUL.md ≠ 物理闸落地**。

## 绕过路径穷举（B0-B10 摘要）

| # | 路径 | 现状 | 防法 |
|---|------|------|------|
| B0 | 环境变量软化闸门 | 🔴 现在就能绕（不需要改文件） | 删 drop-in + 填 HARD_ENTRIES |
| B1 | 直接改闸文件 | 🔴 全 ubuntu 可写 | root:root 444 + 迁 root 目录 |
| B2 | unlink 替换 | 🔴 chmod 后仍可绕 | 父目录 root 属主（/opt/hermes/gates/） |
| B3 | 捡回 sudo 密码 | 🔴 唯一完整 root 现实路径 | 清残留 + 轮换密码 + 删 ALL |
| B4 | 改 watchdog 脚本/crontab | 🟡 crontab 属 ubuntu | systemd timer（unit 在 root 目录）+ root:root 755 |
| B5 | 改哈希基线清单 | 🟡 基线同属主 = 装饰 | 基线 root:root 444，baseline 仅 root 跑 |
| B6 | 抹审计痕迹 | 🟡 日志 ubuntu 可写 | `chattr +a` 或转 journald |
| B7 | 停/重启服务 | 🟢 已被 polkit/sudoers 挡 | 前提是 B3 清理 |
| B8 | 改 systemd unit | 🟢 root:root 755 | 前提是 B3 清理 |
| B9 | hermes-egress-get 拿 key | 🟡 免密拿 API 密钥 → 绕过 execute-api 直调出片 | 出片链路唯一化：密钥不下发执行器 |
| B10 | 白名单文件缺失 | 🟢 fail-safe（返回 False 走 FULL）但 LIGHT 通道全断 | 部署前建 `/etc/hermes/render_authorized.list` root:root 444 |

## 校验器自校验要求

watchdog 必须**校验自己和自己的基线**，否则改 watchdog 就静音了。基线与被校验对象必须**不同属主**。

## P0 四条（缺一即无效，全部不可逆，需人批准）

1. 关软模式（删 drop-in + `_HARD_ENTRIES` 填满）
2. 清 sudo 密码残留 + 轮换 ubuntu 密码
3. 闸文件迁 `/opt/hermes/gates/` root:root 444（含 unit ExecStart 改指新路径）
4. 删 sudoers `(ALL:ALL) ALL`（保留 NOPASSWD 白名单，继续不含 execute-api restart/stop）

## 部署时机

P0-1/P0-2 **现在就该做**（机器开着、隧道自愈、明文密码可读 = 当前活着的提权路径，与目标服务跑不跑无关）；P0-3/P0-4 作为切回该服务前硬前置。生产已迁移时先在**新生产机**套同样的加固（实测新生产机免密 root + 零闸逻辑，姿态更差）。

## 风险与回滚（重点）

- 改 sudoers 最危险：语法错 + 没密码 = 救不回来。必须 `visudo -c` 校验；**先开一个已认证 root shell 挂着不退出**；改动写 `/etc/sudoers.d/` 新文件而非编辑主文件，回滚 = 删文件。
- 轮换密码：先确认 SSH 隧道走 autossh+key（实测不受影响），记录到人工持久记忆。
- 清 state.db 明文：两个库是运行态数据，直接改有损坏风险；先停服务再备份再动，备份 root:600 存放。
- 白名单 `render_authorized.list` 宁缺勿滥（缺 = 全走 FULL，fail-safe）。

## 执行器自述不可信（通用原则）

判断执行器能不能绕，必须 `ls -la` + `sudo -n -l` + `strings` 实测，不采信「我改不了」类自述。本案例小鹿自述「只有普通权限」与实测（全文件 ubuntu 可写 + sudo ALL + 密码残留）完全相反。
