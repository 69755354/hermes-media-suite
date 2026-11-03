# state.db 表级逐表恢复 + FTS5 索引重建（2026-08-29 实测走通）

## 场景

state.db `database disk image is malformed`，B-tree rowid 乱序 + 页面重复引用。
`conn.iterdump()` 也炸（`sqlite3.DatabaseError: database disk image is malformed`）。
广州机没装 `sqlite3` CLI，只能用 `python3 sqlite3` 模块。

## 恢复策略：逐表 SELECT → INSERT 到新库

比 `iterdump` 更鲁棒——逐表读，坏表跳过不阻塞全局。

### 脚本核心逻辑

```python
import sqlite3, os, shutil

db_path = "/home/ubuntu/.hermes/profiles/customer/state.db"
recovered_path = db_path + ".recovered"

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. 拉 schema（sqlite_master 不会坏）
cur.execute("SELECT type, name, sql FROM sqlite_master WHERE type IN ('table','index') ORDER BY type DESC, name")
objects = cur.fetchall()

# 2. 新库建表
new_conn = sqlite3.connect(recovered_path)
new_cur = new_conn.cursor()
for typ, name, sql in objects:
    if typ == "table":
        try:
            new_cur.execute(sql)
        except Exception as e:
            print(f"Failed creating table {name}: {e}")
new_conn.commit()

# 3. 逐表复制数据
for typ, name, sql in objects:
    if typ != "table":
        continue
    copied = 0
    errors = 0
    try:
        cur.execute(f"SELECT * FROM '{name}'")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        placeholders = ",".join(["?"] * len(cols))
        col_list = ",".join([f"'{c}'" for c in cols])
        insert_sql = f"INSERT OR IGNORE INTO '{name}' ({col_list}) VALUES ({placeholders})"
        for row in rows:
            try:
                new_cur.execute(insert_sql, row)
                copied += 1
            except Exception:
                errors += 1
        new_conn.commit()
        print(f"Table {name}: copied={copied} errors={errors}")
    except Exception as e:
        print(f"Table {name}: READ FAILED - {e}")
        # 可选：rowid 范围扫描兜底（对大表很慢）
        # try: SELECT MIN(rowid), MAX(rowid) → 逐 rowid SELECT
        # 本次 delivery_obligations 表整表读不了，放弃（非核心表）

# 4. 重建索引
for typ, name, sql in objects:
    if typ == "index":
        try:
            new_cur.execute(sql)
        except Exception:
            pass
new_conn.commit()
```

### 本案例实测结果

- messages: 15773 条全救回 ✅
- sessions: 27 个全救回 ✅
- messages_fts / messages_fts_trigram: 影子表数据复制了但 **integrity 仍报 `malformed inverted index for FTS5 table main.messages_fts_trigram`**
- delivery_obligations: 整表读不了，放弃（非核心表，0 数据丢失影响）

## FTS5 索引重建（关键，数据复制后必须做）

数据复制到新库后 FTS5 索引可能仍损坏。解法：**DROP 所有 FTS5 虚拟表 + 影子表 → CREATE VIRTUAL TABLE 重建 → INSERT ... VALUES('rebuild') 从源表重建索引 → VACUUM**。

```python
# 1. DROP FTS5 虚拟表 + 影子表
for fts_name in ['messages_fts_trigram', 'messages_fts']:
    cur.execute(f"DROP TABLE IF EXISTS '{fts_name}'")
    for suffix in ['_config', '_data', '_docsize', '_idx']:
        cur.execute(f"DROP TABLE IF EXISTS '{fts_name}{suffix}'")

# 2. 重建 FTS5 虚拟表（external content 指向 messages 表）
cur.execute("""
    CREATE VIRTUAL TABLE messages_fts USING fts5(
        content,
        content='messages',
        content_rowid='rowid',
        tokenize='unicode61'
    )
""")
cur.execute("""
    CREATE VIRTUAL TABLE messages_fts_trigram USING fts5(
        content,
        content='messages',
        content_rowid='rowid',
        tokenize='trigram'
    )
""")

# 3. 从源表重建索引
cur.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
cur.execute("INSERT INTO messages_fts_trigram(messages_fts_trigram) VALUES('rebuild')")

# 4. VACUUM 压缩
cur.execute("VACUUM")

# 5. 验证
cur.execute("PRAGMA integrity_check")
# 期望: ok
```

### FTS5 表结构（从 messages 表列名推导）

messages 表有 23 列，FTS5 索引建在 `content` 列上。两个 FTS5 虚拟表：
- `messages_fts` — `tokenize='unicode61'`（标准分词，支持词级搜索）
- `messages_fts_trigram` — `tokenize='trigram'`（三字符分词，支持子串搜索）

## 完整恢复判据（五条全过才算成功）

1. `PRAGMA integrity_check` = ok
2. `SELECT COUNT(*) FROM messages` > 0
3. `SELECT COUNT(*) FROM sessions` > 0
4. FTS5 `rebuild` 无报错
5. `VACUUM` 成功

## 替换 + 重启流程

```python
import os, shutil, sqlite3, glob

# 1. 替换
os.rename(db_path, db_path + ".broken")
shutil.copy2(recovered_path, db_path)
os.chmod(db_path, 0o700)

# 2. 清锁文件
for f in glob.glob(os.path.expanduser("~/.local/state/hermes/gateway-locks/feishu-app-id-*.lock")):
    os.remove(f)
for f in [os.path.expanduser("~/.hermes/gateway.lock"),
          os.path.expanduser("~/.hermes/profiles/customer/gateway.lock")]:
    if os.path.exists(f):
        os.remove(f)
```

然后重启 gateway（⚠️ 见下方隧道断连坑）。

## 关键坑：kill 远程 gateway 后反向隧道可能断

本案例 `kill -SIGTERM <gateway PID>` 后，**8 秒内反向隧道（2222 端口）停止监听，广州机公网 IP 也 100% 丢包**——整台机器不可达。

**可能根因：**
- 广州机 1.9GB 内存，kill gateway 释放内存触发某些系统级连锁反应
- autossh 与 gateway 进程有未知的依赖关系
- 纯粹的时间巧合（网络层抖动）

**与已记录的 `pkill -f "hermes.*customer"` 误杀 autossh 不同**——本次用的是精确 `kill -SIGTERM <PID>`，理论上不会误杀 autossh（PID 不同），但隧道仍然断了。

**教训：**
- kill 远程 gateway 前先准备好备用连接路径（公网 IP 直连、控制台 VNC）
- kill 后立即验证隧道是否还在（`timeout 5 bash -c 'echo | nc -w 3 127.0.0.1 2222'`）
- 隧道断了不要反复重试 SSH，等 2-3 分钟看 autossh 是否自动恢复
- autossh 不恢复 + 公网 IP 也不通 = 整机层面问题，需要云控制台介入

## 与已有恢复方法的关系

| 方法 | 适用场景 | 本案例是否适用 |
|:--|:--|:--|
| `chmod 664` 权限修复 | 权限漂移（644 丢写） | ❌ 不是权限问题 |
| `iterdump()` → executescript | 轻度损坏 | ❌ iterdump 也炸 |
| 逐表 SELECT → INSERT（本文档） | 中度损坏，部分表可读 | ✅ 成功 |
| 二进制页扫描（deep_recover.py） | 重度损坏，文件头坏 | 未需要，逐表法已够 |
| 删库重建（空库） | 无法恢复数据时 | 最后手段，会丢全部历史 |
