# 分工体系漏洞审计（2026-08-23 claude 终审）

执行器：claude（sg-division-audit-claude-20260822.md 任务书）
落盘：`workflow/projects/xiaolu-bug-sweep/staging/sg-deploy/分工体系漏洞分析_20260822.md`（566 行，14 项漏洞）

## 审计背景

新加坡机「分工体系」（codex/claude 执行器 + 内容闸链 + attest 签字）部署后，派 claude 独立审计「还有哪些漏洞」。核心价值：两份已有修复方案都没覆盖的盲点被揪出。

## P0-1：execute_api.py 内部自带完整创作流水线（最大发现）

`/execute` 与 `/job` 内部自带创作全链：
- `node5_storyboard:211` 调 DeepSeek 出 6 镜分镜（含运镜）
- `node6_character_image:231` 硬编码「彩铅风格」生角色图
- `node8_prompts:255` 以 temp=0.3 出 Seedance 提示词
- `node9_compliance:274` 用 8 个硬编码词当合规检查
- `node11_compose:305` 进程内跑 ffmpeg

**后果**：Hermes POST 一次文案，就在「纯执行 API」名义下完成创作+质检+出片+合成全链，codex 零参与、零 attest、零内容闸。闸2.5/闸2.6 都拦不到——这条路上 prompt 从不作为文件存在。

**待定处理**（2026-08-23 拍板前）：明早第一步跑两条只读命令（生产 execute_api.py 的 md5 对比 + `entry=` 调用量统计），确定「直接下线」还是「先加过渡闸」。在 P0-1 之前收紧任何别的闸，都只是给正门换锁。

## P0-2：打包夹带闸是 WARN 不是拦截

`task_brief_gate.py:144` 的 13 词黑名单（`gate_config.yaml:13-26`）是唯一专拦夹带的闸，但 `mode: WARN`（:106）只记录不拦。本次任务书自身即样本：`USER_REQ=` 实际只有「让claude分析还有哪些漏洞」7 字，「Hermes 自由发挥」写在该行之外。正确夹带与错误夹带在闸眼里完全一样。

## P0-3：定案与 channel_gate 方案正面冲突（两份方案都没发现）

`write_attest.sh:84-95` 的 record 无 `role` 字段，创作与质检都签 `channel=codex` → 方案的 `reviewer.channel ≠ producer.channel` 判据**恒为假，一上线就锁死主链**；放宽成「有两份 attest」则 codex 连跑两次即自审通过。解法：加 `role`+`reviews`，判据改用 `token_id` 区分执行实例（token 由 dispatch 签发、O_EXCL 一次性消费，同一次执行拿不到两个）。

## P0-4：feishu_send_video.py 93 行零闸

视频主交付物完全绕过 send_gate。

## 次要项

- claude 壳 token 校验是弱实现（非原子、无白名单、无绑定——codex 壳已修的四个缺陷它全有）
- `TASK_GATE_ENABLED` 默认 0 = 校验默认关
- `/etc/hermes/render_authorized.list` 已含 2 条使火龙项目豁免 G_RENDER_READY
- confirm 无 TTL 无产物绑定（改了分镜仍算已确认）

## SG 相比广州已修好的（不重复计）

- `_HARD_ENTRIES` 让 soft 模式对三个生产 entry 永久失效
- confirm skip 被明确拒（`CONFIRM_SKIP_REJECTED`）
- 服务绑 `127.0.0.1` 而非 `0.0.0.0`

## 天行者拍板结论（2026-08-23）

1. **QC-C 质检**：让 codex 自己做（自动派 codex，不设人工门 rc=3）
2. **LIGHT 白名单豁免**：全部取消，所有项目走 FULL 完整确认流程（白名单清空=保留注释删路径行，root:root 0644 需用户终端 sudo 执行，改完重启 execute-api 验证）
