---
name: ai-image-gen-strategy
description: AI生图选型codex vs Seedream。触发:生图/图生图/比基尼拦截/图假僵硬。
---

# AI 生图模型选型与实操

多模型（codex gpt-image-2 / Seedream 5.0）生图策略，2026-08-09 实测定案。

## 生图流程（2026-08-09 P1-6 提速省钱定案）

**标准预览 → 确认 → high 终稿**（不再默认所有候选 high）：
1. 首轮：**quality=medium 出 1 张预览**（快、便宜），给用户/客户看方向
2. 确认方向后：**quality=high 出终稿**（细节拉满）
3. 场景复杂/客户已明确要高清 → 直接 high（跳过预览）
- 收益：候选阶段不再烧 high 的钱和时间（high 单张 2-4 分钟 vs medium 快一半）
- 已完成的对比测试不受影响，本规则约束「新开生图任务」

## 模型对比（实测结论）

| 维度 | codex (gpt-image-2) | Seedream 5.0 (火山) |
|:--|:--|:--|
| 通道 | OpenAI 直连（新加坡机通） | 火山 ARK，新加坡机需走广州 relay |
| 锁脸一致性 | ✅ 高（参考图垫图稳） | ❌ 低（五官会飘，需加强约束） |
| 真实摄影感 | ❌ 假（皮肤均匀、精修感、摆拍感） | ✅ 真（逆光柔焦、抓拍感、胶片氛围） |
| 动态姿势 | ❌ 僵硬（奔跑像机器人扭） | ⚠️ 一般 |
| 人脸风格 | 偏中国面孔 | 偏混血网红脸 |
| 安全墙 | 严格（比基尼=sexual 拦截） | 宽松（比基尼一次过） |
| 尺寸 | 最大 8K/3840px | ≥368万像素，如 2160x3840 |

## 选型规则（用户 0809 最终定案：**生图首选 codex**）

- **默认生图 → codex**（用户明确「先把codex升级成首选」）
- **quality 选择**：按 P1-6 流程——首轮 medium 预览（快/便宜），确认方向后 high 终稿；场景复杂/客户明确要高清 → 直接 high。**「quality=high 必带」是终稿规则，不是首轮规则**（避免预览阶段烧 high 的钱）
- **Seedream 仅作备选**：简单真实感场景（海边/探店/生活照）可切，复杂场景容易跑偏
- **复杂/风格化场景（仙侠/特效/商业定稿）→ codex 稳赢**（实测仙侠版：Seedream 把小鹿画成男性，codex 锁脸+构图+光影全胜）
- 动态姿势：AI 静态生成器不擅长奔跑/回眸等瞬时动态，优先「站在浅水中回眸」这类静态构图，动态感靠环境暗示
- codex 出图后如用户质疑「假/僵」，主动对比两模型让用户定——但默认先 codex
- **⚠️ codex 图生图「3D 三视图 → 真人写实」拉不动（2026-08-23 火龙男主实测，老板「这个仿3d风格的人看起来很假。还是要搞成写实的」）**：gpt-image-2 把 3D 角色图转真人写实，产出仍是 3D 渲染/CG 感——皮肤光滑均匀、无毛孔纹理，照片级真实感 codex 静态图达不到（与文生图偏假同一根因）。**不达标就不交付**，如实报告「还是 CG 感」，别拿预览图当成功。要照片级静态真人写实可切 Seedream（真实感好但锁脸弱，需接受五官漂移风险），或等出片看 Seedance 从彩铅还原的效果由老板定。
- **自动降级铁律（2026-08-09 用户定案）**：codex 无法完全按提示词执行 → 自动换 Seedream，**不用问用户**。触发条件：安全墙拦截（比基尼/泳装/贴身 sexual）、连续失败、超时、出图不达标。其他节点同理：首选通道执行不了就自动切备用通道，不阻塞不询问——用户要的是「跑得动」，不是「先问一下」

## codex 生图参数（gpt-image-2）

- `--size`：auto 或自定义（如 2160x3840），最大 8K/3840px，默认 auto 约 941x1672 竖版
- `--quality`：**low/medium/high/auto，默认 medium——实测 high 明显改善动作僵硬**（「头扭得没那么变态」），皮肤细节也更好
- `--n` / `--background` / `--output-format` / `--output-compression` / `--augment`

