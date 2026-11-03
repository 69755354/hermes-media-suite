# Hash-Verify 基线刷新与 MISMATCH 定性

> 2026-08-26 实战：物理闸 P0 修复后双机 9 项 MISMATCH 的定性 + 基线刷新全流程。

## 工具链

```
hash-verify.sh → hash_verify.py（只校验不刷基线）
基线文件 = /home/ubuntu/.hermes/guard/hashes/<filename>.md5
清单文件 = /home/ubuntu/workflow/guard/hash_manifest.yaml（声明式，schema_version: 1）
```

hash_verify.py 只做校验（对比 .md5 文件 vs 实际文件），**没有刷新基线的功能**。刷新基线 = 直接覆盖 `.md5` 文件。

## MISMATCH 定性方法论

每项 MISMATCH 必须逐个追溯，判定是**授权变更**还是**篡改**：

```
① stat --format='%y' <文件>   → 修改时间
② git log --oneline --all -- <文件>  → 是否有对应 commit
③ 对照修改时间与已知授权操作（codex 修复、老板指示改动、P0/P1 执行步骤）
④ 双机当前哈希对比（SG vs 广州）→ 一致 = 同版本，基线不同 = 建基线时间不同
```

### 判定标准

| 证据 | 定性 |
|:---|:---|
| 修改时间能对应到已知授权操作 | 授权变更 |
| 有 git commit 可追溯 | 授权变更 |
| 双机当前哈希一致但基线不同 | 双机建基线时间不同，非篡改 |
| 无 git 记录 + 无授权操作记录 + 时间不明 | 疑似篡改，需人工调查 |

## 基线刷新操作

```python
import hashlib, os

# 计算当前文件 MD5
def refresh_baseline(target_path, hash_dir, hash_filename):
    digest = hashlib.md5(usedforsecurity=False)
    with open(target_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            digest.update(chunk)
    new_hash = digest.hexdigest()
    
    hash_path = os.path.join(hash_dir, hash_filename)
    
    # 备份旧基线
    old_hash = ""
    if os.path.isfile(hash_path):
        with open(hash_path) as f:
            old_hash = f.read().strip()
        if old_hash != new_hash:
            import subprocess
            ts = subprocess.run(["date","+%Y%m%d_%H%M%S"], capture_output=True, text=True).stdout.strip()
            os.rename(hash_path, f"{hash_path}.bak-refresh-{ts}")
    
    # 写新基线
    with open(hash_path, "w") as f:
        f.write(new_hash + "\n")
    
    return old_hash, new_hash
```

广州机刷新走 SSH：
```bash
ssh -p 2222 ubuntu@127.0.0.1 "echo '<new_hash>' > /home/ubuntu/.hermes/guard/hashes/<filename>"
```

## 刷新后验证

```bash
# SG
/home/ubuntu/.hermes/scripts/hash-verify.sh
# 广州
ssh -p 2222 ubuntu@127.0.0.1 '~/.hermes/scripts/hash-verify.sh'
```

全绿 = `ALL_OK`，exit code 0。

## 物理闸待人工项解决模式

P0 修复后的 5 类待人工项及处理方式：

| 项 | 类型 | 处理 |
|:---|:---|:---|
| MISMATCH定性 | 可由Hermes完成 | 逐项追溯→判定→刷新基线→验证 |
| G10写权限隔离 | 不可逆/root操作 | 准备命令给用户终端执行，AI不碰root |
| P1-3毕业 | 时间条件 | 等满7天观察期，不能越权切 |
| 字符串自证残留 | 智力活 | 派codex设计收口方案（不能执行器自创授权模型） |
| 独立终审 | 独立性要求 | 派CC复核（实现者不自审） |

## G10 写权限隔离方案（待用户终端执行）

当前问题：guard/attest/tickets 目录全是 ubuntu:ubuntu 可写，Hermes 跑在 ubuntu 下，能自己伪造旁证。

隔离方案（需 root）：
```bash
# 1. 建独立用户
sudo useradd -r -m -d /home/gatekeeper -s /bin/bash gatekeeper

# 2. attest目录chown（SG + 广州）
sudo chown gatekeeper:ubuntu /home/ubuntu/workflow/guard/attest/
sudo chmod 770 /home/ubuntu/workflow/guard/attest/

# 3. tickets目录
sudo chown gatekeeper:ubuntu /home/ubuntu/workflow/guard/tickets/
sudo chmod 770 /home/ubuntu/workflow/guard/tickets/

# 4. write_attest.sh setuid（让它以gatekeeper身份写attest）
sudo chown gatekeeper:gatekeeper /home/ubuntu/.hermes/scripts/write_attest.sh
sudo chmod 4750 /home/ubuntu/.hermes/scripts/write_attest.sh
```

G10 成立前：producer attest 只能 WARN，不能宣称物理不可伪造。

## 字符串自证残留

两个旁路口子：

1. **TASK_GATE_ENABLED=0 + SKIP_REASON=任意串** → codex_exec_gated.sh 放行，只留WARN
2. **SKIP_KB_GATE=1 + SKIP_REASON=任意串** → kb_gate_sg.py 放行运维类prompt（无内容生产关键词时）

收口原则：不能由执行器自创授权模型，需对接现有票据系统（workflow_ticket.py 一次性 token）。
