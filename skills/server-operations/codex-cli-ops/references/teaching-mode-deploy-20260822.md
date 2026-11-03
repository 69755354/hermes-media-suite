# 学生私聊教学模式部署实操（2026-08-22）

小鹿（广州机 customer profile）教学模式 = 隐藏入口 + 首次上报审批 + 白名单即教学。部署时配置/锚点清单。

## 关键路径（广州机）

| 文件 | 用途 |
|:---|:---|
| `/home/ubuntu/.hermes/hermes-agent/plugins/platforms/feishu/teaching_router.py` | 路由模块（v2.1：隐藏入口+上报审批+会话状态机） |
| `/home/ubuntu/.hermes/profiles/customer/config/teaching_admins.json` | 管理者白名单（老板 open_id + notification_open_id） |
| `/home/ubuntu/.hermes/profiles/customer/config/teaching_students.json` | 学生白名单（**审批制初始为空**，批一个加一个） |
| `/home/ubuntu/.hermes/profiles/customer/teaching/teaching_state.sqlite3` | 独立教学状态库（不碰 customer state.db） |
| `/home/ubuntu/workflow/projects/ai-teacher-bot/lesson_packs/` | 14 个课次包 yaml |

## 接线锚点（adapter.py）

- 入口：`_handle_message_event_data()`（约 2615 行）→ `_process_inbound_message()`（约 3411 行）
- 插入点：`_process_inbound_message()` 内 `normalized` MessageEvent 构建之后、`_dispatch_inbound_event(normalized)` 之前
- `sender_primary`（open_id）在该函数内已解析，可直接用
- 教学总开关默认关闭（TEACHING_MODE_ENABLED），接线后客户零影响
- CUSTOMER 分支逐字不改；route() 异常 → 内部告警 → 落回客户链路

## 部署顺序要点

1. 备份 adapter.py / SOUL / gateway_state.json
2. teaching_router.py scp 到 feishu 插件目录 + `py_compile`
3. 配置 JSON **本地 write_file → scp → chmod 600**（ssh heredoc 会剥双引号，见 codex-cli-ops）
4. 建 teaching/ 目录（状态库）
5. 接线 adapter（按函数锚点不按行号）
6. SOUL 第 1 条同步改学生私聊措辞（替换「教学群白名单/教师身份白名单」为「p2p + 学生白名单 + 口令建立」）
7. 重启 gateway → 验证新 PID + feishu connected
8. 灰度：老板私聊试跑（自己不在学生白名单时先把自己加进去测试）

## 验证要点

- 未审批客户发 `/上课` → 无响应、走客户链路、不泄露教学存在
- 首次私聊 → 老板收到静默上报（匿名标识+open_id+时间）
- 老板回「开」→ 学生进白名单 → 学生收到「上课权限已经开通」
- 白名单学生私聊 → 免口令直接教学；`/下课` 退出后再次私聊自动重建
- 教学能力调用：课次包允许 + billing 积分足够 + 原子预占，余额不足降级文字

## 状态机

学生注册：unseen → pending（首次上报，set_if_absent 防并发重复）→ approved（老板审批）
教学会话：无会话/过期 → 自动建 active；/下课 → closed（资格保留）；paused 不因普通消息续期
