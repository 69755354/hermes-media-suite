# 运行时调用坑（claude/codex 远程调用实测）

## claude -p 的 prompt 传入方式（2026-08-13 血泪教训）

`claude -p` 支持 **stdin 或位置参数** 两种方式传 prompt，但：

- ❌ `claude -p "$(cat "$PROMPT_FILE")"` —— 中文/带空格/多行的 prompt 会被 **bash 分词拆碎** → claude 收到残缺 prompt → 空输出或 `Execution error`，**静默挂 2 天没被发现**
- ✅ `claude -p ... < "$PROMPT_FILE"` —— stdin 方式，完整可靠（逐参数测试：stdin + --append-system-prompt-file + --add-dir + --allowedTools 全组合正常）

诊断方法：**对比成功/失败日志的时间戳**。wrapper 从「正常输出 8KB」变「空输出 71 字节」的时间点 = 改动 wrapper 的时间点 → 是加固时改坏的，不是模型/网络挂了。

修复纪律：**任何「加固/优化」改动，改完必须用真实调用路径跑一次**，不是 shellcheck/语法检查。

## DS 降级时的 Bedrock 环境变量劫持

`CLAUDE_CODE_USE_BEDROCK=1` 会劫持路由——用 claude 壳 + DS 端点降级时，**必须 `env -u CLAUDE_CODE_USE_BEDROCK`** 清掉，否则请求照样打 Bedrock，报 `400 model identifier is invalid`（看着像 DS 挂了，其实是 Bedrock 不认 DS 模型名）。

## codex doctor 假阳性

本机 `codex doctor` 常态报 2 fail（npm prefix 冲突：运行 /usr/lib/node_modules，npm 全局指向 ~/.npm-global）——**不影响执行，别当挂了的信号**。健康检查要用 L3 端到端探针（改一个坏函数+跑测试），不是 ping API。

## 健康检查三层判定（agent_health_check.sh）

- L1 环境坏（二进制/沙箱）→ `ENV_BROKEN`：修环境，**别降级**
- L2 鉴权坏 → `AUTH_BROKEN`：换 key，**别降级**
- L3 端到端失败（连续 2 次间隔≥5min）→ `DOWN`：真挂，走降级矩阵
- L3' 限流/429/503 → `DEGRADED`：**等重试，别降级**（限流是暂时的，降级有代价）

探针设计：故意用「返回 a-b 的 add 函数 + 断言 add(2,3)==5」——一次验证读文件/改文件/跑 shell/看失败后修正四件事。只 ping API 会把「鉴权通但改不动文件」误判为健康。
