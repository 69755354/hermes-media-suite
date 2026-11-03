# DM消息投递排查 · 5步法（用户提供 2026-07-12）

## 排查步骤

### 1. 看Gateway实时日志 + 用其他微信发消息

```bash
journalctl --user -u hermes-gateway-customer -f
# 另开终端
grep "_process_message\|from_user_id\|Received" \
  /home/ubuntu/.hermes/profiles/customer/logs/gateway.log
```

从另一个微信号发消息给闲置号，观察日志是否有事件触发。

### 2. 日志完全没有 → 微信桥接器未上报私聊事件

检查：
- iLink 收消息/好友消息开关（iLink服务端配置）
- 登录状态（gateway_state.json platforms.weixin.state）
- 回调连接（/proc/PID/environ 确认 WEIXIN_TOKEN 存在）
- 同步缓冲区（sync.json get_updates_buf 是否变化）

### 3. 日志有但被忽略 → dmPolicy 拦截

检查 `gateway/platforms/weixin.py` 的 `_process_message` 流程：

```python
# 第1432行
elif not self._is_dm_intake_allowed(sender_id):
    return    # ← 消息被静默丢弃
```

解决：
- 把 dmPolicy 从 `pairing`/`allowlist` 调为 `open`
- 或批准配对码
- 或添加对方 wxid 到白名单

### 4. 已调用模型但发不出 → 发送权限/风控

检查：
- 发送频率限制（`sendmessage rate limited` 错误）
- iLink 发送权限
- 风控策略

### 5. 确认没有配置成仅群聊/仅@触发

检查 `WEIXIN_GROUP_POLICY` 和 `_is_dm_allowed` 逻辑。

## 核心原则

**不要直接公开全放行。** 建议逐个添加 wxid 白名单（`WEIXIN_DM_POLICY=allowlist` + `WEIXIN_ALLOWED_USERS=wxid1,wxid2`），或走配对模式逐一审批。

## 日志定位关键词

```
grep -n "_process_message\|from_user_id\|is_dm_intake\|is_dm_allowed\|dm_policy\|pairing\|intake" \
  /home/ubuntu/.hermes/hermes-agent/gateway/platforms/weixin.py | head -30
```
