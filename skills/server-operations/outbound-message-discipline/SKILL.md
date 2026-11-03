---
name: outbound-message-discipline
description: 对外消息纪律（群+私聊）。触发：发消息/设计消息拦截/bot回复。
version: 1.0.0
author: Hermes curator
license: MIT
metadata:
  hermes:
    tags: [对外消息, 过程静默, 物理拦截, 回执, 飞书, 表情过滤]
    category: server-operations
---

# 对外消息纪律（2026-08-16/17 天行者多次纠正沉淀）

## When to Use

- 给客户/达人/群里/私聊发消息前——检查内容是不是「只发结果不发过程」
- 收到新任务——先回受理回执（时间基于真实历史，不编）
- 要设计/评估消息拦截方案——先读第三节「物理拦截误杀教训」
- bot 回复出现表情/媒体消息处理异常、API 超限——查第四节接收过滤

Hermes（新加坡主助手）给客户/达人/群里/私聊发消息的统一纪律。**铁律优先级：过程静默 > 结果交付 > 安全过滤**。

## 〇之一、产出完成即主动发（不得等催）

用户拍过：「视频好了没 好了自动发出来，不要让我催」（2026-09-30 又因两份文档跑完没发被质问「你怎么不主动发出来」）。

规则：视频、文档、规则、表格、报告——**跑完/验收完的第一时间主动发到指定群或私聊**，不等用户问。只发「结果 + 文件/链接」，过程静默；发完在下一轮汇报里一句话带过。

## 〇、飞书可选中复制（2026-09-30 用户投诉）

飞书适配器见到带 markdown 特征（**加粗** / | 表格 | / - 列表）的回复就发成 **post 富文本消息**，手机端长按无法自由划选复制。

规则：用户要看/要拷的回复（清单、规则、话术、步骤、汇报）写成**纯文本行**——不用 `**`、不用 `|` 表格，用「- 」和换行；这样走 msg_type=text，客户能随手选中复制。需要富文本排版的长文档另发 Word / 飞书云文档（见 `feishu-article-delivery`）。

## 一、只发结果，不发过程（最高优先级，老板连续多次批评）

**群聊和私聊都只发最终结果，过程全静默。** 老板原话：「在群里面回消息的时候，不要出过程，我不是跟你说过了吗」「你把机器人在群里面回复的那个过程不要发出来，昨天不是说了嘛」。

**禁止发**（这些全是过程）：
- 过程描述：正在下载 / 在查 / 在跑 / 在搜 / 在转写 / 拆解中 / 搜索中 / 验证中 / 测试中 / 处理中 / 重启了 / 网关重启了 / 会话已恢复 / 查了一下 / 拿到数据
- 中间状态：服务状态 / 进程 / PID / 部署 / 迁移 / 日志 / 测试通过 / 改动文件 / 权限已开
- 工具名/路径：codex / claude / hermes / ffmpeg / Seedream / Seedance / 婵镜 / 豆包 / 火山 / API / gateway / /home/ / /tmp/ / wiki/ / outputs/（见 SOUL 第 12 条）

**只发**：收到回执（「收到，马上处理，预计 X 分钟」）、最终结果（「做好了，视频在这」「报告在这」「链接」）、交付物。

**执行方式**：靠 SOUL 自觉 + 静默处理。**不要自己发明激进物理拦截**（见第三节教训）。

## 二之补、群里做视频 = 直接出片（2026-08-30 老板定案，优先级最高）

**群里任何人让你做视频 = 直接出片，不等老板批准。** 老板原话：「以后让你在群里面做视频你就直接出不要等我来同意了」。

- 群里 @ 机器人 = 授权执行信号，跟私聊指令同等效力
- 做视频 = 直接走生产流程出片，不需要先问老板「要不要跑/要不要出」
- 覆盖所有群里视频请求，不限于客户/达人，不限是否有 permissions.json 权限
- **唯一例外**：涉及不可逆授权（如花钱买新 API key）或超出成本边界时才问
- 这条是「二、受理回执」的补充：视频任务在群里 = 不需要回执请求批准，直接干

## 二、受理回执：先回执，后干活；时间不编

客户/达人下任务 → **先回「收到，马上给您处理，预计 X 分钟」**（让人知道收到了，不是卡了）→ 才进入处理。同一任务只回一次，追问不回执。

