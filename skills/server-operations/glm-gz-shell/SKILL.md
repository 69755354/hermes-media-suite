---
name: glm-gz-shell
description: 触发：生成任务/文案/分析/策略/写码。广州机GLM5.2执行壳，带工具循环和gate token。
---

# 广州机 GLM 5.2 执行壳

## 定位
Hermes 调度，广州机 `glm_native_invoke.py` 干活。GLM 5.2 直连阿里云百炼，带 read_file/write_file/terminal 三件工具，25 轮自主循环。

**优先级：** 生成任务（文案/分析/策略/写码）优先走本壳，不丢 codex/CC。

## 前置条件
- 广州机 gateway 活着（飞书 bot `cli_aad9fec111389cdc`）
- SSH 隧道通：`ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1`
- 脚本路径：`~/.hermes/scripts/glm_native_invoke.py`（广州机本地）
- API：阿里云百炼 `https://ws-i44wcdhq2lfdnl07.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
- 模型：`glm-5.2`
- API Key 从 `~/.hermes/config.yaml` 的 `providers.custom_glm.api_key` 读取

## 调用流程

### 1. 写任务书
任务书是 KV 文本格式，必填字段：

```
TASK_TYPE: <文案|分析|策略|视频|探店|口播|分镜|长文|网文|小红书|生图|运维|机械|校对|格式|摘要>
USER_REQ: <用户原话或任务描述>
```

可选字段：
```
PROJECT_DIR: <项目目录绝对路径>
READ_SKILL: <skill名>
DATA_SOURCE: <数据来源说明>
OUTPUT: <期望输出路径>
PRELOAD_NODES: <节点ID>
```

**写法：** 在新加坡机用 write_file 写到 `/tmp/glm_brief_<ts>.md`，再 scp 到广州机 `/tmp/`。

### 2. 生成 gate token
glm_native_invoke.py 需要环境变量 `TASK_GATE_TOKEN` 指向 token 文件。

```bash
# 在广州机执行：
TOKEN=$(python3 -c "import uuid; print(uuid.uuid4().hex)")
BRIEF_SHA=$(sha256sum /tmp/glm_brief_<ts>.md | awk '{print $1}')
mkdir -p /home/ubuntu/workflow/gate_tokens
cat > "/home/ubuntu/workflow/gate_tokens/${TOKEN}.json" <<EOF
{"token_id":"${TOKEN}","brief_sha256":"${BRIEF_SHA}","issued_at":$(date +%s),"expires_at":$(($(date +%s)+600)),"used":false}
EOF
chmod 600 "/home/ubuntu/workflow/gate_tokens/${TOKEN}.json"
```

### 3. 执行
```bash
ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 \
  "TASK_GATE_TOKEN='$TOKEN' python3 ~/.hermes/scripts/glm_native_invoke.py /tmp/glm_brief_<ts>.md /tmp/glm_out_<ts>.txt --model glm-5.2"
```

### 4. 读结果
```bash
ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 'cat /tmp/glm_out_<ts>.txt'
```

结果状态码：
- `OUTPUT: <路径>` → 产出已落盘
- `BLOCKED: <原因>` → 卡点拦截
- `COMPLIANCE: <问题点>` → 合规拦截
- `NEED_INFO: <缺什么>` → 缺信息

### 5. 清理
```bash
ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 \
  "rm -f /tmp/glm_brief_<ts>.md /tmp/glm_out_<ts>.txt /home/ubuntu/workflow/gate_tokens/${TOKEN}.json"
```

## 工具能力
glm_native_invoke.py 内置三个工具，GLM 自主调用：
- `read_file(path)` — 读文件
- `write_file(path, content)` — 写文件（自动建父目录）
- `terminal(command, timeout=120)` — 执行 shell 命令

最多 25 轮工具循环，温度 0.2，max_tokens 8192。

## 封装脚本

在新加坡机创建 `~/.hermes/scripts/glm_gz_shell.sh`，一键完成写任务书→scp→生成token→执行→读结果→清理：

```bash
#!/usr/bin/env bash
# glm_gz_shell.sh — 从新加坡机远程调广州 GLM 壳
# 用法: glm_gz_shell.sh <TYPE> <PROJECT_DIR> "prompt..."
set -uo pipefail
TYPE="$1"; shift
PROJECT_DIR="$1"; shift
PROMPT="$*"
TS=$(date +%s)
BRIEF="/tmp/glm_brief_${TS}.md"
OUT="/tmp/glm_out_${TS}.txt"

cat > "$BRIEF" <<EOF
TASK_TYPE=${TYPE}
PROJECT_DIR=${PROJECT_DIR}
USER_REQ=${PROMPT}
EOF

scp -P 2222 -o ConnectTimeout=10 -o BatchMode=yes "$BRIEF" ubuntu@127.0.0.1:/tmp/ || exit 2

ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 "
TOKEN=\$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
BRIEF_SHA=\$(sha256sum /tmp/$(basename $BRIEF) | awk '{print \$1}')
mkdir -p /home/ubuntu/workflow/gate_tokens
cat > /home/ubuntu/workflow/gate_tokens/\${TOKEN}.json <<INNER
{\"token_id\":\"\${TOKEN}\",\"brief_sha256\":\"\${BRIEF_SHA}\",\"issued_at\":\$(date +%s),\"expires_at\":\$(($(date +%s)+600)),\"used\":false}
INNER
chmod 600 /home/ubuntu/workflow/gate_tokens/\${TOKEN}.json
TASK_GATE_TOKEN=\${TOKEN} python3 ~/.hermes/scripts/glm_native_invoke.py /tmp/$(basename $BRIEF) /tmp/$(basename $OUT) --model glm-5.2
RC=\$?
rm -f /home/ubuntu/workflow/gate_tokens/\${TOKEN}.json
exit \$RC
"
RC=$?

ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 "cat /tmp/$(basename $OUT)" 2>/dev/null
rm -f "$BRIEF"
ssh -p 2222 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@127.0.0.1 "rm -f /tmp/$(basename $BRIEF) /tmp/$(basename $OUT)" 2>/dev/null
exit $RC
```

## 注意事项
- token 10 分钟过期，生成后立即执行
- 任务书 sha256 必须和 token 里的 brief_sha256 一致，否则 gate 拦截
- 广州机 config.yaml 里的 `providers.custom_glm.api_key` 必须有效
- glm_native_invoke.py 的 `validate_gate_token` 会校验 token 文件、sha256、过期、used 标记
- Hermes 不自己生成内容，只打包任务书、调壳、读结果、转白话回传
- 知识库引用铁律：内容生产类任务，任务书里要写 READ_SKILL 让 GLM 自己读
