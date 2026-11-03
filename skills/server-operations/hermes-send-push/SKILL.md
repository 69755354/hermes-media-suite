---
name: hermes-send-push
description: "hermes send: push script results to user DM. 触发：任务完成推送。"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, send, push, notification, weixin, feishu, dm]
---

# Hermes 消息直推（hermes send）

## 何时用

- 用户要「出片后推微信」「任务完成通知」「脚本跑完提醒我」
- 用户要「推给飞书机器人私聊 / 推群里」——一律先考虑 `hermes send`，不要急着配 outbound webhook
- cron/watchdog/视频流水线需要在无人值守时把结果推给天行者本人

## 核心命令

```bash
# 列出所有可用目标（先查这个！）
hermes send --list

# 推私聊 DM（本机已验证：微信 DM 通道正常）
hermes send --to "weixin:o9cq80-_0LC4JqLptMI37QFgnC7o@im.wechat" "消息内容"

# 从文件读正文
hermes send --to <target> -f /path/to/output.txt

# 带附件（图片/视频/文档）——在正文里写 MEDIA:<绝对路径>
hermes send --to <target> "成片来了 MEDIA:/home/ubuntu/output.mp4"

# 静默模式（只返回退出码）
hermes send -q --to <target> "done"
```

## 目标格式

| 写法 | 含义 |
|:---|:---|
| `weixin` | 微信 home channel |
| `weixin:o9cq80-...@im.wechat` | 微信指定 DM（天行者本人） |
| `telegram` / `telegram:-100xxx:thread` | 电报 home / 指定群+话题 |
| `feishu` | 飞书 home channel |

不确定就用 `hermes send --list` 看实际可用的。

## 推飞书客户（客户对接全走飞书，2026-08-05 实测）

**必须带 `-p customer`** —— 客户在 customer profile 的飞书通道上，默认 profile 只有微信：

```bash
# 1. 先列 customer profile 的可用目标
hermes -p customer send --list
# → Feishu: feishu:oc_xxx (dm) / feishu:小鹿运营群 (group) / Weixin: weixin:o9cq807...@im.wechat (dm)

# 2. 推客户飞书 DM（出片交付）
hermes -p customer send --to "feishu:<CLIENT_CHAT_ID>" "视频出片完成 ✅ 标题"

# 3. 推天行者本人飞书（内部通知）
hermes -p customer send --to "feishu:<ADMIN_CHAT_ID>" "内部消息"
```

**飞书目标对照（customer profile）：**
| 目标 | 谁 | 用途 |
|:---|:---|:---|
| `feishu:<ADMIN_CHAT_ID>` | 天行者本人 | 内部通知 |
| `feishu:<CLIENT_CHAT_ID>` | 客户（心理顾问） | 出片交付 |
| `feishu:小鹿运营群` | 运营群 | 群发 |

**如何识别目标是谁：** 查 `~/.hermes/profiles/customer/channel_directory.json`（平台列表）+ `logs/gateway.log` 里该 chat_id 的 inbound 消息文本，或 `platforms/pairing/feishu-approved.json` 的 open_id 对应。别凭猜推错人。

## 为什么优先 hermes send 而不是 outbound webhook

| 维度 | hermes send | outbound webhook |
|:---|:---|:---|
| 接收端 | **不需要**，复用 gateway 平台凭证 | 需要外部 HTTP 端点 |
| 配置 | 零配置，直接跑 | 要 config.yaml 加 hooks.outbound |
| 适用 | 推给天行者本人私聊 | 推给 CI/dashboard/外部系统 |
| 签名 | 无 | HMAC-SHA256（GitHub 风格） |

本机实测（2026-08-05）：本地没有 n8n、没有飞书机器人 webhook、helper API 不在——outbound webhook 没有接收端可推，`hermes send` 一条命令秒达微信 DM。

## 一次发多份成片（批量交付）与送达核实

一条命令里放多行 `MEDIA:<绝对路径>` 即可批量发（飞书 `_standalone_send` 的行为）：正文先作为一条 text 消息发出，然后**每个 MEDIA 各发一条独立消息**，返回值只带**最后一条**的 `message_id`；中途任一份失败会返回 error（rc=1），所以 rc=0 即代表全部媒体都发出去了。