**⚠️ 但别把回执变成反复确认（2026-08-17 老板连续纠正）**：群里有权限/老板已说「跑」的任务，**直接干，不要再问「要出片吗/要确认吗/要回执吗」**。老板原话：「姐也给他们开了做视频的权限了，你为什么还要问我呢」「我不是在群里面说了让你跑吗」「不用在群里回执了，我已经让你跑了」。判断：发起人有视频权限（permissions.json unlimited）或老板在群里说过「跑」→ 视为已授权，直接执行到底；只有权限不足/无明确授权/涉及新付费边界才问。回执是「收到后马上处理」的信号，不是「请求批准」的借口。

**预计时间禁止随便编**（老板：「预计多少分钟是你随便编的吧」）：基于**真实历史耗时**（同类型任务以前跑过多久），不确定报保守值「预计 30 分钟」。宁可报大，不可报假精确（5/15/20 这种拍脑袋数字）。

回执用大白话，不含工具名/路径。

## 二之三、要客户补充信息：一条消息问全（2026-11-02 用户定）

机器人需要客户提供信息时，**必须一次性把缺的项全部列出来**（编号 1/2/3，一条消息问完），客户一次答完就能继续；禁止挤牙膏式一次只问一项、再问一项。

- 发布流程缺标题/任务/时间/条数 → 一条消息列全，不要先问标题、再问时间
- 不确定客户要什么 → 也只问一次，把可选答案写进同一个问题里
- 问完就停，不要重复菜单、不要重复上一句

落地：`feishu_publish_bot/bot.py` 的 SYS 判断规则第 3、5 条已改为「一次问全」。

## 三、物理拦截误杀教训（2026-08-17 两次翻车）

**背景**：为了「不发过程」做了物理拦截（feishu_send_gate 黑名单 + guard OUTBOUND 硬闸）。

**翻车 1**：黑名单词太激进（把「收到」「处理」「预计 30 分钟」等正常词也拦了）→ 正常消息发不出去 → **bot 卡死**（用户感知「挂了」）。老板：「你这个闸门设计的有问题，先把它去掉」「你这个物理拦截上次就把自己拦截死了」「很多情况下会误杀消息」。

**翻车 2**：拦截后 bot 尝试重发/等待 → 卡死循环。

**定案**：
- **OUTBOUND 物理闸已移除**（node-entry-guard.py 的 OUTBOUND 分支 `if False` 禁用），靠 SOUL 规则 + 静默处理
- **宁可放过，不可误杀**——任何「消息拦截」设计的第一原则
- 真要设计拦截（老板点名 Claude 出方案时）：三层判定（明显结果→放行 / 明确过程→拦截 / 不确定→**放行**）、白名单优先、拦截后静默不发不重发不卡死
- **表情超限的正解是接收侧过滤，不是发送侧拦截**（见第四节）

## 四、飞书表情/媒体消息接收过滤（防 API 超限）

**问题**：飞书把**所有消息类型**推给 bot（用户发内置表情贴纸 sticker、富文本 post、图片 media 等），bot 每条都调 API → 请求翻倍 → 免费版 API 超限（群里成员实测反馈）。

**正解（已落地）**：改飞书平台插件 `plugins/platforms/feishu/adapter.py`，`_on_message_event()` 入口加前置过滤：
```python
_IGNORED_INBOUND_MESSAGE_TYPES = {"sticker", "post", "media", "audio", "file"}
# 命中 → 直接 return：不排队、不下载媒体、不查联系人、不进 agent、不回复
# webhook 仍回 HTTP 200 ACK 防飞书重试；普通 text 消息正常处理
```
只动 feishu 插件，不影响其他平台。**不要用通用 webhook.py 或 message_filters 做**（webhook.py 的 feishu 只是投递名单；message_filters 是关键词过滤且触发太晚）。

**⚠️ 名单演进（2026-08-18 更新）**：8-17 初版名单包含 `image` 和 `video`，导致用户发图/发视频被静默丢弃（用户发火龙 logo 图，我这边只看到文字「logo」）。8-18 天行者要求放行：把 `image`、`video` 从忽略名单移除（改前先 `cp adapter.py adapter.py.bak_<日期>` 备份；改完用「后台 kill PID 让 systemd 自动拉起」姿势重启 gateway，见 hermes-gateway-ops）。当前名单只拦 `sticker/post/media/audio/file`。教训：黑名单一刀切会误伤正常业务（图片素材、原片视频是核心工作流输入），宁可放过、只拦明确会刷 API 的类型。

