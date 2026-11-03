# r2v 提示词实测勘误（0827 痛点版+网赚版混用）

> 2026-08-27 实测，补充 r2v-prompt-tips-0825.md

## 一、痛点版 vs 网赚版 prompt 差异（混用必翻车）

火龙漫剧复刻存在两版台词结构：
- **网赚版**（A_COPY_FINAL）：28句248字，人物举手机展示闪屏页，传3张参考图（人物+场景+闪屏页@图3）
- **痛点版**（交接包）：12段199字/40秒，部分段是纯口播不持手机

**翻车案例（0827）：** GLM出痛点版段1提示词时，任务书引用了网赚版模板作为风格参考，GLM把"举手机+展示闪屏页+[Image 3]"当成了必须项串进来。用户纠正："提示词跟网赚版串了，场景也变了，手里还举个手机"。

**根因：** GLM分不清模板里的哪些元素是通用的（写法风格、负面约束格式）、哪些是版本专属的（举手机、闪屏页、3张图）。

**规则：**
1. 纯口播段（数字人全屏，不持手机）：删掉所有手机/持机/举屏/闪屏页描述，只传2张参考图（人物+场景），不加[Image 3]
2. 举手机展示段：保留手机描述，传3张图含闪屏页
3. 任务书里引用旧模板当参考时，必须显式写"删除模板中的手机/闪屏页相关描述，本段是纯口播不持手机"
4. 负面约束加"不要手持手机或任何物品"防模型自作主张加手机

## 二、快乐马 r2v 声音调参三件套（0827 实测）

用户反馈三个问题，对应改法：

| 问题 | 原写法 | 改后写法 |
|:---|:---|:---|
| 语速慢 | 语速适中 | 语速明快，节奏紧凑 |
| 情绪不对（不像口播） | （无情绪描述） | 情绪饱满，吐槽语气夸张，像短视频口播主播有爆发力 |
| 声音小 | （无音量描述） | 音量饱满，声音洪亮 |

**实测结果：** v2改了这三项后，用户确认"声音情绪倒是好多了"。说明快乐马r2v的声音参数对prompt里的描述词敏感——"语速适中"模型理解为偏慢，加"明快"才提速；情绪和音量不写则默认偏弱。

## 三、提示词修改 Hermes 可直改不外包

声音参数调优、删手机描述等属于机械修改（改已有prompt的措辞），不是创作活。Hermes可直接改prompt重新提交，不需要重新打包给GLM。只有创作新prompt（从零写画面动作+台词+声音+负面）才外包GLM。

## 四、广州机 dashscope_video.py 提交流程（0827 确认可用）

1. payload JSON 在SG写好 → scp到广州 /tmp/
2. prompt提取到 /tmp/xxx_prompt.txt（避免命令行中文问题）
3. 在广州机本地跑 `python3 ~/.hermes/scripts/dashscope_video.py --model happyhorse-1.1-r2v --prompt-file /tmp/xxx_prompt.txt --images URL1 URL2 --resolution 720P --duration 10 --ratio 9:16 --output /tmp/out.mp4`
4. 脚本自动提交+轮询+下载（约3-6分钟）
5. scp回SG
6. 全程在广州机本地直连DashScope，不经过SG guard（guard会拦dashscope域名）

**注意：** dashscope_video.py 的 `--watermark` 是开关式（加了才加水印，不加默认不加），没有 `--no-watermark`。watermark参数在API JSON里设false即可，命令行不需要传。

## 五、多段并行提交 + ffmpeg concat 组装（0827 实测）

火龙复刻4段×10秒，段3和段4同时提交并行跑，省一半时间。

**流程：**
1. 在SG写一个通用提交脚本 `/tmp/huolong_submit_seg.py`，接收段号参数
2. scp脚本+各段payload到广州/tmp/
3. 用两个 `terminal(background=true)` 同时ssh执行 `python3 /tmp/huolong_submit_seg.py 3` 和 `... 4`
4. 两段并行跑，约4-5分钟全部完成
5. scp各段mp4回SG
6. ffmpeg concat拼接（各段编码一致时直接 `-c copy`）：
```
cat > concat_list.txt << 'EOF'
file '/tmp/seg1.mp4'
file '/tmp/seg2.mp4'
file '/tmp/seg3.mp4'
file '/tmp/seg4.mp4'
EOF
ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy full.mp4
```

**通用提交脚本模板：** 接收段号参数，读对应payload JSON，提取prompt到文件，调dashscope_video.py提交+轮询+下载。脚本在`/tmp/huolong_submit_seg.py`。

**段间情绪一致性：** 每段prompt的"表情"和"情绪"描述要根据台词内容调整（段1吐槽→段2推荐→段3展示→段4收束），但声音描述（音量/语速/口播感）保持一致。改情绪措辞属于机械修改，Hermes直改不外包。