## OpenAI 安全墙（重点坑）

- 「比基尼」触发 sexual 拦截，**连续两次都被拒**（input 和 output 阶段都拦）
- codex 自己换「运动泳衣」也被拦；「高领全覆盖连体泳装」能过但出图保守
- 要性感泳装 → 换 Seedream（火山宽松）
- 拦截错误特征：`safety_violations=[sexual]`、`moderation_blocked`

## 图生图（img2img）实操

用户定稿模板（7/24 最终版）+ 小鹿参考图路径见 `references/img2img-template.md`：
- **图生图不写五官文字**，面部靠参考图锁定
- 空变量直接删除整条
- 人脸漂移兜底句：「保持参考图人物面部五官、脸型基础特征不变」
- 参考图：`workflow/projects/xiaolu-img/assets/xiaolu_sheet.jpg`（2278x1280，豆包三视图设定图）

> 📎 本地生活探店短视频方法论（知识库必读/共情六层/素材规划/合规软化）见 `references/local-life-short-copy.md`——写探店短文案、生图素材分配前先读。

## 角色图「实景融合」技巧（2026-08-09 茗希项目实测）

客户要「出镜人设融入真实门店」时，**不要生成白底角色设定图**，用实景垫图做环境融合版：
- 命令：codex exec `-i 实景1.jpg -i 实景2.jpg`（多张实景做场景参考）+ 提示词写「以附上的实拍图为场景参考，角色自然站在高端门店室内」
- 效果：角色在真实环境里（粉色按摩床/纱帘/木质地板），电影级光影，浅景深，高端精致感
- codex 会自动加专业控制词（avoid plastic skin/beauty-filter/exact celebrity likeness/low-end clinic look 等），保留即可
- **季节感要主动问/确认**：客户说「夏天」→ 换夏季穿搭（白色方领短袖/牛仔短裙/小白鞋）+ 明亮夏日自然光，重生成一版
- 成品落 `projects/<项目>/outputs/` 目录（不是 assets/，assets 只放客户原始素材）

## 探店实景高端化 + 服务过程垫实景（2026-08-09 用户纠正×2）

**① 客户实景照直接用于视频会太「生活化」，必须 AI 高端化处理：**
- 提示词核心：**场景结构 100% 保留原实拍**（床/柜台/布局不变，客户到店能对上），只升级光影/质感/氛围（暖色自然光/光线层次/材质光泽/电影级摄影感）
- **客户给几张实景就处理几张，漏一张=漏一个镜头场景**（茗希客户给了理疗室/服务区/美容室 3 张，我只处理 2 张被纠正「实景图有3张吧」）
- 分镜素材分配时逐镜核对：哪些镜用哪张实景，别让实景躺着没用

**② 探店视频的「服务过程/体验」镜（按摩/理疗/护理），人物必须在真实门店实景里：**
- ❌ 不能垫 AI 想象的高端背景（客户到店对不上 = 探店假）
- ✅ 双参考图：`-i 高端理疗室实景 -i 角色参考图`——甜妹俯卧在**真实粉色按摩床上**，理疗师只露手部做按摩（保健按摩过程，非医疗治疗）
- 合规细节：只拍手部按摩动作，不出现针/艾灸/仪器等医疗器材；理疗师不露脸
- **「坐着放松」的空洞体验镜=废稿**（用户纠正「你没有服务过程谁知道你干嘛的」）——探店视频必须有服务过程，观众才看懂店是干嘛的

## 明星脸需求 → 风格化处理（2026-08-09 用户定案）

客户说「想要像XX明星那种」时，**按「XX风格」处理，不直接复刻明星脸**：
- ✅ 「王心凌风格」= 甜妹娃娃脸、圆眼带卧蚕、甜美笑容、空气刘海、邻家精致感（借鉴气质，不点名明星）
- ❌ 直接提示词复刻明星长相 → 肖像/版权风险 + AI 画明星脸易被平台识别拦截
- 落地：角色图提示词写「X风格甜妹」+ 风格特征描述，不写明星姓名；生图参考图仍锁客户确认的人设脸
- 跟客户确认时主动说清：「我们按风格化出，不直接复刻明星脸（安全）」——客户通常接受，若坚持要完全像则先提示风险再走

