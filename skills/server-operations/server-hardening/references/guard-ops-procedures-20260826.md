# Guard 运维操作手册（2026-08-26 沉淀）

## 1. MISMATCH 定性与基线刷新

### 场景
hash-verify 报 `MISMATCH` / `SECURITY_BREACH`，需判定是授权变更还是篡改，然后决定是否刷新基线。

### 定性流程
1. 跑双机 hash-verify 拿到全部 MISMATCH 文件清单：
   ```bash
   /home/ubuntu/.hermes/scripts/hash-verify.sh 2>&1
   ssh -p 2222 ubuntu@127.0.0.1 '~/.hermes/scripts/hash-verify.sh 2>&1'
   ```
2. 逐文件查修改时间和 git log：
   ```bash
   stat --format='%y' <file>
   cd /home/ubuntu/workflow && git log --oneline -3 -- <file>
   ```
3. 定性标准：能追溯到 git commit 或老板指示的改动 = 授权变更；找不到来源 = 篡改，需排查
4. 授权变更 → 刷新基线；篡改 → 不刷新，排查根因

### 基线刷新方法
hash-verify 只校验不刷基线。基线 = `~/.hermes/guard/hashes/<file>.md5` 文件内容。

```python
import hashlib, os
# 计算新 MD5
digest = hashlib.md5(usedforsecurity=False)
with open(target_path, "rb") as f:
    for chunk in iter(lambda: f.read(1024*1024), b""):
        digest.update(chunk)
new_hash = digest.hexdigest()
# 备份旧基线
os.rename(hash_path, hash_path + f".bak-refresh-{timestamp}")
# 写新基线
with open(hash_path, "w") as f:
    f.write(new_hash + "\n")
```

广州基线刷新通过 SSH 执行（md5sum + cp + echo）。

### 验证
刷新后双机跑 hash-verify 必须 `ALL_OK`：
```bash
/home/ubuntu/.hermes/scripts/hash-verify.sh 2>&1 | tail -2
ssh -p 2222 ubuntu@127.0.0.1 '~/.hermes/scripts/hash-verify.sh 2>&1 | tail -2'
```

### 2026-08-26 实例
SG 7项 + 广州2项 MISMATCH，全部追溯为授权变更（SOUL.md更新、codex重建guard、P1-1票据闸修复等），基线刷新后双机 ALL_OK。

---

## 2. Gate Liveness Probe observe 模式假告警

### 问题
活性探针 `gate_liveness.py` 每5分钟构造一个伪造必拦 payload（write_file 到 `guard/tickets/__liveness_forged_xxx.json`），期望 guard 返回 `rc=2, decision=block`。

但在 observe 模式下，guard 检测到 block 决策后仍返回 `rc=0`（放行），探针判定 `active_block=false` → 触发 `GATE_DOWN` 告警。

### 根因
- 广州 guard 是 `fail_closed=false`（observe 期），DELEGATE/PRODUCE/TERMINAL 等分支要满7天观察最早9/2才能毕业切 enforce
- 探针检查的是「是否实际拦截」，但在 observe 模式下设计上就是只记录不拦
- 探针没有区分 enforce 和 observe 模式来判健康

### 诊断方法
```bash
# 查探针状态
ssh -p 2222 ubuntu@127.0.0.1 'python3 ~/.hermes/guard/bin/gate_liveness.py \
  --config ~/.hermes/config.yaml --guard-dir ~/.hermes/guard \
  --alert-pipeline ~/.hermes/guard/bin/alert_pipeline.py \
  --alert-config ~/.hermes/guard/alert_pipeline.json \
  --status-file ~/.hermes/guard/gate_liveness_status.json --no-alert 2>&1'
```
看 `active_block: false` + `active_block_detail.returncode: 0` + `decision: null` = observe 模式假告警。

```bash
# 确认 guard 模式
ssh -p 2222 ubuntu@127.0.0.1 'python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location(\"guard\", \"/home/ubuntu/.hermes/guard/node-entry-guard.py\")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(\"mode:\", mod._mode())
print(\"fail_closed:\", mod._fail_closed())
"'
```

### 处置
- 这是 observe 模式的预期行为，不是真故障
- ack 掉告警：`alert_pipeline.py ack <alert_id>`
- 修探针：在 observe 模式下检查「是否检测到 block 决策」而不是「是否实际拦截」

### 修复（2026-08-26 已落地）

