# 微信 Bot 多用户接入

## 架构说明

AstrBot + openclaw-weixin 的 bot 号是一个**真实微信个人号**，通过 ClawBot 插件扫码登录。这不是公众号也不是企业微信，就是一个个人微信号。

## 加好友流程

1. 登录 bot 号的微信号需要设置微信号/手机号可见
2. 其他人搜该号添加好友
3. 加好友后即可私聊
4. 加好友后即可拉进群

## 权限

- `enable_id_white_list: false` → 任何好友都能用
- `friend_message_needs_wake_prefix: false` → 私聊直接发，无需前缀
- `reply_with_mention: true` → 群里需要 @ 才触发

## 群聊

- 群内不 @bot 号的消息完全忽略
- 只有 @小鹿 或 `/` 前缀才会触发回复
- 回复发到群里，可见所有人

## 常见问题

**Q: 别人加了 bot 号但 bot 不回复？**
A: 检查 `enable_id_white_list` 是否为 `false`。默认是 `true` + 空白名单 = 全部拦截。

**Q: bot 在群里看不到消息？**
A: bot 号是基于 openclaw-weixin 长轮询的，收消息有 35 秒延迟。确认 bot 号已被拉进群，且群消息是 bot 号能收到的（有些群设置了「仅群主/管理员可添加」）。

**Q: 能把 bot 号直接推送给客户加吗？**
A: 可以。把 bot 号的微信号或手机号发给客户，让他们自行添加。也可以通过微信号的二维码分享给客户。
