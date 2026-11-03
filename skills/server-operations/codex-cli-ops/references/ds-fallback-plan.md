# DS 降级容灾方案（2026-08-12 实测落地）

> 背景：cc（Claude Code/Bedrock）与 codex 是主执行器，DeepSeek（DS）是 Hermes 主对话模型。老板问「cc 挂了、codex 挂了、或都挂了怎么办，只能用 DS 替代该怎么弄」——Claude 给出方案并**实测跑通**。

## 一句话结论

**DS 顶不了「审查」，顶得了「执行」。** 两个执行壳（claude/codex）都能换后端，DS 缺的不是工具能力，是判断力和上下文长度。**DS 能验证，不能发现**——被指向正确问题时能找证据，不能自己提出正确问题。

## 实测通道（2026-08-12 本机全跑通）

| 通道 | 命令 | 实测 |
|:--|:--|:--|
| DS 顶 cc 位 | `claude` 壳 + `https://api.deepseek.com/anthropic` + `deepseek-v4-pro` | 通。改文件、跑测试、审代码全可用 |
| DS 顶 codex 位 | `codex exec` + `https://api.deepseek.com/v1` + `wire_api=responses` + `deepseek-v4-flash` | 通。apply_patch 改文件成功 |
| DS 原生 API | `/v1/chat/completions`（含 function calling） | 通，1.2–1.7s 首响 |

## 两个坑（已写进脚本，别踩第二次）

1. **`CLAUDE_CODE_USE_BEDROCK=1` 会劫持路由**——本机环境变量里有它，不 `env -u` 清掉，`ANTHROPIC_BASE_URL` 形同虚设，请求照样打 Bedrock → 表现为 `400 model identifier is invalid`，看着像 DS 挂了，其实是 Bedrock 不认 DS 模型名。
2. **codex 壳只能用 `deepseek-v4-flash`**——`deepseek-v4-pro` 走 codex 协议被服务端明确拒（`Codex integration with deepseek-v4-pro will be available starting early August 2026`）。所以 codex 位降级后拿到的是 flash，比 cc 位更弱一档。

另：本机 `bwrap` 沙箱坏（`RTM_NEWADDR: Operation not permitted`），codex 位必须 `danger-full-access`。降级期 **WORKDIR 白名单是唯一防线**，不能再放宽。

## 健康检查：怎么判断「真挂了」

**核心原则：三层里只有第三层失败才算挂。** 前两层是环境问题，降级会掩盖故障。

| 层 | 查什么 | 失败叫什么 | 该干什么 |
|:--|:--|:--|:--|
| L1 | 二进制在不在、沙箱好不好 | `ENV_BROKEN` | 修 PATH / 换 sandbox_mode。**别降级** |
| L2 | key 在不在、鉴权过不过 | `AUTH_BROKEN` | 换 key / login。**别降级** |
| L3 | 端到端：改一个坏函数并跑通测试 | `DOWN` | 真挂，走降级矩阵 |
| L3' | 限流/额度/过载（429/503/quota） | `DEGRADED` | **等重试，别降级**——限流是暂时的，降级是有代价的 |

- L3 探针故意用「返回 a-b 的 add 函数 + 断言 add(2,3)==5」——一次验证读文件/改文件/执行 shell/看到失败后修正四件事。只 ping API 会把「鉴权通但改不动文件」误判为健康。
- 判定阈值：L3 连续失败 2 次（间隔 ≥5 分钟）才置 DOWN。单次失败可能是网络抖动。
- **`codex doctor` 常态报 `2 fail` 是 npm prefix 冲突**（运行 `/usr/lib/node_modules`，npm 指向 `~/.npm-global`），不影响执行——别当挂了的信号。

## 降级矩阵

### cc 挂 → DS 顶什么
| 活 | 能否顶 |
|:--|:--|
| 单文件/单函数级代码审查 | ✅ 能（要求带行号证据） |
| 已知问题的定位取证 | ✅ 能（给明确入口文件） |
| 跑现有测试并解读失败 | ✅ 能（测试是客观 oracle） |
| 契约文档「填模板」 | ⚠️ 半能（模板和不变量清单要人/codex 先给） |
| 跨 900 行以上多文件状态机审查 | ⚠️ 半能 |
| 攻击路径构造（找绕过） | ❌ 不能（这是 cc 在门禁 P0 里的核心贡献） |
| 从零定架构约束/非目标边界 | ❌ 不能（会输出正确但空洞的清单） |
| 终审签字（放行不可逆变更） | ❌ 不能 |

