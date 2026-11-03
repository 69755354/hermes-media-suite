# cc/codex 挂时的 DS 降级容灾（2026-08-12 实测落地）

## 一句话结论
DS 顶不了「审查」，顶得了「执行」——DS 缺的不是工具能力，是判断力和上下文长度（128k）。「能验证，不能发现」：DS 能在被指向正确问题时找到证据，不能自己提出正确问题。

## 实测通道（全部跑通）
- DS 顶 cc 位：`claude` 壳 + `https://api.deepseek.com/anthropic` + `deepseek-v4-pro` ✅（改文件/跑测试/审代码全可用）
- DS 顶 codex 位：`codex exec` + `https://api.deepseek.com/v1` + `wire_api=responses` + `deepseek-v4-flash` ✅（apply_patch 改文件成功）
- DS 原生 API：`/v1/chat/completions`（含 function calling）✅ 1.2–1.7s 首响

## 两个坑（已写进 ds_fallback.sh，别踩第二次）
1. **`CLAUDE_CODE_USE_BEDROCK=1` 会劫持路由**：不 `env -u` 清掉，`ANTHROPIC_BASE_URL` 形同虚设，请求照样打 Bedrock → 报 `400 model identifier is invalid`，看着像 DS 挂了，其实是 Bedrock 不认 DS 模型名。
2. **codex 壳只能用 `deepseek-v4-flash`**：`deepseek-v4-pro` 走 codex 协议被服务端拒（`Codex integration with deepseek-v4-pro will be available starting early August 2026`）。所以 codex 位降级后拿到 flash，比 cc 位 pro 弱一档。
3. 本机 bwrap 沙箱坏（`RTM_NEWADDR: Operation not permitted`）→ codex 位必须 `danger-full-access`，降级期 **WORKDIR 白名单是唯一防线**，不能再放宽。

## 健康检查：怎么判断「真挂了」（agent_health_check.sh）
三层判定，**只有 L3 失败才算挂**；前两层是环境问题，降级会掩盖故障：
| 层 | 查什么 | 失败叫啥 | 该干啥 |
|:--|:--|:--|:--|
| L1 | 二进制在不在、沙箱好不好 | ENV_BROKEN | 修 PATH/换 sandbox_mode。**别降级** |
| L2 | key 在不在、鉴权过不过 | AUTH_BROKEN | 换 key / codex login。**别降级** |
| L3 | 端到端：改一个坏函数并跑通测试 | DOWN | 真挂，走降级矩阵 |
| L3' | 限流/额度/过载（429/503/quota） | DEGRADED | **等重试，别降级**（限流是暂时的，降级有代价） |

- L3 探针故意用「返回 a-b 的 add + 断言 add(2,3)==5」：一次验证读文件、改文件、执行 shell、看到失败后修正四件事。只 ping API 会把「鉴权通但改不动文件」判成健康。
- 判定阈值：L3 连续失败 2 次（间隔 ≥5min）才置 DOWN。单次失败可能是网络抖动。
- **codex doctor 常态报 2 fail 是 npm prefix 冲突**（运行 `/usr/lib/node_modules`，npm 指向 `~/.npm-global`），不影响执行——别当挂了的信号。

## 降级矩阵
- **cc 挂 → DS 顶**：单文件/单函数审查 ✅；已知问题定位取证 ✅（给明确入口文件）；跑现有测试解读失败 ✅（测试是客观 oracle，DS 判断力不足被测试兜住）；契约填模板 ⚠️ 半能（模板/不变量清单要人/codex 先给）；跨 900 行以上多文件状态机审查 ⚠️ 半能；攻击路径构造（找绕过）❌；从零定架构约束/非目标边界 ❌；终审签字 ❌
- **codex 挂 → 更好的选择是让 cc 自己端到端做完**（cc 有完整工具权限），DS 只做机械活。DS 顶 codex 位仅适用于「cc 也不可用或很贵」。codex 位：机械批量修改 ✅ / 有明确 diff 意图的单点修复 ✅ / 按现成测试修到绿 ✅ / 新写单测 ⚠️（负向用例要人指定）/ 多文件垂直切片 ⚠️（拆单文件级串行喂）/ 大重构/状态机 ❌ / 数据迁移脚本 ❌
- **都挂 → DS 顶全部**：内容生产几乎无损（WORKFLOW_SPEC 19 节点 LLM 配置本来就 15 处 deepseek-v4-flash，内容链本来就跑 DS，只影响「有人在旁边审」）；写代码降级但可用（走 cc-slot pro，`git checkout -b ds-degraded/<日期>-<任务>`、任务粒度砍单文件单函数、每次改完必跑测试、产出进 outputs/degraded/ 打 `DS_DEGRADED` 标记不进主干）；**架构审查不降级，改「冻结 + 排队」**（DS 顶不了，硬顶等于自己给自己签字；DS 可做预处理：整理变更清单/跑现有测试/收集证据/列「不确定的 N 个点」）

## 降级期不可放宽的三条
1. 测试是唯一 oracle——降级期禁止「测试跑不过但我觉得对」的合并
2. 单一实现 owner 照旧——DS 顶班时它就是 owner，产出不能由它自己终审
3. 不可逆操作零降级（见硬红线）

## 硬红线（禁止降级，等 cc/codex 恢复）
判据不是「任务大小」，是**这一步错了能不能撤回**：
- 门禁注册表/状态机改写（workflow_gate.py 一个 return 位置错 = 19 门全锁死或全放开）
- skills 树删除/合并（**Git 之外不可回滚，审核时无原文可比对**）
- 任何主干 push/发布/客户交付物定稿
- 数据迁移/schema 变更/批量删文件
- 安全边界改动（wrapper 白名单/key 处理/--allowedTools/sandbox_mode）
- 首次客户方案/报价/策略定稿
- 灰区处理：拿不准就当红线。DS 降级 prompt 写死第 3 条：遇到不可逆需求输出 `BLOCKED_NEEDS_PRIMARY:<原因>` 并停止，不许自己判断能不能做。

**可以降级**：只读审计/取证/测试复跑、新分支上的代码实现（不合主干）、内容生产全链、文档/日报/总结、机械批量修改（分支上且有测试）。

## 恢复后要做的
1. `git log --all --grep=DS_DEGRADED` + 扫 `outputs/degraded/` 列出全部降级产出
2. 逐个过 cc 审查（这是排队的那批）
3. 重点复核降级期新写的测试——DS 写的负向用例最可能不足
4. 检查有没有 `BLOCKED_NEEDS_PRIMARY` 被绕过执行

## 落地文件
- `scripts/agent_health_check.sh`（三层健康检查，`--json` 给 Hermes 调度用）
- `scripts/ds_fallback.sh cc-slot|codex-slot "<任务>" [workdir]`
- `wiki/spec/DS_FALLBACK_PLAN.md`（完整方案）
- 用法：`bash scripts/agent_health_check.sh [cc|codex|ds]` → DOWN 才 `bash scripts/ds_fallback.sh <slot> "<任务>"`

## 诚实弱点（方案自述）
- DS 顶 cc 位只有 1 个样本，且是已知答案复现——未知问题表现无数据
- 没测长任务（128k 上下文跑 1h+ 是否漂移未知）
- 单点依赖 DeepSeek 一家——config.yaml 还有 GLM-5.2 和豆包可做第四条腿（本次没测；注意 GLM key 已失效见 claude-code-ops 踩坑）
- danger-full-access 无沙箱是最大残余风险（bwrap 修好前）