**顺带事实**：bot 回复文本带 emoji 表情 ≠ 额外 API 调用（1 条消息 1 次）；真正超限源是「每条消息都调 API 处理」。但老板要求禁 emoji（文本和 reaction 都不发）——照做（小鹿 SOUL 已写「禁 emoji 铁律」）。

## 五、发素材/截图给用户确认：一次一张（2026-08-18 老板纠正）

**老板要「一张张发」= 一条消息一张图，不是一条消息塞多个 MEDIA、也不是分批发。** 会话实录：「你把你自己截图的发给我看看 一张张发」→ 我一次发 12 张 → 老板「重新发」→ 我理解成「继续发下一批」，又批量发 → 老板「我说的是一次发一张」「你听不懂我说话吗」。

**正确姿势**：
- 用户说「一张张发」→ 每条消息 `MEDIA:<路径>` 只放**一张图**，等用户确认收到再发下一张
- 先确认用户要看哪一批再发（「我看看哪些可以用」= 挑素材，别自作主张把 logo 加工品/人物参考全塞过去）
- 一次发 12 张图大概率被吞/刷屏，且用户无法逐张点评；一次一张用户才能说「这张能用/那张不行」

## 六、发视频/文件：走飞书原生 media 消息，MEDIA: 语法用户看不到（2026-08-18 老板多次暴怒，二次定案）**老板原话：「发飞书 你不要每次都发路径，我看不了，直接发视频出来」「说了不要发路径，直接发视频出来就行了」「真是服了你 你脑子有病吗？说了不要发路径 说不听是吧 把你的规则改掉」「我说了直接发飞书，media我看不了」。**

**⚠️ 核心事实（2026-08-18 实测确认）**：**`MEDIA:<路径>` 语法在飞书端不渲染成视频**——用户看到的是路径文本，等于没发。所以「只发 MEDIA 单行」是错误姿势（本 skill 旧版写的就是它，用户看的是路径，反复暴怒）。**正确姿势 = 飞书原生 media 消息**：

- **视频交付**：走飞书原生 media 消息——`POST /open-apis/im/v1/files`（file_type=mp4）上传拿 file_key → `POST /open-apis/im/v1/messages?receive_id_type=open_id`（或 chat_id）`msg_type=media` 发出去。⚠️ `msg_type=video` 不合法（API 报 `invalid msg_type: video`），`msg_type=file` 是附件不是可播放视频。现成脚本：`/tmp/feishu_send_video.py`（含 load_env/get_token/upload_video/send_video_msg 完整函数，复制到 `~/.hermes/scripts/` 持久化）。
- **图片/文件交付**：同样走飞书 API（图片 file_type=image + msg_type=image；文件 msg_type=file），或确认 MEDIA 语法在图片上是否渲染（视频确认不渲染，图片待实测——不确定就都用原生 API）
- **回复正文一律不出现文件路径字符串**（`/home/`、`/tmp/`、`seedance_clips/` 等全禁）；说明文字只描述内容不出现路径
- 发送前自检：回复里搜 `/` 开头的路径，有就删；且确认不是用 MEDIA: 语法发视频
- 同名覆盖重发会被飞书平台缓存成旧消息（用户看到旧版）→ 换新文件名（带时间戳）再发
- 用户说「发个链接」= 走 Caddy 公网直链（/usr/share/caddy → http://<SG_HOST>/xxx）或 COS 预签名，不给路径文本（注意：COS 预签名链接豆包等外部 AI 工具打不开，外部工具用 Caddy 直链）

## 七、给用户发终端命令：按平台选格式（2026-08-22 微信复制脏字符事故）

**微信发命令必须纯文本，禁止反引号/代码块/markdown 符号**——微信复制会把反引号、行首序号（如 `00~`、`01~`）等隐藏字符带进终端，用户粘贴后报 `command not found`（实录：`-bash: 00~ssh: command not found`），来回折腾 4 轮才定位。飞书可以直接发代码块（复制不带脏字符）。

