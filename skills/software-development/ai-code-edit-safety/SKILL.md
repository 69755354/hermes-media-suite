---
name: ai-code-edit-safety
description: 触发：让codex/claude改代码/修bug/联调。先搭工程地基再改，改完必验，否则AI越改bug越多。
author: Hermes curator
license: MIT
version: 1.0
metadata:
  hermes:
    tags: [codex, claude, code-editing, testing, git, quality]
    category: software-development
---

# AI 改代码安全网（2026-08-11 小程序联调沉淀）

## When to Use

触发：让 codex/claude 修改代码、修 bug、重构、搭项目、联调。核心场景：用户抱怨「AI 越改 bug 越多」——根因是 AI 在盲改（无测试、无类型、无 git、代码不可读），本 skill 给出让 AI 安全改代码的工程流程。

## 核心原则

**让 AI 改代码前，必须先有工程地基。** 盲改 = 改一处崩三处且无人发现。

## 🚨 第零步・禁止盲改协议（2026-10-10 用户拍板入规，优先级高于下方所有步骤）

**触发：任何「修 bug / 修报错 / 排故障」任务。** 禁止一上来就改代码。

1. **第一阶段只读、不改一行**：追完整调用链，找到**最初的出错点**。
2. **三层分离写清，各附证据**（文件行号 / SQL / 日志片段）：
   - 表象 = 用户看到的现象
   - 直接诱因 = 触发报错的那一步
   - 根因 = 谁该做而没做的那一步（**不猜，读代码坐实**）
3. **给 2–3 个修复方案，每个都带副作用**，标明哪个断根、哪个兜底、哪个是事后补。
4. **用户选定方案后才允许改代码。**

**为什么强制**：只治「不崩」的降级补丁（try/except、return None、跳过校验）会让故障换一层再冒出来，客户侧看仍是「挂了」——看似修好实际没修；反复盲改还会引入新 bug 并掩盖根因。

**反例（本项目）**：会话代际漂移致网关失联，先被改成 `raise → log+return None`，错误立刻换层暴露为 `context conversation unavailable`——本该当时就停下来追调用链。

细节见 `references/no-blind-fix-protocol.md`。

## 步骤（按顺序）

1. **git init + 首次提交**（记录当前状态快照，之后每次修改可回滚）
   ```bash
   git init && git add -A && git commit -m "chore: pristine snapshot"
   ```
2. **补 tsconfig strict**（让编译器先拦类型错）——`strict: true` + 项目对应类型包
3. **格式化代码**（拆超长单行）——代码不可读 = AI 读不懂 = 改错。这是被低估的一步
4. **写核心单测**（请求层/金额格式化/幂等键等关键逻辑；Node 原生 `node:test` 即可，别引 vitest/jest 大包——小程序/轻项目装不上）
5. **加 npm 脚本**：`typecheck`（tsc --noEmit）/ `test` / `format`
6. **改完必验**：每批改动跑 `npm run typecheck && npm test`，全绿才 commit；测试不过 → `git checkout <文件>` 回滚重改
7. **分批复改**：不要一次改完全部，按优先级分批（如：上线阻塞 → 高危逻辑 → 工程），每批独立 commit

## 联调分工模式（Claude 设计 + codex 实现）

前后端联调这类「设计+实现」分离的活，最优分工：
- **Claude 出契约文档**：接口路径/方法/请求响应/envelope/错误码/完整类型/mock 方案/环境配置/待确认阻塞项（每个阻塞项给默认决策，不阻塞实现）
- **codex 按文档实现**：每章验证+commit，测试全绿才下一章
- **契约以实际后端为准**：前端契约和后端实现全 DIFF 时，以后端实际为准改前端，加 `backend-adapter.ts` 集中转换，页面不散落兼容逻辑

## 审查-修复-验证循环（2026-08-12 定案，防 codex 越改越烂的核心流程）

