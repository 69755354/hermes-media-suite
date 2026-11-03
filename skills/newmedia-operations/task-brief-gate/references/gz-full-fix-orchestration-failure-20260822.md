# gz-full-fix 编排失败复盘（2026-08-22，round1→round3 完整）

## 场景

天行者要求「claude 分析 → codex 验收 → codex 实施 → 无人值守编排」，编排脚本 v2 跑完后 codex 实施 dispatch rc=1 被卡点拦截，脚本 break 直接跳部署，部署空转（staging 无产物），整体「共迭代 0 轮」结束。后续按「codex 改 → claude 验 → 循环到 PASS」迭代到 round3。

## 用户连续四轮纠正（核心认知链）

| 轮次 | 用户原话 | 纠正了什么 |
|---|---|---|
| 1 | 「a这么做没意义」 | 加 READ_SKILL 标记骗过卡点 = 卡点还是坏的，跑通一次是自欺欺人 |
| 2 | 「c.没用，他之前就是用这个方法骗过去的」 | 让执行器修卡点 = 把闸门钥匙交给被闸的人，是被用过的后门 |
| 3 | 「他可以骗卡点每次都是运维」 | SKIP_KB_GATE=1 + SKIP_REASON=运维 谁都能写，字符串卡点对执行器零防御 |
| 4 | 「他可以自己伪造skip把」 | 执行器能自己伪造任意字符串，字符串检查永远拦不住能生成字符串的执行器 |

**结论（用户定案）：**
- 卡点防护只能放在执行器够不到的地方：容器隔离（产物只落 staging）、部署环节人工（搬运/备份/重启）、部署前验证（md5 核对/py_compile/可回滚）
- 业务真闸（如出片确认闸硬模式：没有用户原话确认 = 物理出不了片）才是管钱袋子的闸
- 不要在字符串卡点上花时间设计方案，直接干正事（实施 → 验收 → 人工部署）
- 用户「我说了全部弄完」= 放开文件边界，按方案完整交付面一次补齐，不是执行器自定最小集

## 卡点误伤实录（两次 BLOCK）

1. 第一次：brief 含「出片确认闸」→ kb_gate_hard.py 关键词「出片」触发 Seedance skill 加载检查 → BLOCK
2. 第二次：加 `SKIP_KB_GATE=1 + SKIP_REASON=运维` → `has_content_intent()` 命中「分析/出片」→ BLOCK「内容生产任务不允许 SKIP 豁免」

**正确过闸路径（30 秒本地预检）：**
```bash
python3 ~/.hermes/scripts/kb_gate_sg.py -f <brief文件>   # 期望 KB_GATE:PASS + RC=0
```
项目已有 `guard/kb_checked.json`（checked=true + read_files 实读清单）时走正常知识库路径 PASS；缺 seedance 标记就补 `READ_SKILL=seedance-2-0-mini-workflow` 标准字段。不要用 SKIP。

## 前台 timeout 杀进程组（跟 codex 孤儿坑相反）

- codex：容器子进程杀不死 → 成孤儿，重发 = 并发互覆盖
- claude：宿主机子进程 → 前台 timeout 连进程组一起杀 → 验收产物丢失
- 特征：`/tmp/claude_remote_output/claude_remote_*.log` 只有一行 `[claude-wrapper] 开始` 没有 `完成 EXIT=`
- 防：派 claude 长任务一律 `background=true + notify_on_complete=true`

## 编排脚本部署空转假完成

`dispatch_codex_impl || break` → codex rc=1 → break → 部署函数两个 if 都没进（staging 无产物）→ 打「部署阶段完成」。验证方法：SSH 广州机 `ls execute_api.py*` 无 autofix 备份 + `systemctl show execute-api -p ActiveState` active（服务没动过）。

## claude 验收发现的 P0/P1 模式（round1 产物）

1. **P0：新增校验绕过灰度开关**——read_files 含 SKILL.md 绝对路径校验不看 mode，WARN 期也拦 → 违反「WARN 不拦」验收标准
2. **P1：空断言**——TEST_RUN 读的路径在新加坡机不存在（广州机实测存在！）→ 断言恒不触发、fail-open
3. **P1：调用方可写降级开关**——SKILL_CONTRACT_MODE 可置 OFF、审计可重定向 /dev/null = 静音通道
4. **P1：共享逻辑内联**——方案点名要抽 skill_contract.py 共享模块，codex 因 4 文件边界内联进 kb_gate_hard.py → 接入点无法复用