探针的 `active_block_probe()` 增加 `_detect_guard_mode()` 读取 `~/.hermes/guard/entry_guard_mode`，
与 node-entry-guard 的 `_mode()` 逻辑对齐（值不在 {observe, enforce} 时默认 observe）：

- **enforce 模式**：`returncode == 2 and decision == "block" and not created` = 通过
- **observe 模式**：guard 返回 rc=0 且 stdout 为空（observe 不输出 decision），
  探针从 `entry_guard_audit.jsonl` 读最后5条，找 `session_id` 匹配的记录，
  检查 `decision == "block" and not created` = 通过

关键坑：observe 模式下 guard 的 `_evaluate()` 确实返回 `decision=block`，
但 `main()` 在 observe 分支只写 audit jsonl，不往 stdout 输出。
探针如果从 stdout 读 decision 会读到 null。
修复后探针在 observe 模式下从 audit jsonl 读 decision。

探针文件有两份（广州）：
- Git 源：`/home/ubuntu/workflow/guard/gate_liveness.py`
- 运行入口：`/home/ubuntu/.hermes/guard/bin/gate_liveness.py`（非软链，独立副本）
两份都要同步。

---

## 3. 字符串自证残留收口（R7）

### 问题
两个字符串旁路可以让执行器绕过物理闸：

1. `TASK_GATE_ENABLED=0 SKIP_REASON=任意串` → codex_exec_gated.sh 放行，只留 WARN
2. `SKIP_KB_GATE=1 SKIP_REASON=任意串` → kb_gate_sg.py 对非内容生产 prompt 放行

### 收口方案（三层防御）
1. **codex_exec_gated.sh**：`TASK_GATE_ENABLED=0` 必须带 `GATE_BYPASS_TOKEN=<32位hex>`，通过 `kb_gate_sg.py --consume-token` 消费验证。SKIP_REASON 仍需声明（审计留痕），但单独不再授权放行。
2. **kb_gate_sg.py**：`SKIP_KB_GATE=1` 必须带 `KB_BYPASS_TOKEN=<32位hex>`，复用 KB_GATE_TOKEN 的同一加固实现（白名单 + O_EXCL 原子消费 + 项目绑定）。
3. **node-entry-guard.py**：新增 `STRING_BYPASS_RE` 正则 + `_string_bypass_attempt()` 函数，在 TERMINAL 分支检测到 `TASK_GATE_ENABLED=0` 或 `SKIP_KB_GATE=1` → 记 security_alert 并阻断。

### 误判防护
正常运维命令（磁盘清理、服务重启）不含旁路字符串，不受影响。紧急运维通过 `kb_token_issue.sh` 签发 bypass token 走合法路径。

### 风险
- `codex_task.sh` 如果使用旧字符串旁路，部署后会 BLOCKED，需迁移到 `GATE_BYPASS_TOKEN` 或走 `hermes_task_dispatch.py`
- Guard 修改后需重启 gateway 才能加载新代码
- 广州机需同步改动

---

## 4. 人工确认项处理流程

P0 物理闸部署后遗留的人工确认项处理顺序：

1. **MISMATCH 定性** — 查 git 记录逐文件判定授权变更 vs 篡改 → 授权变更刷基线
2. **字符串自证残留** — 派 codex 出收口方案 → 双机同步 + 语法检查 + 基线刷新
3. **G10 写权限隔离** — 需 root 建独立 OS 用户 + chown attest/tickets 目录 → root 操作走用户终端
4. **P1-3 毕业时间** — 纯时间条件（最早9/2），无法提前
5. **独立终审** — 派 CC 复核全部提交和运行证据

### G10 写权限隔离方案（待用户终端执行）
```
# 建独立用户
sudo useradd -r -m -d /home/gatekeeper -s /bin/bash gatekeeper
# attest/tickets 目录 chown
sudo chown gatekeeper:ubuntu /home/ubuntu/workflow/guard/attest/
sudo chmod 770 /home/ubuntu/workflow/guard/attest/
sudo chown gatekeeper:ubuntu /home/ubuntu/workflow/guard/tickets/
sudo chmod 770 /home/ubuntu/workflow/guard/tickets/
# write_attest.sh setuid
sudo chown gatekeeper:gatekeeper /home/ubuntu/.hermes/scripts/write_attest.sh
sudo chmod 4750 /home/ubuntu/.hermes/scripts/write_attest.sh
# 广州同步
```
目的：让 Hermes（ubuntu）不能直接写 attest/tickets，封死伪造旁证的口子。
