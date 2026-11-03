---
name: video-content-extraction
description: 视频文件与短视频链接内容提取。触发：分析视频讲了什么/口播转写/字幕OCR/下载抖音视频/拿到逐字稿。
license: internal
metadata:
  hermes:
    tags: [douyin, transcription, whisper, video, extraction]
    related_skills: [content-hunter, hermes-gateway-ops]
---
> ⚠️ **旧口径存档（2026-09-21 前）**：本文的利益点表述可能含新规禁项（无广告类／躺赚白嫖／吊打竞品／绝对免费／直接提现）。**只作历史参考，出片一律按优矩最新口径**，禁照搬。


# 视频内容提取（抖音口播转写 / 画面 / 元数据）

从短视频链接拿到「视频到底说了什么」——口播逐字稿（whisper）、画面描述（视觉模型）、元数据（标题/作者/互动）。与 content-hunter 的截图+视觉分析互补：**画面用 vision，口播用 whisper**。

## When to Use
- 用户发抖音分享链接说「分析这个视频内容」「看看他说了什么」
- 用户提供本地视频，需要语音转文字、画面分析或字幕 OCR
- 需要视频口播逐字稿（内容分析/结构拆解/文案参考）
- 需要视频元数据（标题/作者/点赞/时长）

## 转写链工具（2026-10-02 落地，实测可用）

工具目录：`/home/ubuntu/workflow/tools/asr/`（`.hermes/scripts/` 是受保护目录，写不进去）

```bash
# 转写逐字稿（固定 small 起步，不过自动升 medium；每档先繁转简、纠错、再查闸）
python3 /home/ubuntu/workflow/tools/asr/asr_run.py <音视频> <输出前缀>
```

> 2026-10-02 用户定：**固定 small 起步，不启用 tiny/base**（草稿档已从链中去掉）。

- **关键教训：「打回重跑」救不了同音字**——medium 自己也会把「火龙漫剧」听成「火龙慢剧」，换高档位错同一处。真正解掉的是**同音字纠正表 + 闸**（`asr_gate.py` 的 `correct()` / `check()`），不是升档。
- 闸的判据：必对项存在性（品牌名必须出现正确写法『火龙漫剧』）+ 错字黑名单 + 金额白名单 + 繁体检测；命中即 rc=2 打回。
- **必须自带繁转简（zhconv）**：base/tiny 会整段输出繁体，纠正表全是简体模式时会一条都匹配不上（实测 base 在参考片上 0 纠正）。顺序：繁转简 → 同音字纠正 → 查闸。
- 实测（含纠正层后）：base 327–341 MB / 4–6s，难片也能过闸，但仍有零星残留错（「反思我了」「常开」「都不会套」）⇒ **base 仍定位草稿**；small 一次纠错后干净，作默认。
- 实测：small 输出 587–615 MB / 15–31s，一次纠错后全过；medium（逐词时间码）峰值 **1.9 GB** / 99s——**small 起步不只是快，也是内存安全线**；tiny 268 MB / 4.6s 只适合草稿。
- **纠正表怎么长本事**：每次 `correct()` 把纠正记录自动写 `/home/ubuntu/workflow/tools/asr/corrections_log.tsv`；遇新素材/新口音时跑一次 `--audit`（small+medium 都跑，归一化去标点/时间码/中文数字后逐句比对，不一致的写 `<前缀>_suspect.txt`）——实测 35 处噪声归一化后剩 7 处真差异（如 medium 把「签到」听成「千道」）⇒ 人工确认后补进 CORRECT 表。
- **人工核是最后一道，不可省**：闸只能拦系统性错听（品牌名/提现/签到/火龙币），审计只能标「可疑」；意思级同音错（「仓电搜」应为「商店搜」、「玄患重生填宠」应为「玄幻重生甜宠」）只能人看。**当合规依据或对外交付的逐字稿，出稿后先列「自动核结果+可疑清单」交用户抽验，确认才算定稿**。

## Whisper 档位选型（2026-10-02 实测，6 条真实素材）

| 档位 | 内存峰值 | 单条耗时 | 实测表现 | 用途 |
|:--|--:|--:|:--|:--|
| tiny | 275 MB | 6.6s | 错字多 | 批量初筛 |
| base | 480–620 MB | 4–7s | 自有底片尚可；**参考片错关键词**（提现→体现、火龙漫剧→喉咙漫剧）、常出繁体 | 只当粗稿，不做核对 |
| **small** | **620 MB** | **13–20s** | 接近 medium：合规词「提现」对、4-A 全对；偶发错字（签到→遷到、午休→武修） | ⭐ 常规默认（人工扫一遍错字） |
| medium | 1381 MB | 54s | 最准 | 终检/合规定稿 |

**判据**：涉及品牌名/提现等合规词核对的，用 **small 起步**；只有需要零错字才上 medium。base/tiny 绝不用于素材核对或合规判断。

- 云端备选：Bedrock `mistral.voxtral-small-24b-2507` 句级时间码、2.9s、约 0.0006 元/条，但同音字会错（火龙漫剧→火狼模具），只能当草稿，不能当合规依据；`voxtral-mini-3b` 不可用（意译）。
- 不要用 Nova Lite 看视频做台词核对：实测会凭空编台词。
- 本机 ASR 是唯一的内存大户：medium 峰值 1.38 GB，跑它时不要并行开别的重活；small 只 620 MB。

### 自动审核（有文案时首选，2026-10-02 落地）

```bash
python3 /home/ubuntu/workflow/tools/asr/asr_verify.py <转写稿> <文案或.ass文件> [--apply 纠正后输出路径]
```

- **文案来源**：字幕 `.ass` 里就是文案；但必须剥掉 `[Script Info]`/`[V4+ Styles]` 文件头与免责声明行（已内置）。
- **只在转写稿真正覆盖的窗口内比对**（用 ≥6 字的相同块做锚点定位），否则会把整片文案当差异报一堆噪声。
- **差异分两类，处理不同**：
  - 近音/同音（pypinyin 比拼音）→ 判**听错** → **自动按文案改回**（可核验，不是让模型自由改）；
  - 非近音 → 判**临场改词/漏念** → **只标记，绝不动手**。
- 每次自动纠正写错题本 `/home/ubuntu/workflow/tools/asr/errors_db.tsv`（时间／素材／错的原样／正确写法／类型／来源），写入去重。
- 实测：段2 把「填宠」自动改成「甜宠」、段1 零纠正零标记；错题本去重生效。
- **价值**：判据从「猜对错」变成「对答案」——有文案的素材不再需要人工逐句审。无文案素材（参考片/竞品片）降级为 纠正表 + 闸 + `--audit`。

### 自动审核 v2（有文案时首选，2026-10-02 按 Claude 方案 P1 升级）

```bash
python3 /home/ubuntu/workflow/tools/asr/asr_verify.py <转写稿> <文案（建议传分段文案）> [--apply 输出]
```

