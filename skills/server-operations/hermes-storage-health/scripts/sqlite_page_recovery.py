#!/usr/bin/env python3
"""
SQLite 损坏库深度恢复——从文件头损坏但数据页完好的 .db 中救出 messages/sessions。
2026-08-16 小鹿案例实测：38M 库救回 messages 7042 条 + sessions 12 条。

用法：
    python3 sqlite_page_recovery.py <broken.db> <output.db> [--schema-from <healthy.db>]

原理：
    1. 文件头损坏 ≠ 数据丢失。SQLite 数据页按固定页大小(4096)存储，损坏的通常只是
       头部/页表，leaf table 页（类型13）仍完好。
    2. 直接扫描所有页，按 SQLite 记录格式手动解析每条记录。
    3. 按「列数 = 表身份」分类（Hermes: messages=23列, sessions=52列），
       重建标准库并插入。

关键坑（都踩过）：
    - parse_cell 的 header 长度 varint（hlen）包含 varint 自身字节数：
      序列类型数组结束位置 = hlen_varint起点 + hlen - 1，不是 varint之后 + hlen - 1。
      写错会整体错位 1-2 列。
    - sessions 尾部 NULL 会被解析 trim 掉列，用「≥20列 + 首列是会话ID格式」识别，
      不要用精确列数。
    - messages 有外键引用 sessions——先插 sessions，或对缺失 session 建占位行。
    - 重建库 schema 从健康库（如 ~/.hermes/state.db 主库）拉取，过滤 sqlite_sequence
      （保留名），逐条 execute 而非 executescript。
"""
import struct, sqlite3, sys, os, subprocess, re

# ---------- SQLite 记录解析 ----------

def parse_varint(buf, off):
    result = 0
    i = off
    while i < len(buf) and i < off + 9:
        b = buf[i]
        if i == off + 8:
            result = (result << 8) | b
            i += 1
            break
        result = (result << 7) | (b & 0x7f)
        i += 1
        if b < 0x80:
            break
    return result, i

def parse_serial(buf, off, serial):
    if serial == 0: return None, off
    if serial == 1: return buf[off], off+1
    if serial == 2: return struct.unpack('>h', buf[off:off+2])[0], off+2
    if serial == 3: return int.from_bytes(buf[off:off+3], 'big', signed=True), off+3
    if serial == 4: return struct.unpack('>i', buf[off:off+4])[0], off+4
    if serial == 5: return int.from_bytes(buf[off:off+6], 'big', signed=True), off+6
    if serial == 6: return struct.unpack('>q', buf[off:off+8])[0], off+8
    if serial == 7: return struct.unpack('>d', buf[off:off+8])[0], off+8
    if serial == 8: return 0, off
    if serial == 9: return 1, off
    if serial in (10, 11): return None, off
    if serial >= 12 and serial % 2 == 0:
        n = (serial - 12) // 2
        return buf[off:off+n], off+n
    if serial >= 13 and serial % 2 == 1:
        n = (serial - 13) // 2
        return buf[off:off+n].decode('utf-8', errors='replace'), off+n
    return None, off

def parse_cell(buf, off):
    """解析一条记录（跳过 rowid varint，直接读 payload）。⚠️ header 边界是最大坑。"""
    try:
        plen, p = parse_varint(buf, off)
        rowid, p2 = parse_varint(buf, p)
        hlen, p3 = parse_varint(buf, p2)
        # header 结束位置 = hlen varint 起点 + hlen - 1（hlen 含 varint 自身）
        array_end = p2 + hlen - 1
        serials = []
        pp = p3
        while pp < array_end:
            s, pp = parse_varint(buf, pp)
            serials.append(s)
        values = []
        vp = array_end
        for s in serials:
            v, vp = parse_serial(buf, vp, s)
            values.append(v)
        return rowid, values
    except Exception:
        return None, None

# ---------- 页扫描 ----------

def scan_pages(db_path):
    data = open(db_path, 'rb').read()
    page_size = struct.unpack('>H', data[16:18])[0]
    if page_size == 1:
        page_size = 65536
    n_pages = len(data) // page_size
    print(f'页大小 {page_size}, 总页数 {n_pages}', file=sys.stderr)

    from collections import Counter
    types = Counter()
    records = []
    for i in range(1, n_pages):
        off = i * page_size
        if off + 100 > len(data):
            break
        ptype = data[off]
        types[ptype] += 1
        if ptype != 13:  # leaf table 页
            continue
        try:
            n_cells = struct.unpack('>H', data[off+3:off+5])[0]
            if n_cells == 0 or n_cells > 1000:
                continue
            for c in range(n_cells):
                ptr = struct.unpack('>H', data[off+8+c*2:off+8+c*2+2])[0]
                try:
                    rowid, vals = parse_cell(data, off + ptr)
                    if vals:
                        records.append((i, rowid, vals))
                except Exception:
                    pass
        except Exception:
            continue
    print(f'页类型分布: {dict(types)}', file=sys.stderr)
    print(f'共提取 {len(records)} 条记录', file=sys.stderr)
    return records, data

# ---------- 表身份分类 ----------

