# Feishu 新人入群欢迎消息实现（2026-07-13）

## 需求

用户进群时，bot 自动发欢迎消息 + 自我介绍。例如：
```
欢迎xxx加入小鹿的大家庭！🎉

我是小鹿，你的运营小帮手～

🔍 搜爆款 — 帮你看看同行都在卷什么
✍️ 写文案 — 把话说到人心坎里
📊 做分析 — 扒同行老底
🎬 做视频 — 探店/宣传片一条龙

有啥需要直接说，别客气！😎
```

## 实现

### 1. 注册事件

在 `plugins/platforms/feishu/adapter.py` 的 `_build_event_handler()` 中，添加：

```python
.register_p2_im_chat_member_user_added_v1(self._on_user_added_to_chat)
```

添加到 `bot_added` 行之后。

### 2. 事件数据结构

Lark API `im.chat.member.user.added_v1` 的事件 body：

```
P2ImChatMemberUserAddedV1
├── event → P2ImChatMemberUserAddedV1Data
│   ├── chat_id: str          ← 群聊 ID
│   ├── operator_id: ...      ← 操作人
│   ├── users: [ChatMemberUser]  ← 加入的用户列表
│   │   └── ChatMemberUser
│   │       ├── name: str     ← 用户姓名
│   │       ├── user_id: str  ← 用户 ID
│   │       └── tenant_key: str
│   ├── name: str             ← 群名
│   └── external: bool
```

### 3. Handler 实现

```python
def _on_user_added_to_chat(self, data: Any) -> None:
    event = getattr(data, "event", None)
    chat_id = str(getattr(event, "chat_id", "") or "")
    users = getattr(event, "users", []) or []
    if not chat_id or not users:
        logger.debug("[Feishu] user_added event: no chat_id or users, skipping")
        return
    names = [u.name for u in users if hasattr(u, "name") and u.name]
    if not names:
        logger.debug("[Feishu] user_added event: no user names found")
        return
    name_list = "、".join(names)
    welcome = f"欢迎{name_list}加入小鹿的大家庭！🎉\n\n我是小鹿，你的运营小帮手～..."
    loop = self._loop
    if not self._loop_accepts_callbacks(loop):
        logger.warning("[Feishu] Adapter loop not ready, skipping welcome for %s", name_list)
        return
    self._submit_on_loop(
        loop,
        self._send_welcome_message(chat_id, welcome),
    )

async def _send_welcome_message(self, chat_id: str, content: str) -> None:
    import json
    payload = json.dumps({"text": content}, ensure_ascii=False)
    try:
        resp = await self._send_raw_message(
            chat_id=chat_id, msg_type="text",
            payload=payload, reply_to=None, metadata=None,
        )
        if resp and getattr(resp, "success", lambda: False)():
            logger.info("[Feishu] Welcome sent to chat %s", chat_id)
        else:
            logger.warning("[Feishu] Welcome send failed to chat %s: %s", chat_id, resp)
    except Exception as e:
        logger.error("[Feishu] Welcome send error to chat %s: %s", chat_id, e)
```

### 4. 重启网关

```bash
# 找到 customer profile 的网关 PID
ps aux | grep "profile customer.*gateway" | grep -v grep
# 杀掉旧进程（systemd 自动重启）
kill <PID>
# 等几秒后验证
sleep 10 && tail -5 /home/ubuntu/.hermes/profiles/customer/logs/gateway.log
# 预期：Gateway running with 2 platform(s)
```

## 结构要点

| 组件 | 位置 | 说明 |
|:----|:----|:-----|
| 事件注册 | `_build_event_handler()` 链式调用 | 在 bot_added 行后添加 user_added |
| 同步处理器 | `_on_user_added_to_chat(self, data)` | 解析事件、构造欢迎词、提交到 event loop |
| 异步发送 | `_send_welcome_message(self, chat_id, content)` | 通过 `_send_raw_message()` 发送文本消息 |

## 关键模式

1. **回调线程 → Event Loop：** Feishu SDK 的 event handler 在回调线程中执行。发送消息必须通过 `self._submit_on_loop(loop, coroutine)` 投递到 asyncio event loop。
2. **消息格式：** Feishu 文本消息 content 为 `{"text": "..."}` JSON 字符串。
3. **多人同时加群：** `users` 是数组，同时拉多人时一次性处理。
4. **静默失败：** 欢迎消息发失败只打日志，不抛异常、不影响群聊功能。

## 可扩展事件

| 事件方法 | 触发时机 | 典型用途 |
|:--------|:---------|:---------|
| `register_p2_im_chat_member_user_added_v1` | 用户加入群 | 欢迎消息 |
| `register_p2_im_chat_member_user_deleted_v1` | 用户被移除 | 日志/告警 |
| `register_p2_im_chat_member_user_withdrawn_v1` | 用户主动退群 | 告别消息 |
| `register_p2_im_chat_disbanded_v1` | 群解散 | 清理资源 |
| `register_p2_im_message_reaction_created_v1` | 消息被加表情 | 互动统计 |

## 注意事项

- ⚠️ 修改 Hermes 核心源码，升级后会丢失
- ⚠️ SDK 版本要求：lark-oapi >= 1.6.0（`extra_ua_tags` 参数）
- ⚠️ 事件需要飞书机器人有 `im:chat:member:user:added` 事件订阅权限
