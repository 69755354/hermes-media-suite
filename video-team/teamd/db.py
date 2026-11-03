#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite 台账：任务、阶段、产出物、付费调用、事件。"""
import sqlite3, json, pathlib, time, os

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_PATH = pathlib.Path(os.environ.get("TEAM_DB") or (ROOT / "state" / "team.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, title TEXT, batch TEXT, account TEXT,
  budget_calls INTEGER DEFAULT 0, status TEXT DEFAULT 'open',
  created_at TEXT, closed_at TEXT
);
CREATE TABLE IF NOT EXISTS stages(
  task_id TEXT, stage_id TEXT, ord INTEGER, status TEXT DEFAULT 'pending',
  owner_role TEXT, assignee TEXT, budget_calls INTEGER DEFAULT 0, used_calls INTEGER DEFAULT 0,
  attempts INTEGER DEFAULT 0, lease_until REAL, heartbeat_at REAL,
  blocked_reason TEXT, blocked_next TEXT,
  started_at TEXT, finished_at TEXT, updated_at TEXT,
  PRIMARY KEY(task_id, stage_id)
);
CREATE TABLE IF NOT EXISTS artifacts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, stage_id TEXT,
  path TEXT, sha256 TEXT, size INTEGER, note TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, task_id TEXT, stage_id TEXT,
  n INTEGER, note TEXT
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, task_id TEXT, stage_id TEXT,
  kind TEXT, actor TEXT, payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_stages_task ON stages(task_id, ord);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, id);
"""

def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def connect(path=None):
    p = pathlib.Path(path) if path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    return con

def event(con, task_id, stage_id, kind, actor, **payload):
    con.execute("INSERT INTO events(ts,task_id,stage_id,kind,actor,payload) VALUES(?,?,?,?,?,?)",
                (now(), task_id, stage_id, kind, actor or "-", json.dumps(payload, ensure_ascii=False)))

def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]
