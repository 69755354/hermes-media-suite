---
name: douyin-publish-automation
description: Use when automating Douyin creator-center publish.
---

# 抖音创作者中心自动发布（Playwright/CDP）踩坑

单条命令：`publish_once.py <视频> --title T --tags "#a|#b" --task 关键词 [--publish]`，不加 `--publish` 只填不发。

## 铁律

1. **上传前必须清草稿**。发布成功后抖音把 `/content/upload` 重定向回 `/content/post/video`，页面上唯一的 `input[type=file]` 是**封面图**输入（accept 只有图片），视频 set_input_files 会等到超时。处理：URL 含 `post/video` 或找不到 `input[accept*='video']` 时，先点「重新上传」清草稿，再等 video 输入框 attached（最多 20s）。
2. **只认 `input[accept*='video']`**，禁止 `input[type=file]` 取第一个。
3. **星图任务是弹窗（.semi-modal-content），不是下拉**。点「请选择星图任务」→ 等弹窗 visible → 弹窗内按关键词找含「任务:」的行 → 取该行 `input[type=radio]` 坐标点击 → 点「确定」→ 回读占位符确认。
   任务名示例：`任务: 火龙漫剧星广-260915-激励-新码-1-优矩互动 星广 按效果结算 ...`；「激励」「免费-新码」「APP种草」包含匹配。
4. **封面弹窗里的 img/canvas 常返回 0×0**，DOM 点不中。用弹窗 bounding_box 的比例坐标点第一帧：`x = box.x + 0.14*w`，`y = box.y + 0.87*h`（1122×658 实测 228,652 命中）；再点「完成」，轮询 `[role=dialog]` 归零。
5. **封面失败必须中止**，不能 `ok=True` 兜底后继续发布——会发出默认封面且日志看不出来。发布前轮询等「封面检测中/检测中」消失。
5.2 **检测结论只在整页 innerText 里**：浮层是 fixed 定位，`offsetParent===null`，按弹窗/portal 作用域读文字永远读不到 → `counts {封面检测:0}` 误判失败。必须 `document.body.innerText` 匹配「封面检测通过」。另外：**不要在自己的选帧方法里点「完成」**，完成按钮归下游 close/readback 流程所有，重复点会让下游 `candidates {完成:0}` 直接 abort。

5.1 **封面帧只能走「选择封面」弹窗，页面上的 `verCover-*` 缩略图 `pointer-events:none`，点不动**。真实判定：页面上 8~10 个 `verCover-BgBhLS` 全在 `previewVer-*` 预览层里，`elementFromPoint` 落不到它，点了 DOM 零变化。正确路径：点「选择封面」→ 等弹窗出现（**懒加载，实测最长 12s，等待窗口给到 25s**）→ 点「封面检测」/「重新检测」→ 读到「封面检测通过 / 暂未发现封面低质问题」→ 点「完成」→ 关掉弹窗后才点「发布」。
5.1.1 **弹窗是封面编辑器，不是时间轴选帧器**：开出来后是「设置竖封面 / 设置横封面 / AI封面 / 模板 / 上传封面 / 重新检测 / 完成」这一套标签页，里面没有帧时间轴。想指定某一帧，最稳的是走「上传封面」的 `input[type=file]`（accept `image/png,image/jpeg,image/jpg`，共 6 个 file input，第 1 个是图片封面）直接 set_input_files 一张抽好的图，再点「重新检测」。
5.1.2 **检测结论渲染在 fixed 定位的 portal 里，`offsetParent === null`**，所以「modal 节点 innerText」和「按 offsetParent 过滤的 portal」都读不到结论 → 表现为 `counts {封面检测: 1}` 但 0.1s 判 failed。取结论必须读整页 `document.body.innerText`（发布页 body 只有 ~1k 字符，开销可忽略）。
5.2 **判据只认完整词**：通过=`封面检测通过`/`暂未发现封面低质问题`；失败=`低质问题较多`/`封面检测未通过`/`封面质量较低`。禁止用「异常/不正常/不通过/违规」扫整页——侧栏「违规记录」和整页「作品未见异常」会必然误伤，导致 0.1s 假失败、counts 全 0。
5.3 **counts 全 0 + elapsed 0.1 = 没找到检测控件**，此时应报 `missing` 并等待/开弹窗，不能判 `failed`。
6. **发布按钮**先等 `is_enabled()` 最多 30s，再滚动、再点。
7. **拟人化**：点击前 sleep 乘 0.85~1.35；多条之间随机 5–8 分钟（或按客户规则 ≥35min），不要固定秒数。