三道防线（宁可不动手，也不改错）：
1. **整篇匹配度分档**：≥0.85 正常改；0.6–0.85 严格模式（只改完全同音）；**<0.6 判文案不对，整篇降级不自动改**。
2. **完全同音 + 上下文约束**：等长、逐字同音（多音字有交集即算）、且差异左右各 ≥4 字能对齐，才自动改；单字全局替换禁止。
3. **保护类只标不改**：金额/数字/否定词/品牌/提现/签到；改完重跑闸，不过则撤回该处。

实测：段1（匹配度 0.95）零纠正零标记；段2 文案不全（0.62）自动降级拒绝动手；故意改坏文案（0.55）整篇降级拒绝自动改。
**关键**：必须传**分段文案**（`s1_preview.ass`/`s2_preview.ass` 这类），传整片文案会因句子错位而误判。

- **文案（金标）从哪抽**：从项目 `spec/分镜表_*.md` 的**「台词清单」表**抽（5 列：序号|段|说话人|台词|类型），每段一个 txt 存 `tools/asr/scripts/<项目>_S<N>.txt`。⚠️ **不要从「分镜表」区块抽**——那张表只有单人台词，会漏对白，导致匹配度虚低、被守卫误拦。
- **金标集实测（免费-11）**：段2 用完整台词后匹配度 **0.89 → 正常模式 → 自动改 1 处（填宠→甜宠）、人工看 0 处**；段1 匹配度 0.95 零纠正零标记 ⇒ 有完整分段文案时**审核+纠错全自动、零人工**。

### 错题本 v2（SQLite，2026-10-02）

- 库 `errors.db` 三张表：`mishear`（听错记录）/ `speech_diff`（口播偏差，永不升规则）/ `rules`（自动规则）。
- **规则升级**：同一 (错,对,上下文锚) 在 **≥2 个不同素材**出现才升为`生效`，否则仅`候选`；生效规则导出 `correct_auto.tsv`（独立于手写 18 条，**整体删除即可回滚**）。
- `asr_gate.correct()` 自动加载 `correct_auto.tsv`，**按上下文锚替换**：`重生填宠`→`重生甜宠` 会改，但「填个表」不会被动 ⇒ 单字规则必须带锚，禁止全局替换。
- **上下文锚归一化（关键）**：锚取**固定窗口且从未自转写（错字）侧**：`转写[j1-2 : j2+2]`（左2字+错块+右2字）。两个坑：①锚从正确文案侧取会含正确字，纠错时在错文本里匹配不上；②窗口不固定则同一错法因锚长短不同被当成两条，规则计数虚高。
- 自检/报表：`python3 errors_db.py report`。

## 本地视频三层提取

| 层 | 工具 | 产出 |
|:---|:---|:---|
| 语音转文字 | faster-whisper（small，CPU int8） | 带时间戳台词稿 |
| 画面分析 | ffmpeg 抽帧 + vision | 场景、人物、动作描述 |
| 字幕 OCR | tesseract（chi_sim+eng） | 画面内文字 |

优先使用已验证脚本：

```bash
~/.hermes/hermes-agent/venv/bin/python3 /home/ubuntu/.hermes/scripts/extract_video_content.py <视频路径> [tiny|base|small|medium]
```

- 默认 `small`，输出实时带时间戳文本，并保存 `<视频名>_transcript.txt`
- 模型优先从 `~/.cache/huggingface/faster-whisper-<模型>` 本地目录加载，避免联网校验超时
- 画面分析按需抽帧：`ffmpeg -y -i <视频> -vf fps=1 frame_%04d.jpg`（最低每秒1帧，禁用 fps=1/3 或更低——会漏画面切点，用户0826明确纠正）
- 字幕 OCR：`tesseract frame.jpg stdout -l chi_sim+eng`
- Hugging Face 下载受限时使用 `HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`

### ⚠️ 空转写回退：纯录屏/UI演示视频无口播（2026-08-26 实测）

**症状**：whisper 转写返回空（所有 segment 无文本），但视频文件正常、ffprobe 有音频流。

**根因**：视频是**纯画面录屏 / 平台 UI 演示 / 背景音乐无口播**——音频流存在但不含人声（只有 BGM / 环境音 / UI 音效），whisper 正确返回空。**不是 bug，不是模型问题，不需要重试或换模型**。

**正确处理**：
1. whisper 空结果 = 该视频无口播语音，直接跳过语音层
2. **全量依赖画面层**：ffmpeg 每秒1帧抽帧 + vision_analyze 批量送帧（每轮7帧并行），从画面提取内容（人物/场景/UI/字幕文字/平台标识/互动数据）
3. 字幕 OCR 可补充画面内文字（如剧名、互动数据、简介文字），但 vision 通常已覆盖
4. **不要因空转写反复重试 whisper 或升级模型**——纯录屏视频换 medium/large 一样空

**识别信号**：用户发来的视频若是手机录屏（平台界面操作、选集页、筛选页、上新列表），基本无口播；若是短剧正片片段（4-6秒切片），可能有台词也可能只有画面+字幕。本案例4个视频全部空转写，2个是正片片段（纯画面+字幕无语音）、2个是平台功能页录屏。

**批量处理模式**：多个视频并行提取时，先并行跑 ffprobe 拿元数据 → 并行提音频+转写 → 并行抽帧 → vision 批量送帧（每轮7帧）。空转写的视频直接跳到 vision 画面分析，不阻塞其他视频的处理。

### 用户发素材视频时：主动提取+匹配，不要问内容（2026-08-26 定案）

**触发：** 用户在项目进行中发来视频文件（飞书附件/本地文件），说「你自己去匹配」「给你做素材用」或直接甩文件不说话。

**铁律：用户发视频 = 你自己去提取内容，不要问用户「这视频里是什么」。**

执行三步：
1. **ffprobe 全量**：时长、分辨率、编码、文件大小，一次跑完所有视频
2. **whisper 转写 + ffmpeg 抽帧(fps=1) + vision_analyze**：并行处理，每视频抽帧后取首帧+中帧送vision看画面。无口播的短视频也要抽帧做画面分析——靠画面匹配
3. **匹配项目素材清单**：把提取结果对照后期合成方案的素材需求表，列出哪个视频对应哪个素材位、哪些缺、哪些有多

**关键坑：**
- whisper 转写结果为空 ≠ 视频坏了——可能是纯画面+背景音短视频(4-6s)，靠画面分析即可
- 用户说「你自己去匹配」时不要反问「这是哪个剧的」——用户给了素材就是让你用
- 合成方案里写的「同一剧目一致性」是理想约束不是铁律——用户说可以不同剧就不同剧，不要拿方案当铁律挡用户（2026-08-26 用户原话「不一定要一部剧」）
- 白底Logo去透明用 ffmpeg chromakey：`ffmpeg -y -i logo.png -filter_complex "chromakey=white:0.01:0.1,format=rgba" -c:v png logo_alpha.png`

## 飞书入站视频被网关忽略时捞回（file 类型被过滤，2026-08-20 实测）

**症状**：用户说「视频发你了啊，提取内容分析」，但机器上找不到视频文件。`/tmp/feishu_video_*.mp4` 可能是 49 字节坏文件（下载残留/占位，`ffprobe` 报 moov atom not found）。

**根因**：Feishu adapter 的 `_IGNORED_INBOUND_MESSAGE_TYPES = {sticker, media, audio, file}`——用户发的视频若以 **file** 类型到达（不是 image/video 类型），网关直接忽略、不下载，日志只留一行。查证：

