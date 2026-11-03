# 闸活性排查速查（2026-08-26）

> 当「闸好像没在拦」时按此顺序排查。来源：claude 诊断 + codex 实施 P0-1/P0-4/P0-5。

## 排查顺序

```bash
# 1. 闸文件存在吗？
ls -la ~/.hermes/guard/node-entry-guard.py

# 2. hook 挂载了吗？
grep -A5 hooks ~/.hermes/config.yaml

# 3. 闸有真实流量过吗？（当日审计 >0 条 = 有流量过闸）
grep -c "$(date +%Y-%m-%d)" ~/.hermes/guard/entry_guard_audit.jsonl 2>/dev/null

# 4. 活性探针三问全绿吗？
python3 ~/.hermes/guard/bin/gate_liveness.py \
  --config ~/.hermes/config.yaml \
  --guard-dir ~/.hermes/guard \
  --alert-pipeline ~/.hermes/guard/bin/alert_pipeline.py \
  --alert-config ~/.hermes/guard/alert_pipeline.json \
  --status-file ~/.hermes/guard/gate_liveness_status.json

# 5. hash 清单里有这个文件吗？（有人删清单行 = 关警报）
grep node-entry-guard ~/.hermes/scripts/hash-verify.sh
# 或新清单：
grep node-entry-guard /home/ubuntu/workflow/guard/hash_manifest.yaml

# 6. 探针最新状态
cat ~/.hermes/guard/gate_liveness_status.json

# 7. 广州远程复核
ssh -p 2222 ubuntu@127.0.0.1 \
  'ls -la ~/.hermes/guard/node-entry-guard.py; \
   grep -A5 hooks ~/.hermes/config.yaml; \
   cat ~/.hermes/guard/gate_liveness_status.json'
```

## 静默死亡的六种形态

| 形态 | 表现 | 检测方法 |
|---|---|---|
| 文件缺失 | 闸文件不存在 | `ls` + hash-verify FILE_MISSING |
| 没接电 | 文件在、hook 没挂 | 探针①挂载在不在 |
| 空转 | 文件在、hook 挂了、逻辑被改恒放行 | 探针②干跑必拦payload验证decision=block |
| 清单删行 | hash-verify FILES 数组被删了缺失文件行 | expected_count 断言 + MANIFEST_TAMPERED |
| 软模式未转硬 | 闸代码完整但模式开关在 observe/SOFT_PASS | 查 entry_guard_mode / systemd drop-in 环境变量 |
| 探针误报observe为故障 | observe模式下guard返回rc=0但decision=block写在audit jsonl，探针按enforce标准判rc=0=不健康→GATE_DOWN假告警 | 见下方「observe模式探针适配」 |

## observe模式探针适配（2026-08-26 修复）

**问题：** gate_liveness探针的`active_block_probe`构造必拦payload（伪造写tickets文件），检查`returncode==2 and decision=="block"`。但广州guard在observe模式（`entry_guard_mode`文件内容为`policy`，`_mode()`读到不在{observe,enforce}里→默认observe），observe模式下guard返回`rc=0`（不实际拦截），只写audit jsonl记录`decision=block`。探针从stdout读decision读到null→判不健康→每5分钟推GATE_DOWN假告警。

**修复：** 探针新增`_detect_guard_mode()`读`entry_guard_mode`文件（逻辑与`node-entry-guard._mode()`对齐：值为`policy`或其他非`observe`/`enforce`的→`observe`；文件不存在→`observe`）。observe模式下从`entry_guard_audit.jsonl`读最后5条记录，找匹配`session_id`的记录检查`decision=="block"`；enforce模式保持原来检查`rc==2`。两种模式都检查`target_created==false`（即使observe也不能让伪造文件落盘）。

**同步注意：** 广州机探针在两个位置都有副本：`/home/ubuntu/workflow/guard/gate_liveness.py`（Git源）和`/home/ubuntu/.hermes/guard/bin/gate_liveness.py`（运行入口，不是软链是独立副本）。同步时两个位置都要scp。

## 已落地修复

- **gate_liveness.py**：5分钟 timer，三问，GATE_DOWN 推人
- **hash_manifest.yaml**：声明式清单 + expected_count 断言 + 人批退役墓碑
- **alert_pipeline.py**：P0/P1/P2 分级，24h 去重，5 分钟重推，每日心跳
- **node-entry-guard.py 重建**：实现放 `workflow/guard/`（Git 内），hook command 指向 workflow 路径

## 根因一句话

闸的正常工作方式就是沉默——不放行不报错不输出，「没消息」既可能是「一切正常」也可能是「闸死了」。没有活性探针，这两种状态不可区分。探针的唯一有价值的一问是：**实际构造一次必拦动作，验证真的被拦**。
