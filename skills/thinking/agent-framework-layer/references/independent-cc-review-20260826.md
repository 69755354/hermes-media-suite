# 独立CC终审复核记录（2026-08-26）

来源：独立终审session，复核物理闸修复全部提交、运行证据和MISMATCH定性。
终审报告：`/home/ubuntu/workflow/outputs/independent_review_20260826.md`

## 复核方法

1. 读每个被改文件（codex_exec_gated.sh, kb_gate_sg.py, node-entry-guard.py, feishu_send_gate.py, gate_liveness.py）
2. 读git log和diff（`git log --oneline -20`，`git diff guard/node-entry-guard.py`）
3. 读方案文档（string_residue_fix_20260826.md, MISMATCH_qualification_recommendations_20260826.md）
4. 实际跑测试验证（语法检查、回归测试、功能测试、双机对比）
5. 对抗探针（8种STRING_BYPASS_RE绕过变体、feishu_send_gate正则测试、白名单绕过测试）

## 总判定：FAIL

### 阻断级（P0）

**P0-1：node-entry-guard.py线上版脱离Git提交**
- 磁盘版：1143行，MD5 `ae4336c8efd47e345b551905f446ab37`
- Git提交版（`bda1b04`）：540行，MD5 `75a1cceedc4b258f47367ec39d701f50`
- 两者无继承关系（独立重写），不是增量修改
- 丢失属性：逃生阀TTL+理由要求、approve硬拦、policy/branch_mode、部分PROTECTED覆盖
- 回归测试：10 failed, 8 passed

**验证方法**：
```bash
wc -l /home/ubuntu/.hermes/guard/node-entry-guard.py  # 1143
cd /home/ubuntu/workflow && git show HEAD:guard/node-entry-guard.py | wc -l  # 540
diff /home/ubuntu/workflow/guard/node-entry-guard.py /home/ubuntu/.hermes/guard/node-entry-guard.py  # IDENTICAL (git源=运行时)
cd /home/ubuntu/workflow && git diff --stat guard/node-entry-guard.py  # 986 insertions, 383 deletions
grep -c 'branch_mode\|entry_guard_policy\|BRANCH' /home/ubuntu/.hermes/guard/node-entry-guard.py  # 0 (丢失policy)
cd /home/ubuntu/workflow && git show HEAD:guard/node-entry-guard.py | grep -c 'branch_mode\|entry_guard_policy\|BRANCH'  # 4 (提交版有)
```

**P0-2：MISMATCH定性全部判为授权变更缺乏证据**
- MISMATCH文档建议：1项"疑似篡改" + 5项"需人工再查" + 3项"批准候选须人工拍板"
- 但基线已全部刷新为ALL_OK（07:38第一代 + 07:47第二代）
- 9项中仅2项有完整Git追溯（workflow_ticket双机 = 提交`784ba4d`）
- 基线刷新发生在MISMATCH文档写作之前，文档声明"本执行器未执行任何一代刷新"

**验证方法**：
```bash
# 检查备份文件时间线
ls -la /home/ubuntu/.hermes/guard/hashes/*.bak-*
# 对比备份vs当前
for f in /home/ubuntu/.hermes/guard/hashes/*.bak-r7-20260826_074758; do
  base=$(basename "$f" .bak-r7-20260826_074758)
  echo "--- $base ---"
  echo "  backup: $(cat "$f")"
  echo "  current: $(cat /home/ubuntu/.hermes/guard/hashes/$base)"
done
# 检查MISMATCH文档结论
grep 'MANUAL_REVIEW_REQUIRED' /home/ubuntu/workflow/outputs/MISMATCH_qualification_recommendations_20260826.md
```

### 高危（P1）

**P1-1：逃生阀无条件旁路**
```python
# 当前版（1143行）：
if OFF_FILE.exists():
    _security_alert("GUARD_BYPASSED", "entry guard disabled by .entry_guard_off")
    return 0  # 无条件放行！不查理由、不查TTL

# 提交版（540行）有约束：
# - OFF_REASON_FILE 必须非空
# - OFF_TTL = 1800 (30分钟自动过期)
# - age > OFF_TTL → 不放行
```

**P1-2：feishu_send_gate docstring与代码不一致**
- docstring说"路径等靠SOUL.md软规则约束，不在物理闸拦"
- 代码中SENSITIVE_PATH_PATTERNS仍硬拦`/home/`路径、`.env`引用、`config.yaml`
- `\.env\b`正则在中文中失效：`修改了.env文件`→不匹配（`\b`在中文非词字符间不触发）
- `/home/\S+\.\w{2,5}\b`误拦正常URL：`https://example.com/home/page.html`→BLOCKED