```bash
grep "Ignoring inbound message before dispatch" ~/.hermes/logs/gateway.log | tail
# 形如：... Ignoring inbound message before dispatch: id=om_x100b... msg_type=file
# 这条 id 就是被忽略的消息，捞回要用它
```

**捞回三步（飞书开放 API，免费）**：

1. 拿 tenant_access_token（凭证 FEISHU_APP_ID/FEISHU_APP_SECRET 在 `~/.hermes/.env`）：
```bash
curl -s -X POST 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal' \
  -H 'Content-Type: application/json' \
  -d '{"app_id":"<APP_ID>","app_secret":"<APP_SECRET>"}'
# 响应 data.tenant_access_token
```

2. 按 message_id 查消息内容拿 file_key：
```bash
curl -s -H "Authorization: Bearer <token>" \
  'https://open.feishu.cn/open-apis/im/v1/messages/<message_id>'
# 返回 body.content 里 {"file_key":"file_v3_...","file_name":"SVID_....mp4"}
```

3. 下载文件：
```bash
curl -s -H "Authorization: Bearer <token>" -o /tmp/<file_name> \
  'https://open.feishu.cn/open-apis/im/v1/messages/<message_id>/resources/<file_key>?type=file'
# 成功 = HTTP 200 + 真实字节数（46MB mp4 正常）；ffprobe 验证 moov atom 在
```

**要点**：
- message_id 从 gateway.log 的 Ignoring 行拿（就是被忽略那条）；本案例 19:23 被忽略、21:08 用户追问时才捞回，消息还在可下载
- 捞回后照常走 whisper 转写 + ffmpeg 抽帧 + vision 画面分析，不要另起流程
- 恢复流程对任何被 file/media 类型过滤的入站消息都适用（不限于视频）
- 已知边界：adapter 忽略 file 是设计行为，不是 bug；要根治需改 `_IGNORED_INBOUND_MESSAGE_TYPES`（在 hermes-agent 代码里），日常用 API 捞回即可

## 查看素材群/飞书群最近消息（2026-08-22 实测，触发：用户说「看看群里」「群里发了什么」）

现成脚本：`scripts/feishu_pull_group.py`（`python3 <skill_dir>/scripts/feishu_pull_group.py [chat_id] [page_size]`，默认素材群 <MATERIAL_GROUP_CHAT_ID>，默认 20 条，按时间倒序）。

- 凭证从 `~/.hermes/.env` 的 FEISHU_APP_ID/FEISHU_APP_SECRET 自动读，不需要手动传
- 输出每条消息：时间戳/类型/text 全文前 150 字（file/media 只给 key 前 20 位）/发送者脱敏前 8 位
- 常见用途：群里客户/同事发抖音链接要复刻（`text` 含 https://m.douyin.com/share/video/... + 需求描述）→ 先拉群确认需求原文，再走复刻流程（下载→拆解→方案）；`file`/`media` 消息 = 素材文件，key 可配合捞回流程下载
- 与 `feishu_send_file.py`（发文件到素材群）是同一组凭证的对称操作

## 抖音口播转写完整工作流（2026-08-11 实测成功，36.5s 逐句转写）

```bash
# ① 分享链接 → 重定向拿 video_id（手机 UA 必须）
curl -s -L "https://v.douyin.com/<短码>/" \
  -H "User-Agent: Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1" \
  -o /tmp/douyin_redirect.html -w "最终URL:%{url_effective}"
# 重定向到 https://www.iesdouyin.com/share/video/<video_id>/...

# ② 页面 HTML → 提取 play_addr.uri（视频 URI）
curl -s "https://www.iesdouyin.com/share/video/<video_id>/" -H "UA同上" -o /tmp/douyin_video.html
# 正则: "play_addr":{"uri":"v0d00fg10000..."  ← 这是视频 URI
# 同页可提取: <title>/description（标题、作者、点赞）/duration

# ③ 下载视频（手机 UA；第一次 302 小 HTML 必须 -L 跟进）
curl -s -L "https://www.iesdouyin.com/aweme/v1/play/?video_id=<URI>&ratio=720p&line=0" \
  -H "UA同上" -o /tmp/douyin_video.mp4
file /tmp/douyin_video.mp4   # 应显示 ISO Media, MP4

# ④ ffmpeg 提音频 + faster_whisper 转写
ffmpeg -y -i /tmp/douyin_video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 /tmp/douyin_audio.wav
python3 -c "
from faster_whisper import WhisperModel
m = WhisperModel('small', device='cpu', compute_type='int8')
for seg in m.transcribe('/tmp/douyin_audio.wav', language='zh')[0]:
    print(f'[{seg.start:.1f}s-{seg.end:.1f}s] {seg.text}')
"
```

输出：逐句时间戳+文本，直接可做内容分析/结构拆解。

### ⚠️ whisper 长段缺失：关联字幕文件是权威来源（2026-08-27 实测）

**症状**：whisper 转写某段视频时，中间 10–20+ 秒的音频完全没有输出（不是繁体/错字，是整段空白），但视频文件正常、ffprobe 有音频流、首尾段转写正常。

**根因**：音量偏低/BGM盖过人声/音频编码问题导致 whisper 在特定片段检测不到人声段。**不是 bug，不需要重试或换模型**——换 medium/large 一样缺。

**正确处理**：
1. 如果视频有关联字幕文件（`.ass`/`.srt`/`.vtt`），**直接用字幕文件作为权威台词来源**——字幕是制作时人工校对过的，比 whisper 更准确更完整
2. 项目目录里搜 `find <项目目录> -name "*.ass" -o -name "*.srt"`，按时间戳对应
3. `.ass` 文件解析：`Dialogue:` 行格式为 `Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text`，Start/End 是 `H:MM:SS.cs` 格式（厘秒）
4. 没有字幕文件时，该段内容标注「whisper 未检出，无字幕文件可补」，不编造

**实测案例**：v15夜店高颜值版 40.5s 视频，whisper 只转写出 0-10.5s 和 31-40s 两段，中间 20 秒空白。从 `字幕_夜店高颜值_v8.ass` 拿到完整 28 句台词（0.79s-40.50s 全覆盖），比 whisper 更准确。

### ⚠️ whisper 中文转写输出繁体字（2026-08-27 实测）

faster-whisper 转写中文音频时，输出文本可能是**繁体中文**（如「有些人我真是無語了」「放著白嫖的漫劇你不看」）。这不是模型选错语言，是 whisper 中文模型倾向输出繁体。

**处理方式**：
- 转写后做繁简转换再使用——用 `opencc`（`pip install opencc-python-reimplemented`）或手动对照
- 繁体不影响时间戳准确性，做台词本时转成简体即可
- 不要因为输出是繁体就怀疑转写结果错了或换模型

## 抖音反爬备用：Playwright + 手机UA（2026-08-15 实测，curl 拿不到直链时）

> 现成脚本：`scripts/douyin_download.py`（`python3 <skill_dir>/scripts/douyin_download.py <短链或video_id> [输出路径]`，自动完成 短链→video_id→DOM取src→curl下载 全流程）

