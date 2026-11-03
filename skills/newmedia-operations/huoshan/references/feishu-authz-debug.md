# 飞书授权调试：两层架构

> 2026-07-13 会话沉淀。用户反映「群聊里的新用户@小鹿没回复」，经排查发现网关层`_is_user_authorized`拒绝用户，即使适配器层`_admit`已放行。

## 两层授权架构

飞书消息进入Bot需过两道门：

```
用户@小鹿
  ↓
① 适配器层 _admit()          ← plugins/platforms/feishu/adapter.py:4282
  - 检查 GROUP_POLICY / DM_POLICY / ALLOW_ALL_USERS
  - 检查 @提及
  ↓  返回 None(放行) 或 RejectReason(拒绝)
② 网关层 _is_user_authorized()  ← gateway/authz_mixin.py:264
  - 检查 FEISHU_ALLOW_ALL_USERS env var
  - 检查 FEISHU_ALLOWED_USERS allowlist
  - 检查 pairing 批准列表
  - 默认拒绝(no allowlists configured = deny)
  ↓
Bot接受到消息
```

## 各配置组合的实际效果

### 群聊（`chat_type=group`）

| FEISHU_ALLOW_ALL_USERS | GROUP_POLICY | 结果 |
|:----------------------|:-------------|:-----|
| `true` | 任意 | ✅ **能回复** — 网关层直接放行 |
| `false` | `open` | ❌ **不能回复** — 适配器层放行，但网关层默认拒绝 |
| `false` | `allowlist` | ❌ 需要allowlist配置 |

**关键坑：** `GROUP_POLICY=open` 只在适配器层有效。网关层`_is_user_authorized`不信任`open`策略（代码注释：trusting 'open' was a fail-open）。唯一能让群聊用户通过网关层的方式是`FEISHU_ALLOW_ALL_USERS=true`。

### 私聊（`chat_type=dm`）

| FEISHU_ALLOW_ALL_USERS | DM_POLICY | 结果 |
|:----------------------|:----------|:-----|
| `true` | 任意 | ✅ 直接回复 |
| `false` | `pairing` | ✅ pairing拦截→生成配对码→通知管理员→用户待批准 |
| `false` | `open` | ❌ 网关层拒绝(同群聊逻辑) |

## pairing系统行为

- **只在DM生效** — 群聊消息被网关层拒绝后**静默丢弃**（看日志`Unauthorized user`），不会生成配对码
- **通知给管理员** — pairing系统在`~/.hermes/pairing/`目录生成`{platform}-pending.json`文件
- **现有监控脚本**：`feishu-pairing-monitor.sh` 每2分钟检查pending文件，有新用户就推送到管理员的微信
- **auto-approve**：可用cron脚本自动批pending用户（见`auto_approve_feishu.py`）

## 调试步骤

当用户反映「收不到回复」时：

```
1. 查日志
   grep 'Unauthorized user' ~/.hermes/profiles/customer/logs/gateway.log
   → 有记录说明网关层拒绝

2. 确认 ALLOW_ALL_USERS
   grep FEISHU_ALLOW_ALL_USERS ~/.hermes/profiles/customer/.env
   → 最后一条生效，必须是 true

3. 查 pairing
   ls ~/.hermes/profiles/customer/pairing/  # profile级别
   ls ~/.hermes/pairing/                      # 全局级别
   → 有pending文件说明pairing拦截成功

4. 如果是群聊
   → ALLOW_ALL_USERS=true 是唯一解法
   → pairing对群聊无效（静默丢弃，不生成配对码）
```

## 配置正确位置

```yaml
# config.yaml — 必须放在 platforms.feishu.extra 下
platforms:
  feishu:
    enabled: true
    extra:
      group_sessions_per_user: true    # 正确位置
```

⚠️ 配置顶层的`group_sessions_per_user: true`不会被读到，基类适配器读的是`self.config.extra`。