8. **深链 `post/video?order_id=<id>` 打开时任务已自动挂上**：抖音按 order_id 预选任务，页面渲染「任务名 + 更换/删除」，但**没有选中态控件**。此时若只认选中态就会判未挂 → 去点选择框 → `star task card not found` 直接中止。判定必须看两样同时成立：①URL host 为 `creator.douyin.com` 且 query 里 `order_id` **精确等于**本单（禁止子串匹配，`xorder_id=`/前缀都会误判）；②整页 `innerText` 含归一化任务名（NFKC + 去零宽 + 各种破折号统一为 `-`）并出现「更换」或「删除」。选择前、提交前各复核一次。
9. **发布成功回执只认这三样**：平台 `result: SUCCESS` + 作品号（work_id）+ 星图任务剩余额度减 1；作品列表回读常因采集任务失败而读到旧 JSON，`verify_published` 报 not-in-list 不等于没发出去，直接开 `creator.douyin.com/creator-micro/content/manage` 读首条标题/时间才是硬证据。

## 并发

一个 chat 同时只允许一个发布线程（单飞锁）。重复「确认」只回「正在发布中」。否则双线程抢锁 → HTTP 429 `operation in progress`，且出现两条不同间隔播报。

## 多客户（winport/远程控制面）发布

- **不设发布时段（2026-10-29 用户拍板，永久口径）**：客户说了时间就按客户说的时间发；没说就确认后立即发（首条约 now+2 分钟，批内每条隔 5 分钟）。禁止把计划排到「下一个合法窗口」，禁止向客户索要发布时段。客户机 `prepare` 自带的 windows / ≥130 分钟提前量只是历史默认值，机器人收到准备结果后必须一律用 `_mt_reschedule_item` 重排覆盖成客户时间或立即发；`require_window=False`，dry-run 的 `SCHEDULE_OUT_OF_WINDOW` 作非阻断。