当 curl 路线失败（share 页 `_ROUTER_DATA` 空壳 / aweme API 返回 blocked / `aweme/v1/play` 空文件）时，改用 Playwright 直接开 www.douyin.com/video/<id>，从页面 video 元素拿直链：

```python
# 前置：pip3 install playwright；chromium 由 `python3 -m playwright install chromium` 安装
# douyin_download.py 内部已自动探测 chromium 路径，无需手动指定
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = browser.new_context(
        viewport={'width': 390, 'height': 844},   # 手机 viewport 必须
        user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        locale='zh-CN')
    page = context.new_page()
    page.goto("https://www.douyin.com/video/<video_id>", wait_until='domcontentloaded', timeout=45000)
    time.sleep(6)   # 等视频加载
    # 关键：video 元素的 src 就是可下载直链（readyState=4 说明已加载）
    src = page.evaluate("() => { const v = document.querySelector('video'); return v ? (v.src || v.currentSrc) : null; }")
    # 形如 https://m.douyin.com/aweme/v1/playwm/?video_id=v0200fg10000...&ratio=720p&line=0
```

- video_id 从分享短链重定向拿（`v.douyin.com/<短码>` → 最终 URL 里的 `/share/video/<id>/`）
- 页面标题含完整文案（如「Seedance2.5真的next level了！...」），`body innerText` 含作者/@名/赞/藏/BGM
- 拿到 src 后用 curl `-L` + 手机 UA 直接下载 mp4（HTTP 200，2-3MB 正常）
- **AI 生成结果（TOS/火山 CDN）下载走 8899 relay**（2026-08-15 实测）：Seedance 生成结果的 `video_url` 是 TOS 国内 CDN，新加坡机 curl 直连超时（exit 28 / 0 字节），必须经广州 relay 透传：`curl -sL "http://127.0.0.1:8899/upload?url=<urlencode(video_url)>" -o out.mp4`
- 抽帧：`ffmpeg -y -i x.mp4 -vf "fps=1" -q:v 2 /tmp/frames/frame_%04d.jpg`（最低每秒1帧）
- **只提取不编造**：画面分析做不了（视觉通道断/无OCR）时如实说拿不到，禁止凭标题+常识编画面描述或编提示词（与 content-hunter §9.10 同款铁律）

### 🚨 放行逻辑（用户追问后确认，避免误判「是不是因为看过」）

抖音放行的是**「链接来源真实」不是「观看者身份」**：
- 分享链接 URL 参数里的 `did`/`iid`/`share_sign` 是「从 App 里分享过」的凭证——所以**匿名全新 context（无 cookie、无登录）照样能拿直链**，跟"谁看过这个视频"无关
- 反爬挡「不是浏览器的请求」，但挡不了**真实浏览器里已加载的 video 元素**（挡了它自己的播放器也播不了）
- 播放器「打开App」遮罩只挡「看」，不挡「加载」——video 元素在 DOM 已真实加载（readyState=4），绕到 DOM 后面读元素即可
- **无需 cookie、无需登录**。若用户问「是不是因为我（用户）看过才放行」→ 答：不是，分享链接本身自带放行凭证

## 群聊任务先确认对象再动手（2026-08-27 用户连批两次）

**症状**：群里方漠阳发抖音链接（吃瓜小刘子）让分析+对比夜店版，随后说"这个字幕和音量都太小了，参考网赚口播模板"。我没仔细追溯消息上下文就默认改了V15夜店版，用户问"她让你改的是这个视频么"时又瞎猜换口，被连批"你改半天连改哪个视频都没搞清楚""你本来就错了"。

**根因**：群聊多消息上下文中"这个"指代不清时，凭最近上下文猜对象而不是回溯消息链确认。用户追问=信号让你STOP去查源，不是让你再猜一次。

**铁律**：
1. 群聊任务动手前，拉完整消息链（`feishu_pull_group.py`）按时间顺序通读，确定请求针对的是**哪个具体视频/文件**
2. 指代不清时逐条对齐消息时间线，别凭印象
3. 用户问"你改的是这个吗"→ 立刻回源验证，**禁止猜**。用户已经知道答案，在测你能不能查
4. 确认对象→复述确认→再动手。改错对象=白干+浪费用户时间+信任损耗
5. **被质疑时禁止改口**：用户问"她让你改的是这个视频么"，如果没查过就不要回答"可能是另一个"——这等于承认没查过就动手了。正确做法：说"我去查"然后拉gateway日志+消息链确认
6. **gateway日志是真相来源**：群消息nonsupport的视频查不了详情时，用时间戳grep gateway.log，能看到reply_to_id（指向哪条视频）、私聊里用户说了什么、bot发了什么文件

## 要点/坑
- **⚠️ cv2.shape 是 (h, w) 不是 (w, h)——竖屏视频别误判成横屏（2026-08-18 火龙漫剧实测，血泪）**：`cv2.imread()` 返回的 shape 是 `(height, width, channels)`，720x1280 竖屏视频抽帧后 cv2 读出来是 `(1280, 720, 3)`（= 高1280 宽720 = 竖屏），不是「变成横屏了」。ffprobe 报 `width=720 height=1280` 与 cv2 `(1280,720)` 是一致的，不要看到 `(1280,720)` 就以为画面旋转了/ffmpeg 自动旋转了，为此折腾 `-noautorotate`/display matrix 排查纯属浪费时间。确认方向最快方式：`from PIL import Image; Image.open(f).size`（PIL 是 (w,h)，与 cv2 互补印证）；或 vision 直接看图（人物正立=没旋转）。**cv2 里用 `img.shape[0]`=高、`img.shape[1]`=宽**。
- **手机 UA 是必须的**（桌面 UA 触发验证码/拿不到 play URI）
- `aweme/v1/play` 第一次返回 302 小 HTML，**必须 `-L` 跟进**才有真实 mp4
- 转写模型 faster-whisper-small 在 `~/.cache/huggingface/faster-whisper-small`（**勿删**）
- 长视频（>2min）转写耗时，用 `medium` 模型更准但更慢；短视频 `small` 够用
- 若 whisper 未装：`~/.hermes/hermes-agent/venv/bin/pip install faster-whisper`；HF 下载被墙需 `HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1`
- **Playwright chromium 路径自动探测（2026-08-28 修复）**：`douyin_download.py` 已改为 `find_chromium()` 自动探测，优先用 playwright 内置 `executable_path`，fallback 到 glob 扫描 `~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome`，不再硬编码版本号。**如果仍然报 `Executable doesn't exist`**：说明 chromium 没装，运行 `python3 -m playwright install chromium` 安装即可（约115MB）。磁盘清理删 `~/.cache/ms-playwright/` 后需重装

## 批量分类分析工作流（6-20条视频级分类任务，2026-09-03 实测）

触发：用户发一批抖音链接要求「分析分类」「看看有多少子分类」「结合V6版本分析」。

与单条深度拆解不同——批量分类不需要逐帧 vision，用**首帧+中帧+尾帧**三帧采样即可判一级分类+子类+主播形象+底部声明。

