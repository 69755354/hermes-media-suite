# Hash-Verify 基线刷新流程

> 当受保护文件发生**授权变更**后，需刷新 MD5 基线使 hash-verify 恢复 ALL_OK。

## 何时刷新

- codex/claude 修改了受 PROTECTED 保护的门禁文件（node-entry-guard.py、codex_exec_gated.sh、kb_gate_sg.py 等）
- 经人工定性：MISMATCH 全部可追溯到授权变更（git commit、老板指示），无篡改
- 刷新前必须先完成定性，不能跳过直接刷

## 刷新步骤（SG 机）

```python
import hashlib, os

# 受保护文件的 hash_file 映射在 /home/ubuntu/workflow/guard/hash_manifest.yaml
# 基线文件在 /home/ubuntu/.hermes/guard/hashes/<hash_file>

changed = [
    ("node-entry-guard.py.md5", "/home/ubuntu/.hermes/guard/node-entry-guard.py"),
    ("codex_exec_gated.sh.md5", "/home/ubuntu/.hermes/scripts/codex_exec_gated.sh"),
    # ... 其他变更文件
]

hash_dir = "/home/ubuntu/.hermes/guard/hashes"
timestamp = "20260826_073801"  # date +%Y%m%d_%H%M%S

for hash_file, target_path in changed:
    digest = hashlib.md5(usedforsecurity=False)
    with open(target_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            digest.update(chunk)
    new_hash = digest.hexdigest()
    hash_path = os.path.join(hash_dir, hash_file)

    # 备份旧基线
    old_hash = ""
    if os.path.isfile(hash_path):
        with open(hash_path) as f:
            old_hash = f.read().strip()
    if old_hash and old_hash != new_hash:
        os.rename(hash_path, f"{hash_path}.bak-refresh-{timestamp}")

    # 写新基线
    with open(hash_path, "w") as f:
        f.write(new_hash + "\n")

    print(f"✅ {hash_file}: {old_hash[:12]}... → {new_hash[:12]}...")
```

## 广州机刷新

广州的 hashes 目录在 `/home/ubuntu/.hermes/guard/hashes/`，通过 SSH 操作：

```bash
ssh -p 2222 ubuntu@127.0.0.1 'cd /home/ubuntu/.hermes/guard/hashes && \
  for f in <hash_file.md5>; do \
    target=<对应文件路径>; \
    newhash=$(md5sum "$target" | cut -d" " -f1); \
    cp "$f" "$f.bak-refresh-$(date +%Y%m%d_%H%M%S)" 2>/dev/null; \
    echo "$newhash" > "$f"; \
    echo "✅ $f: → ${newhash:0:12}..."; \
  done'
```

## 验证

刷新后必须跑双机 hash-verify 确认 ALL_OK：

```bash
# SG
/home/ubuntu/.hermes/scripts/hash-verify.sh

# 广州
ssh -p 2222 ubuntu@127.0.0.1 '~/.hermes/scripts/hash-verify.sh'
```

两机都必须输出 `ALL_OK`。如果有 FAIL，说明刷新不完整或文件未同步。

## MISMATCH 定性方法

对每个 MISMATCH 文件：

1. `stat --format='%y' <file>` — 查修改时间
2. `git log --oneline --all -- <file>` — 查 git 提交记录
3. 对照时间线：修改时间是否对应某次授权的 codex/claude 执行
4. 双机当前哈希是否一致（一致 = 同版本，基线不同只是建立时间不同）

**所有 MISMATCH 都可追溯 = 授权变更，可刷新基线。**
**有任何一项无法追溯 = 疑似篡改，不可刷新，需人工调查。**

## hash_manifest.yaml 结构

```yaml
schema_version: 1
expected_count:
  gz: 11  # 广州受保护文件数
  sg: 17  # SG受保护文件数
common:       # 双机都有
  - id: <name>
    path: <绝对路径>
    hash_file: <basename.md5>
    retired_by: null
gz_only:      # 广州独有
  - ...
sg_only:      # SG独有
  - ...
```

hash-verify 脚本只做校验（`hash_verify.py`），不刷基线。基线就是 `hashes/` 目录下的 `.md5` 文件内容。刷新 = 重写这些文件。
