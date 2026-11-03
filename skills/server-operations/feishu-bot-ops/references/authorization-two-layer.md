# 飞书授权两层机制 + 群聊「未授权」静默吞（2026-08-14 实测）

## 症状

群里的人 @ 机器人下任务，机器人毫无反应；journalctl 搜到：

```
WARNING gateway.run: Unauthorized user: ou_81da29b8e6547a2fee9a239f970d71ef (None) on feishu
```

以为配了 `FEISHU_GROUP_POLICY=open` 就该通，实际还是被拦。

## 根因：授权有独立两层，`.env` 只配飞书层不够

1. **飞书 adapter 层**（`plugins/platforms/feishu/adapter.py`）
   - 读 `FEISHU_DM_POLICY` / `FEISHU_GROUP_POLICY`（默认 `allowlist`）/ `FEISHU_REQUIRE_MENTION`
   - 在消息进 gateway 前先拦一道（`_should_process` / `_allow_group_message`）

2. **gateway 核心层 `_is_user_authorized`**（`gateway/authz_mixin.py`）
   - 检查顺序（源码注释写明）：
     1. per-platform allow-all（`FEISHU_ALLOW_ALL_USERS`）
     2. 平台 allowlist（`FEISHU_ALLOWED_USERS`）
     3. DM pairing 已批
     4. `GATEWAY_ALLOW_ALL_USERS`
     5. 默认拒绝
   - `FEISHU_ALLOW_ALL_USERS` 在 `platform_allow_all_map` 里（`Platform.FEISHU` 有映射），设 `true` 在第一步直接 `return True`

## 🔴 关键坑：群聊被 gateway 层拦 = 静默忽略

只有 **DM** 才回配对码（`Hi~ I don't recognize you yet! Here's your pairing code: XXXX`）；
**群聊被拦连个提示都没有**（`gateway/run.py` 注释原话：`In DMs: offer pairing code. In groups: silently ignore.`）。

所以群里的人下任务被吞，你根本不知道有人找过你，必须查日志才发现。

## ✅ 放开全员（对内团队常用）

```
FEISHU_ALLOW_ALL_USERS=true   # gateway 核心层放行（关键，只配 GROUP_POLICY=open 不够）
FEISHU_GROUP_POLICY=open      # 飞书层群聊放行
FEISHU_REQUIRE_MENTION=true   # 群里仍要 @ 才触发（防刷屏，通常保留）
```

只放群聊、不放私聊：`FEISHU_GROUP_POLICY=open` + 私聊保持 `FEISHU_DM_POLICY=pairing`。

## 排查命令

```bash
# 看谁被拦（含 open_id，可对照飞书后台成员 open_id 定位是谁）
journalctl --user -u hermes-gateway --since "1 hour ago" | grep -i "Unauthorized user"

# 对比 .env mtime vs 被拦时间——「配置加晚了」是常见误判：加配置前被拦的记录仍留在日志里
stat -c '%y' ~/.hermes/.env
```

## ⚠️ `.env` 授权配置改了免重启

- `_is_user_authorized` 经 `_auth_env(name)` → `get_secret(name)` → secret scope 读
- secret scope 是 **per-turn 重建**：`build_profile_secret_scope(Path(profile_home))` 每次用 `load_env_file(home/.env)` 读 .env 文件全量
- 所以 `.env` 改完**下次消息就生效**，不用重启 gateway
- ⚠️ gateway 进程 `/proc/<pid>/environ` 里**看不到**这些授权值——它们走 secret scope contextvar（内存），不是 os.environ；拿 `/proc/environ` 验证「配置没加载」是错的验证方法

## 相关文件路径

- `gateway/authz_mixin.py` —— `_is_user_authorized`（line ~386）、`platform_allow_all_map`（含 FEISHU）
- `gateway/run.py` —— line ~14711 `Unauthorized user` 日志、line ~1835 `load_hermes_dotenv`、line ~1972 `build_profile_secret_scope`
- `agent/secret_scope.py` —— `get_secret` / `build_profile_secret_scope` / `_GLOBAL_ENV_EXACT`
- `plugins/platforms/feishu/adapter.py` —— adapter 层 `FEISHU_GROUP_POLICY` / `FEISHU_ALLOW_ALL_USERS`