### 步骤
1. **批量下载**：`douyin_download.py` 逐条下载（串行，防OOM）
2. **批量 ffprobe + 提音频**：for循环跑完，拿时长/分辨率/编码+wav
3. **批量 whisper 转写 + fps=1 抽帧**：串行跑，每条30-36s视频约30-40帧
4. **读转写文本**：先读全部转写文本，用口播内容做一级分类预判（口播提激励？底部有声明？）
5. **三帧 vision 分析**：每条取首帧+中帧+尾帧送 vision（每轮7帧并行），每帧问：人物特征/年龄/性别/发型/穿着/场景/AI还是真人/画面内文字UI/底部有无提现声明
6. **对照V6框架分类**：用转写+画面信息对照 `references/video-template-classification-v6-20260830.md` 的分类口径做一级分类→二级子类
7. **沉淀**：写入 `wiki/concepts/<主题>-category.md`，同步更新 V6 参考文件
8. **素材归档**（2026-09-03 定案）：分析完的视频+转写+抽帧不能只放 /tmp（会被清），必须归档到 `wiki/concepts/<主题>-samples/` 下永久保留，建 INDEX.md 索引标注子类/主播形象/场景。方沐阳原话：「这些素材作为高颜值口播的分类沉淀下来」——素材本身就是分类标准范例，后续做同类素材时参照执行

### 关键技巧
- **转写文本可区分口播vs剧情**：口播段是独白体，剧情段是对话体（A说B答）——转写文本特征直接判断段落属性
- **尾帧判底部声明**：vision 看尾帧有无「具体金额以实际活动为准…」提现声明——区分软网赚vs通用口播的关键
- **首帧判主播形象**：AI数字人vs真人、年龄风格、穿搭——颜值维度分类依据
- **中帧判App展示**：有无App界面贴图/功能弹窗/漫剧引流片段——子类分类依据
- **同账号同文案换形象=A/B测试**：发现同账号发了2条几乎一致文案的视频仅数字人形象不同，这是批量测试素材的常见手法
- **whisper 输出繁体不影响分类**：转写文本用于分类判断，不用于交付，无需繁简转换

### 与单条深度拆解的区别

| 维度 | 批量分类（本节） | 单条深度拆解（上文） |
|:---|:---|:---|
| 视频数 | 6-20条 | 1条 |
| 抽帧密度 | 首帧+中帧+尾帧（3帧/条） | 每秒1帧（30-40帧/条） |
| vision轮数 | 1-2轮（7帧/轮） | 5-6轮 |
| 分析深度 | 一级分类+子类+主播形象 | 14问+商业本质+结构时间轴 |
| 产出 | 分类矩阵+沉淀文档 | 拆解报告+复刻方案 |
| 执行器 | Hermes直接做（不派codex） | 打包派codex |

## 单条视频深度拆解完整流水线（2026-08-26 实测，火龙漫剧通用口播模板）

当用户发一条抖音链接要求「拆解这个视频」时（非批量、非复刻，而是分析结构/卖点/话术/模板），走以下端到端流水线：

### 步骤
1. **下载**：`python3 scripts/douyin_download.py <video_id> /tmp/<name>.mp4`
2. **ffprobe**：拿时长/分辨率/编码 `ffprobe -i <mp4> -v quiet -show_entries format=duration -show_entries stream=width,height,codec_name -of csv=p=0`
3. **提音频+转写**：`ffmpeg -y -i <mp4> -vn -acodec pcm_s16le -ar 16000 -ac 1 <wav>` → faster-whisper small 转写，输出带时间戳逐字稿
4. **抽帧**：逐帧抽或至少每秒1帧（用户0826明确纠正：每3秒抽1帧会漏画面切点和微表情）。命令：`ffmpeg -y -i <mp4> -vf "fps=1" -q:v 2 <outdir>/frame_%04d.jpg`（40秒视频=40帧）。转场密集段可逐帧抽：`ffmpeg -y -i <mp4> -q:v 2 <outdir>/frame_%05d.jpg`。**禁用 fps=1/3，密度不够会漏关键画面切换和微表情**
5. **vision逐帧分析**：用 `vision_analyze` 批量送帧（每轮7帧并行），每帧问：人物特征/场景/画面风格/构图/画面文字UI/手机界面展示。40帧分6轮送完。
6. **打包codex深度分析**：把口播逐字稿+逐帧画面分析打包给codex，要求按14问拆解框架+商业本质4维度（商业模式/话术结构/省略信息/启示）+结构时间轴+模板特征总结+复刻要点输出报告

### 关键坑
- **codex大上下文分析超时（2026-08-26 实测）**：prompt含多帧vision分析+完整逐字稿+10问框架+商业分析 = 2000+字上下文，codex effort=high 思考阶段就300s+。**正解：一开始就 background=true + timeout=600 + notify_on_complete=true**，不要先foreground 300s失败再重试（浪费一轮300s）。判断标准：prompt超过2000字或含多帧画面分析 → 直接后台600s
- **read_file误判codex产出为binary（2026-08-26 实测）**：codex写的.md文件若含超长行（300+字符/行），read_file会误判为binary拒绝显示。用 `cat <文件> | head -N` 或 terminal 读，不要依赖 read_file
- **vision_analyze并行送帧**：一轮送7帧（7个vision_analyze调用放在同一个assistant turn），runtime并行执行，比逐帧串行快7倍
- **🚨 抽帧密度不够=漏关键信息（0826用户明确纠正）**：每3秒抽1帧（fps=1/3）会漏掉画面切点、转场、微表情、CTA闪现。用户原话「你拆视频的时候就需要每帧都拆，不然你中间会漏掉很多东西」。最低每秒1帧（fps=1），转场密集段逐帧抽
- **🚨 delegate对比报告可能不准——必须实看成片画面验证（0827实测）**：用 delegate_task 让子agent 基于文档（拆解报告+合成方案+台词本）分析成片vs原片差异，子agent 没看成片画面就断言「大字完全缺失」「画中画缺失」——实际成片已烧入这些元素。子agent 基于文档分析 = 基于设计意图分析，不是基于实际画面。**任何成片质量评估必须抽帧+vision实看画面**，不能只靠文档对比。delegate 产出的报告要抽查关键结论是否与画面一致，不一致的结论标注不可信
- **🚨 复刻=全部复刻不只台词（2026-08-27 用户纠正）**：用户说「你的台词跟原片都不一样」后明确裁定——复刻是全部复刻（台词+结构+节奏+大字+时间轴+画中画时段+页面顺序），只换人物和场景。自作主张写新台词、改结构、缩短口播段 = 不是复刻是改编。**复刻任务开工前先扒原片完整台词逐字稿（whisper转写），逐句对照原片时间轴，不凭记忆或方案文档拼凑台词。** 同时原片画面结构（数字人段时长、App页面出现顺序和各自时长、画中画出现/退出时间、大字内容和触发时间）全部照抄，只把数字人形象和背景环境换成新的人物/场景

### 报告转docx发飞书群（2026-08-26 实测）