**正确姿势：**
- 微信：命令写成一行纯文本，不包反引号、不加 `$` 前缀、不用代码块；地址/IP 逐个字符给清楚（实录：IP 复制时末尾混入 `01~` 变成 `<GZ_HOST>01`，与真实 `<GZ_HOST>` 差一位）
- 用户复制出错（`command not found` / 命令前有乱字符）→ 第一反应是「复制带脏字符」，让用户**手动敲**，不要换格式再发一遍
- 飞书：代码块照常可用
- 关键命令（含 IP/端口/密码提示）发完后让用户描述期望现象（如「光标停住不动=成功」），比让用户贴报错更快确认

## 八、P0 重建后 feishu_send_gate 仍误杀合法回复（2026-08-26 实测）

2026-08-26 物理闸 P0 重建（`feishu_send_gate.py` 重建为 P0-3）后，customer profile 日志再次出现：
```
WARNING gateway.platforms.base: [feishu] customer outbound content blocked
WARNING gateway.platforms.base: [feishu] Send failed: 内容含敏感信息，已拦截，联系管理员
WARNING gateway.platforms.base: [feishu] Fallback send also failed: 内容含敏感信息，已拦截，联系管理员
```

**场景：** 客户问「那个闸的搞完了？」→ 小鹿生成了 518 字回复（关于物理闸修复进度）→ 被 `feishu_send_gate` 拦死，客户只看到没回复 → 用户问「小鹿挂了？」。

**这跟第三节 2026-08-17 的翻车是同一类问题**——黑名单词太激进，把包含「闸」「guard」「拦截」等字眼的合法回复也拦了。P0 重建时没有吸取旧教训，黑名单没有做例外/白名单。

**排查方式：**
```bash
# 查 customer profile 日志
ssh -p 2222 ubuntu@127.0.0.1 "grep -A2 'outbound content blocked' ~/.hermes/profiles/customer/logs/gateway.log | tail -20"
```
看到 `outbound content blocked` = 回复被拦（bot 没挂，是消息发不出去）。

**feishu_send_gate.py 黑名单分类（2026-08-26 源码实读）：**

硬拦（命中直接 block，返回"内容含敏感信息，已拦截，联系管理员"）：
| 类别 | 触发词/正则 | 误杀风险 |
|---|---|---|
| 内部路径 | `/home/` `/tmp/` `/root/` `/usr/` `/etc/` `workflow/` `projects/` `.hermes` `wiki/` `outputs/` | 高——讲进度必提路径 |
| 内部文件 | `.py` `.json` `.yaml` `.log` `.db` `.sql` `.sh` | 高——提脚本名就中 |
| 内部工具 | `codex` `claude` `hermes` `terminal` `gateway` `seedream` `seedance` `婵镜` `ffmpeg` `deepseek` `豆包` `火山引擎` `openai` | 高——讲技术栈必中 |
| 内部术语 | `api_key` `app_secret` `app_id` `websocket` `open_id` `chat_id` | 中——真正该拦的 |
| 服务器标识 | `新加坡机` `广州机` `relay` `反隧` `隧道` `systemd` `ubuntu` | 高——讲运维必中 |
| 超过80行 | `len(text.splitlines()) > 80` | 中 |

软拦（observe 模式只记日志不拦，enforce 模式才拦）：
- 过程词：`正在下载/转写/拆解/搜索/测试/验证/处理/分析/运行/跑/查/搜`
- 状态词：`服务状态/进程/pid/部署/迁移/日志/测试通过/改动文件`
- 结构词：`来源：http` `置信度` `口径` `暂无公开数据` `内部建议` `执行者：`

**问题诊断：** 小鹿回客户讲进度时，消息里只要有 `codex`、`workflow/guard/`、`.py` 就命中硬黑名单。连续多条被拦 = 客户完全收不到回复 = 用户以为 bot 挂了。

**排查命令：**
```bash
ssh -p 2222 ubuntu@127.0.0.1 "grep 'outbound content blocked' ~/.hermes/profiles/customer/logs/gateway.log | tail -10"
```

**判断 bot 是否挂了时，先看日志有没有 `outbound content blocked`——有 = 闸拦了回复，不是 bot 挂了。**