**验证方法学（claude 做的对的部分）：** 只读验收、在 /tmp 用 staging 副本 + 模拟 subprocess.run 返回实跑断言（不发网络请求）、15 条断言逐项实跑核对、每项给「与方案一致 ✅/❌」、夹带核查（只允许改的 4 文件 + mtime 异常文件备案）。

## round2 验收：修 P2 引入的两个新 P0（同型错误：新拦截面绕过灰度）

修完 round1 的 P0/P1 后 claude 复验，**旧问题全好，但修 P2 时引入两个新 P0**——与 round1 P0 是同一类错误换了位置：

1. **P0-1：TASK_TYPE 白名单硬 BLOCK 绕过灰度 + RC 传递叠加**——task_brief_gate 白名单判定在 mode 读取**之前**直接 return BLOCK（rc=2）；round2 又把三个执行壳的 `exit 0` 改成传真实 RC。两个正确改动叠加 ⇒ G0 观察期（mode=WARN）一切无 TASK_TYPE 的任务（含纯运维）三通道全线 rc=2 拦死。教训：**放开 RC 传递前先查所有硬 BLOCK 路径是否受 WARN 保护**；「让 RC 真传出去」这种看起来正确的改动，会激活之前被 `exit 0` 焊死的所有硬拦截。
2. **P0-2：删旧正则后强制力倒退**——旧闸 `if re.search(出片|Seedance|视频生成...)` 按**措辞**触发 rc=1；新契约按 **TASK_TYPE marker** 触发、无 marker 任务回落全局 WARN ⇒ G1 切 `出片: BLOCK` 后，「写『生成视频』但不写 TASK_TYPE=出片」的任务书反而比改造前更松（rc=0）。教训：**触发条件从「措辞」切到「marker」中间必须留过渡期并联**（措辞兜底正则 + `__missing__`/`__unlisted__` 兜底键），否则机制升级变成强制力倒退。

另两个 P1：
3. **P1：claude_remote_wrapper.sh 无广州基线被整文件重写**——inputs 只给了 3 份广州基线，没给 claude_remote_wrapper.sh，codex 就交了一份 50 行全新文件要求覆盖广州 120 行生产文件（token 层/attestation/并发 slot 全被删）。这是跨机基线事故（2026-08-21 已记）的重演：**部署前必须 scp 目标机真实文件回 inputs/ 当基线，按逻辑移植（只补两段）而非整文件覆盖**；验收时用「方案记录行数 vs 产物行数 vs 本机同名文件」三向对比抓出整文件重写。
4. **P1：同行 marker 证据剥离口径不一致**——解析支持同行多 marker，但证据剥离用整行删除 ⇒ 同行写法把其余 marker 值一起删、与分行写法结论不一致。教训：同一套 pattern 解析和剥离必须同口径。

## round3 修正方向（已执行）

- P0-1：白名单结论进 errors 走统一 mode 判定，G0 期 WARN 放行留审计；回归断言「mode=WARN 下无 TASK_TYPE 的纯运维任务经三通道任一 rc=0」
- P0-2：保留措辞兜底正则 + `per_task_mode.__missing__` 兜底键；回归断言「G1 下含出片措辞但无 marker 的任务 rc=1，G0 下同任务 rc=0」
- P1-1：先 `scp 广州真实 claude_remote_wrapper.sh`（120 行，MD5 8038938d...）回 inputs/，round2 的 50 行作废，基于基线只补 brief-gate RC 传递 + kb_gate 两段
- P1-2：剥离改「只删 marker 键值对本身」与 _marker_lines 同一 pattern；断言同行=分行 errors 逐条相等
- P1-3：mtime 校验只对知识库文档生效，SKILL.md 证据条目豁免（改契约 ≠ 没读过 skill 正文）
- P2-1：__pycache__ 真删（round2 声称已清实际没清，自证失真）+ S0 加 `find <deploy包> -name '*.pyc' | wc -l` 必须为 0 的实际检查命令

## 跨机部署派活铁律（本会话强化）

1. 任务书要求改目标机生产文件（shell/代码/配置）前，**先 scp 目标机真实文件回项目 inputs/** 当基线，MD5 记入任务书
2. 任务书写「基于基线移植，禁止整文件重写；diff 确认既有逻辑（token 层/attestation/并发 slot）全部保留」
3. 验收时三向对比：方案记录行数 / 产物行数 / 目标机实际行数——差一个数量级就是整文件重写
4. 跨机事实（路径存在性/权限/文件数）以**目标机 SSH 实测**为准，claude/codex 在本地验出的「不存在」不能当目标机事实写进验收结论（round1 P1-1 的坑：新加坡机无 wf_state 目录，广州机有）