codex产出的md报告需转docx发飞书群时：
1. **md→docx**：用python-docx脚本转换（处理标题##/###、表格|、列表-、加粗**，跳过表格分隔行`|---|`），保存为`<报告名>.docx`
2. **发群**：`python3 scripts/feishu_send_file.py <docx路径> <chat_id>`（素材群chat_id=`<MATERIAL_GROUP_CHAT_ID>`）
3. **两份文件并行**：拆解报告+生产方案可同时转docx+发群（两个terminal调用放同一turn并行）
4. **md→docx转换脚本**：`scripts/md_to_docx.py`（处理标题/表格/列表/加粗/引用，跳过代码块和表格分隔行）。用法：`python3 <skill_dir>/scripts/md_to_docx.py <input.md> <output.docx>`

## 批量拆解（20+ 视频级任务，2026-08-16 方沐阳案例）
- **工程结构**：`workspace/video-deconstruct-<日期>/` 下三脚本分工——`batch_download.py`（Playwright 手机UA 串行下载，视频 ID 列表写死）、`batch_transcribe.py`（ffmpeg 提音频 + faster-whisper 转写，每句带时间戳）、`batch_frames.py`（抽帧）
- **串行防 OOM**：低内存机（3.6G）批量下载/转写必须串行；转写（whisper small 峰值 1-2G）与 codex 大任务**不能并发**，否则 OOM。但**内存允许时批量拆解可多进程并行**（2026-08-16 用户拍板）：3.6G 可跑 4 组 codex，留 1-2 个槽给其他任务；下次批量任务**一开始就分 2-4 组**（每组独立输出文件，最后合并），不要单进程硬跑
  - ⚠️ **中途才拆分组 = 亏**（2026-08-16 实测教训）：任务已跑 30+ 分钟快完成时才想起并行，此时拆组会**浪费已跑时间 + 多进程写同一输出文件冲突**。判断：任务接近收尾（输出文件已在增长、最后章节在写）→ 让它跑完，**下次一开始就分组**；任务刚开始（大量视频未处理）→ 立刻拆组并行才有收益
- **抽帧密度（用户纠正）**：3-5 帧/视频太少——30 秒视频每 12 秒一帧会漏转场/卖点/CTA。拆解用 **每 5 秒一帧 + ffmpeg scene detect 关键帧**（30 秒视频 10-30 帧），结构完整且 vision 分析量可控。批量抽帧脚本参考 `batch_frames_v2.py`（时间轴帧每5s + scene>0.3 关键帧 + 间隔<2s 去重，输出 f_序号_秒数.jpg 便于定位）
- **单条失败不阻塞**：个别视频下载失败（已删/私密/无 video 元素）记下原因继续，19/20 可用不影响整体
- **数据三件套齐了才算就绪**：videos/ + transcripts/ + frames/ 全部生成后，才打包上下文派 codex 拆解（转写内容喂给 codex 做分析，不要只靠抽帧）
- **批量拆解维度约定（2026-08-16 用户确认）**：达人批量拆解（「看看这些视频怎么做的」）用**内容拆解 7 维**——类型/结构（开头钩子-中段-收口）/卖点/话术/画面证据/合规风险/可借鉴点，证据靠转写时间戳+抽帧秒数，不是六维逆向分析。**别对达人批量任务上六维完整拆解**（运镜/光影/风格/音色/置信度/逆向 prompt 那套是生产参考用的，达人看了太重）。用户问「拆解方案怎么设计的、从哪些维度拆」→ 如实答 7 维内容拆解 vs 框架六维的适用边界
- **🚨 拆解完必须沉淀为数字资产（2026-08-16 用户定案）**：拆解成果不能发完就丢——归档到 `wiki/teardowns/`：① 拆解报告（命名 `日期_主题_类型.md`）② 原始素材（视频/转写/帧/脚本，保留可复跑可溯源）③ 更新 `README.md` 资产索引。这是别人没有、可复用可迁移的核心资产，下次生产同类素材先查库
  - **⚠️ 只归档「可复用资产」，不归档「一次性情报」（2026-08-16 用户纠正）**：像「文档自相矛盾清单」这种给甲方确认完就过时的情报，**不值得归档**；只有下次能直接复用的东西（拆解报告本身/方法论/素材/红线库）才进 `wiki/teardowns/`。归档前自问：三个月后这文档还有用吗？
- **🚨 交付给达人：直接发飞书原生文件消息，别发 COS 链接（2026-08-16 实测）**：COS 签名链接给外部人打不开（默认域名未备案超时/加速域名签名 403），飞书群里直接点开的正解是 `im/v1/files` 上传 + `im/v1/messages` 发文件消息（`msg_type=file`）。报告类先转 docx 再传（feishu_send_gate 的敏感词闸会把 URL 里的 `.md` 当内部文件泄露拦掉）。文本消息仍走 feishu_send_gate.py（@ 强制 + 敏感词闸）。现成脚本：`scripts/feishu_send_file.py`（`python3 <skill_dir>/scripts/feishu_send_file.py <文件路径> [chat_id]`）。
- **🚨 群消息里「调度过程描述」同样是暴露（2026-08-16 老板两次点名）**：对外消息出现「打包 codex 深度分析」「effort=high」「派 codex 做」这类**调度词**，跟暴露路径/工具名一样违规——客户只该看到「结果/结论/文件」，不该看到「我怎么在干活」。发群前自检：这句话是「我在怎么干活」→ 删；是「干完了什么」→ 留。注意：**另一个群会话（gateway 里同时跑的会话）也可能在群里发调度过程**——收到老板「又在群里暴露工具了」时，先查是不是群会话发的（`grep oc_52b229 gateway.log | tail`），是的话停掉那个会话的 turn，主会话接手静默交付。
- **🚨 批量拆解先问「素材有没有跑过数据」（2026-08-16 老板定案）**：拿到一批素材（尤其达人来料）先问客户有没有曝光/点击/消耗等投放数据——**跑过数据 → 基于真实跑量做归因分析才有价值；没跑过 → 明说「现在的拆解/画像只是素材制作参考，等跑出数据再做基于数据的归因」**。老板原话：「如果这些素材只是单单做出来，他没有跑过数据的，你做的分析就没什么用」。别让客户以为没数据支撑的拆解能当效果结论（详见 content-data-review「素材分析前先问有没有跑过数据」）。
- **🚨 分析报告不做 humanizer 去AI味（2026-08-16 老板纠正）**：codex 写分析类报告（拆解/画像/市场分析）时如果自动加载 humanizer 去AI味 = 加戏。**分析报告重点是数据准确、逻辑清楚，不是文风自然**——去AI味是给客户看的文案/口播稿用的。派 codex 任务书里明确「分析报告不做 humanizer」，或它自己在 AGENTS.md 里加载了也让它跳过。同时**对外报告要精简**（≤80 行只写结论，删来源/置信度/口径解释——见 feishu-group-delivery「报告精简铁律」），但**精简 ≠ 去AI味**：精简是删自证噪音，去AI味是改文风，分析报告只需精简不需去AI味。

## 引用上游文档做标准时的铁律（2026-08-16 火龙文档踩坑）

**拿外部文档（甲方规范/平台要求）当判定标准前，必须先核对文档内部是否自相矛盾**——本次拆解火龙漫剧 19 条素材时，引用了火龙投稿指引的「高清1080P以上」判 19/19 不达标，但文档另一处明确写「竖版 1080×1920 **或 720×1280**」——720P 是合规范式，判定错了。

