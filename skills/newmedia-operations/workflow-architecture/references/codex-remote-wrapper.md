# Codex 远程调用包装（广州机→新加坡机）

> 2026-08-10 天行者定案：广州机（小鹿）不装 codex，所有「智力活」通过 SSH 免密甩给新加坡机 codex。
> 归属：本文件挂在 workflow-architecture 下（codex-workflow-deployment 是 user-owned 不可写，如需合并请 `hermes curator adopt codex-workflow-deployment`）。

## 架构

```
广州机（小鹿/无 codex）──SSH 免密──▶ 新加坡机（codex + 工作流 + wiki）
   ssh ubuntu@<新加坡IP> "bash ~/.hermes/scripts/codex_remote_wrapper.sh '<任务>'"
```

## 通用调用包装（~/.hermes/scripts/codex_remote_wrapper.sh）

```bash
#!/bin/bash
# 参数：$1=任务prompt（必填） $2=effort（默认high） $3=workdir（默认/home/ubuntu/workflow）
flock /tmp/codex.lock bash -c "
    echo \"$1\" | codex exec --skip-git-repo-check \
        -c model_reasoning_effort=$2 \
        -c sandbox_mode=danger-full-access \
        -C \"$3\" 2>&1
" | tee -a /tmp/codex_remote_output/remote_$(date +%Y%m%d_%H%M%S).log
```

特性：
- flock 并发锁（与本地 codex 调用互斥防 OOM）
- effort: low=机械执行 / high=深度分析
- 输出落盘 /tmp/codex_remote_output/<时间戳>.log + stdout，结尾 `OUTPUT: <路径>`
- 返回码透传（广州机脚本可判断成败）

## 前置条件

1. 新加坡机 authorized_keys 含广州机公钥（命名 guangzhou-to-singapore）
2. sshd_config: PubkeyAuthentication yes + PasswordAuthentication no（安全）
3. 本机 codex 可无交互调用（codex exec --skip-git-repo-check 返回正常）

## 同步小鹿配置（含 codex）

要同步给广州机的文件清单：
- 工作流定义：WORKFLOW_REGISTRY.yaml / WORKFLOW_SPEC.yaml v5.0 / 重构方案×3
- 脚本：workflow_gate.py / review_gate.py / data_source_gate.py / confirm_gate.py / codex_preload_manifest.py
- **codex 配置**：~/.codex/config.toml（模型/权限/sandbox/项目信任）——**不打包 auth.json 密钥**（敏感，安全通道单独传）
- 远程包装：codex_remote_wrapper.sh
- skills：workflow-execution-guard / codex-bridge / humanizer 等
- Hermes 配置：config.yaml 节点参数

传输方式：广州机侧 `scp ubuntu@新加坡IP:/tmp/sync_to_xiaolu/sync_to_xiaolu.tar.gz /tmp/` 拉取（广州机→新加坡方向 SSH 通）。

## 踩坑

- 广州机只通 8899 HTTP relay（cdn_relay）时，SSH 22 是新加坡主动连不进去的——文件传输用广州机主动 scp 拉取，不是新加坡 push
- codex 密钥（auth.json）绝不进打包文件，传输安全第一
- 远程调用先小规模验证（effort=low 测链路）再全量，避免烧 token