**为什么 codex 单独改会越改越烂：** 无测试兜底/无外部验证/自产自评盲区。解决不是换模型，是给流程套安全网：

```
① Claude（审）→ 实测定位问题（构造穿越测试，先证明「确实能绕过」）
        ↓ 给修复建议（含：改哪/怎么改/别碰什么）
② codex（改）→ 按建议改 → 每步跑测试 → 绿了才下一步 → git commit
        ↓
③ Claude（再审）→ 突变测试打穿 → 发现新问题 → 回到①
```

**5 个关键机制：**
1. **审查者先实测再给建议**——不是读代码说「可能有问题」，是构造用例证明绕过（touch 空文件/伪造哈希/三步绕过）
2. **codex 每步验证 + commit**——改前 git 快照，改后跑测试，全绿才 commit，挂了 git checkout 回滚
3. **交叉验证不信自证**——codex 说「修好了」→ 审查者用突变测试打穿（构造破坏性用例看抓不抓得住），只信实测
4. **分块改 + 回归测试补丁**——分 P0/P1/P2 批，每批验证；每次修复补守门测试（manual 门不得盖章/未获批上游必 BLOCKED/legacy 适配器仍执行）
5. **执行者分离（生产者 ≠ 评审者）**——codex 改的 Claude 审，同一个模型既不生产也不自评

**⚠️ Claude 会话复用旧 session 缓存坑（2026-08-12 实测）：** 连续多轮审查时 Claude 会返回上一轮的旧报告（同一项目两次「再审」拿到的都是第五轮门禁旧报告）。让它重新审查时 prompt 显式声明「这是新任务，不要复述之前的报告」或换工作目录，否则拿到的可能是过期结论。

## 多轮修复循环（round 循环）纪律（2026-08-22 六轮沉淀）

codex 改 → claude 验的循环如果超过 3 轮，按以下纪律走，防「改个没完了」：

1. **用户止损偏好（第一优先）**：用户对无限循环会烦（原话：「这改个没完了啊」）。**主动给止损选项，不等用户开口**：
   - 选项 1：跑完当前这轮，PASS 就部署
   - 选项 2：不循环了，代码层直接部署（验收已 PASS 的部分先上，文档后补）
   - 选项 3：再 FAIL 就停，把 FAIL 项列给用户拍板
   用户回「跑完这轮」= 执行选项 1，等结果再报，不自行扩大范围。

2. **文档层问题专门检查（部署说明/修正说明类产物）**：循环到后期代码常已 PASS，卡点全在**文档事实陈述层**。三类高频坑：
   - **映射表掉行**：staging 目录有文件但部署说明文件映射表没有 = 静默不部署（execute_api.py 消失三轮无人发现）。防法：机械断言——staging 下每个 `*.py/*.sh/*.yaml` 必须在映射表出现一次、条数相等，否则停止。靠人眼核对不够。
   - **同一个错数换位置继续存在**：修好清单本体，却把错数写进「当前状态」栏（round5 的 1 vs 17 → round6 又出现）。防法：修正后全文 grep 旧错值，不只改被点名的位置。
   - **文档自述要原文照跑验证**：「无法重建」「只剩 1 个」这类陈述，把文档自带的扫描脚本原文照跑一遍，以输出为准。事实陈述错了=把已完成的事推给部署当天。
   - **纯文档轮也要验代码哈希**：改文档时用 md5sum 全部部署目标，确认与上一轮逐个相同（防「用改文档掩盖代码回归」）。

3. **基线来源标注**：文档引用基线时必写来源（scp 实时 vs 快照复制）与取得时间，并加「部署前实机复算 md5 不等则停」门禁——否则 diff 结论可能建立在过期基线上。

4. **部署前先确认生产归属（最大教训）**：六轮改造全做完才发现：目标机服务已被停、生产在另一台机且跑的是**完全不同**的代码（同名文件、不同行数、无闸逻辑）。**动手前先查**：目标服务 `systemctl is-active`、目标文件 md5/行数/关键函数清单、哪台机是当前生产。改造做在退役代码上 = 白做。