- 外部文档常有多处规则互相打架（例：一处说「必须1080P」，另一处把720P列为合规；一处禁「免费」话术，另一处要求「免费爽看」作为核心卖点）
- **做法**：引用文档当标准前，先通读全文搜矛盾（同一规则的不同表述、红线段 vs 要求段、范例 vs 禁令），把矛盾点列出来再判定；拿不准时按「最保守口径」判但标注矛盾，或让甲方确认
- 拆解报告里的规格判定错了 → 要在群里补发更正说明，并在资产库里同步修正，不留错误结论

## 国内访问新加坡 Web 服务：广州机中转（2026-08-16 实测打通）

**症状**：新加坡机（<SG_HOST>）的网页/服务**国内手机打不开**——国内网络（含广州机）访问新加坡公网 IP 超时/被墙。服务器本身正常（本机 curl HTTP 200）。**不是服务器故障，是国内↔新加坡跨境不通**。

**链路（手机 → 广州公网 → Caddy → 隧道 → 新加坡服务）**：
```
手机(国内) → 广州公网80(<GZ_HOST>) → Caddy /factory/ → 广州127.0.0.1:18090 → SSH -R隧道 → 新加坡127.0.0.1:8090
```

**搭建步骤**：
1. 广州机安全组放行 80 端口（腾讯云控制台，来源 0.0.0.0/0）
2. **新加坡机建反向隧道**（新加坡机经 2222 反隧连广州机，把本地服务映射到广州机）：
   ```bash
   # 新加坡机执行（新加坡机无 autossh，用普通 ssh 后台）
   nohup ssh -N -i ~/.ssh/id_ed25519 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
     -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no \
     -R 18090:127.0.0.1:8090 ubuntu@127.0.0.1 -p 2222 > /tmp/tunnel18090.log 2>&1 &
   # 验证：广州机上 curl http://127.0.0.1:18090/login → 200
   ```
   ⚠️ **`-R` 方向**：`-R <广州端口>:<新加坡目标>:<新加坡端口>` 写的是**出口机（新加坡）本地目标**，别把 8090 当广州本地
3. **广州机 Caddy 加路由——用 admin API 免 sudo**（Caddyfile 是 root 所有，普通用户改不了；admin API 在 127.0.0.1:2019 可免密改）：
   ```bash
   # 读现有 srv1 routes → 插新路由到最前 → PATCH
   curl -s http://127.0.0.1:2019/config/apps/http/servers/srv1/routes > /tmp/routes.json
   # 新路由: {"match":[{"path":["/factory/*"]}],"handle":[{"handler":"reverse_proxy","upstreams":[{"dial":"127.0.0.1:18090"}]}],"terminal":true}
   curl -s -X PATCH -H "Content-Type: application/json" --data @/tmp/routes_new.json \
     http://127.0.0.1:2019/config/apps/http/servers/srv1/routes
   ```
4. **后端 FastAPI 子路径部署两个坑**（缺一不可）：
   - **服务端**：FastAPI 加 `root_path="/factory"`（环境变量控制，`XG_FACTORY_ROOT_PATH`）——否则重定向 Location 是 `/login` 丢前缀
   - **前端 JS**：所有 `fetch('/api/...')` 相对路径在 /factory/ 反代下会打到根路径 → 404。**必须**给 api() 加前缀：`const API_BASE = location.pathname.match(/^\/factory/) ? '/factory' : '';` 然后 `url = API_BASE + url`
   - 验证链路：`curl -sL http://<GZ_HOST>/factory/login` → 200 且页面含登录表单

**持久化注意**（两个隐患）：
- 隧道是普通 ssh 起的，断了不会自动重连 → 建议新加坡机装 autossh 保活
- Caddy admin API 改的是**运行时配置**，Caddy 重启后丢失 → 要持久化需把路由写进 Caddyfile（需 sudo）

## 复刻视频（对白不变，只换人物场景）提取与交付（2026-08-17 火龙漫剧案例）

**触发**：用户发抖音链接说「复刻这条视频/照着做一版/换个受众再做」，指定新人群画像（如中年下沉市场、女性35+、三线以下城市）。这类任务跟普通拆解不同：**对白是源文件，画面按新人群重设计**。

**铁律1：复刻=全部复刻，只换人物和场景。** 转写的逐字稿 = 复刻版台词本，直接原样复制进新方案，禁止总结/润色/换说法/「优化」口播。**复刻范围不止台词**——画面结构、时间轴节奏、大字关键词内容/触发时间、画中画出现/退出时段、App界面展示顺序，全部照抄原片。**唯一允许改的只有人物（年龄/性别/穿搭）和场景（背景环境）**。用户原话（2026-08-27）：「复刻就是所有的复刻，除了人物、场景不复刻以外」。如果自作主张改台词、改结构、改大字、缩短口播段、调整页面顺序 = 不是复刻是改编，用户会指出「你的台词跟原片都不一样」。

**铁律2：出片前必查权限。** `read_file(/home/ubuntu/.hermes/permissions.json)` 按发起人 user_id 查 level：
- basic（默认/未配置）→ 禁视频/生图，**禁止调付费API出片**，话术「您的权限暂不支持视频生成和图片生成，文案类功能正常使用，如需升级请联系管理员」
- unlimited（天行者 ou_2bf2509d...）→ 放行
- **basic 用户的可交付边界 = 完整复刻方案**（对白原样 + 人物/场景/穿搭/手机演示按新人群重设计的分镜+提示词），先交付方案，权限升级后再出片——拒绝≠什么都不给

**提取阶段固定动作（免费，先做完再谈方案）**：
1. 下载原片（douyin_download.py 或 curl 流程，见上）
2. ffprobe 拿时长/分辨率/编码（复刻版总时长对标原片，43s片按±1s控）
3. ffmpeg 提音频 + faster-whisper 转写 → **带时间戳逐字稿**（这就是复刻台词本）
4. 逐帧或至少每秒1帧抽帧 + vision 分析：人物（年龄/性别/穿着）、场景、风格（AI生成/实拍）、画面内文字/UI元素（手机弹窗演示、底部合规小字、「内容由AI生成」标识——复刻版要保留这些元素）。**禁用每3秒抽1帧，会漏画面切点和微表情（0826用户纠正）**
5. 落盘拆解记录（对白/画面/结构/合规小字），再进方案设计

案例细节：`references/video-replication-case-20260817.md`
下游链路（codex 打包 5 文件 / `_自备文案.flag` / SPEC 与 REGISTRY 路径坑 / 合规风险标注）：`references/video-replication-prereq.md`

## 视频模板对比分析（拆解完成后的自然跟进）

> 详见 `references/video-template-comparison.md`

触发：用户分析完一条视频后说「跟我们XX模板对比」「跟网赚模板比一下」。

步骤：① search_files 搜索项目目录定位内部模板定义文件（`生产方案.md`/`拆解报告.md`/`_知识库引用.md`）→ ② 提取对比维度（核心承诺/痛点/证据/UI展示方式/人设/机位/底部声明/CTA/时长/分辨率/字幕）→ ③ 按生产方案 A2 边界规则判定模板归属 → ④ 输出逐维度对比表+关键差异点+对我们模板的启示。

