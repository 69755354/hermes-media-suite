# codex 沙箱限制与跨机运维执行器选型（2026-08-26 实测）

## codex exec 沙箱禁 SSH 出站

**症状：** 把需要 SSH 到广州机执行的运维任务丢给 `codex exec` 执行，报：
```
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
BLOCKED: 执行沙箱禁止配置 loopback
```

**根因：** codex exec 默认用 bwrap 沙箱，沙箱不允许创建 network namespace 的 loopback 设备 → SSH 无法出站。

**解法：** SSH 远程操作不丢 codex。Hermes 直接用 terminal 工具 SSH 到广州机执行。`--dangerously-bypass-approvals-and-sandbox` 可以绕过沙箱限制，但不推荐用于运维任务（无审批无沙箱风险太大）。

## 执行器选型矩阵（2026-08-26 定案）

| 任务类型 | 执行器 | 原因 |
|--|--|--|
| 生成任务（文案/分析/策略/写码） | 广州机 glm_native_invoke.py | GLM 5.2 直连阿里百炼，带工具循环，不绕 SSH |
| SSH 远程运维 | Hermes terminal 直接执行 | codex 沙箱禁 SSH 出站 |
| 本地写码/文件操作 | codex exec（沙箱内） | 安全隔离，适合纯本地操作 |

## glm_native_invoke.py 关键信息

- 脚本路径：广州机 `~/.hermes/scripts/glm_native_invoke.py`（706 行）
- API：`https://ws-i44wcdhq2lfdnl07.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
- 模型：`glm-5.2`
- API Key 来源：`~/.hermes/config.yaml` 的 `providers.custom_glm.api_key`
- 工具：read_file / write_file / terminal（25 轮循环，温度 0.2，max_tokens 8192）
- 门禁：需要 `TASK_GATE_TOKEN` 环境变量指向 `/home/ubuntu/workflow/gate_tokens/<token>.json`
- token 校验：sha256 匹配任务书内容 + 10 分钟过期 + 一次性 used 标记

## 封装脚本

新加坡机 `~/.hermes/scripts/glm_gz_shell.sh` 一键完成：写任务书 → scp → 生成 token → 执行 → 读结果 → 清理。

用法：`bash ~/.hermes/scripts/glm_gz_shell.sh <TYPE> <PROJECT_DIR> "prompt..."`
