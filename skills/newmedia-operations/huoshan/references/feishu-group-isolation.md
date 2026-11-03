# 飞书群聊用户隔离 & 授权配置

## 症状

1. **群聊需求混在一起：** 用户A说「帮我的火锅店做视频」，用户B说「帮我的奶茶店写文案」，小鹿把A的需求和B的信息混在一起回答。
2. **新用户@小鹿不回复：** 日志报 `WARNING gateway.run: Unauthorized user: ou_xxx on feishu`，消息静默丢弃。

## 根因分析

两个问题互相关联但属于不同层级：

### 问题1：会话隔离失效

Hermes 基类适配器读取 `group_sessions_per_user` 的位置不对。

```python
session_key = build_session_key(
    event.source,
    group_sessions_per_user=self.config.extra.get("group_sessions_per_user", True),
    thread_sessions_per_user=self.config.extra.get("thread_sessions_per_user", False),
)
```

`self.config.extra` 是 **平台专属**的 `PlatformConfig.extra`，不是配置文件顶层。

**✅ 正确配置：**

```yaml
# ~/.hermes/profiles/<profile>/config.yaml
platforms:
  feishu:
    enabled: true
    extra:
      group_sessions_per_user: true
```

**❌ 无效：**
```yaml
group_sessions_per_user: true   # 顶层，platform adapter 读不到
```

### 问题2：网关层授权拦截（🔥 本会话关键发现）

**飞书适配器有两道门：**

```
用户消息
  ↓
【第一道门：适配器 _admit】 ← GROUP_POLICY=open → 放行 ✅
  ↓
【第二道门：网关 _is_user_authorized】 ← 这是真正的拦截点 💀
  ↓
通过 → 交给agent处理
拒绝 → 群聊静默丢弃，DM生成配对码
```

**关键代码：** `gateway/authz_mixin.py:491-514`

```python
# 当 adapter 有自己的访问策略时
if self._adapter_enforces_own_access_policy(...):
    if source.chat_type in {"group", ...}:
        effective_policy = self._adapter_group_policy(...)
        # 只有当策略是 "allowlist" 时才信任适配器
        if self._adapter_group_has_sender_allowlist(...):
            return True
    if effective_policy == "allowlist":
        return True
    # "open" 策略不信任 → 走到这里
    # 最终 fallthrough 到：
    return os.getenv("GATEWAY_ALLOW_ALL_USERS", "").lower() in {"true", "1", "yes"}
```

**结论：** 就算 `GROUP_POLICY=open`，网关层也不信任。唯一让群聊新用户通过的办法是设置 `FEISHU_ALLOW_ALL_USERS=true`。

**配对码（pairing）只对私聊生效**（`gateway/run.py:8961-8967`），群聊静默丢弃。

### 修复

```bash
# .env 中确保 FEISHU_ALLOW_ALL_USERS=true，且没有冲突行
grep -n 'FEISHU_ALLOW_ALL_USERS' .env
# 应该只有一行 =true，多余的行注释掉
```

### 验证

```bash
# 重启网关
systemctl restart hermes-gateway-customer

# 检查日志，新用户消息应该在 incoming 后正常进入 agent 处理
grep "inbound message" gateway.log | tail -5
# 不应再有 "Unauthorized user" 警告
grep "Unauthorized user" gateway.log
```

## 完整飞书授权链路

```
Feishu WebSocket/Webhook 收到消息
  ↓
_admit()  ← 适配器级：检查 GROUP_POLICY / DM_POLICY / @提及
  ↓ 通过
BasePlatformAdapter.handle_message()
  ↓
build_session_key()  ← 会话key生成：依赖 group_sessions_per_user
  ↓
_is_user_authorized()  ← ⭐ 网关级：检查 ALLOW_ALL_USERS / pairing store / 环境变量白名单
  ↓ 通过
GatewayRunner._authorize_and_run()
  ↓
agent 处理 → 回复
```

## 记忆层注意事项

会话 key 隔离了（A和B在不同会话中），但 Hindsight 记忆不隔离。
A 项目中存的记忆在 B 的会话中也会被检索到。

wiki/shop-info 文件名规范： `<用户ID_店名>.md`

## 相关文件

- `gateway/session.py` — `build_session_key()` 函数
- `gateway/platforms/base.py` — `handle_message()` line ~4604
- `plugins/platforms/feishu/adapter.py` — `_resolve_sender_profile()` line ~4083, `_admit()` line ~4282
- `gateway/authz_mixin.py` — `_is_user_authorized()` line ~264
- `gateway/run.py` — `Unauthorized user` 日志 line ~8959, 配对码生成 line ~8961
