# hash-verify FAIL 修复：三类判定 + 操作序列（2026-08-21 两机实测）

## 先判类（跑 `bash ~/.hermes/scripts/hash-verify.sh` 后对每条 FAIL 归三类）

| FAIL 形态 | 含义 | 处理 |
|---|---|---|
| `文件不存在` | 保护清单里的文件已删/从未部署 | 先 `grep -rl <文件名> /home/ubuntu/workflow/scripts /home/ubuntu/.hermes/scripts` 确认无引用（含无 `__pycache__/*.pyc` 残留）→ 无引用才从 hash-verify.sh 的 FILES 数组删条目；有引用 = 文件被误删，先恢复文件 |
| `哈希记录不存在` | 磁盘文件在、`hashes/` 下没有对应 .md5 | 补建：`md5sum <文件> > hashes/<名>.md5`（格式两列，行尾带文件名） |
| `哈希不匹配` | 磁盘文件被合法更新过，哈希清单滞后 | 更新：`echo "$(md5sum <文件>) " > hashes/<名>.md5`（保持两列格式） |

**关键区分「哈希滞后」vs「被篡改」**：`stat -c '%y %n' <hash文件> <磁盘文件>`——哈希文件时间戳早于磁盘文件（如 8/9 vs 8/19）= 合法更新后没同步哈希，不是入侵；跨机对照：在新加坡机跑同一 hash-verify.sh，若两机 FAIL 列表一致 = 历史遗留共性问题。

## 操作序列（改前必备份）

```bash
# 1. 备份
cp /home/ubuntu/.hermes/scripts/hash-verify.sh /home/ubuntu/.hermes/scripts/hash-verify.sh.bak-<日期>
cp -r /home/ubuntu/.hermes/guard/hashes /home/ubuntu/.hermes/guard/hashes.bak-<日期>

# 2. 按类处理（更新/补建 .md5；删 FILES 条目用 sed -i '/<文件名>/d'）

# 3. 验证
bash /home/ubuntu/.hermes/scripts/hash-verify.sh   # 期望 ALL_OK
```

## ⚠️ 输出截断坑（2026-08-21 实测）

`hash-verify.sh | tail -8` 只显示最后几条——**前面的 FAIL 会被截掉**。FILES 数组 10 条时 tail -8 看不到前 3 条（本次就是 SOUL.md/huoshan/shuziren 被截，第二次跑才发现）。**验证必须看全量输出**：先跑一遍不带 tail 记下全部 FAIL，修完再跑一遍对比，确认 FAIL 列表清空而非「看起来少了」。

## 两机 hash-verify.sh 内容一致性

新加坡机和广州机的 hash-verify.sh 正文（FILES 数组）相同（注释都写「新加坡机版」），但实际部署文件可能不同——广州机缺 feishu_send_gate.py/node-entry-guard.py（无引用无 pyc，从未部署过）。**每台机按自己的磁盘现实修，别照抄另一台的修法**。
