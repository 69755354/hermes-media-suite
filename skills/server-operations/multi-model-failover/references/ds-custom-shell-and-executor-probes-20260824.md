# DS 转正自建壳 + 执行器可用性实测（2026-08-24）

> 会话背景：codex/claude 被判断「不能用了」→ 用户规划用 DeepSeek 替代执行，自建 DS 壳。
> 本文件是 multi-model-failover 的补充：codex 401 陷阱、自建壳方法、执行链路判断点。

## 1. codex 报 401 但任务能跑（判断可用性看完整输出）

codex exec 报 `401 Unauthorized: Provided authentication token is expired.`（models 列表刷新 + websocket 连接失败）时**任务仍可能成功**：fallback 通道照样执行、输出正常、tokens used 照扣（实测「只回复OK」→ OK + 11,194 tokens + EXIT=0）。

本会话因此误报「codex 不可用」，被用户质疑（「codex不是升级pro了」）后完整跑才发现能跑。

**判定步骤：**
1. **完整跑一次小任务**看最终输出和 exit code——不是看前几行错误日志就下结论
2. `auth.json` 里 access_token exp 在未来 ≠ 服务端没吊销（本地缓存可能被别处刷新顶掉；exp 9/3 照样 401）
3. 401 是 websocket 通道的，HTTP fallback 可能正常
4. 可用性结论必须基于「端到端小任务跑通」，不是日志无错

codex 认证方式：chatgpt 登录（`~/.codex/auth.json`，auth_mode=chatgpt）。本地 rollout 会话（`~/.codex/sessions/**/rollout-*.jsonl`）**无 usage 字段**，不落 token 账。

## 2. 自建 DS 壳：规则层平移 + 执行方式切换

codex/claude 断供 → DS 转正时**不要从零造壳**：

- codex_exec_gated.sh（11KB）的 12 条规则**全部模型无关**：TASK_GATE_TOKEN 打包卡点校验（kb_gate_sg.py 原子消费+项目绑定）、flock 并发槽、workdir 白名单/拒符号链接、kb 知识库卡点、attest 产物双签、日志/审计、require-in-project、MODEL_ID 变量
- 只有最后一行「调 codex CLI」跟模型有关 → 复制成通用壳，只改执行段

**ds_native_invoke.py 差距（4.2KB vs codex 壳 11KB）：**
- 有：TASK_GATE_TOKEN 校验（但用旧内联实现，非 kb_gate_sg.py 白名单+原子消费）、DS API 调用、落盘
- 缺：kb 闸、flock 并发、workdir 白名单、attest 签章、日志/审计、require-in-project

**关键：执行方式必须从「agent 工具循环」换成「喂饱直调」**
- codex/claude 壳 = agent 模式：给任务书，它自己读文件/跑命令/改文件（工具循环）
- DS 原生 API = 一次性模式：prompt 喂进去吐一个文件，**没有工具，不会自己读文件**
- 所以 DS 任务书必须**自包含**：数据源内容内嵌或 Hermes 预读拼接，DS 一次吐完
- 代价：DS 直调无多轮自我修正，一次成型错了就错 → 质量防线 = 任务书写得比给 codex 更细 + 产物独立复核

## 3. 执行链路判断点（为什么 Flash/Pro 包不下「整个执行」）

执行不是纯机械，链路里嵌着判断点，弱模型在判断点上崩：

| 环节 | 性质 | Flash/Pro 行不行 |
|---|---|---|
| 读方案/任务书 | 理解 | 能读但理解易偏 |
| 照方案填提示词/参数 | 机械 | ✅ 能 |
| 提交生成 API | 机械（Hermes 干） | — |
| 出片质检（抽帧看图判好坏） | 判断+视觉 | ❌ 崩（视觉未验证） |
| 后期合成 ffmpeg | 机械（脚本干） | — |
| 异常处理（API 报错/素材缺/门禁拦） | 判断 | ❌ 崩（脑补方案） |
| 内容微调（差一点改提示词重跑） | 判断 | ❌ 崩（镜2 教训） |
| 不可逆提交/发布 | 人工门 | DS 不碰 |

正解 = 机械部分给 DS（MECHANICAL 全接 / ANALYTIC 出证据）、判断点回高级模型或人（CREATIVE 不碰 DS）。**「DS 只当手，不当脑」**；codex 出方案写到「执行零判断」只能消掉部分判断点，异常/质检/主观裁决消不掉。

## 4. 相关实测锚点（2026-08-24）

- claude 实际模型 = **claude-opus-5**（attest 硬编码 sonnet-4 不可信）；Opus 5 定价 $5/$25/缓存 $0.50
- claude 固定注入 ≈ 1 万/轮（AGENTS.md 5K + 内置 5K）；轮数 ≈ 工具调用数 × 1.9
- 典型分析任务 30-55 轮（读 6 文件+写 3 文件+自检 10 项）；瘦身四招可砍半（任务书内嵌/模板/自检脚本化/精炼数据源）
- 详细见 llm-cost-analysis 的 2026-08-24 实测节