- **标题 30 字必须在两处卡死**：① 机器人拟稿文本（LLM 会自称「30字」实际 33，在 reply 前用正则把标题截到 30 并回写真实字数）；② 计划标题（批量原来直接取素材文件名，32 位哈希或超长中文名会让整批报 `TITLE_TOO_LONG`）。文件名是哈希/纯英文/超 30 字时回落统一标题，不要在客户端放宽 30 字限制。
- **计划里的 `piece.platform_account_id` 必须是空字符串**：`publish_exec._verify_account` 拿它跟页面真实 `uid/sec_uid` 比对，填 `env_x:平台` 永远对不上（报「实际平台账号无法确认或与计划不一致」）。留空才会按当前登录账号自动绑定。改计划后必须用 `material_fingerprint`（schema `publish-content/3`）重算 `compliance.content_hash`，再跑 dry-run 换新 `confirm_token`。
- **publish 不能放在远程 exec 里跑**：远程 op 约 100 秒被掐断且回报 rc=0，看起来成功其实进程已死。用 `DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW` 分离启动，日志重定向到文件，靠读日志判断结果。
- **每次失败都会冻结通道**：重试前 `publish-hold-clear --channel <ch>`；`run/stage2-ledger.json` 里残留的 `RESERVED` 用 `Stage2Ledger.recycle_zombie()` 回收（只对 RESERVED 且 schema=2 有效）。远程解冻不用客户动手：`python3 projects/publish_control/remote_pc.py exec --customer <cid> --timeout 60 -- <venv python> -m agent.winport.cli publish-hold-clear --channel env_1:douyin --reason "..." --data <cust dir>`，返回 `{"cleared": true}` 才算解开。
- **封面步必须排在“等上传/转码完成”之后，且没指定封面就整体跳过**（2026-10-29 实修）：`fill()` 原顺序是 上传→填标题→**封面**→等转码，视频还在传时点「封面检测」抖音不返回结论，等待超时即 `cover is not confirmed: detect: cover.detect.result=timeout` 并冻结通道。改法：把 `_finalize_upload_evidence()`/`_wait_transcode()` 提到 `_choose_cover()` 之前；`_choose_cover()` 开头若 `covers` 全空且未开 `cover_upload`/`cover_ai`，直接置 `_cover_check_ok=True` 打印 `cover.skipped` 返回，不打开封面面板。实测 fill 跑通：`cover.skipped` + `cover.verify fallback_used:true` + `filled:true`，未点发布。**防回归**：上线前/改完必跑 `python3 projects/publish_control/scripts/check_publish_invariants.py <publish_exec.py>`，它校验“转码等待在封面之前”和“无封面就跳过、且在开面板之前返回”两条；任一被改回去直接 FAIL（拿旧版实测会失败，能复现本次事故）。
- **`NO_UPLOAD_BYTES` 多数不是草稿问题，是分片上传**：抖音把视频拆成上百个 chunk POST 到 `tos-d-*.douyin.com`，单个请求 body 永远小于本地文件大小，用「单请求 ≥ 文件大小」判据必然误报（日志特征：`requests:0 / responses:几百 / bytes:0`）。1.2.153-h1 起按 host/content-type 聚合 chunk 字节，攒够文件大小后由 `_finalize_upload_evidence` 落一条 `chunked_aggregate` 合成记录。真草稿复用同样报这个码，特征是页面停在 `post/video` 且完全没有上传请求，先清草稿再跑。
- **弹窗卡片选不中≠任务下架（2026-10-29 实修）**：现象 `xingtu.cards count=4` 后报 `star task card did not become selected`。两个真因：①`dispatch_event("click")` 是不可信事件，label 默认激活不触发、`semi-radio` 永远不 checked → `click_picker_element` 必须先 `item.click()`（真鼠标）再退回 dispatch；②搜索框过滤生效后列表重渲染、`data-xt-idx` 重新编号，点击前捕获的 index 会指向别的卡或空节点 → 点前 sleep 1.5s 用 `matching_rows()` 重取一次 index，失败再重取重试一次。排查时先用 `collect_xingtu`/picker DOM 看真实卡片数，别把 0 卡当成订单没了。
- **星图「同名任务」去重必须带视频指纹，不能用类别词判重**（2026-10-29 实修）：机器人下发的 `task_name` 是类别词（`APP种草`/`免费-新码`），本地账本若只比 task_name/order_id，第 1 条发成功后同批第 2 条起全部误报 `XINGTU_DUPLICATE_LOCAL`（现象：本批第 2 条「本次发布未确认成功」，stderr `xingtu.dedup result:blocked matched:APP种草`）。正确判定：账本条目带 `media_sha256`，「同一任务身份 + 同一视频指纹」才算重复；历史无指纹条目只在 order_id 精确相等时拦截。改 `xingtu_tasks.find_used_task/append_used_task` + `publish_exec.preflight_xingtu/record_xingtu_publish` 两处调用。
- **热修程序文件会被启动链完整性拦死**：`MANIFEST.json` 校验 141 个启动链文件，改过 `agent/winport/*.py` 后发布直接 `INTEGRITY_FAILED`（抓数不受影响）。必须同步重算该文件在 MANIFEST 里的 `bytes/sha256`（顺带 bump version + 同步 VERSION 文件与其清单条目），静默重启 `runtime/pythonw -m winport --data <data>`，再读 `run/integrity.json` 复核 `ok:true / modified:[]`（并确认 healthz 版本号已变）才算修好。
- **publish 的计划时间窗口是 `0 <= now - schedule_at <= 600s`**（`publishing=True` 分支）。`dry-run` 默认走 `min_lead_minutes=130` 会报 `too_soon`，所以别拿 dry-run 产出给 publish 用：直接 `build_preview(..., publishing=True)` 生成 preview 文件和 `confirm_token`，同一脚本里立刻 publish，token 才不会因 schedule 变动失效。
- **改排期只能走机器人，客户机不接 schedule 命令**（`agentpoll.ALLOWED_KINDS` 只有 publish/collect/report/status）。机器人侧 `_mt_change_schedule` 的可行路径：在客户机重写 `plan.schedule_at` → 重跑 dry-run 换新 `confirm_token` → 存回 `mt_batches`；已确认(`scheduled`)的批次同样适用，排期线程按新时间下发。支持「改到明天11点」「第2条改到20:30」「全部改到…」。
- 排期下发必须**到点之后**才执行（客户机只接受计划时间之后、10 分钟内）；提前下发会报 `SCHEDULE_OUT_OF_WINDOW`。机器人排期线程原来把计划改到 now+90s 后立刻 enqueue，实际比计划早 67s，必然被拒——重排后必须等 `schedule_at` 到点再下发。
- **`封面检测` 不能被发文助手的 `重新检测` 冒充**：`_cover_lookup` 是全文档扫描，发文助手侧栏也有「重新检测」，旧逻辑把它当成「封面检测已点过」，于是永远不点真正的「封面检测」，空等 90s 报 `cover.detect.result=timeout`。修法：`重新检测` 只有在封面弹窗作用域内（`scoped>0`）才算已点击，否则忽略。
- **`_run_cli` 必须显式 `encoding="utf-8", errors="replace"`**：agent 环境带 `PYTHONIOENCODING=utf-8`，子进程输出 UTF-8，父进程 `text=True` 默认按 cp936 解码 → reader 线程崩，`proc.stdout/stderr` 变 None，控制面只收到 `exit=2` 和空诊断，看起来「失败但没原因」。
- **`published=False` 不等于没发出去**：页面 `signal=success_toast` 且 URL 跳到 `/content/manage` 时作品已发布，只是没抓到 work_id。回读管理页首条标题+时间（`creator.douyin.com/creator-micro/content/manage`）才是硬证据，禁止只凭 work_id 判失败。

