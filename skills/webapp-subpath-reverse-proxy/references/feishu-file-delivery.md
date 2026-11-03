# 飞书原生文件消息交付（代替 COS 链接）

**背景（2026-08-16）**：给外部人（达人/客户）发文件时，COS 签名链接打不开：
- 默认域名 `cos.ap-guangzhou.myqcloud.com` 未备案 → 国内手机访问超时
- 加速域名 SDK 签名有 bug（Domain 拼接错，`sc.cos.accelerate...` 缺桶名）→ 403

**正解**：飞书原生文件消息（不依赖链接存活、不受域名/备案影响，比 COS 3 天签名稳）：

```
1. POST open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal  → tenant_access_token
2. POST open.feishu.cn/open-apis/im/v1/files
   (multipart form: file_type=stream, file_name=<文件名>, file=<二进制内容>)  → data.file_key
3. POST open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id
   (JSON: receive_id=<chat_id>, msg_type=file, content={"file_key": ...})  → data.message_id
```

**报告类交付流程**：md → docx（python-docx 把标题/表格/段落转 Word）→ 原生文件消息发群。

**已验证实现**：`/tmp/send_quadrant.py`、`/tmp/send_profile_short.py`（本会话跑通，message_id 确认发送成功）。

**配套**：
- 发文本摘要 + @ 达人：`feishu_send_gate.py send <chat_id> <open_id> "<文本>"`（文本里不要写 `<at>`，闸自动加）
- 敏感词闸：文本含内部词（codex/路径等）→ BLOCKED