### codex 挂 → DS 顶什么
**更好的选择不是 DS 顶 codex，而是让 cc 自己端到端做完**（cc 有完整工具权限；codex 壳降级只能 flash 比 pro 弱）。DS 顶 codex 位仅适用于「cc 也不可用或很贵」的情况。
| 活 | 能否顶 |
|:--|:--|
| 机械批量修改（改名/替换/格式） | ✅ 能（先 git checkout -b） |
| 有明确 diff 意图的单点修复 | ✅ 能（期望 diff 写进 prompt） |
| 按现成测试修到绿 | ✅ 能 |
| 新写单元测试 | ⚠️ 半能（会写 happy path，负向用例要人指定） |
| 多文件垂直切片实现 | ⚠️ 半能（必须拆单文件级串行喂） |
| 大重构/状态机改造 | ❌ 不能（上下文 128k + 只有 flash） |
| 数据迁移脚本 | ❌ 不能（不可逆） |

### 两个都挂 → DS 顶全部
- **内容生产：几乎无损。** SPEC 里 19 节点 LLM 配置本来就是 15 处 `deepseek-v4-flash` + 4 处 `none`，`node4_review_scorer.py` 四维盲评 Judge 也是 DS。cc/codex 挂了不影响内容生产——只影响「有人在旁边审」。
- **写代码：降级但可用。** 走 cc-slot（pro）。规则：先 `git checkout -b ds-degraded/<日期>-<任务>`；任务粒度砍到单文件/单函数；每次改完跑测试，跑不通回滚；产出进 `outputs/degraded/` 打 `DS_DEGRADED` 标记，不进主干。
- **架构审查：不降级，改成「冻结 + 排队」。** 把需审查的变更冻结在分支排队，等 cc/codex 任一恢复后批量过审。DS 可做**预处理**（整理变更清单/跑测试/收集证据/列「我不确定的 N 个点」）——这是恢复后审查的输入，不是审查结论。

## 硬红线（禁止降级，等恢复）

判据不是「任务大小」，是**这一步错了能不能撤回**：
- 门禁注册表/状态机改写（WORKFLOW_REGISTRY.yaml、workflow_gate.py）——一个 return 位置错了就是 19 门全锁死或全放开
- skills 树的删除/合并——**skills 树在 Git 之外，删了不可回滚**
- 任何 git push 到主干、发布到外部平台、客户交付物定稿
- 数据迁移、schema 变更、批量删文件
- 安全边界改动（wrapper 白名单、key 处理、allowedTools、sandbox_mode）
- 首次给客户的方案/报价/策略定稿

**可以降级：** 只读审计/取证/测试复跑、新分支上的代码实现（不合主干）、内容生产全链、文档/日报/总结、机械批量修改（分支上且有测试）。
**灰区：拿不准就当红线。** DS 降级 prompt 里写死：遇到不可逆需求输出 `BLOCKED_NEEDS_PRIMARY:<原因>` 并停止。

## 恢复后要做的事

1. `git log --all --grep=DS_DEGRADED` + 扫 `outputs/degraded/` 列全部降级产出
2. 逐个过 cc 审查（排队那批）
3. 重点复核降级期新写的测试——DS 写的负向用例最可能不足
4. 检查有没有 `BLOCKED_NEEDS_PRIMARY` 被绕过执行

## 落地脚本

```bash
bash scripts/agent_health_check.sh            # 人读
bash scripts/agent_health_check.sh --json    # 机读，给 Hermes 调度用
bash scripts/agent_health_check.sh cc        # 单查
bash scripts/ds_fallback.sh cc-slot "<任务>" [workdir]
bash scripts/ds_fallback.sh codex-slot "<任务>" [workdir]
```

## 已知弱点（诚实说）

- DS 顶 cc 位能力评估只有 1 个样本，且是已知答案的复现（gate 审计）——真实故障面对未知问题表现无数据
- 没测过长任务——128k 上下文跑 1 小时以上会不会漂移未知
- 单点依赖 DeepSeek 一家——config.yaml 里还有 GLM-5.2 和豆包可做第四通道，没测
- `danger-full-access` 是真危险——bwrap 修好前降级期 codex 位没有沙箱，只有 WORKDIR 白名单，是最大残余风险
