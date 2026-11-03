# Session Reset Notification → User Confusion (2026-07-13)

## 现象

4:00 AM 定时会话重置触发后，用户聊天界面收到一条系统消息：

```
◐ Session automatically reset (daily schedule at 4:00). Conversation history cleared.
Use /resume to browse and restore a previous session.
Adjust reset timing in config.yaml under session_reset.
◆ Model:
◆ Provider: custom_custom
◆ Context: 1.0M tokens (detected)
```

用户以为这是 bot 对「介绍下自己」的回复，误以为 bot 坏了。

## 根因

config.yaml 中配置了 session_reset.at_hour: 4 和 mode: both。凌晨4点定时重置触发后，**系统通知被当作普通消息发送给了用户**。用户侧看不到消息来源的区别——以为是bot发的。

## 影响

- 新用户或次日用户看到的是系统通知，不是欢迎语
- 用户困惑「bot怎么回了一堆技术参数」
- 对 bot 的第一印象打折

## 解决方案

### 方案A：关掉定时重置，只用空闲超时

```yaml
session_reset:
  mode: timeout       # 仅空闲超时重置
  idle_minutes: 1440  # 24小时无对话才重置
```

去掉 at_hour，避免固定时间点发通知。

### 方案B：保留重置，SOUL.md加解释

在欢迎语前加一段：

```
注意：每天凌晨4点系统会自动清理旧会话。
如果看到「session reset」之类的系统消息，不用管它。
直接说你的需求就行~
```

### 方案C：cron静默删会话，不发通知

```bash
cronjob action=create name=silent-session-cleanup \
  schedule="0 4 * * *" no_agent=true \
  script="/home/ubuntu/.hermes/profiles/customer/scripts/cleanup-sessions.sh"
```

脚本：直接删 state.db 的 sessions + messages 表，stdout为空则无通知。

## 检查方法

```bash
grep "Session expiry\|Session reset" /home/ubuntu/.hermes/profiles/customer/logs/gateway.log
```
