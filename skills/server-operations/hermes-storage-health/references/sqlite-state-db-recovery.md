# SQLite state.db 深度恢复实战（2026-08-16 小鹿事故）

## 事故链
1. 广州机 2G 内存双网关 → OOM SIGKILL → SQLite 非正常关闭 → FTS 索引损坏（fts5 corruption）
2. 修复时**没等旧进程完全退出**就 mv/重建库 → 文件头被写坏（`file is not a database`，38M 库全不可读）
3. 换空库恢复运行 → 但 sessions 表结构不兼容（13 列 vs Hermes 新版 52 列）→ 反复 disk=0、进程挂

## 根因（codex RCA 结论）
- 直接原因：活跃 PID/SQLite 连接存活时对库做 mv/重建/替换 → 新旧 inode 与 WAL/SHM 错配
- 软件根因：Hermes 对单文件 SQLite 的所有权/维护边界不完整（多连接、raw 探测、WAL fallback 无统一互斥）
- 放大器：2G 内存反复 OOM（非首因——日志显示 08-06 就有 IOERR，比 OOM 早 9 天）

## 修库硬门禁（先过 4 道再动文件）
```bash
systemctl --user stop hermes-gateway-customer.service
systemctl --user is-active hermes-gateway-customer.service   # 必须 inactive
pgrep -af 'hermes.*profile customer'                         # 必须无输出
lsof /home/ubuntu/.hermes/profiles/customer/state.db*        # 必须无 fd
```
- ⛔ 禁止 mv/cp/scp 活跃库做备份/恢复（rename 不使已开 fd 失效）
- ✅ 备份用 SQLite Online Backup API（`src_conn.backup(conn)`）或 `VACUUM INTO`

## 深度恢复步骤（文件头损坏时）
1. **文件头修复**：损坏库头不是 `SQLite format 3\0` → 用干净库前 100 字节覆盖坏库头 → 从 `not a database` 变 `malformed`（有救）
2. **PRAGMA recovery**：Python 自带 SQLite ≥3.45 支持 `conn.execute('PRAGMA recovery')`；版本越新越强（本机 3.53 成功、广州 3.45 失败）
3. **二进制页扫描（最后手段）**：按页大小 4096 遍历，leaf table 页（类型 13）解析 cell 记录
   - 页头：1字节类型 + 2字节 cell 数 + 2字节内容起始 + 4字节右兄弟，cell 偏移数组在页头后
   - **parse_cell 关键 bug 教训**：`hlen`（header 总长，含自身 varint）的序列数组区结束 = `p2 + hlen - 1`（p2 是 hlen varint 起点），数据区从同一位置开始；用 `p3 + hlen - 1`（p3 是 hlen 之后）会多算，导致所有字段错位
   - 序列类型码：0=NULL 1=u8 2=u16 3=u24 4=u32 6=u48 7=f64 8/9=0/1，≥12 偶数=blob、≥13 奇数=text（长度 (s-12)//2 或 (s-13)//2）
4. **按列数识别表**：不同表列数不同——先统计列数分布（Counter），按已知表结构匹配（messages=23 列、sessions=52 列新/13 列旧）
   - ⚠️ 旧 13 列 sessions 是错误解析产物（hash 格式 id），真会话要从 messages 反推（`SELECT session_id, COUNT(*), MIN(timestamp), MAX(timestamp) FROM messages GROUP BY session_id`）
5. **重建库**：从主库（同机另一个 profile 的正常 state.db）dump 完整 schema 建新库，再插数据；`sqlite_sequence` 是保留名要过滤；FTS 表先跳过 Hermes 会重建

## Hermes state.db 关键事实
- customer profile 库路径：`~/.hermes/profiles/customer/state.db`；主库 `~/.hermes/state.db`
- **sessions 表必须 52 列含 `parent_session_id`**——13 列旧结构不兼容 → `disk=0` 写失败、进程反复挂
- `WAL journal_mode unsupported on this filesystem` 是 Hermes 对任意 IOERR 的硬编码文案，不是文件系统不支持 WAL 的证据（ext4 上实测 WAL 可用）

## 防复发
- 升内存（2G→4G+）解决 OOM 放大器
- systemd 加 MemoryMax
- 每日 SQLite Online Backup 快照（不是 cp）
- 启动前 integrity_check + schema 版本校验