```python
body = ['这批跑完了，一次发你：']
for f in sorted(files):
    body += [os.path.basename(f), 'MEDIA:' + f]
subprocess.run([HERMES,'send','--to','feishu:'+DM,'--json','\n'.join(body)], capture_output=True)
```

**交付后必须外部核实**（返回值只有一个 message_id，证明不了 N 份都到了）：用 app 凭证取 `tenant_access_token`，读消息列表数新增条目——

```
GET /open-apis/im/v1/messages?container_id_type=chat&container_id=<oc_...>&sort_type=ByCreateTimeDesc&page_size=30
```

媒体消息在列表里 `msg_type` 显示为 `nonsupport`（飞书列表接口不渲染 file/video 内容），按 `create_time` 数出「1 条 text + N 条 nonsupport」即核实通过。注意：**单条 `GET /im/v1/messages/{message_id}` 会返回 HTTP 500**，不要用它做核实，用列表接口。

交付后落一个 `DELIVERED.json`（message_id + sha256 + 时间），下次定时任务据此判已完成，避免重复发送。

## 坑：cron 会话里往「本 job 自己的交付目标」发消息会被静默跳过（2026-10-14 实测）

cron agent 进程里 `hermes send --to <该 job 的 deliver 目标>` 会返回 **exit 0**，但 stdout 是
`Skipped send_message to feishu:<chat_id>. This cron job will already auto-deliver its final response to that same target. …`
（`tools/send_message_tool.py::_maybe_skip_cron_duplicate_send`，判据＝env `HERMES_CRON_AUTO_DELIVER_PLATFORM/CHAT_ID/THREAD_ID`）。

后果：用「`returncode==0 and "Sent to" in stdout`」判成功的哨兵脚本（如 `/home/ubuntu/autodeliver/auto_deliver.py`）会把每次发送都记成 FAIL → 一条也发不出去、每轮重试、报告里一直刷 FAIL；手动 shell 跑（无 cron env）才真发。

- 想在 cron 内真发媒体：调用子进程时清掉那三个 env（`env -u HERMES_CRON_AUTO_DELIVER_PLATFORM -u HERMES_CRON_AUTO_DELIVER_CHAT_ID …`），或把哨兵拆到 `deliver=none/local` 的独立 job。
- **`/home/ubuntu/autodeliver/auto_deliver.py` 已自带修复**（2026-10-14）：它给 `hermes send` 子进程传一份 pop 掉那三个 env 的 `os.environ` 副本，所以直接跑 `python3 auto_deliver.py` 就能真发，不必再套 `env -u`。
- 不要把 stdout 里的 `Skipped` 当成功吞掉——那是静默丢消息；也别当普通 FAIL 忽略，它代表「根本没发」。

## 踩坑

- **不要配群里机器人**：天行者明确要求「不要推群里，直接推给飞书机器人私聊」——先 `--list` 找 DM 目标
- **hook 事件 ≠ send**：新版（0.20.0+）的 outbound_webhooks 支持 on_session_end/subagent_stop 等事件，但那是推外部 HTTP 的，推本人私聊用 send 更直接
- 含 `gateway` 关键词的终端命令会被安全层误拦，send 本身不含该词不受影响
- **哨兵只许发成片，中间分段必须挡在名单外**（2026-10-22 事故）：`auto_deliver.py` 原先只按目录+大小筛，正在拆镜的项目（如 `galimard-koubo-20261021/output/seg1_take1.mp4`、`seg2.mp4`、`wan_5s_test.mp4`）会把测试分段当「成片」推进客户群，一次刷 6 条噪音，还夹在正常交付的抽帧说明中间。已修：`SKIP_NAME_TOKENS`（seg/take/test/compare/sample/draft/tmp/broll/raw）按文件名过滤、`MIN_AGE_SEC=120` 刚落盘的不发、`/home/ubuntu/.hermes/state/auto_deliver_blocklist.json` 按路径封掉被老板否掉的旧版（blocklist 值写原因）。结论：**能发的是「成品名」，不是「output 目录里所有 mp4」**；新增项目先确认它的中间件叫法，再决定要不要放开。同理，正在交互式改稿的项目由会话自己带抽帧核验交付，哨兵别和它抢着发。

## 验证

```bash
hermes send --to "weixin:o9cq80-_0LC4JqLptMI37QFgnC7o@im.wechat" "测试推送 ✅"
# 期望输出: Sent to weixin home channel (chat_id: o9cq80-...)
```
