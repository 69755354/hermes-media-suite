# 出提示词任务书打包配方（2026-08-23 火龙分镜→提示词包实录）

> 场景：分镜脚本已验收 PASS（G_CREATIVE_READY 已过），用户说「出提示词吧」——把分镜脚本每镜的「可独立投喂 prompt」规范化为最终可提交 API 的 PROMPT_PACKAGE（MEDIA_PREP 的 PROMPT_READY 子状态）。

## 任务书头部（照抄即可，TASK_TYPE 用白名单内的「分镜」）

```
TASK_TYPE=分镜
READ_SKILL=seedance-2-0-mini-workflow
USER_REQ=<用户原话一字不差>
DATA_SOURCE=<分镜脚本绝对路径>,<MATERIAL_MAP 绝对路径>,<SHOT_REF 绝对路径>,<characters_v2/>,<materials/>
PROJECT_DIR=<项目目录>
```

- 两个 READ_SKILL 都写：`seedance-2-0-mini-workflow`（红果踩坑）+ `seedance-four-layer-prompt`（四层结构）——第零步让执行器 read_file 两个 skill 再动手（防假读，标记+真实读取成对）。
- DATA_SOURCE 全部指向项目内路径（容器挂载限制），SHOT_REF 是唯一画面依据要显式声明。

## 提示词包每镜必含结构（缺一不可，写进任务书）

1. 镜号 + 视频有效时段（精确时码，来自分镜脚本，禁改）
2. 第一层 导演意图（1-2 句人话）
3. 第二层 全局锁定（reference_images 绝对路径 + @图1/@图2/@图3 顺序 + 人物/场景/材质锁定 + 光影 + 动态强度 + 通用负面）
4. 第三层 正向补充（动作序列 + 运镜 + 手机屏处理 + 台词，回指分镜脚本原文一字不改）
5. 第四层 专属负面（分镜脚本专属负面原文 + 红果负面词）
6. 生成参数建议（duration 整数秒 + 冗余裁切策略）

## 🕳️ 时长冗余裁切策略（核心新知识，Seedance duration 只收 4-15 整数秒或 -1）

分镜镜头有效时长常为非整数（10.050s）或 <4s（2.033s），不能直接传 duration。规则：**生成整数冗余时长 → ffmpeg 精确裁切到有效时段，绝不反改分镜的 0.000—43.000 结构**。每镜在提示词包标注「生成时长 + 裁切策略 + 裁切点说明」。

火龙 8 镜参考表（可作模板）：
| 镜 | 有效时段 | 生成时长 | 裁切 |
|---|---|---|---|
| S01 | 10.050s | 10s 或 11s | 裁到 10.050s |
| S02 | 2.033s | 4s（最小） | 裁到 2.033s |
| S03 | 7.867s | 8s | 裁到 7.867s |
| S04 | 4.000s | 4s 或 5s | 裁到 4.000s |
| S05 | 6.000s | 6s | 整数正好 |
| S06 | 4.650s | 5s | 裁到 4.650s |
| S07 | 5.400s | 6s | 裁到 5.400s |
| S08 | 3.000s | **不生成** | 真实尾卡硬切，禁止提交生成任务 |

配套：整段真实素材（实拍尾卡/贴片段）一律禁止模型生成；所有后期层（悬浮 UI/金额/字幕/贴纸）禁止进模型 prompt，只保留「干净覆盖区」描述。

## 台词格式铁律（逐镜校验）

- 英文双引号 " 包裹，禁止「」、【】、（）、<>
- 单镜台词总字数 ≤20 汉字（多句按句列时码区间）
- 镜头以口播开场 → prompt 加「开头先停顿半秒，然后直接开口说台词，不说任何多余的字」，负面加「多余的话、乱语」
- 台词原文一字不改；待确认台词保留 note 不擅自定音
- 声音描述禁写「语速快」，统一「语速适中，吐字清晰」

## 硬约束（写进任务书尾部）

- 只写 staging 产出目录，禁改生产文件/重启服务/SSH 跨机
- 禁止调付费/外部 API、禁止真跑模型、禁止真提交生成任务——本任务只出提示词文本
- 台词、切换点、画面结构以分镜脚本和 SHOT_REF 为准，禁止新增/删减/改写；素材不造
- 触发词拆分写法（s-e-e-d-a-n-c-e 等），避免 kb_gate 误判

## 派活命令（与火龙先例一致）

```bash
cd <项目目录> && rm -f /tmp/prompt_pack.log && \
sg docker -c "python3 /home/ubuntu/workflow/hermes_task_dispatch.py \
  --brief briefs/prompt-pack-codex-<日期>.md \
  --project <项目目录> --target codex -- \"\$(cat briefs/prompt-pack-codex-<日期>.md)\" <项目目录>" \
  > /tmp/prompt_pack.log 2>&1; echo "RC=$?" >> /tmp/prompt_pack.log
```

- 后台跑（background=true + notify_on_complete=true），前台 timeout 会成孤儿/被杀
- 预计耗时：分镜实施 ~21 分钟，提示词规范化 ~15-20 分钟（大任务书读 skill + 逐镜展开）

## 参考

- 输出样例：火龙 staging/storyboard-taskbook-20260823/implementation/PROMPT_PACKAGE_20260823.md
- 上游分镜脚本结构：「可独立投喂 prompt」字段已含参考图绑定/人物锁定/运镜/台词/负面，规范化只补四层标注、开场停顿、时长策略、动态强度、字数校验