## 已验证成功路径（2026-10-13 真机，唯一一次带星图任务的真实发布）

- 记录：账号 douyin-pilot-001（漫半拍），19:41 点了唯一一次发布，作品管理页出现该条「审核中」，作品号 `7696116152744922410`（后续只读回读确认）。执行器当轮自判 UNKNOWN 是因为管理页回读没加载完，不是没发出去。证据在 `/home/ubuntu/workflow/projects/publish-worker-deploy/stage2-exec/`：`REPORT_PUBLISH_1.md`、`REPORT_PUBLISH1_READBACK.md`、`REPORT_ROUND5B.md`。
- 星图选任务的可用做法（真机验证过，不是推测）：①任务名按全名写死并与计划**一字不差**比对；②`selected_name` 从回填行 `[class*=star-wrapper]` 的「任务: 」到「 客户: 」之间取全文，别读被 CSS 截断的 `task-name` 元素；③每轮用「弹窗是否真的关闭」验收，失败按任务名重新定位卡片重试，上限 3 次，重试仍关不上判红；④选中星图任务后发布时间被平台锁成「立即发布」且整块 disabled，不要去点定时单选。
- **未验证**：星图后台侧的投稿状态读回从未真跑过，10-13 只拿到抖音侧作品号；「星图剩余额度减 1」不能当既成事实，没回读就标 UNKNOWN。
- **迁移纪律**：这套是 Mac 独立执行器（stage2-exec）验证的，Windows 客户机 1.2.15x 是另一套实现。任何客户端重写发布链路，必须把上面 4 条做法等价移植并纳入 `check_publish_invariants.py`，否则就是「文档里有、代码里没有」，回归必然重演。

## 改客户端发布链路的三条硬规矩（2026-11-03，反复踩过后定）

1. **先抓真机 DOM，再改代码**。改 `publish_exec.py` 任何选择器/回读契约前，先 `connect_over_cdp("http://127.0.0.1:9224")` 连客户机现有浏览器，把弹窗和表单的真实结构 dump 出来（卡片类名、`data-xt-card-id`、radio 的 label、`更换/删除` 在哪一层、挂载后名字是否被截短）。禁止照文档或日志猜——10-29 已写过「别再猜选择器」，2026-11-03 又因为没先抓 DOM 白绕两轮。
2. **两条选择路径都要改、都要验**。选星图任务有 publish 和 fill 两条分支：`publish` 走 `_xingtu_select_fill_row(wait_for_selection=True)` 有 radio 兜底；`fill` 传 `wait_for_selection=False`，旧代码点完卡片不看 radio 就 `return fresh or current`，把「没选中」当成功。点选顺序固定 `label.semi-radio` → `input[type=radio]` → 卡片，点完必须读到 `checked`（或弹窗已关）才算选中，然后点弹窗「确定」。改一条分支不算修完。
3. **挂载回读按真实表单结构写**。挂上后表单是 `card-container-*` 里放 `任务:`，`更换`(`span.reload-*`)/`删除`(`span.delete-*`) 在卡片外面一层的 wrapper；显示的是**截短名**（不含「奖金无上限落地页…」后缀）。契约必须：可见 + 非 `.semi-portal/[role=dialog]/.semi-modal` + 非 `creator-layout` + 文本里 `任务:` 恰好一次 + 向上 3 层找到同时含更换/删除的 wrapper + 页面「请选择星图任务」占位消失；名字比较用「全等 / 互相包含」。`readback_via` 正解是 `form_card`。

上线顺序（缺一步不算修好）：

```
python3 scripts/check_publish_invariants.py <publish_exec.py>     # 第7/8条守上面两条
python3 tools/build_bundle.py build --root . --version X --out .  # 首跑常报 self-binding size changed，重跑一次即过
python3 scripts/predeploy_gate.py --build-dir <包目录> --customer <cid>   # 断言+版本+现网哈希三合一
```

部署后必须真机跑一次 fill，验收 `filled=true` 且 `xingtu.readback ok=true / readback_via=form_card`；真机发布验收仍是「真发出一条带星图任务的」，fill 成功不等于发布验收。

## 日志

每步一条 `PS {"step":...}`：`uploaded/title/tags/declaration/star_hit/star_task/cover_dialog/cover_frame/cover/publish_ready/publish_clicked/published`。`star_task` 或 `cover` 为 `ok:false` 时不要继续往下发。
