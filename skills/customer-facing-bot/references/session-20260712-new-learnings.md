# 2026-07-12 会话新增知识点

## 1. Feishu Group Policy 配置

飞书机器人拉进群后 @它不回消息 → 群策略默认 `allowlist`（空白名单）。

**修复：** 在 customer `.env` 加 `FEISHU_GROUP_POLICY=open`，重启网关。

说明：`open` 允许群内任何 @机器人的用户使用，配合 quota 做限制。

## 2. Feishu 批准锁恢复位

连续批准失败 → 平台被锁 3600s。

**锁文件：** `profiles/customer/platforms/pairing/_rate_limits.json`

**恢复位：** 删 `_lockout:feishu`，`_failures:feishu` 置 0。

**批准命令：** `hermes --profile customer pairing approve feishu <用户收到的配对码>`

注意：配对码是 8 位字符（如 jgm67s8r），不是 `pairing list` 显示的哈希。

**批准后初始化配额：** 新用户加到 `quota_tracker.json`: `{"ou_xxx": {"date": "当日", "used": 0}}`

## 3. 网关重启（从 Hermes 会话内）

`systemctl --user restart` 在当前会话中因 SIGTERM 传播而失败。

**方案：** `systemd-run --user --scope sh -c 'sleep 3 && systemctl --user restart hermes-gateway-customer'`

## 4. Lightclaw 新号绑定（远程不可操作）

必须用户在本地操作：浏览器打开 lightclaw 控制台 → 扫码绑定 → 拿到 UIN + API Key 发给 agent → agent 配环境变量 `LIGHTCLAW_API_KEY_${UIN}=${KEY}` 并重启网关。

## 5. 管理员通知偏好：只部分平台

用户明确要求只收飞书新用户通知，微信的不发。实现：不同平台创建独立 cron job，不想要的平台脚本直接 `exit 0`。

## 6. 飞书机器人群聊配额

飞书群里的用户和私聊用户共享配额（同一份 `quota_tracker.json`）。每人每天 3 次。
