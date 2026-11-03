# 飞书配对申请监控（2026-07-12 搭建）

## 场景

飞书机器人作为客户入口，新用户申请加入时需要管理员批准。但管理员只在主微信号上收通知，不想看 WeChat 渠道的申请通知。

## 方案

给飞书单独创建 cron job，只监控 `feishu-pending.json`，有新用户直接推管理员微信。

## Cron 配置

```bash
cronjob action=create \
  name="飞书申请监控" \
  schedule="every 2m" \
  prompt="检查 /home/ubuntu/.hermes/profiles/customer/platforms/pairing/feishu-pending.json 和 feishu-approved.json。如果 pending 里有之前没见过的用户ID，立即通知我。不要用代码块，直接说「有新的飞书用户申请加入：xxx」。" \
  deliver="weixin:<admin_chat_id>@im.wechat"
```

## WeChat 渠道静默处理

管理员不要求 WeChat 渠道的通知，`check-pairing.sh` 改为 `exit 0` 静默退出：

```bash
#!/usr/bin/env bash
# Silent mode - WeChat pairing checks run without notification
exit 0
```

## 关键路径

```
飞书用户发消息 → feishu-pending.json 增加条目
  → cron 每2分钟检查 → 发现新条目
  → 推送到管理员微信：通知用户ID
  → 管理员回复「批准」
  → 执行 hermes --profile customer pairing approve feishu <CODE>
  → 用户移到 feishu-approved.json
  → 客户可以正常使用飞书机器人
```

## 数据文件位置

- 待批准：`/home/ubuntu/.hermes/profiles/customer/platforms/pairing/feishu-pending.json`
- 已批准：`/home/ubuntu/.hermes/profiles/customer/platforms/pairing/feishu-approved.json`
