# Feishu Developer Console Permission Checklist

当飞书机器人无法在群聊中接收/发送消息时，需要在 [飞书开发者后台](https://open.feishu.cn/app) 检查以下配置：

## 1. 权限管理（必加）

在「权限管理」页面搜索并添加以下权限：

| 权限KEY | 说明 | 认证方式 |
|:-------|:-----|:---------|
| `im:message` | 获取单聊、群组消息（收消息） | 应用身份 |
| `im:message:send_as_bot` | 以机器人身份发送消息（发消息） | 应用身份 |

**操作步骤：**
1. 进入「权限管理」页面
2. 搜索权限名称（支持中英文）
3. 找到对应权限 → 点「开通」
4. 点右上角「发布」使权限生效

**注意：** 如果只有「免审权限」标签页，搜索 `im:message` 即可找到消息相关权限。一般不需「需审核权限」。

## 2. 事件订阅（必加）

在「事件与回调」页面添加事件：

| 事件 | 说明 |
|:----|:-----|
| `im.message.receive_v1` | 接收消息事件 |

**操作步骤：**
1. 进入「事件与回调」页面
2. 点「添加事件」
3. 搜索 `im.message.receive_v1` → 添加
4. 点右上角「发布」

## 3. 应用能力

在「应用能力」→「机器人」确保已开启机器人能力（显示 ✓ 机器人）。

## 常见问题

| 症状 | 原因 | 解决 |
|:----|:-----|:-----|
| 群里@机器人不回复 | 缺少 `im:message` 权限 | 添加权限+发布 |
| 机器人在群里已审批但不回 | 群策略为 `allowlist`（默认）且白名单为空 | `.env` 加 `FEISHU_GROUP_POLICY=open` |
| 必须@才回，想改成不用@ | `FEISHU_REQUIRE_MENTION=true`（默认） | `.env` 加 `FEISHU_REQUIRE_MENTION=false` |
| 机器人回复了但用户看不到 | 缺少 `im:message:send_as_bot` 权限 | 添加权限+发布 |
| 群里所有消息都回，想只回功能相关 | `FEISHU_REQUIRE_MENTION=false` 全量回复 | 改用 SOUL.md 消息过滤规则，让 agent 自行判断（见主skill「群聊消息过滤」章节） |

## 环境变量对照表

| 环境变量 | 默认值 | 说明 |
|:---------|:------|:-----|
| FEISHU_GROUP_POLICY | allowlist | 群聊策略：open/allowlist/blacklist/admin_only/disabled |
| FEISHU_REQUIRE_MENTION | true | 群聊是否需要@才回复 |
| FEISHU_ALLOW_ALL_USERS | false | 是否允许所有用户发DM |
| FEISHU_DM_POLICY | pairing | DM策略：open/pairing/allowlist/disabled |

## ⚠️ 环境变量加载陷阱

.env 文件中的环境变量**不一定**被网关进程加载。验证方法：

```bash
cat /proc/<gateway_PID>/environ | tr '\0' '\n' | grep FEISHU
```

如果环境变量缺失，必须**直接写到 systemd service 文件**中：

```ini
[Service]
Environment="FEISHU_GROUP_POLICY=open"
Environment="FEISHU_REQUIRE_MENTION=false"
```

然后：
```bash
systemctl --user daemon-reload
systemd-run --user --scope bash -c "sleep 3 && systemctl --user restart hermes-gateway-customer"
```