def classify(records):
    """按列数分类 + 打印样本，确认表身份。⚠️ 别猜，打印样本确认。"""
    from collections import Counter
    col_counts = Counter(len(r[2]) for r in records)
    print(f'列数分布: {dict(col_counts)}', file=sys.stderr)
    # 样本确认（关键！13列≠sessions，sessions实际52列）
    shown = {}
    for pg, rowid, vals in records:
        n = len(vals)
        if n not in shown:
            shown[n] = (pg, rowid, vals)
            print(f'  {n}列样本: {str(vals[:4])[:80]}', file=sys.stderr)

    # Hermes 库: messages=23列, sessions=52列（尾部NULL会trim，用>=20+ID格式识别）
    messages = [r for r in records if len(r[2]) == 23]
    sessions = [r for r in records
                if len(r[2]) >= 20 and isinstance(r[2][0], str)
                and len(r[2][0]) >= 12 and re.match(r'^\d{8}_', r[2][0])]
    return messages, sessions

# ---------- 重建 ----------

def rebuild(messages, sessions, out_db, schema_db=None):
    if os.path.exists(out_db):
        os.remove(out_db)
    conn = sqlite3.connect(out_db)

    # 从健康库拉 schema（本地或远程）
    schema_sql = ''
    if schema_db:
        if os.path.exists(schema_db):
            c = sqlite3.connect(schema_db)
            schema_sql = ';\n'.join(r[0] for r in c.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL") if r[0])
            c.close()
    if not schema_sql:
        print('⚠️ 无健康库可用，建最小结构（sessions+messages）', file=sys.stderr)
        conn.executescript('''
        CREATE TABLE sessions (id TEXT PRIMARY KEY, source TEXT NOT NULL DEFAULT 'feishu',
            started_at REAL NOT NULL DEFAULT 0, message_count INTEGER DEFAULT 0);
        CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES sessions(id), role TEXT NOT NULL,
            content TEXT, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT,
            timestamp REAL NOT NULL, token_count INTEGER, finish_reason TEXT,
            reasoning TEXT, reasoning_content TEXT, reasoning_details TEXT,
            codex_reasoning_items TEXT, codex_message_items TEXT,
            platform_message_id TEXT, observed INTEGER DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1, compacted INTEGER NOT NULL DEFAULT 0,
            effect_disposition TEXT, api_content TEXT, display_kind TEXT,
            display_metadata TEXT);
        ''')

    if schema_sql:
        # ⚠️ 过滤 sqlite_sequence（保留名）+ 逐条 execute（executescript 整体失败）
        for stmt in schema_sql.split(';'):
            stmt = stmt.strip()
            if not stmt or 'sqlite_sequence' in stmt.lower():
                continue
            if 'messages_fts' in stmt.lower() and 'create' in stmt.lower():
                continue
            try:
                conn.execute(stmt)
            except Exception:
                pass
        conn.commit()

    # 先插 sessions
    s_ok = 0
    for pg, rowid, vals in sessions:
        try:
            sid = vals[0]
            if not sid:
                continue
            conn.execute('INSERT OR IGNORE INTO sessions (id,source,started_at,message_count) VALUES (?,?,?,0)',
                         (sid, 'feishu', 0))
            s_ok += 1
        except Exception:
            pass
    print(f'sessions 插入: {s_ok}', file=sys.stderr)

    # 再插 messages（23列映射，跳过 id 自增）
    m_ok = 0
    for pg, rowid, vals in messages:
        try:
            sid = vals[1] if len(vals) > 1 else None
            if not sid:
                continue
            if not conn.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone():
                conn.execute('INSERT OR IGNORE INTO sessions (id,source,started_at) VALUES (?,?,?)',
                             (sid, 'feishu', vals[7] if len(vals) > 7 else 0))
            cols = ['session_id','role','content','tool_call_id','tool_calls','tool_name',
                    'timestamp','token_count','finish_reason','reasoning','reasoning_content',
                    'reasoning_details','codex_reasoning_items','codex_message_items',
                    'platform_message_id','observed','active','compacted','effect_disposition',
                    'api_content','display_kind','display_metadata']
            ph = ','.join(['?'] * len(cols))
            conn.execute(f'INSERT INTO messages ({",".join(cols)}) VALUES ({ph})', vals[1:23])
            m_ok += 1
        except Exception:
            pass
    print(f'messages 插入: {m_ok}', file=sys.stderr)

    conn.commit()
    print('最终 messages:', conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0], file=sys.stderr)
    print('最终 sessions:', conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], file=sys.stderr)
    print('integrity:', conn.execute('PRAGMA integrity_check').fetchone()[0], file=sys.stderr)
    conn.close()
    print('OK:', out_db)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('用法: python3 sqlite_page_recovery.py <broken.db> <output.db> [--schema-from <healthy.db>]')
        sys.exit(1)
    broken = sys.argv[1]
    out = sys.argv[2]
    schema_from = None
    if '--schema-from' in sys.argv:
        schema_from = sys.argv[sys.argv.index('--schema-from') + 1]
    records, _ = scan_pages(broken)
    messages, sessions = classify(records)
    print(f'识别: messages={len(messages)}, sessions={len(sessions)}', file=sys.stderr)
    rebuild(messages, sessions, out, schema_from)
