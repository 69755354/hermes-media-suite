"""冻结契约对应的 SQLite 状态仓库；文件系统保存产物，SQLite 保存状态、审批、任务和审计。"""
# > 执行者：codex
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from . import config


NODE_STATES = {
    "BLOCKED_UPSTREAM", "READY", "RUNNING", "PRODUCED", "INTERNAL_REVIEW",
    "CLIENT_CONFIRM", "GATE_CHECKING", "SIGNED_OFF", "FAILED_RETRYABLE",
    "FAILED_TERMINAL", "WAITING_BOSS_APPROVAL", "ROLLED_BACK",
    "WAITING_CLIENT_INFO", "PAUSED_BY_CLIENT", "CANCELLED_BY_CLIENT",
    "ABANDONED", "EXPIRED",
}


def utc_now() -> str:
    # 审计链按时间排序；微秒精度避免同一秒内多事件因随机 UUID 排序而断链，
    # 也避免完全相同事件在同一秒产生相同哈希。
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def utc_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class StateStore:
    _THREAD_LOCKS = tuple(threading.RLock() for _ in range(256))
    _THREAD_LOCK_STATE = threading.local()

    def __init__(
        self,
        db_path: Path | str,
        schema_path: Path | str | None = None,
        *,
        lock_dir: Path | str | None = None,
        audit_fsync: bool = False,
    ):
        # 连接与跨进程锁都从同一个规范化绝对路径派生，避免相对路径别名
        # 把同一数据库误判成多个数据源。
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.schema_path = Path(schema_path or config.DDL_PATH)
        self.extension_schema_path = config.EXTENSION_DDL_PATH
        self._write_lock = threading.RLock()
        if isinstance(lock_dir, str) and not lock_dir.strip():
            raise ValueError("lock_dir 不能为空")
        self._lock_dir = (
            Path(lock_dir).expanduser().resolve()
            if lock_dir is not None
            else self.db_path.parent / ".factory-locks"
        )
        if self._lock_dir.exists() and not self._lock_dir.is_dir():
            raise ValueError("lock_dir 必须是目录路径")
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        self._audit_fsync = bool(audit_fsync)
        self._initialize()

    @property
    def lock_dir(self) -> Path:
        return self._lock_dir

    def _connect(self) -> sqlite3.Connection:
        timeout_ms = config.sqlite_busy_timeout_ms()
        conn = sqlite3.connect(
            self.db_path, timeout=timeout_ms / 1000, isolation_level=None
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={timeout_ms}")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def interprocess_lock(
        self, name: str, *, blocking: bool = False
    ) -> Iterator[bool]:
        """同一主机多进程互斥；所有业务键共享一个文件的独立字节锁。"""
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        offset = int(digest[:15], 16)
        lock_key = (str(self._lock_dir), offset)
        held = getattr(self._THREAD_LOCK_STATE, "held", None)
        if held is None:
            held = self._THREAD_LOCK_STATE.held = {}
        if held.get(lock_key, 0):
            held[lock_key] += 1
            try:
                yield True
            finally:
                held[lock_key] -= 1
            return

        # POSIX record locks are process-scoped, so a bounded in-process lock set
        # is also required to make independent request threads contend correctly.
        thread_lock = self._THREAD_LOCKS[offset % len(self._THREAD_LOCKS)]
        locally_acquired = thread_lock.acquire(blocking=blocking)
        if not locally_acquired:
            yield False
            return

        path = self._lock_dir / "state-store.lock"
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o640)
        acquired = False
        try:
            flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
            try:
                fcntl.lockf(descriptor, flags, 1, offset, os.SEEK_SET)
                acquired = True
                held[lock_key] = 1
            except BlockingIOError:
                pass
            yield acquired
        finally:
            if acquired:
                held.pop(lock_key, None)
                fcntl.lockf(descriptor, fcntl.LOCK_UN, 1, offset, os.SEEK_SET)
            os.close(descriptor)
            thread_lock.release()

    def _append_audit_ledger(
        self, ledger: Path, event: dict[str, Any]
    ) -> None:
        """SQLite 提交后追加镜像日志；普通审计默认依赖 close 刷盘。"""
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(event) + "\n")
            if self._audit_fsync:
                handle.flush()
                os.fsync(handle.fileno())

    def consume_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        *,
        now: float | None = None,
    ) -> bool:
        """原子消费一个单机跨进程限流配额。"""
        if limit < 1 or window_seconds < 1:
            raise ValueError("限流参数必须为正数")
        timestamp = datetime.now(timezone.utc).timestamp() if now is None else now
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        state_dir = self._lock_dir / "rate-limits"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / f"{digest}.json"
        with self.interprocess_lock(f"rate-limit:{digest}", blocking=True) as acquired:
            if not acquired:
                raise RuntimeError("跨进程限流锁获取失败")
            if state_path.exists():
                stamps = json.loads(state_path.read_text(encoding="utf-8"))
                if not isinstance(stamps, list):
                    raise RuntimeError("跨进程限流状态损坏")
            else:
                stamps = []
            recent = [
                float(stamp)
                for stamp in stamps
                if timestamp - float(stamp) < window_seconds
            ]
            allowed = len(recent) < limit
            if allowed:
                recent.append(timestamp)
            temporary = state_dir / f".{digest}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                descriptor = os.open(
                    temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o640
                )
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(canonical_json(recent))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, state_path)
            finally:
                temporary.unlink(missing_ok=True)
            return allowed

    def _initialize(self) -> None:
        # Uvicorn spawn 会让多个子进程同时 import app；基线 DDL 只能有一个执行者。
        with self.interprocess_lock("database-initialize", blocking=True) as acquired:
            if not acquired:
                raise RuntimeError("数据库初始化互斥锁获取失败")
            self._initialize_locked()

    def _initialize_locked(self) -> None:
        with self._write_lock, self._connect() as conn:
            journal_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                raise RuntimeError("SQLite WAL 模式启用失败")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables:
                conn.executescript(self.schema_path.read_text(encoding="utf-8"))
            elif "schema_version" not in tables:
                raise RuntimeError("检测到旧版数据库；请设置 XG_FACTORY_DB 指向新文件后启动")
            version = conn.execute("SELECT version FROM schema_version WHERE singleton_id=1").fetchone()
            if not version or version[0] != 1:
                raise RuntimeError("平台数据库 schema_version 必须为 1")
            conn.executescript(self.extension_schema_path.read_text(encoding="utf-8"))
            self._migrate_asset_evidence_types(conn)

    @staticmethod
    def _migrate_asset_evidence_types(conn: sqlite3.Connection) -> None:
        """兼容早期证据表，使节点0三个内容分支的素材类型都能真实落库。"""
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='asset_evidence_bindings'"
        ).fetchone()
        table_sql = str(row[0] if row else "")
        if "presenter_portrait" in table_sql:
            return
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            conn.executescript(
                """
                BEGIN IMMEDIATE;
                ALTER TABLE asset_evidence_bindings RENAME TO asset_evidence_bindings_legacy;
                CREATE TABLE asset_evidence_bindings (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    planned_asset_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                    evidence_type TEXT NOT NULL CHECK (evidence_type IN (
                        'menu_photo','price_board_photo','storefront_photo','interior_photo',
                        'product_photo','dish_photo','service_process_photo',
                        'drama_scene_reference','character_reference','presenter_portrait',
                        'alcohol_evidence','other'
                    )),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, planned_asset_id),
                    UNIQUE(project_id, asset_id)
                ) STRICT;
                INSERT INTO asset_evidence_bindings(
                    project_id,planned_asset_id,asset_id,evidence_type,created_at
                )
                SELECT project_id,planned_asset_id,asset_id,evidence_type,created_at
                FROM asset_evidence_bindings_legacy;
                DROP TABLE asset_evidence_bindings_legacy;
                COMMIT;
                """
            )
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA foreign_keys=ON")

    def create_project(
        self,
        project_id: str,
        client_name: str,
        project_dir: Path,
        store: dict[str, Any],
        prefs: dict[str, Any],
        *,
        offers: list[dict[str, Any]] | None = None,
        piece_format: str = "VIDEO_SHORT",
        platform: str = "抖音",
    ) -> tuple[str, str, str]:
        now = utc_now()
        client_id = f"cli_{project_id}"
        cycle_id = f"cyc_{project_id}"
        piece_id = f"piece_{project_id}"
        stores = store.get("stores") if isinstance(store.get("stores"), list) else [store]
        offer_rows = offers if offers is not None else store.get("offers", [])
        display = str(store.get("name") or stores[0].get("display_name") or client_name)
        industry_path = str(store.get("industry_path") or "catering/hotpot")
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO clients(id,account_name,display_name,status,timezone,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (client_id, project_id, client_name, "active", "Asia/Shanghai", now, now),
                )
                conn.execute(
                    """INSERT INTO projects(
                        id,client_id,name,project_dir,entry_type,industry_path,stores_json,offers_json,
                        prefs_json,wip_status,owner,next_action,due_at,revision,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        project_id, client_id, display, str(project_dir.resolve()), "FULL_SERVICE",
                        industry_path, canonical_json(stores), canonical_json(offer_rows),
                        canonical_json(prefs), "active", "内容运营", "核验授权与素材", None, 1, now, now,
                    ),
                )
                conn.execute(
                    "INSERT INTO pieces(id,project_id,format,platform,ordinal,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (piece_id, project_id, piece_format, platform, 1, "active", now, now),
                )
                scope = {"deliverables": ["内容方案", "画面规划", "成片", "发布资料包"], "piece_count": 1}
                conn.execute(
                    """INSERT INTO orders(
                        id,project_id,quote_version,quote_snapshot_json,service_scope_json,revise_quota,
                        revise_used,amount_fen,currency,status,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (f"ord_{project_id}", project_id, 1, canonical_json({"mode": "internal_test"}), canonical_json(scope), 2, 0, 0, "CNY", "internal_test_exempt", now, now),
                )
                facts = {"stores": stores, "offers": offer_rows, "industry_path": industry_path}
                conn.execute(
                    "INSERT INTO facts_revisions(id,project_id,rev_no,content_json,content_sha,created_at) VALUES(?,?,?,?,?,?)",
                    (f"facts_{project_id}_1", project_id, 1, canonical_json(facts), digest_json(facts), now),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self.audit(project_id, "system", "system", "project_created", project_id, {"store_name": display, "piece_id": piece_id})
        return client_id, cycle_id, piece_id

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["prefs"] = json.loads(result.pop("prefs_json"))
            result["stores"] = json.loads(result.pop("stores_json"))
            result["offers"] = json.loads(result.pop("offers_json"))
            result["status"] = result["wip_status"]
            result["cycle"] = {"id": f"cyc_{project_id}", "project_id": project_id, "name": "首期"}
            piece = conn.execute("SELECT * FROM pieces WHERE project_id=?", (project_id,)).fetchone()
            result["piece"] = dict(piece) if piece else None
            return result

    def grant_project_access(self, account_name: str, project_id: str) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO client_project_access(account_name,project_id,created_at) VALUES(?,?,?)",
                (account_name, project_id, utc_now()),
            )

    def project_accessible(self, account_name: str, project_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM client_project_access WHERE account_name=? AND project_id=?",
                (account_name, project_id),
            ).fetchone() is not None

    def bind_project_billing(
        self,
        project_id: str,
        customer_id: int,
        account_id: int,
        task_id: int,
        task_type: str,
        estimated_points: str,
        status: str,
    ) -> None:
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO project_billing(
                    project_id,billing_customer_id,billing_account_id,billing_task_id,
                    task_type,estimated_points,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    project_id, customer_id, account_id, task_id, task_type,
                    estimated_points, status, now, now,
                ),
            )
        self.audit(
            project_id,
            "system",
            "system",
            "billing_task_bound",
            str(task_id),
            {"customer_id": customer_id, "account_id": account_id, "estimated_points": estimated_points},
        )

    def project_billing(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM project_billing WHERE project_id=?", (project_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_project_billing(
        self,
        project_id: str,
        status: str,
        *,
        settled_points: str | None = None,
        delivery_id: int | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """UPDATE project_billing
                   SET status=?, settled_points=COALESCE(?,settled_points),
                       delivery_id=COALESCE(?,delivery_id), last_error=?, updated_at=?
                   WHERE project_id=?""",
                (status, settled_points, delivery_id, last_error, utc_now(), project_id),
            )
            row = conn.execute(
                "SELECT * FROM project_billing WHERE project_id=?", (project_id,)
            ).fetchone()
        if row is None:
            raise KeyError(project_id)
        self.audit(
            project_id,
            "system",
            "system",
            "billing_status_changed",
            str(row["billing_task_id"]),
            {"status": status, "settled_points": settled_points, "delivery_id": delivery_id, "last_error": last_error},
        )
        return dict(row)

    def create_remote_production_job(
        self, project_id: str, remote_job_id: str, request_hash: str
    ) -> dict[str, Any]:
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO remote_production_jobs(
                       project_id,remote_job_id,request_hash,status,created_at,updated_at
                   ) VALUES(?,?,?,'queued',?,?)""",
                (project_id, remote_job_id, request_hash, now, now),
            )
        self.audit(
            project_id, "system", "system", "remote_production_submitted",
            remote_job_id, {"request_hash": request_hash},
        )
        return self.remote_production_job(project_id) or {}

    def remote_production_job(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM remote_production_jobs WHERE project_id=?", (project_id,)
            ).fetchone()
            return dict(row) if row else None

    def active_remote_production_jobs(self, limit: int = 5) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(
                """SELECT * FROM remote_production_jobs
                   WHERE status IN ('queued','running') ORDER BY updated_at LIMIT ?""",
                (limit,),
            )]

    def update_remote_production_job(
        self,
        project_id: str,
        status: str,
        *,
        remote_result_path: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"queued", "running", "succeeded", "failed"}:
            raise ValueError(status)
        now = utc_now()
        finished = now if status in {"succeeded", "failed"} else None
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """UPDATE remote_production_jobs
                   SET status=?,remote_result_path=COALESCE(?,remote_result_path),
                       error=?,updated_at=?,finished_at=COALESCE(?,finished_at)
                   WHERE project_id=?""",
                (status, remote_result_path, error, now, finished, project_id),
            )
        row = self.remote_production_job(project_id)
        if row is None:
            raise KeyError(project_id)
        self.audit(
            project_id, "system", "system", "remote_production_status",
            row["remote_job_id"], {"status": status, "error": error},
        )
        return row

    def list_projects(self, account_name: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if account_name is None:
                query = "SELECT p.* FROM projects p ORDER BY p.created_at DESC"
                rows = [dict(row) for row in conn.execute(query)]
            else:
                query = (
                    "SELECT p.* FROM projects p JOIN client_project_access a ON a.project_id=p.id "
                    "WHERE a.account_name=? ORDER BY p.created_at DESC"
                )
                rows = [dict(row) for row in conn.execute(query, (account_name,))]
        for row in rows:
            row["status"] = row["wip_status"]
        return rows

    def update_preferences(self, project_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        project = self.get_project(project_id)
        if not project:
            raise KeyError(project_id)
        prefs = project["prefs"]
        prefs.update(changes)
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "UPDATE projects SET prefs_json=?,revision=revision+1,updated_at=? WHERE id=?",
                (canonical_json(prefs), utc_now(), project_id),
            )
        self.audit(project_id, "client", "client", "preferences_changed", project_id, changes)
        return prefs

    def update_project_flow(self, project_id: str, *, status: str | None = None, next_action: str | None = None) -> None:
        fields, values = [], []
        if status is not None:
            fields.append("wip_status=?")
            values.append(status)
        if next_action is not None:
            fields.append("next_action=?")
            values.append(next_action)
        if not fields:
            return
        fields.append("updated_at=?")
        values.append(utc_now())
        values.append(project_id)
        with self._write_lock, self._connect() as conn:
            conn.execute(f"UPDATE projects SET {','.join(fields)} WHERE id=?", values)

    def _node_row(self, conn: sqlite3.Connection, project_id: str, node_id: str, cycle_id: str | None, piece_id: str | None):
        return conn.execute(
            "SELECT * FROM node_runs WHERE project_id=? AND node_id=? AND cycle_id IS ? AND piece_id IS ?",
            (project_id, node_id, cycle_id, piece_id),
        ).fetchone()

    def set_node(
        self,
        project_id: str,
        node_id: str,
        cycle_id: str | None,
        piece_id: str | None,
        status: str,
        *,
        executor: str | None = None,
        error_class: str | None = None,
    ) -> None:
        del executor
        if status not in NODE_STATES:
            raise ValueError(f"非法节点状态: {status}")
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._node_row(conn, project_id, node_id, cycle_id, piece_id)
                if row:
                    if row["status"] == "CANCELLED_BY_CLIENT" and status != "CANCELLED_BY_CLIENT":
                        conn.execute("COMMIT")
                        return
                    conn.execute(
                        "UPDATE node_runs SET status=?,finished_at=?,revision=revision+1,updated_at=? WHERE id=?",
                        (status, now if status in {"SIGNED_OFF", "FAILED_TERMINAL", "ROLLED_BACK"} else None, now, row["id"]),
                    )
                    if status == "CANCELLED_BY_CLIENT":
                        conn.execute("UPDATE run_attempts SET status='cancelled',finished_at=? WHERE node_run_id=? AND status IN ('queued','leased','running')", (now, row["id"]))
                else:
                    run_id = "run_" + uuid.uuid4().hex
                    conn.execute(
                        """INSERT INTO node_runs(
                            id,project_id,node_id,cycle_id,piece_id,status,started_at,finished_at,revision,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (run_id, project_id, node_id, cycle_id, piece_id, status, now if status == "RUNNING" else None, now if status == "SIGNED_OFF" else None, 1, now, now),
                    )
                conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, project_id))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self.audit(project_id, "system", "system", "node_status", node_id, {"status": status, "error_class": error_class})

    def node_runs(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM node_runs WHERE project_id=? ORDER BY created_at", (project_id,))]

    def enqueue_node(self, project_id: str, node_id: str, cycle_id: str | None, piece_id: str | None, request: dict[str, Any]) -> str:
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._node_row(conn, project_id, node_id, cycle_id, piece_id)
                if not row:
                    run_id = "run_" + uuid.uuid4().hex
                    conn.execute(
                        "INSERT INTO node_runs(id,project_id,node_id,cycle_id,piece_id,status,revision,created_at,updated_at) VALUES(?,?,?,?,?,'READY',1,?,?)",
                        (run_id, project_id, node_id, cycle_id, piece_id, now, now),
                    )
                    attempt_no = 1
                else:
                    run_id = row["id"]
                    if row["status"] in {"RUNNING", "SIGNED_OFF", "CANCELLED_BY_CLIENT"}:
                        raise ValueError("节点当前状态不可重复入队")
                    attempt_no = conn.execute("SELECT COALESCE(MAX(attempt_no),0)+1 FROM run_attempts WHERE node_run_id=?", (run_id,)).fetchone()[0]
                    conn.execute("UPDATE node_runs SET status='READY',updated_at=? WHERE id=?", (now, run_id))
                attempt_id = "att_" + uuid.uuid4().hex
                request_hash = digest_json({"project_id": project_id, "node_id": node_id, "attempt": attempt_no, "request": request})
                conn.execute(
                    """INSERT INTO run_attempts(
                        id,node_run_id,project_id,attempt_no,status,request_hash,usage_json,created_at
                    ) VALUES(?,?,?,?,?,?,?,?)""",
                    (attempt_id, run_id, project_id, attempt_no, "queued", request_hash, canonical_json(request), now),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self.audit(project_id, "system", "system", "node_enqueued", node_id, {"attempt_id": attempt_id})
        return attempt_id

    def claim_attempt(self, lease_owner: str, lease_seconds: int = 60) -> dict[str, Any] | None:
        now, expires = utc_now(), utc_after(lease_seconds)
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """SELECT a.*,n.node_id,n.cycle_id,n.piece_id,n.status AS node_status
                       FROM run_attempts a JOIN node_runs n ON n.id=a.node_run_id
                       WHERE a.status='queued' ORDER BY a.created_at LIMIT 1"""
                ).fetchone()
                if not row:
                    conn.execute("COMMIT")
                    return None
                claimed = conn.execute(
                    "UPDATE run_attempts SET status='leased',lease_owner=?,lease_expires_at=?,started_at=? WHERE id=? AND status='queued'",
                    (lease_owner, expires, now, row["id"]),
                )
                if claimed.rowcount != 1:
                    conn.execute("ROLLBACK")
                    return None
                conn.execute("UPDATE node_runs SET status='RUNNING',current_attempt_id=?,started_at=COALESCE(started_at,?),updated_at=? WHERE id=?", (row["id"], now, now, row["node_run_id"]))
                conn.execute("COMMIT")
                result = dict(row)
                result["lease_owner"] = lease_owner
                result["lease_expires_at"] = expires
                result["status"] = "leased"
                return result
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def heartbeat_attempt(self, attempt_id: str, lease_owner: str, lease_seconds: int = 60) -> bool:
        with self._write_lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE run_attempts SET lease_expires_at=?,status='running' WHERE id=? AND lease_owner=? AND status IN ('leased','running')",
                (utc_after(lease_seconds), attempt_id, lease_owner),
            )
            return cur.rowcount == 1

    def finish_attempt(
        self,
        attempt_id: str,
        success: bool,
        *,
        error_class: str | None = None,
        usage: dict[str, Any] | None = None,
        lease_owner: str | None = None,
    ) -> bool:
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM run_attempts WHERE id=?", (attempt_id,)).fetchone()
                if not row or row["status"] == "cancelled":
                    conn.execute("COMMIT")
                    return False
                if lease_owner is not None and (
                    row["lease_owner"] != lease_owner
                    or row["status"] not in {"leased", "running"}
                ):
                    conn.execute("COMMIT")
                    return False
                status = "succeeded" if success else "failed"
                conn.execute(
                    "UPDATE run_attempts SET status=?,error_class=?,usage_json=?,finished_at=?,lease_expires_at=NULL WHERE id=?",
                    (status, error_class, canonical_json(usage) if usage is not None else row["usage_json"], now, attempt_id),
                )
                conn.execute(
                    "UPDATE node_runs SET status=?,finished_at=?,updated_at=? WHERE id=?",
                    ("PRODUCED" if success else ("FAILED_RETRYABLE" if error_class == "retryable" else "FAILED_TERMINAL"), now, now, row["node_run_id"]),
                )
                conn.execute("COMMIT")
                return True
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def reconcile_attempts(self) -> int:
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                rows = conn.execute(
                    "SELECT id,node_run_id FROM run_attempts WHERE status IN ('leased','running') AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
                    (now,),
                ).fetchall()
                for row in rows:
                    conn.execute("UPDATE run_attempts SET status='queued',lease_owner=NULL,lease_expires_at=NULL,error_class='retryable' WHERE id=?", (row["id"],))
                    conn.execute("UPDATE node_runs SET status='READY',current_attempt_id=NULL,updated_at=? WHERE id=?", (now, row["node_run_id"]))
                conn.execute("COMMIT")
                return len(rows)
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def attempts(self, project_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if project_id:
                rows = conn.execute("SELECT * FROM run_attempts WHERE project_id=? ORDER BY created_at DESC", (project_id,))
            else:
                rows = conn.execute("SELECT * FROM run_attempts ORDER BY created_at DESC")
            return [dict(row) for row in rows]

    def add_artifact(
        self,
        project_id: str,
        artifact_id: str,
        path: Path,
        sha256: str,
        client_view_id: str | None = None,
        cycle_id: str | None = None,
        piece_id: str | None = None,
        mock: bool = False,
        *,
        status: str | None = None,
    ) -> str:
        if mock and (artifact_id.startswith("D_") or client_view_id):
            raise ValueError("演示产物不能生成正式客户视图")
        now = utc_now()
        final_status = status or ("exported" if artifact_id.startswith("D_") else "produced")
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                previous = conn.execute(
                    """SELECT * FROM artifacts WHERE project_id=? AND artifact_id=?
                       AND cycle_id IS ? AND piece_id IS ? AND status NOT IN ('superseded','deleted')
                       ORDER BY version DESC LIMIT 1""",
                    (project_id, artifact_id, cycle_id, piece_id),
                ).fetchone()
                if previous and previous["sha256"] == sha256 and previous["path"] == str(path.resolve()):
                    conn.execute("COMMIT")
                    return previous["id"]
                version = (previous["version"] + 1) if previous else 1
                if previous:
                    conn.execute("UPDATE artifacts SET status='superseded',superseded_at=? WHERE id=?", (now, previous["id"]))
                row_id = "art_" + uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO artifacts(
                        id,project_id,artifact_id,cycle_id,piece_id,path,sha256,bytes,version,status,
                        mock,client_view_id,exported_at,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row_id, project_id, artifact_id, cycle_id, piece_id, str(path.resolve()), sha256,
                        path.stat().st_size if path.exists() else 0, version, final_status, int(mock),
                        client_view_id, now if client_view_id else None, now,
                    ),
                )
                conn.execute("COMMIT")
                return row_id
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def artifacts(self, project_id: str, *, client_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM artifacts WHERE project_id=? AND status NOT IN ('superseded','deleted')"
        params: list[Any] = [project_id]
        if client_only:
            sql += " AND artifact_id GLOB 'D_*' AND client_view_id IS NOT NULL AND mock=0"
        sql += " ORDER BY created_at,artifact_id"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params)]

    def artifact(self, project_id: str, artifact_id: str, *, formal_only: bool = False) -> dict[str, Any] | None:
        sql = "SELECT * FROM artifacts WHERE project_id=? AND artifact_id=? AND status NOT IN ('superseded','deleted')"
        if formal_only:
            sql += " AND mock=0"
        sql += " ORDER BY version DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, (project_id, artifact_id)).fetchone()
            return dict(row) if row else None

    def current_manifest(self, project_id: str, artifact_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        items = self.artifacts(project_id)
        allowed = set(artifact_ids) if artifact_ids else None
        return {
            item["artifact_id"]: {"sha256": item["sha256"], "bytes": item["bytes"], "mock": item["mock"]}
            for item in items if allowed is None or item["artifact_id"] in allowed
        }

    def create_confirmation(
        self,
        project_id: str,
        confirm_id: str,
        piece_id: str,
        deadline_at: str | None = None,
        touched_count: int = 0,
        target_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        del touched_count
        target = self.current_manifest(project_id, target_artifact_ids)
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM confirmations WHERE project_id=? AND piece_id=? AND confirm_id=? ORDER BY revision DESC LIMIT 1",
                (project_id, piece_id, confirm_id),
            ).fetchone()
            if row and row["status"] == "pending" and json.loads(row["target_sha_manifest"]) == target:
                return dict(row)
            revision = (row["revision"] + 1) if row else 1
            if row and row["status"] != "invalidated":
                conn.execute("UPDATE confirmations SET status='invalidated',updated_at=? WHERE id=?", (now, row["id"]))
            confirm_row_id = "cfm_" + uuid.uuid4().hex
            conn.execute(
                """INSERT INTO confirmations(
                    id,project_id,piece_id,confirm_id,revision,target_sha_manifest,status,deadline_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,'pending',?,?,?)""",
                (confirm_row_id, project_id, piece_id, confirm_id, revision, canonical_json(target), deadline_at, now, now),
            )
        return next(item for item in self.confirmations(project_id, include_history=True) if item["id"] == confirm_row_id)

    def confirmations(self, project_id: str, *, include_history: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM confirmations WHERE project_id=?"
        if not include_history:
            sql += " AND status <> 'invalidated'"
        sql += " ORDER BY confirm_id,revision DESC"
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, (project_id,))]
        for row in rows:
            row["decision"] = None if row["status"] == "pending" else row["status"]
            row["target_sha_manifest"] = json.loads(row["target_sha_manifest"])
        return rows

    def decide_confirmation(
        self,
        project_id: str,
        confirm_id: str,
        piece_id: str,
        decision: str,
        note: str = "",
        revise_scope: str | None = None,
        actor_type: str = "client",
        *,
        revision: int | None = None,
        attribution: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"ok", "revise", "pause"}:
            raise ValueError("非法确认决定")
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM confirmations WHERE project_id=? AND piece_id=? AND confirm_id=? AND status <> 'invalidated' ORDER BY revision DESC LIMIT 1",
                    (project_id, piece_id, confirm_id),
                ).fetchone()
                if not row:
                    raise KeyError(confirm_id)
                if revision is not None and row["revision"] != revision:
                    raise RuntimeError("CONFIRMATION_REVISION_CONFLICT")
                if row["status"] != "pending":
                    if row["status"] == decision:
                        conn.execute("COMMIT")
                        return dict(row)
                    raise RuntimeError("CONFIRMATION_ALREADY_DECIDED")
                conn.execute("UPDATE confirmations SET status=?,decided_at=?,attribution=?,updated_at=? WHERE id=?", (decision, now, attribution, now, row["id"]))
                decision_id = "dec_" + uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO decisions(
                        id,project_id,piece_id,kind,point_or_gate,target_sha_manifest,revision,decision,
                        actor,actor_type,note_free_text,revise_scope,attribution,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        decision_id, project_id, piece_id, "client_confirm", confirm_id,
                        row["target_sha_manifest"], row["revision"], decision, actor or actor_type,
                        actor_type, note, revise_scope, attribution, now,
                    ),
                )
                if decision == "revise" and attribution in {"client_taste_change", "client_scope_expansion"}:
                    conn.execute("UPDATE orders SET revise_used=revise_used+1,updated_at=? WHERE project_id=?", (now, project_id))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self.audit(project_id, actor or actor_type, actor_type, "client_confirmation", confirm_id, {"decision": decision, "revision": row["revision"], "revise_scope": revise_scope, "note": note})
        return next(item for item in self.confirmations(project_id, include_history=True) if item["id"] == row["id"])

    def invalidate_confirmations(self, project_id: str, confirm_ids: list[str], reason: str) -> int:
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM confirmations WHERE project_id=? AND confirm_id IN ({','.join('?' for _ in confirm_ids)}) AND status <> 'invalidated'",
                (project_id, *confirm_ids),
            ).fetchall()
            for row in rows:
                conn.execute("UPDATE confirmations SET status='invalidated',updated_at=? WHERE id=?", (now, row["id"]))
                existing = conn.execute("SELECT MAX(revision) FROM decisions WHERE project_id=? AND piece_id=? AND kind='client_confirm' AND point_or_gate=?", (project_id, row["piece_id"], row["confirm_id"])).fetchone()[0] or 0
                conn.execute(
                    """INSERT INTO decisions(
                        id,project_id,piece_id,kind,point_or_gate,target_sha_manifest,revision,decision,
                        actor,actor_type,note_free_text,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("dec_" + uuid.uuid4().hex, project_id, row["piece_id"], "client_confirm", row["confirm_id"], row["target_sha_manifest"], existing + 1, "revoked", "system", "system", reason, now),
                )
        if rows:
            self.audit(project_id, "system", "system", "confirmations_invalidated", ",".join(confirm_ids), {"reason": reason, "count": len(rows)})
        return len(rows)

    def notify(self, project_id: str, kind: str, channel: str, payload: str, piece_id: str | None = None) -> None:
        now = utc_now()
        notification_id = "ntf_" + uuid.uuid4().hex
        outbox_id = "out_" + uuid.uuid4().hex
        payload_json = canonical_json({"message": payload})
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """INSERT INTO notifications(
                        id,project_id,piece_id,confirmation_id,channel,recipient_ref,template_id,payload_json,
                        status,retry_count,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (notification_id, project_id, piece_id, kind if kind in {"C1", "C2"} else None, channel if channel in {"in_app", "feishu", "sms", "wechat", "email"} else "in_app", "client", kind, payload_json, "sent", 0, now),
                )
                conn.execute(
                    """INSERT INTO events_outbox(
                        id,project_id,piece_id,kind,payload_json,scheduled_at,sent_at,delivery_status,
                        retry_count,confirmation_id,idempotency_key,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (outbox_id, project_id, piece_id, kind, payload_json, now, now, "delivered", 0, kind if kind in {"C1", "C2"} else None, f"{project_id}:{kind}:{notification_id}", now),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self.audit(project_id, "system", "system", "notification_sent", kind, {"channel": channel, "digest": hashlib.sha256(payload.encode()).hexdigest()})

    def notifications(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM notifications WHERE project_id=? ORDER BY created_at", (project_id,))]

    def add_internal_review(
        self,
        project_id: str,
        gate_id: str,
        decision: str,
        reviewer: str,
        evidence_path: str,
        stdout: str,
        cycle_id: str | None = None,
        piece_id: str | None = None,
        *,
        evidence_artifact_id: str | None = None,
        check_token: str | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        del cycle_id
        now = utc_now()
        manifest = manifest or self.current_manifest(project_id)
        mapped = "allowed" if decision.upper() == "ALLOWED" else "blocked"
        with self._write_lock, self._connect() as conn:
            revision = (conn.execute("SELECT COALESCE(MAX(revision),0)+1 FROM decisions WHERE project_id=? AND kind='internal_review' AND point_or_gate=?", (project_id, gate_id)).fetchone()[0])
            conn.execute(
                """INSERT INTO decisions(
                    id,project_id,piece_id,kind,point_or_gate,target_sha_manifest,revision,decision,actor,
                    actor_type,evidence_artifact_id,evidence_sha256,check_token,check_result_hash,
                    requires_hashes,produces_hashes,gate_stdout,note_free_text,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    "dec_" + uuid.uuid4().hex, project_id, piece_id, "internal_review", gate_id,
                    canonical_json(manifest), revision, mapped, reviewer, "internal_ops", evidence_artifact_id,
                    (manifest.get(evidence_artifact_id) or {}).get("sha256") if evidence_artifact_id else None,
                    check_token, hashlib.sha256(stdout.encode()).hexdigest(), canonical_json(manifest),
                    canonical_json(manifest), stdout, evidence_path, now,
                ),
            )
        self.audit(project_id, reviewer, "internal_ops", "gate_review", gate_id, {"decision": mapped, "stdout": stdout})

    def reviews(self, project_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM decisions WHERE kind='internal_review'"
        params: tuple[Any, ...] = ()
        if project_id:
            sql += " AND project_id=?"
            params = (project_id,)
        sql += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(sql, params)]
        for row in rows:
            row["gate_id"] = row["point_or_gate"]
            row["reviewer"] = row["actor"]
            row["decision"] = row["decision"].upper()
            row["evidence_path"] = row.get("note_free_text") or ""
        return rows

    def gate_allowed(self, project_id: str, gate_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT decision FROM decisions WHERE project_id=? AND kind='internal_review' AND point_or_gate=? ORDER BY revision DESC LIMIT 1",
                (project_id, gate_id),
            ).fetchone()
            return bool(row and row["decision"] == "allowed")

    def add_asset(self, project_id: str, orig_name: str, stored_name: str, mime: str, size: int, digest: str, store_id: str = "store_main") -> str:
        asset_id = "asset_" + uuid.uuid4().hex[:16]
        with self._write_lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO assets(
                    id,project_id,store_id,original_name,stored_name,relative_path,mime,bytes,sha256,rights_status,uploaded_at
                ) VALUES(?,?,?,?,?,?,?,?,?,'pending',?)""",
                (asset_id, project_id, store_id, orig_name, stored_name, f"assets/{stored_name}", mime, size, digest, utc_now()),
            )
        self.audit(project_id, "client", "client", "asset_uploaded", asset_id, {"mime": mime, "bytes": size, "sha256": digest})
        return asset_id

    def assets(self, project_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM assets WHERE project_id=?"
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute(sql + " ORDER BY uploaded_at", (project_id,))]
            for item in rows:
                item["orig_name"] = item["original_name"]
                item["used_in"] = [r[0] for r in conn.execute("SELECT artifact_id FROM asset_usage WHERE asset_id=?", (item["id"],))]
        return rows

    def bind_asset_evidence(self, project_id: str, planned_asset_id: str, asset_id: str, evidence_type: str) -> None:
        allowed = {
            "menu_photo", "price_board_photo", "storefront_photo", "interior_photo", "product_photo",
            "dish_photo", "service_process_photo", "drama_scene_reference", "character_reference",
            "presenter_portrait", "alcohol_evidence", "other",
        }
        if evidence_type not in allowed or not planned_asset_id.startswith("asset_"):
            raise ValueError("素材证据绑定无效")
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO asset_evidence_bindings(project_id,planned_asset_id,asset_id,evidence_type,created_at) VALUES(?,?,?,?,?)",
                (project_id, planned_asset_id, asset_id, evidence_type, utc_now()),
            )

    def evidence_bindings(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM asset_evidence_bindings WHERE project_id=? ORDER BY created_at", (project_id,)
            )]

    def set_asset_rights(self, project_id: str, asset_id: str, status: str) -> None:
        if status not in {"pending", "verified", "rejected", "revoked"}:
            raise ValueError(status)
        with self._write_lock, self._connect() as conn:
            conn.execute("UPDATE assets SET rights_status=? WHERE id=? AND project_id=?", (status, asset_id, project_id))

    def remove_asset(self, project_id: str, asset_id: str) -> dict[str, Any] | None:
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM assets WHERE id=? AND project_id=? AND deleted_at IS NULL", (asset_id, project_id)).fetchone()
                if not row:
                    conn.execute("COMMIT")
                    return None
                used = conn.execute("SELECT 1 FROM asset_usage WHERE asset_id=? LIMIT 1", (asset_id,)).fetchone()
                if used:
                    raise RuntimeError("ASSET_IN_USE")
                conn.execute("UPDATE assets SET deleted_at=? WHERE id=?", (now, asset_id))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self.audit(project_id, "client", "client", "asset_deleted", asset_id, {"sha256": row["sha256"]})
        return dict(row)

    def add_authorizations(self, project_id: str, rows: list[dict[str, Any]]) -> list[str]:
        now, ids = utc_now(), []
        with self._write_lock, self._connect() as conn:
            for item in rows:
                auth_id = "auth_" + uuid.uuid4().hex[:16]
                ids.append(auth_id)
                conn.execute(
                    """INSERT INTO authorizations(
                        id,project_id,type,person_ref,asset_ref,purpose,platforms_json,valid_from,valid_to,
                        reviewer,credential_no,status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        auth_id, project_id, item["type"], item.get("person_ref"), item.get("asset_ref"),
                        item["purpose"], canonical_json(item.get("platforms", [])), item["valid_from"], item["valid_to"],
                        item.get("reviewer"), item.get("credential_no"), item.get("status", "pending"), now,
                    ),
                )
        return ids

    def authorizations(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM authorizations WHERE project_id=? ORDER BY created_at", (project_id,))]
        for row in rows:
            row["platforms"] = json.loads(row.pop("platforms_json"))
        return rows

    def verify_authorizations(self, project_id: str, reviewer: str) -> int:
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            cur = conn.execute("UPDATE authorizations SET status='verified',reviewer=? WHERE project_id=? AND revoked_at IS NULL", (reviewer, project_id))
            conn.execute("UPDATE assets SET rights_status='verified' WHERE project_id=? AND deleted_at IS NULL", (project_id,))
        self.audit(project_id, reviewer, "internal_ops", "authorizations_verified", project_id, {"count": cur.rowcount, "at": now})
        return cur.rowcount

    def import_insights(self, project_id: str, items: list[dict[str, str]], actor: str) -> int:
        if len(items) < 3:
            raise ValueError("至少导入 3 条已核验洞察")
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            for item in items:
                conn.execute(
                    "INSERT INTO insights(id,project_id,title,source_url,source_name,finding,verified_at,imported_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    ("ins_" + uuid.uuid4().hex, project_id, item["title"], item["source_url"], item["source_name"], item["finding"], item["verified_at"], actor, now),
                )
        self.audit(project_id, actor, "internal_ops", "insights_imported", project_id, {"count": len(items)})
        return len(items)

    def insights(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM insights WHERE project_id=? ORDER BY created_at", (project_id,))]

    def add_verification_task(self, project_id: str, field_name: str, note: str) -> str:
        task_id = "verify_" + uuid.uuid4().hex[:20]
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO verification_tasks(id,project_id,field_name,note,created_at) VALUES(?,?,?,?,?)",
                (task_id, project_id, field_name, note, utc_now()),
            )
        self.audit(project_id, "system", "system", "verification_task_created", field_name, {"task_id": task_id})
        return task_id

    def verification_tasks(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM verification_tasks WHERE project_id=? ORDER BY created_at", (project_id,)
            )]

    def freeze_facts(self, project_id: str, actor: str) -> dict[str, Any]:
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM facts_revisions WHERE project_id=? ORDER BY rev_no DESC LIMIT 1", (project_id,)).fetchone()
            if not row:
                raise KeyError(project_id)
            if not row["frozen_at"]:
                conn.execute("UPDATE facts_revisions SET frozen_at=?,frozen_by=? WHERE id=?", (now, actor, row["id"]))
        self.audit(project_id, actor, "internal_ops", "facts_frozen", row["id"], {"sha256": row["content_sha"]})
        result = dict(row)
        result["frozen_at"] = result["frozen_at"] or now
        return result

    def facts_revision(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM facts_revisions WHERE project_id=? ORDER BY rev_no DESC LIMIT 1", (project_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["content"] = json.loads(result.pop("content_json"))
            return result

    def order(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE project_id=?", (project_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["scope"] = json.loads(result.pop("service_scope_json"))
            result["quote_snapshot"] = json.loads(result.pop("quote_snapshot_json"))
            result["revise_quota_left"] = max(0, result["revise_quota"] - result["revise_used"])
            return result

    def update_order(self, project_id: str, status: str, actor: str, evidence: str | None = None) -> dict[str, Any]:
        allowed = {"quoted", "accepted", "deposit_paid", "fully_paid", "refunding", "refunded", "cancelled", "written_off", "internal_test_exempt"}
        if status not in allowed:
            raise ValueError(status)
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status=?,accepted_at=CASE WHEN ?='accepted' THEN ? ELSE accepted_at END,accepted_by=CASE WHEN ?='accepted' THEN ? ELSE accepted_by END,payment_evidence_ref=COALESCE(?,payment_evidence_ref),updated_at=? WHERE project_id=?",
                (status, status, now, status, actor, evidence, now, project_id),
            )
        self.audit(project_id, actor, "internal_ops", "order_status_changed", project_id, {"status": status})
        return self.order(project_id) or {}

    def save_gate_check(self, project_id: str, gate_id: str, token: str, manifest: dict[str, Any], rc: int, output: str, ttl: int = 300) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO gate_checks(id,project_id,gate_id,token_hash,manifest_json,legacy_rc,legacy_stdout,issued_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?)",
                ("gck_" + uuid.uuid4().hex, project_id, gate_id, hashlib.sha256(token.encode()).hexdigest(), canonical_json(manifest), rc, output, utc_now(), utc_after(ttl)),
            )

    def consume_gate_check(self, project_id: str, gate_id: str, token: str) -> dict[str, Any] | None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM gate_checks WHERE project_id=? AND gate_id=? AND token_hash=? AND consumed_at IS NULL AND expires_at>=?",
                    (project_id, gate_id, token_hash, now),
                ).fetchone()
                if not row:
                    conn.execute("COMMIT")
                    return None
                conn.execute("UPDATE gate_checks SET consumed_at=? WHERE id=?", (now, row["id"]))
                conn.execute("COMMIT")
                result = dict(row)
                result["manifest"] = json.loads(result.pop("manifest_json"))
                return result
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def idempotency_get(self, scope: str, key: str, request_hash: str) -> tuple[int, dict[str, Any]] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM idempotency_keys WHERE scope=? AND key=?", (scope, key)).fetchone()
            if not row:
                return None
            if row["request_hash"] != request_hash:
                raise RuntimeError("IDEMPOTENCY_CONFLICT")
            return row["status_code"], json.loads(row["response_json"])

    def idempotency_put(self, scope: str, key: str, request_hash: str, status_code: int, response: dict[str, Any]) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO idempotency_keys(scope,key,request_hash,response_json,status_code,created_at) VALUES(?,?,?,?,?,?)",
                (scope, key, request_hash, canonical_json(response), status_code, utc_now()),
            )

    def save_download_token(self, token: str, project_id: str, relative_path: str, kind: str, ttl: int = 900, artifact_row_id: str | None = None) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO download_tokens(token_hash,project_id,artifact_row_id,relative_path,kind,expires_at,created_at) VALUES(?,?,?,?,?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), project_id, artifact_row_id, relative_path, kind, utc_after(ttl), utc_now()),
            )

    def resolve_download_token(self, token: str, project_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM download_tokens WHERE token_hash=? AND project_id=? AND expires_at>=?",
                (hashlib.sha256(token.encode()).hexdigest(), project_id, utc_now()),
            ).fetchone()
            return dict(row) if row else None

    def audit(self, project_id: str, actor: str, actor_type: str, action: str, target: str, detail: dict[str, Any]) -> str:
        if actor_type not in {"client", "internal_ops", "internal_ops_impersonation", "system"}:
            actor_type = "system"
        payload = canonical_json(detail)
        # 锁粒度按项目；避免多进程同时读取同一个 prev_hash 形成分叉链，
        # 同时保证 JSONL 顺序与 SQLite 提交顺序一致。
        with self.interprocess_lock(f"audit:{project_id}", blocking=True) as acquired:
            if not acquired:  # blocking=True 理论上不会发生，保留 fail-closed。
                raise RuntimeError("审计链互斥锁获取失败")
            # 时间戳必须在取得项目锁后生成；verify_audit 按 ts 排序。
            ts = utc_now()
            ledger: Path | None = None
            with self._write_lock, self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    previous = conn.execute(
                        "SELECT hash FROM audit_events WHERE project_id=? ORDER BY ts DESC,id DESC LIMIT 1",
                        (project_id,),
                    ).fetchone()
                    prev_hash = previous["hash"] if previous else None
                    chain_seed = prev_hash or "0" * 64
                    digest = hashlib.sha256(
                        f"{chain_seed}|{ts}|{actor}|{actor_type}|{action}|{target}|{payload}".encode("utf-8")
                    ).hexdigest()
                    conn.execute(
                        "INSERT INTO audit_events(id,project_id,ts,actor,actor_type,action,target,prev_hash,hash,detail_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        ("evt_" + uuid.uuid4().hex, project_id, ts, actor, actor_type, action, target, prev_hash, digest, payload, ts),
                    )
                    project = conn.execute(
                        "SELECT project_dir FROM projects WHERE id=?", (project_id,)
                    ).fetchone()
                    if project:
                        ledger = Path(project["project_dir"]) / "event_ledger.jsonl"
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            if ledger is not None:
                self._append_audit_ledger(
                    ledger,
                    {
                        "ts": ts,
                        "actor": actor,
                        "actor_type": actor_type,
                        "action": action,
                        "target": target,
                        "prev_hash": prev_hash,
                        "hash": digest,
                        "detail": detail,
                    },
                )
        return digest

    def verify_audit(self, project_id: str | None = None) -> bool:
        with self._connect() as conn:
            projects = [project_id] if project_id else [row[0] for row in conn.execute("SELECT DISTINCT project_id FROM audit_events")]
            for current_project in projects:
                previous = "0" * 64
                rows = conn.execute("SELECT * FROM audit_events WHERE project_id=? ORDER BY ts,id", (current_project,))
                for row in rows:
                    expected = hashlib.sha256(f"{previous}|{row['ts']}|{row['actor']}|{row['actor_type']}|{row['action']}|{row['target']}|{row['detail_json']}".encode("utf-8")).hexdigest()
                    expected_prev = None if previous == "0" * 64 else previous
                    if row["prev_hash"] != expected_prev or row["hash"] != expected:
                        return False
                    previous = row["hash"]
        return True

    def audit_events(self, project_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if project_id:
                rows = conn.execute("SELECT * FROM audit_events WHERE project_id=? ORDER BY ts DESC,id DESC LIMIT 500", (project_id,))
            else:
                rows = conn.execute("SELECT * FROM audit_events ORDER BY ts DESC,id DESC LIMIT 500")
            return [dict(row) for row in rows]

    def daily_metrics(self, projects_root: Path) -> dict[str, Any]:
        with self._connect() as conn:
            queued = conn.execute("SELECT COUNT(*) FROM run_attempts WHERE status='queued'").fetchone()[0]
            orphaned = conn.execute("SELECT COUNT(*) FROM run_attempts WHERE status IN ('leased','running') AND lease_expires_at<?", (utc_now(),)).fetchone()[0]
            pending_reviews = conn.execute("SELECT COUNT(*) FROM node_runs WHERE status='INTERNAL_REVIEW'").fetchone()[0]
            paid_waiting = conn.execute("SELECT COUNT(*) FROM node_runs WHERE status='WAITING_BOSS_APPROVAL'").fetchone()[0]
            notify_failed = conn.execute("SELECT COUNT(*) FROM notifications WHERE status='failed'").fetchone()[0]
        usage = __import__("shutil").disk_usage(projects_root)
        return {
            "service": "ok",
            "queue": {"queued": queued, "orphaned": orphaned},
            "reviews": {"pending": pending_reviews, "paid_waiting": paid_waiting},
            "notifications": {"failed": notify_failed},
            "disk": {"used_pct": round(usage.used / usage.total * 100, 1), "free_bytes": usage.free},
            "backup": {"status": "not_configured", "note": "首批真实付费客户前必须配置异机备份"},
            "provider": {"paid_api_enabled": config.PAID_API_ENABLED, "balance": "未接入"},
        }