## Staging 独立验收（跨机部署前，2026-08-22 实测）

codex 产出 staging 文件要部署到另一台机器时，**部署前独立验收，不信 codex 自报**——四步：

1. **py_compile**：`python3 -m py_compile <file>` 先过语法
2. **diff 范围核对（抓夹带私货）**：`diff -u <基线> <staging>` 看 @@ 块分布；再对 diff 行做函数名直方图（`grep -oE 'def [a-z_]+|关键标识' | sort | uniq -c`）——改动说明没提的新函数/新分支要逐个看，确认是合理容错不是超范围改动。实例：codex 没写进说明的 `_record_video_cost_safe` 包装，读码确认只是「记账失败不丢视频」的容错才放行
3. **真实逻辑测试（零付费）**：`importlib.util.spec_from_file_location` 加载 staging 模块（不启动服务），直接调目标函数；测试库/测试路径用临时参数隔离（如 `db_path=tmp`、env 指向临时文件）；断言幂等（同参数调两次行数不变）、字段值、分支值。全程不碰付费 API
4. **部署前 MD5 核对**：生产文件 `md5sum` == 任务书给定基线（防被别人改过）才替换；替换前备份 `.bak-<日期>-predeploy`；替换后远端 py_compile + `md5sum` 对比 staging 一致；重启后查新 PID + 环境变量 + 端口健康

**无 sudo 重启 systemd 服务技巧**：服务 `User=<普通用户>` + `Restart=always` 时，同属主 `kill -TERM <PID>` 即可让 systemd 自动拉起新代码（RestartSec=3），不需要 sudo/密码。但先查 sudoers：有该服务的 NOPASSWD 就直接 `sudo systemctl restart`；没有才用 kill 法。验证：`systemctl show <unit> -p MainPID -p ActiveEnterTimestamp`（PID 换新 + 启动时间刷新 = 新代码生效）。

## 补丁基线风险（2026-08-23 分工体系修复实测，部署前必查）

codex 生成补丁时**可能基于 staging 快照而非生产实时文件**（任务书给了生产 MD5，但 codex 的隔离挂载没有生产文件，它会「基于最新快照重建」）。这会造成三类部署事故，claude 独立验证全部抓出：

1. **整文件替换 = 安全降级**：补丁从快照重建时，把 root 只读的闸路径（`/opt/hermes/gates/*`）改回用户目录，等于让被闸对象能改自己的闸；还可能砍掉生产已加的多组硬闸项（如 `_HARD_ENTRIES` 从 8 项变 3 项）。**验证时必须 diff 生产实时文件，不是 diff 快照**——比对 GATE 路径常量、硬闸项集合、行数。结论通常只能是「移植目标 hunk」，不是整文件替换。
2. **改错文件（多副本路径）**：同一闸脚本可能存在多份副本（`/opt/hermes/gates/`、`.hermes/scripts/`、`workflow/scripts/`），生产实际读哪份、文档指向哪份、哈希校验钉哪份可能各不相同。R7 实例：出片入口读 `/opt/hermes/gates/confirm_gate.py`（root 只读、ubuntu 不可写），codex 只改了用户副本 → TTL/哈希根本不生效。**改前先确认生产调用链实际读哪个路径，多副本要么全改要么确认只改生效那份**。
3. **打断生产调用方**：补丁改动参数解析时，可能破坏现有调用方（R3 实例：删了 `--require-in-project` 首参解析，codex_exec_gated.sh:152 还在用 → role='0'、attestation 写不出）。**改接口/参数前先 grep 全部调用方**，向后兼容优先（旧调用不传新参时走默认值）。
4. **WARN→BLOCK 提档必须回放真实样本**：把 gate 从 WARN 提到 BLOCK 前，用历史真实任务书/请求回放测误杀率。R2 实例：回放 49 份真实任务书 65% 被 BLOCK——连验证任务自己的任务书都命中「判定」二字被拦。误杀大头常不是目标词，而是缺标记/PRELOAD 等**一直靠 WARN 蒙混过关的既有不合规**被一起提档。**先修生成侧（让任务书模板自动补齐标记），再提档**；直接提档 = 自己先派不出活。
5. **「对齐某机」先实查目标现状**：用户说「跟 XX 一样」时，先查 XX 的真实现状再动手——它可能不是「已规范样板」而是同样在 WARN 放水/低档质检。本 session 实例：新加坡 task_brief_gate 也是 WARN、质检 scorer 也是 flash，只是门禁不校验 producer（8/17 定案后只验文件存在+非空，通道真实性由 wrapper 层 token/kb/attest 负责）。对齐的正确落点是「两边一起收紧」而不是「复制一个同样松的现状」。

