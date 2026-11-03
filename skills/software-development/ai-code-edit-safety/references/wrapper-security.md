# 远程 AI 调用 wrapper 安全加固（2026-08-11 P0-1/3 实测）

> 场景：广州机（小鹿）通过 SSH 远程调新加坡机 codex/claude 的 wrapper 脚本。Claude 架构审查发现两条攻击链，已实测修复。

## 漏洞 1：prompt 命令注入（P0-3）

**错误写法**（prompt 被拼进 bash -c 字符串）：
```bash
flock /tmp/codex.lock bash -c "claude -p \"$PROMPT\" ..."
# 恶意 prompt: "审查项目 $(rm -rf /home/ubuntu) 的问题"
# bash 会把 $(...) 当命令执行 → 任意命令执行
```

**修复**：prompt 写文件，claude/codex 从文件读；参数白名单：
```bash
printf '%s' "$PROMPT" > "$PROMPT_FILE"   # chmod 600
case "$EFFORT" in low|medium|high) ;; *) exit 1;; esac
case "$WORKDIR" in /home/ubuntu/workflow*|/tmp*|/home/ubuntu/billing-system*) ;; *) exit 1;; esac
flock /tmp/codex.lock claude -p "$(cat "$PROMPT_FILE")" ...
rm -f "$PROMPT_FILE"
```

## 漏洞 2：key 泄漏在进程命令行（P0-1）

**错误写法**（env 内联参数仍显示在 ps argv）：
```bash
flock /tmp/codex.lock env AWS_BEARER_TOKEN_BEDROCK="$(cat keyfile)" claude ...
# ps aux 仍能看到完整 key：env 的参数原样显示在命令行
```

**修复**：export 从文件读，只进进程环境（/proc/PID/environ 同 uid 可读，ps 看不到）：
```bash
export AWS_BEARER_TOKEN_BEDROCK="$(cat "$KEYFILE")"
flock /tmp/codex.lock claude ...   # 命令行无 key
```

**验证**：`ps aux | grep -F "ABSK..." | grep claude` 应无输出。

## 漏洞 3：多 wrapper 各自实现 → 修一个漏一个

codex_task.sh / codex_remote_wrapper.sh / claude_remote_wrapper.sh 三份脚本各自拼调用命令，加固只落在 wrapper 上，codex_task.sh 还在裸拼 prompt。收敛成单一入口 `run_executor.sh <executor> <effort> <workdir> <prompt_file>`，其他路径删除。

## 修复后测试

- 注入测试：`bash wrapper.sh '测试 $(touch /tmp/pwned) 注入' /tmp` → 不生成 pwned 文件
- key 测试：跑任务时 `ps aux | grep -F "ABSK"` → 无命中
