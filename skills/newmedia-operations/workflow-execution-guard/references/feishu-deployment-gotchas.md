# 飞书部署避坑（2026-07-13 会话沉淀）

## 1. group_sessions_per_user 必须放在 platforms.feishu.extra

```yaml
# ❌ 不生效（顶层配置）
group_sessions_per_user: true

# ✅ 生效（平台专属 extra）
platforms:
  feishu:
    enabled: true
    extra:
      group_sessions_per_user: true
```

**原因：** 基类适配器 `BasePlatformAdapter.handle_message()` 读的是：
```python
self.config.extra.get("group_sessions_per_user", True)
```
其中 `self.config` 是 `PlatformConfig`，其 `extra` 字段来自平台专属 section，不是全局 config。

**影响链路：** Feishu adapter → `_process_inbound_message()` → `self.build_source()` 传了 `user_id`(open_id) + `user_id_alt`(union_id) → 基类 `handle_message()` → `build_session_key(source, group_sessions_per_user=True)` → 不同 user 拿到不同 session key（`agent:customer:feishu:group:oc_xxx:ou_aaa` vs `ou_bbb`） → 会话隔离。

**默认值：** `True`（fallback），但显式写进 extra 才保险。重启后生效。

## 2. 欢迎事件需要飞书开发者后台授权

代码已注册 `register_p2_im_chat_member_user_added_v1(self._on_user_added_to_chat)`，欢迎消息逻辑在 `_on_user_added_to_chat` 已写好。但需要飞书侧开权限：

### 必要条件（缺一不可）

| 项 | 位置 | 操作 |
|:---|:-----|:-----|
| 权限 | 开发者后台→权限管理 | 开通 `im:chat:member:readonly`（读取群成员列表） |
| 事件订阅 | 开发者后台→事件与回调 | 添加 `im.chat.member.user.added_v1` |
| 发布 | 开发者后台→版本管理与发布 | 点「发布」使新权限生效 |

**不发布=新权限不生效，飞书不会推新人入群事件。**

### 排查流程

新人入群无欢迎时：
1. 确认 `im:chat:member:readonly` 权限已开通
2. 确认 `im.chat.member.user.added_v1` 事件已订阅
3. 确认最新版本已发布
4. 查网关日志：`journalctl -u hermes-gateway-customer \| grep -i welcome\|user_added`

## 3. 用户会话隔离全链路

```
飞书消息入站
  ↓
Feishu adapter._process_inbound_message()
  ↓
self.build_source(
    chat_id=chat_id,
    chat_type="group",
    user_id=sender_profile["user_id"],        ← open_id (ou_xxx)
    user_name=sender_profile["user_name"],
    user_id_alt=sender_profile["user_id_alt"], ← union_id (on_xxx)
)
  ↓
MessageEvent(source=source)
  ↓
_dispatch_inbound_event() → _handle_message_with_guards() → self.handle_message(event)
  ↓
BasePlatformAdapter.handle_message(event)
  ↓
build_session_key(
    event.source,
    group_sessions_per_user=self.config.extra.get("group_sessions_per_user", True),
)
  ↓
participant_id = source.user_id_alt or source.user_id  ← union_id > open_id
session_key = f"{ns}:{platform}:group:{chat_id}:{participant_id}"
  ↓
每个用户独立会话 key → 独立 agent cache → 对话上下文不混
```

**注意：** 会话隔离解决问题1（对话上下文）。Hindsight记忆全局共享导致问题2（记忆检索串用户），需要在 SOUL.md 层面加规则：检索记忆时先过滤用户ID。