## 一次修完原则（2026-08-16 平台前缀问题沉淀）

**用户核心痛点：「修一处漏一处，点状修复永远修不完」。** 同一类问题反复出现（如部署前缀 404、路径硬编码）时，别再逐条补漏——直接：

1. **全面审计一次**：派 codex 用 grep 系统性扫描整类问题（如所有 href/src/location.href/fetch/RedirectResponse/JSON 路径），产出完整问题清单（文件+行号+原文+影响+状态）
2. **让 codex 自己修自己验**：把「修完全部 + 自己验证 + 回归测试」打包给执行器，不信「已修」标注，自己核对每处
3. **验证要有自动化**：TestClient/单元测试双模式（部署前缀模式 + 无前缀本地模式都要跑），断言每个页面 href/src 带前缀
4. **修完静态扫描确认无残留**：grep 所有硬编码模式确认归零，再交付用户测试

**⚠️ 部署前缀问题的正确修法（FastAPI + Caddy/nginx 子路径反代）：**
- ❌ 模板裸相对路径 `static/app.js`：深层 URL（/projects/new、/projects/{id}/confirm/C1）下解析成 /projects/static/... → 404
- ❌ 硬编码根绝对路径 `/projects/new`：反代丢前缀 → 404
- ✅ 服务端模板用 `request.url_for('route_name', ...).path` 生成具名 URL（root_path 自动带前缀）
- ✅ 服务端 JSON 路径（next/media_url/下载链接）用 `_prefix()` 统一函数
- ✅ 前端 JS 统一 `p(path)` 函数：`if (path.startsWith('/')) path = API_BASE + path`（所有 fetch/location.href/href 赋值都过它，不要维护白名单）
- ✅ 静态资源加 no-cache 头 + 换文件名（app.js → app_v3.js）强制浏览器拿新版
- ✅ root_path 只影响 OpenAPI/重定向，**不影响模板里硬编码的绝对路径**——必须 url_for/_prefix/p() 三路统一

## Pitfalls（实测教训）

1. **无测试 = 越改越烂**：AI 改 A 处时 B/C 处依赖 A 的逻辑崩了，没人发现因为不跑测试。这是「越改 bug 越多」的第一根因
2. **无 git = 没法回滚**：改坏了只能继续让 AI 改，恶性循环
3. **TS 类型形同虚设**：`declare const wx: any` + `Page(options: any)` 让类型检查变语法糖，正负号写反编译器都不拦
4. **超长单行不可 review**：450 字符/行 → AI 读不懂 → 改错，报错行号无定位价值
5. **wrapper 安全**：远程调 AI 的 wrapper 有命令注入 + key 泄漏两个坑（见 references/wrapper-security.md）

## 验证

- `git log --oneline` 应有：pristine snapshot → tooling → tests → 各修复批次
- `npm run typecheck` 0 errors
- `npm test` 全绿（地基测试 + 修复新增测试）

## 参考

- `references/wrapper-security.md` — 远程 AI 调用 wrapper 的安全加固模式（P0-1/3 实测）
