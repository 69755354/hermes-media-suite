#!/usr/bin/env python3
"""Default read-only. Explicit --apply is an operator action; never called at startup."""
import argparse
import json
import re
import sqlite3
from pathlib import Path

SQL = Path(__file__).resolve().parents[1] / 'migrations/20261028_device_binding.sql'

def validate(c):
    for table, cols in {'customers': ['default_title','default_topics','policy_version','active_device_id','binding_epoch','dispatch_paused','device_binding_enabled'], 'commands': ['device_id','binding_epoch'], 'remote_ops': ['device_id','binding_epoch'], 'customer_devices': ['device_id','customer_id','token_hash','status','binding_epoch','last_seen']}.items():
        present = {r[1] for r in c.execute(f'PRAGMA table_info({table})')}
        if not set(cols) <= present:
            raise ValueError('missing columns: '+table)
    indexes = {r[1]: r for r in c.execute('PRAGMA index_list(customer_devices)')}
    ix = indexes.get('one_active_customer_device')
    if not ix or not ix[2] or not ix[4]:
        raise ValueError('active device unique partial index missing or conflicting')
    if [r[2] for r in c.execute('PRAGMA index_info(one_active_customer_device)')] != ['customer_id']:
        raise ValueError('active device index columns conflict')
    index_sql = c.execute("SELECT sql FROM sqlite_master WHERE name='one_active_customer_device'").fetchone()[0]
    if "wherestatus='active'" not in re.sub(r'\s+', '', index_sql.lower()):
        raise ValueError('active device index predicate conflict')
    if c.execute("SELECT customer_id FROM customers WHERE binding_epoch<0 OR dispatch_paused NOT IN (0,1) OR device_binding_enabled NOT IN (0,1)").fetchall():
        raise ValueError('invalid customer binding flags')
    for row in c.execute('SELECT token_hash, status, binding_epoch FROM customer_devices'):
        if not re.fullmatch('[0-9a-f]{64}', row[0]) or row[1] not in ('active','isolated','retired') or row[2] < 0:
            raise ValueError('invalid device record')
    if c.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('foreign key conflicts')
    if c.execute("SELECT customer_id FROM customer_devices WHERE status='active' GROUP BY customer_id HAVING count(*)>1").fetchall():
        raise ValueError('multiple active devices')
    if c.execute("SELECT c.customer_id FROM customers c LEFT JOIN customer_devices d ON d.device_id=c.active_device_id AND d.customer_id=c.customer_id WHERE c.device_binding_enabled=1 AND (d.device_id IS NULL OR d.status!='active' OR d.binding_epoch!=c.binding_epoch)").fetchall():
        raise ValueError('active binding mismatch')
    for (value,) in c.execute('SELECT default_topics FROM customers WHERE default_topics IS NOT NULL'):
        obj = json.loads(value)
        if not isinstance(obj, list) or not all(isinstance(x,str) for x in obj):
            raise ValueError('invalid default_topics')
    if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('integrity check failed')

def migrate(c):
    c.execute('BEGIN IMMEDIATE')
    try:
        sql = '\n'.join(x for x in SQL.read_text().splitlines() if not x.startswith('--'))
        for stmt in sql.split(';'):
            if not stmt.strip(): continue
            m = re.search(r'ALTER TABLE (\w+) ADD COLUMN (\w+) (\w+)', stmt)
            if m:
                cols = {r[1]: r[2] for r in c.execute('PRAGMA table_info('+m[1]+')')}
                if m[2] in cols:
                    if cols[m[2]].upper() != m[3].upper():
                        raise ValueError('conflicting column '+m[2])
                    continue
            c.execute(stmt)
        validate(c)
        c.commit()
    except Exception:
        c.rollback()
        raise

if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('database', type=Path); ap.add_argument('--apply',action='store_true'); a=ap.parse_args()
    c=sqlite3.connect(a.database.resolve().as_uri()+('?mode=rw' if a.apply else '?mode=ro'),uri=True)
    c.execute('PRAGMA foreign_keys=ON')
    try:
        migrate(c) if a.apply else validate(c)
        print(json.dumps({'ok':True,'mode':'apply' if a.apply else 'read-only'}))
    finally: c.close()