## 复杂风格化场景

仙侠/特效/战袍等复杂场景的实测对比、可复用提示词、codex 对比方法 → `references/complex-scene-generation.md`

## Seedream 调用要点（新加坡机）

- 必须经广州 relay：`http://127.0.0.1:8899/upload?url=<ARK URL 编码>`
- 模型：`doubao-seedream-5-0-260128`
- size 必须 ≥368万像素（2160x3840 等），否则 InvalidParameter
- 图生图传参考图：`image_list: [{"image": <b64>}]`，body 写文件再 `curl --data-binary @file`（b64 太长会 Argument list too long）
- 下载图片：relay GET 转发（TOS 只认 GET，POST 会 412）
- 详见 `singapore-guangzhou-relay` skill
- **⚠️ 文生图提交三步坑（2026-08-19 周哥彩铅图实测，血泪）**：
  1. **seedream_gen.sh 直连 ARK 会 HTTP 000**（新加坡机直连不通）——必须改走 relay：`curl -sS -X POST "http://127.0.0.1:8899/upload?url=<urlencode(ARK生成endpoint)>" -H "Authorization: Bearer <ARK_KEY>" -H "Content-Type: application/json" --data-binary @payload.json`，成功返回 200 + `data[0].url`。
  2. **payload 生成脚本 stdout 别混入 JSON**：`python3 - <<'PY' > payload.json` 里 `print("ready")` 会写进文件首行 → ARK 报 `could not parse the JSON body`（InvalidParameter）。生成脚本只 `json.dump` 不 print；提交前先 `python3 -c "import json; json.load(open('payload.json'))"` 校验。
  3. **TOS 下载必须带完整签名 URL**：Seedream 返回的 url 带 `X-Tos-*` 签名参数，整串（含 query）经 relay GET 才 200；只传路径（不带签名）→ TOS AccessDenied（EC:0003-00000015）。签名 URL 里 `&` 要 urlencode（`quote(url, safe='')`）。下载命令：`curl -sS -o out.jpeg "http://127.0.0.1:8899/upload?url=<urlencode(完整签名URL)>"`，`file out.jpeg` 确认 JPEG 再落盘。