**🚨 隧道断了时给用户命令自己跑（2026-08-28 实测）：** 反向隧道（2222）断了 = 新加坡连不上广州机 = 没法远程查日志。此时给用户一条命令让他在广州机终端直接跑：
```bash
grep 'outbound content blocked' ~/.hermes/profiles/customer/logs/gateway.log | tail -20
```
有输出 = 闸还在拦消息；无输出 = 闸没拦，可能是别的问题（gateway 挂了、网络不通、消息没到）。**先排除闸拦截，再查其他原因。** 隧道断了时不要干等——把能给的排查命令给用户，让用户帮查。

**处置（2026-08-26 老板拍板，已落地）：**

老板三句话定调：**1. 收窄硬黑名单只留凭证类；2. 工具名/路径靠 SOUL 软规则管；3. 天行者 user_id 白名单豁免。**

已改 `feishu_send_gate.py`（双机同步+基线刷新+ALL_OK）：

**硬拦（只留凭证类，命中直接 block）：**
- `api_key=xxx`、`app_secret=xxx`、`password=xxx` 等凭证赋值（正则匹配 `key=value` 或 `key: value` 形式）
- 私钥（`-----BEGIN PRIVATE KEY-----`）
- Bearer token、`sk-` 开头的 OpenAI key、`ark-` 开头的火山 key
- 完整内部路径+文件后缀（如 `/home/ubuntu/.hermes/config.yaml`）——单纯路径片段（`workflow/`、`.hermes`）不拦
- `.env` 文件引用

**不再拦（从硬黑名单移除，交给 SOUL 软规则管）：**
- 工具名（codex、hermes、ffmpeg、seedance、豆包等）— 正常回复提一句不该被拦
- 服务器标识（新加坡机、广州机、ubuntu等）
- 路径片段（workflow/、.hermes、wiki/ 等）
- 过程词、报告结构词 — 全移除

**天行者白名单豁免：**
- 天行者飞书 user_id `ou_9b793886207dc39cb0a8befbcac6065f` 硬编码到 `ADMIN_WHITELIST`
- `send` 命令的 `open_id` 参数命中白名单 → `check_text()` 直接返回空列表，跳过所有黑名单检查
- `check` 命令不知道 recipient，不豁免（用于通用检查）

**网关层调用链：**
- 广州 `gateway/platforms/base.py` 的 `_CUSTOMER_OUTBOUND_GATE_PLATFORMS = frozenset({"feishu", "weixin"})` 保持不变
- 网关调 `feishu_send_gate.py check <text>` → 命中黑名单返回 exit=2 → 网关拦发
- 白名单豁免在 `feishu_send_gate.py` 内部，网关层不用改

**验证测试结果：**
| 测试 | 期望 | 结果 |
|---|---|---|
| `api_key=sk-xxx` | 拦 | ✅ rc=2 |
| `codex跑完了` | 放行 | ✅ rc=0 |
| `workflow/guard目录更新了` | 放行 | ✅ rc=0 |
| `/home/ubuntu/.hermes/config.yaml` | 拦 | ✅ rc=2 |
| `-----BEGIN RSA PRIVATE KEY-----` | 拦 | ✅ rc=2 |
| `做好了，视频在这` | 放行 | ✅ rc=0 |

**核心教训沉淀：**
  - 物理闸只拦凭证泄露（不可逆伤害），不拦信息暴露（SOUL 软规则管）
  - 白名单是必须的——管理员/老板对话不该被物理闸拦
  - 黑名单设计的第一原则仍是「宁可放过，不可误杀」
  - ⚠️ **同一条教训第三次踩了（2026-08-26）**——08-17 翻车、P0 重建后翻车、收窄后落地。每次黑名单写太宽都是同一个死法。**写黑名单时先问：这个词在正常回复里会不会出现？会就别放硬拦。**

**完整源码和测试细节** → 见 `server-hardening` skill 的 `references/feishu-send-gate-tuning-20260826.md`

## 关联

- 报告精简铁律（删来源/置信度/口径，精简≠删排版）→ 见 `feishu-group-delivery`（用户自有 skill，未 adopt）
- 群权限（permissions.json + SOUL 14/15 视频权限/防冒充）→ 见 `workflow-architecture` 与 wiki/spec/群权限.md
- 会话续接 7 天 / Hermes cron 禁 gateway 重启走系统 crontab → 见 `hermes-gateway-ops`（用户自有 skill，未 adopt）
- 远程 bot 存活诊断（SSH→进程→日志→适配器→.env 凭证）→ 见 `feishu-bot-ops`