**验证方法**：
```bash
python3 /home/ubuntu/.hermes/scripts/feishu_send_gate.py check "/home/ubuntu/.hermes/config.yaml"  # BLOCKED
python3 /home/ubuntu/.hermes/scripts/feishu_send_gate.py check "<SG_HOST>上操作"  # OK (服务器标识已移除)
python3 -c "import re; print(re.search(r'\.env\b', '修改了.env文件'))"  # None (中文漏拦)
```

**P1-3：GZ的sg_only文件不在hash监控范围**
- codex_exec_gated.sh和kb_gate_sg.py在GZ磁盘上存在（与SG同MD5）
- 但hash_manifest.yaml标记为sg_only，GZ hash-verify不检查它们
- GZ篡改这两个文件不会被检测到

**验证方法**：
```bash
ssh -p 2222 ubuntu@127.0.0.1 'md5sum /home/ubuntu/.hermes/scripts/codex_exec_gated.sh /home/ubuntu/.hermes/scripts/kb_gate_sg.py'
# 与SG对比
md5sum /home/ubuntu/.hermes/scripts/codex_exec_gated.sh /home/ubuntu/.hermes/scripts/kb_gate_sg.py
# 检查manifest
grep -A2 'codex_exec_gated\|kb_gate_sg' /home/ubuntu/workflow/guard/hash_manifest.yaml  # 都在sg_only段
```

### 正向确认（R7字符串旁路收口）

**STRING_BYPASS_RE检测**：
```python
STRING_BYPASS_RE = re.compile(
    r"(?:TASK_GATE_ENABLED\s*=\s*0|SKIP_KB_GATE\s*=\s*1)"
)
```
- 8种绕过变体全部BLOCKED（含export/env/空格/双零变体）✓
- 只读命令（grep/cat）不受影响（_readonly_terminal先放行）✓
- 误判：非只读命令含字面字符串被拦（echo/sed管道/python -c），方向安全

**codex_exec_gated.sh四条路径**：
1. ENABLED!=0 → TASK_GATE_TOKEN校验 ✓
2. ENABLED=0 + 无SKIP_REASON → BLOCKED ✓
3. ENABLED=0 + SKIP_REASON + 无GATE_BYPASS_TOKEN → BLOCKED ✓
4. ENABLED=0 + SKIP_REASON + GATE_BYPASS_TOKEN → 消费token ✓
无绕过缺口。

**feishu_send_gate白名单**：
- frozenset不可变 ✓
- user_id是飞书平台分配固定标识，不可伪造 ✓
- check模式不豁免（不知道recipient），send模式豁免（知道recipient）✓

**gate_liveness探针**：
- observe模式从audit jsonl读decision判健康 ✓
- 不会永远报绿（audit找不到session_id → None → 不健康）✓
- 竞争风险：只读最后5行，高并发可能读不到（假阴性方向安全）

### 语法检查结果
```
kb_gate_sg.py          py_compile OK ✓
node-entry-guard.py    py_compile OK ✓
feishu_send_gate.py    py_compile OK ✓
gate_liveness.py       py_compile OK ✓
codex_exec_gated.sh    bash -n OK ✓
```

### 双机一致性
```
node-entry-guard.py    SG ae4336c8 = GZ ae4336c8 ✓
feishu_send_gate.py    SG 611d63a0 = GZ 611d63a0 ✓
codex_exec_gated.sh    SG cfb0c513 = GZ cfb0c513 ✓
kb_gate_sg.py          SG cf73b22e = GZ cf73b22e ✓
hash-verify SG          17/17 ALL_OK ✓
hash-verify GZ          11/11 ALL_OK ✓
```

### 毕业前必须修复
1. P0-1：确定node-entry-guard.py可信版本（恢复540行版或追认1143行版+补齐丢失属性）
2. P0-2：MISMATCH 9项人工逐项签字后才允许受控更新基线
3. P1-1：逃生阀恢复TTL(30分钟)+非空理由要求
4. P1-2：feishu_send_gate docstring与实现对齐（改docstring或删SENSITIVE_PATH_PATTERNS）
5. P1-3：GZ磁盘上的sg_only文件纳入hash监控范围