- **新人物彩铅三视图 = 文生图一步到位（2026-08-19 周哥实测，用户「不用生成四张，生成一张就行了」）**：不做「写实定妆 4 张挑 1 → 图生图转彩铅」两步；直接文生图一张「正面/四分之三侧面/背面+脸部特写」的彩铅素描（白底 9:16，size 1728x2304），人物全部特征写进 prompt。生成后 vision 核验：三视图齐全/年龄气质/白发胡茬/服装/彩铅非照片非卡通/白底/无五官漂移。
- **彩铅三视图的「还原」发生在 Seedance 出片时，不是生图阶段图生图（2026-08-23 火龙男主，用户「彩铅三视图是在生视频的时候还原」「你出真人写实三视图是干嘛用？」后固化，血泪）**：彩铅三视图就是出片 @图1（Seedance 生成时从彩铅还原真人写实，prompt 写「从彩铅还原真人写实」）。**不要**额外图生图「从彩铅还原成真人写实预览图」当出片参考——那是多余产物；出图前先想清楚这张图在链路里的用途，用户会当场质疑「你出XX是干嘛用」。真人写实预览图只用于给用户确认形象方向（非必需），出片链路不需要。
- **角色三视图排版必须对齐原参考版式（2026-08-23 火龙男主，用户「三视图是这个排版吗」后固化）**：codex gpt-image 默认把三视图排成竖版 2x2 四宫格（左上特写/右上正面/左下侧面/右下背面），但原参考图（如 3D 三视图）常是**横版 1 行 4 列**（左列脸部特写占满整列高 + 右侧正面/侧面/背面全身横排）。生成前先 vision 看原参考图版式，prompt 显式写排版（横竖版/列数/特写与全身位置/尺寸如 2304x1728 横版），出完自检排版一致再发用户。
- **三视图标准排版规格（2026-08-23 联网查证 + 用户确认，出图 prompt 直接照抄）**：16:9 横版（尺寸 2560x1440，勿用 4:3/竖版）——左 1/3 面部特写（头顶至锁骨，突出五官/发丝细节）+ 右 2/3 横向并排 正视图 | 正侧视图(90°) | 后视图 三个全身；三视图严格等高、人物大小一致、脚底对齐同一基线；纯白背景。codex 生成后 vision 逐项核验：16:9 比例/特写位置/三视图顺序/等高/基线/角度，任一不对就重出。
- **⚠️ 成功响应没有 code 字段（2026-08-22 实测：图已生成但脚本判错没下载）**：ARK `images/generations` 成功响应直接是 `{"model":..., "created":..., "data":[{"url":"https://ark-acg-cn-beijing.tos-cn-beijing.volces.com/...","size":"1440x2560"}], "usage":{...}}`——**没有 `code` 字段**。脚本 `if resp.get("code") != 0: raise` 会把成功当失败（code=None），图已生成（钱已扣）但没下载。**`data` 是 list 不是 dict**——判断必须兼容：`d = resp.get("data"); items = d if isinstance(d, list) else (d or {}).get("image_list") or []`（写 `data.get("image_list")` 对 list 会 AttributeError）。files 上传成功响应同理：顶层直接 `{"object":"file","id":"file-xxx"}`（不是 `data.id`），取 `resp.get("id")`。
- **⚠️ 新加坡机直连 TOS 下载不通时走广州机中转（2026-08-22 实测）**：生成的图 URL 在 `tos-cn-beijing`，新加坡机 curl 直连可能超时/失败（网络不通，跟调 ARK 一样）。可靠路径：**经广州机 curl 下载再 scp 回**（广州能访问国内 TOS）：
  ```bash
  timeout 60 ssh -p 2222 ubuntu@127.0.0.1 "curl -sL -o /tmp/图.jpeg '<TOS URL 完整带签名>'"
  scp -P 2222 ubuntu@127.0.0.1:/tmp/图.jpeg ./
  # scp 多个远程文件每个都要带 host: 前缀——只写一个 host: 其余路径会被当本地文件
  scp -P 2222 ubuntu@127.0.0.1:/tmp/a.jpeg ubuntu@127.0.0.1:/tmp/b.jpeg ./
  ```
  签名 URL 有效期 86400s，超时重新生成。

## ⚠️ AI 生成文字/UI/界面 = 硬边界（2026-08-11 Claude 审查实测）

**结论：AI 生成器（codex gpt-image / Seedream 都一样）无法稳定生成可读中文文字和真实 App 界面。** 视频里出现「手机 App 素材区」「商品页截图」「弹窗文字」等需要可读文字的镜头：

- ❌ 不要交给 AI 生成——**中文必然乱码**（字形涂鸦/不可读/图标混乱/缩略图重复）
- ✅ 用**真实截图**替换——把手机 App 真实界面截图垫进画面/合成时贴上
- 审查发现的典型 AI 生成 UI 崩坏清单（Claude 审 c_01/c_03 帧）：
  - 文字全乱码（"分/办"字形涂鸦）、图标混乱（灰色挂锁乱摆）
  - 缩略图重复同一头像、占位块看不出含义
  - 缺标题栏/返回按钮，孤立漂浮控件
  - 手机物理错误：两侧都有实体按键、悬空无投影、屏幕亮着但不对人物打光
  - 与人物重叠/压肩、被画幅裁切、安全区被字幕压

**判稿标准：** 镜头里有「需要可读文字/真实 UI」的元素 → 素材映射阶段就标「真实截图替换」，不进 AI 提示词。AI 画 UI 只会浪费时间返工。

## ⚠️ codex 文生图三视图极易跑偏（2026-08-25 火龙实测，血泪）

**codex gpt-image-2 文生图出"真人三视图"时，prompt 不够明确会导致三类跑偏：**

1. **性别跑偏**：要求男性，出成女性（prompt 里没写清 "male" 或被参考图干扰）
2. **排版跑偏**：要求三视图（左1/3特写+右2/3三全身），出成三格连环画/竖版四宫格
3. **风格跑偏**：要求照片级写实，出成 3D/CG/动漫风格

