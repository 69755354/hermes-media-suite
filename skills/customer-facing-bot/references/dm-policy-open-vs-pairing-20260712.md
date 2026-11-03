# DM Policy: open vs pairing — 2026-07-12 实测记录

## 场景

客户 bot 「小天」用 iLink WeChat 绑闲置号，目标是让客户加了就能直接聊，不需要管理员手动批准配对。

## 第一次尝试：只改 ALLOW_ALL_USERS

```ini
WEIXIN_DM_POLICY=pairing    # 默认值
WEIXIN_ALLOW_ALL_USERS=true  # 改成 true
```

**结果：不行。** 新用户发消息没反应。闲置号收到了消息但不回复。

## 根因分析

weixin.py 里有两种 DM 判断：

```python
def _is_dm_allowed(self, sender_id: str) -> bool:
    if self._dm_policy == "disabled":
        return False
    if self._dm_policy == "allowlist":
        return sender_id in self._allow_from
    if self._dm_policy == "open":
        return self._open_dm_opted_in()    # ← 只有这里检查 ALLOW_ALL_USERS
    return False                            # ← pairing 走这里 = False

def _is_dm_intake_allowed(self, sender_id: str) -> bool:
    ...
    if self._dm_policy == "pairing":
        return True                          # ← 允许 intake（生成配对码）
    ...
```

当 `dm_policy=pairing`：
- 消息能进来（intake_allowed = True → 生成配对码）
- 但用户不能直接聊（dm_allowed = False → 被拦截）
- `ALLOW_ALL_USERS` 只在 `dm_policy=open` 分支里检查

## 正解

```ini
WEIXIN_DM_POLICY=open          # 改为 open
WEIXIN_ALLOW_ALL_USERS=true    # 配合使用
```

重启网关后用另一个号发消息 → 小天直接回了。

## 启示

- **ALLOW_ALL_USERS 不独立生效**，它只是被某个 policy 调用的开关
- 要把权限做对，必须**同时看 DM policy + ALLOW_ALL_USERS 两个配置**
- 配合每日配额（3次/天）+ 功能权限（permissions.json）可以在 open 模式下防刷