关键判定规则（四类模板，2026-09-03 更新）：
- **网赚剧情**：前段有场景化剧情演绎钩子（5-14s，2-3人互动，悬念/冲突/反转），后段接口播推广。钩子段非口播是关键判别特征。可含漫剧正片引流段。详见 `references/video-template-categories-20260830.md`
- **网赚口播**：直接面对镜头开讲，无剧情演绎段。分两个分支：**硬网赚**（W-F~W-K，口播直说赚钱/金币/提现）+ **软网赚**（S-G~S-L，颜值主播+口播不提赚钱+底部声明）。2026-09-03 方沐阳定案：软网赚不是独立大类，是网赚口播下的分支。W-K=夜店网赚口播（情绪爆发·多人轮换型，2-3人A→B→C轮换出场+手机屏直出+18层后期贴片）
- **软网赚**：口播主体只讲追剧体验（不直说赚钱/金币/提现），底部挂提现声明。**特点是颜值高的主播形象进行口播**（AI数字人或精心打扮的真人），颜值是第一留人变量——前3秒靠形象留人，不是靠话术。合规风险远低于网赚口播（口播不踩红线，声明在底部）。2026-09-03 正式定义为软网赚分支，6个子类（S-G~S-L），详见 `references/video-template-classification-v6-20260830.md` 和 `wiki/concepts/ruanwangzhuan-soft-category.md`
- **通用口播**：口播只讲追剧体验+无激励信息+底部无提现声明

**对比维度参考**（从生产方案 A2 边界表提取）：核心承诺、主要痛点、必备证据（真实录屏 vs 贴图）、人设、禁止混入项、CTA、底部合规声明有无、时长、分辨率、字幕样式。

> **三类模板体系与网赚剧情子分类**：详见 `references/video-template-categories-20260830.md`（5种钩子套路台词模板 + 8步口播公式 + 6种子分类矩阵 + 文案套路公式 + 未观测组合方向）。
> **V6框架口播类分类分析**：详见 `references/video-template-classification-v6-20260830.md`（6条口播素材的一级分类判定口径 + 软网赚正式分支 + 演员形象分类维度 + 推荐数据字段）。
> **软网赚分支完整分析**：详见 `wiki/concepts/ruanwangzhuan-soft-category.md`（2026-09-03，6条新视频分析，新增S-K/S-L子类，颜值维度presenter_look，软网赚通用骨架+要素替换表）。
> **网赚脚本库**：`wiki/concepts/huolong-wangzhuan-script-library.md`（12条原始脚本+模板分类+合规适配仿写范例）。仿写脚本时必读 `huolong-manju-standard.md` §5话术红线，逐条对照合规适配表做替换。详见 `references/huolong-script-compliance-adaptation.md`。

## 相关
- **🚨 拆解分析先走标准框架（2026-08-15 用户纠正，最高优先级；2026-08-28 升级14问）**：拆视频/爆款拆解/参考视频分析，**先读 huoshan 节点2 的 `references/video-deconstruction-framework.md`（14问拆解框架 + 视频源获取 + 全帧提取 + 情绪弧光 + 爆款因子 + 交付物格式 + 默认禁止项 + 使用边界声明）**——现成框架已在 skill 库，**禁止自创拆解框架**。本会话曾自创「六维拆解」并写成独立规范，被用户指出重复造轮子。若确需新维度，作为该框架的补充小节，不另立山头。
- **引流/卖课类视频（教学号/工具推广）要加「商业本质拆解」维度**（2026-08-16 实测，宁老师讲流量案例）：这类视频表面教方法、实际是销售漏斗——只拆内容（10问框架）会漏掉它的真实目的。补四个商业维度：①**商业模式**——它赚什么钱（卖工具/卖课/直播导流/会员），「卖铲子的人」怎么变现；②**话术结构**——从钩子到 CTA 每一步在改变观众什么心理（恐吓→幻想→降门槛→紧迫感）；③**他没说的**——AI内容限流/批量发布封号/版权风险/工具真实成本，省略了什么；④**对我们的启示**——技术能否平替、客户买工具还是买服务、爆款逻辑哪些能借鉴哪些是红线（如「自动发布」承诺我们不做）。输出文件按 `outputs/<作者>视频内容分析_<日期>.md` 落盘，执行者 codex。
- **AI 视频逆向分析（拆提示词）**：拆 Seedance/即梦类 AI 生成视频的提示词时，用 **huoshan 的 `references/video-deconstruction-framework.md` 第八章**（AI 视频逆向提示词分析，2026-08-15 并入）——六维画面分析（运镜/人物表演/光影质感/场景一致性/AI破绽/结构节奏）+ 第七维音频-口播 + 置信度标签（>0.8 全局锁 / 0.5-0.8 正向补充 / <0.5 丢弃）+ 复现风险清单 + 稀疏采样边界。铁律：基于画面/音频证据反推，声明「非原作者公开 prompt」；视觉模型会幻觉（如把 AI 视频判成"真人实拍"），单帧结论不采信，多帧交叉验证。⚠️ 曾自建 `wiki/concepts/video-reverse-engineering-spec.md` 独立规范，被用户指出重复造轮子（2026-08-15），已删除并并入框架第八章——**禁止另立山头，逆向分析是拆解框架的补充，不是新框架**。
- **逆向提示词 → 生成验证片（2026-08-15 完整闭环）**：用反推 prompt 调 Seedance 生成（经 18888 代理提交 + 8899 relay 下载，见上文）后，**交付前必须按 video-production §11 合成规则重做**——统一 BGM + 环境音叠轨 + loudnorm 归一化 + 技术质检（h264/aac/分辨率/时长/音频码率）。禁止裸 concat 三镜就交付（用户纠正「你剪辑视频没有规则的吗」）。生成验证的价值 = 测「纯文本逆向 prompt 能否驱动生成」，结论：场景/人物/光线命中率高，2.0 Mini 复合动作（行走+回头+笑）会退化，单动作稳。**Seedance API 调用坑**：提交 `POST /api/v3/contents/generations/tasks`（带 JSON body），轮询 `GET /api/v3/contents/generations/tasks/{id}` **必须不带 body**（GET 带 body 哪怕 `{}` 也返回 400）；生成结果 video_url 是 TOS 国内 CDN，海外机直连超时，走 relay 透传下载。
- content-hunter：热门内容批量抓取（元数据/画面截图）——user-owned，如缺口播转写可提议 adopt 合并
- hermes-gateway-ops：`~/.hermes/scripts/extract_video_content.py` 本地视频文件转写（不用下载）
- **竞品方法论对比**：`references/competitor-reverse-prompt-analysis-20260828.md`（桃子的AI小屋反推提示词拆解+与我们框架的逐维度对比）
- **拆解框架改进建议**：`references/deconstruction-framework-improvements-20260828.md`（5个可补入 huoshan video-deconstruction-framework.md 的改进点，huoshan 为 user-owned 无法直接 patch，建议待 adopt 后合入或由用户手动执行）