**强制流程：**\n- prompt 里**显式写**：性别（male/female）、排版（"left 1/3 facial close-up + right 2/3 three full-body views front/side/back"）、风格（"photorealistic, NOT 3D, NOT CG, NOT anime, NOT illustration"）\n- 皮肤质感必写：`natural skin texture with visible pores, NOT plastic, NOT smooth CG skin`（不加会被 codex 出成精修假皮肤）\n- 多角色任务每个 prompt 末尾写：`This character must look DIFFERENT from any other character - distinct face, hair, and clothing`\n- 纯白背景显式写：`Pure white seamless background, no text, no watermark, no logo`\n- 生成后**必须自检**：性别对不对、排版是不是三视图、有没有手部畸形/五官扭曲、写实还是CG\n  - 首选 codex 批量看图（`-i 图1 -i 图2 ...` 一次喂全部，比逐张 vision_analyze 快且可靠）\n  - vision_analyze 可能静默失败（返回 `success:true` 但 "I don't see any image"），不能只看 success 字段\n- **不盲提交**：自检不通过就重出，别直接传给视频生成API（0825翻车：盲提交给快乐马r2v后出片人物完全错误，浪费一次付费生成）\n- **批量并行出图**：6+张图用 bash `&` + `wait` 并行跑 codex exec，比串行快 3-5 倍（详见 `codex-image-vision` skill 批量并行生图章节）

**实测翻车案例（0825火龙）：**
- prompt 只写了 "young male, three-view sheet" → 出成女性雨夜三格连环画
- 修正后加了 "male, left 1/3 close-up + right 2/3 front/side/back, photorealistic NOT 3D NOT CG" → 出成正确男性三视图但偏小（1672×941，非标准2560×1440）
- 用户批"太丑"→ 重出。codex静态图的写实度天花板低于Seedream，但Seedream锁不住性别（彩铅男主能出成女性）

## 角色三视图 + 场景图提示词模板（2026-08-25 火龙V20实测全过）

6张图（3角色三视图+3场景图）codex并行生成，全部通过自检。模板含关键成功要素、可复用prompt模板、实测变量示例、并行脚本结构和批量vision自检方法。

→ 详见 `templates/three-view-and-scene-templates.md`

核心要点：
- 角色三视图prompt必须显式写：性别、排版（左1/3特写+右2/3三全身）、风格（photorealistic NOT 3D NOT CG）、尺寸（2560x1440）、皮肤质感（visible pores NOT plastic）
- 多角色必须写区分句：`This character must look DIFFERENT from any other male character`
- 场景图必须写：尺寸（1440x2560 9:16）、空间方位、光线方向、禁止项（NO people NO text NO logos）、UI留白区
- 并行生成：`echo "prompt" | codex exec ... &` × N + `wait`
- 批量自检：最多6张图一次喂 `codex exec -i img1 -i img2 ... -i img6`，vision_analyze对本地PNG可能全部失败

## 失败重试策略

- codex 超时（420s 无输出）→ 后台方式跑 + 日志落盘 `/tmp/*.log`，检查目标文件是否生成
- 安全墙拦截 → 换措辞/换模型，不硬试
- 视觉分析（vision_analyze）超时 → 用 codex `-i <图>` 看图（需 sandbox_mode=danger-full-access + stdin 传 prompt）
- **vision_analyze 对本地PNG可能全部返回"no image attached"**（2026-08-25实测6张全部失败，返回 `success:true` 但正文说看不到图）→ 直接用codex多图看图替代，一次最多喂6张

## 计费：每批生图出完必须立刻记账（用户 2026-10-30 要求）

- 口径：Seedream 5.0 = **0.22 元/张**，一次调用出一张计一张；测试图、重出图也算（交付张数 ≠ 调用张数）。
- 记账位置：`/home/ubuntu/workflow/projects/huolong-guide/ledger/消耗台账.csv`（与视频同一张表）。
- 命令：

```bash
python3 /home/ubuntu/workflow/projects/huolong-guide/ledger/log_image_cost.py \
  --name "项目名-参考图" --project <项目目录名> --count <调用张数> \
  --res 1728x2304 --note "A1 12/B1 11/C1 11，已发群"
```

- 顺序：**先记账再发群/交付**；账没记完不算收工。
- 复核：写完另起进程读回最后一行，核对张数、单价、金额，别只看写入回执。
