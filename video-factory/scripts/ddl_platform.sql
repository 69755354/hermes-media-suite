-- > 执行者：codex｜对应架构 v2.0 §7.2、§7.7、§8.3、§8.4、§17.2
-- SQLite baseline migration: 0001_platform_contracts
-- 迁移器必须在独占维护窗执行本文件；失败即整体回滚并停止服务。

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS schema_version (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    version INTEGER NOT NULL CHECK (version >= 0),
    migration_id TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    checksum_sha256 TEXT
) STRICT;

INSERT INTO schema_version(singleton_id, version, migration_id, applied_at, checksum_sha256)
SELECT 1, 0, 'bootstrap', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), NULL
WHERE NOT EXISTS (SELECT 1 FROM schema_version WHERE singleton_id = 1);

-- 只允许从 version=0 进入本基线；避免 CREATE TABLE IF NOT EXISTS 被误当旧库升级。
CREATE TEMP TABLE _migration_0001_guard (
    ok INTEGER NOT NULL CHECK (ok = 1)
) STRICT;

INSERT INTO _migration_0001_guard(ok)
SELECT CASE
    WHEN version = 0
     AND NOT EXISTS (
         SELECT 1
         FROM sqlite_master
         WHERE type = 'table'
           AND name IN (
               'clients', 'projects', 'pieces', 'node_runs', 'run_attempts',
               'artifacts', 'decisions', 'events_outbox', 'assets', 'costs',
               'notifications', 'audit_events'
           )
     )
    THEN 1 ELSE 0
END
FROM schema_version
WHERE singleton_id = 1;

CREATE TABLE clients (
    id TEXT PRIMARY KEY,
    account_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'closed')),
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    project_dir TEXT NOT NULL UNIQUE,
    entry_type TEXT NOT NULL DEFAULT 'FULL_SERVICE'
        CHECK (entry_type IN ('FULL_SERVICE', 'CLIENT_COPY', 'TEST_RUN')),
    industry_path TEXT NOT NULL CHECK (industry_path = 'catering/hotpot'),
    stores_json TEXT NOT NULL CHECK (json_valid(stores_json)),
    offers_json TEXT NOT NULL CHECK (json_valid(offers_json)),
    prefs_json TEXT NOT NULL CHECK (json_valid(prefs_json)),
    wip_status TEXT NOT NULL DEFAULT 'queued'
        CHECK (wip_status IN ('queued', 'active', 'waiting_client', 'waiting_internal', 'completed', 'cancelled', 'expired')),
    owner TEXT,
    next_action TEXT,
    due_at TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (id, client_id)
) STRICT;

CREATE TABLE pieces (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    format TEXT NOT NULL
        CHECK (format IN ('VIDEO_SHORT', 'IMAGE_POST', 'WECHAT_CONTENT', 'LONG_FORM')),
    platform TEXT NOT NULL,
    ordinal INTEGER NOT NULL DEFAULT 1 CHECK (ordinal = 1),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id),
    UNIQUE (id, project_id)
) STRICT;

CREATE TABLE node_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    cycle_id TEXT,
    piece_id TEXT,
    status TEXT NOT NULL
        CHECK (status IN (
            'BLOCKED_UPSTREAM', 'READY', 'RUNNING', 'PRODUCED',
            'INTERNAL_REVIEW', 'CLIENT_CONFIRM', 'GATE_CHECKING', 'SIGNED_OFF',
            'FAILED_RETRYABLE', 'FAILED_TERMINAL', 'WAITING_BOSS_APPROVAL',
            'ROLLED_BACK', 'WAITING_CLIENT_INFO', 'PAUSED_BY_CLIENT',
            'CANCELLED_BY_CLIENT', 'ABANDONED', 'EXPIRED'
        )),
    current_attempt_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (piece_id, project_id) REFERENCES pieces(id, project_id) ON DELETE CASCADE,
    UNIQUE (id, project_id)
) STRICT;

CREATE UNIQUE INDEX uq_node_runs_scope
ON node_runs(project_id, node_id, COALESCE(cycle_id, ''), COALESCE(piece_id, ''));

CREATE TABLE run_attempts (
    id TEXT PRIMARY KEY,
    node_run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
    status TEXT NOT NULL
        CHECK (status IN ('queued', 'leased', 'running', 'succeeded', 'failed', 'cancelled', 'expired')),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    lease_owner TEXT,
    lease_expires_at TEXT,
    provider_task_id TEXT,
    error_class TEXT
        CHECK (error_class IS NULL OR error_class IN (
            'retryable', 'non_retryable', 'needs_human',
            'needs_payment', 'rate_limited', 'auth_expired'
        )),
    usage_json TEXT CHECK (usage_json IS NULL OR json_valid(usage_json)),
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (node_run_id, project_id) REFERENCES node_runs(id, project_id) ON DELETE CASCADE,
    UNIQUE (id, project_id),
    UNIQUE (node_run_id, attempt_no),
    UNIQUE (project_id, request_hash)
) STRICT;

CREATE TRIGGER trg_run_attempt_cancel_is_terminal
BEFORE UPDATE OF status ON run_attempts
FOR EACH ROW
WHEN OLD.status = 'cancelled' AND NEW.status <> 'cancelled'
BEGIN
    SELECT RAISE(ABORT, 'cancelled attempt is terminal');
END;

CREATE TRIGGER trg_node_run_cancel_is_terminal
BEFORE UPDATE OF status ON node_runs
FOR EACH ROW
WHEN OLD.status = 'CANCELLED_BY_CLIENT' AND NEW.status <> 'CANCELLED_BY_CLIENT'
BEGIN
    SELECT RAISE(ABORT, 'cancelled node run is terminal');
END;

CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL CHECK (artifact_id GLOB 'A_*' OR artifact_id GLOB 'D_*'),
    cycle_id TEXT,
    piece_id TEXT,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    bytes INTEGER NOT NULL CHECK (bytes >= 0),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    producer_attempt_id TEXT,
    status TEXT NOT NULL DEFAULT 'produced'
        CHECK (status IN ('produced', 'validated', 'exported', 'superseded', 'deleted', 'blocked')),
    superseded_at TEXT,
    mock INTEGER NOT NULL DEFAULT 0 CHECK (mock IN (0, 1)),
    client_view_id TEXT CHECK (client_view_id IS NULL OR client_view_id GLOB 'D_*'),
    download_token TEXT UNIQUE,
    download_token_expires_at TEXT,
    exported_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (piece_id, project_id) REFERENCES pieces(id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (producer_attempt_id, project_id) REFERENCES run_attempts(id, project_id) ON DELETE RESTRICT,
    CHECK (mock = 0 OR download_token IS NULL),
    CHECK (download_token IS NULL OR client_view_id IS NOT NULL),
    CHECK (download_token IS NULL OR download_token_expires_at IS NOT NULL)
) STRICT;

CREATE UNIQUE INDEX uq_artifacts_scope_version
ON artifacts(project_id, artifact_id, COALESCE(cycle_id, ''), COALESCE(piece_id, ''), version);

CREATE INDEX ix_artifacts_formal_client_views
ON artifacts(project_id, client_view_id, piece_id)
WHERE mock = 0 AND client_view_id IS NOT NULL AND status IN ('exported', 'validated');

CREATE TABLE decisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    piece_id TEXT,
    kind TEXT NOT NULL
        CHECK (kind IN ('client_confirm', 'internal_review', 'paid_authorization', 'publish_authorization')),
    point_or_gate TEXT NOT NULL,
    target_sha_manifest TEXT NOT NULL CHECK (json_valid(target_sha_manifest)),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    decision TEXT NOT NULL CHECK (decision IN ('ok', 'revise', 'pause', 'allowed', 'blocked', 'revoked')),
    actor TEXT NOT NULL,
    actor_type TEXT NOT NULL
        CHECK (actor_type IN ('client', 'internal_ops', 'internal_ops_impersonation', 'system')),
    evidence_artifact_id TEXT,
    evidence_sha256 TEXT CHECK (evidence_sha256 IS NULL OR length(evidence_sha256) = 64),
    check_token TEXT,
    check_token_issued_at TEXT,
    check_result_hash TEXT CHECK (check_result_hash IS NULL OR length(check_result_hash) = 64),
    requires_hashes TEXT CHECK (requires_hashes IS NULL OR json_valid(requires_hashes)),
    produces_hashes TEXT CHECK (produces_hashes IS NULL OR json_valid(produces_hashes)),
    gate_stdout TEXT,
    note_free_text TEXT,
    revise_scope TEXT,
    attribution TEXT
        CHECK (attribution IS NULL OR attribution IN (
            'our_error', 'client_fact_correction', 'provider_failure',
            'client_taste_change', 'client_scope_expansion'
        )),
    supersedes_decision_id TEXT REFERENCES decisions(id) ON DELETE RESTRICT,
    invalidated_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (piece_id, project_id) REFERENCES pieces(id, project_id) ON DELETE CASCADE,
    UNIQUE (project_id, piece_id, kind, point_or_gate, revision)
) STRICT;

CREATE INDEX ix_decisions_current_target
ON decisions(project_id, piece_id, kind, point_or_gate, revision DESC);

CREATE UNIQUE INDEX uq_decisions_scope_revision
ON decisions(project_id, COALESCE(piece_id, ''), kind, point_or_gate, revision);

CREATE TABLE events_outbox (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    piece_id TEXT,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    scheduled_at TEXT NOT NULL,
    sent_at TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (delivery_status IN ('pending', 'sending', 'delivered', 'failed', 'dead_letter', 'cancelled')),
    provider_message_id TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    confirmation_id TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY (piece_id, project_id) REFERENCES pieces(id, project_id) ON DELETE CASCADE
) STRICT;

CREATE TABLE assets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    store_id TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    mime TEXT NOT NULL,
    bytes INTEGER NOT NULL CHECK (bytes > 0),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    rights_status TEXT NOT NULL
        CHECK (rights_status IN ('pending', 'verified', 'rejected', 'revoked')),
    uploaded_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE (project_id, stored_name),
    UNIQUE (project_id, sha256)
) STRICT;

CREATE TABLE costs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    piece_id TEXT,
    provider TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    provider_task_id TEXT,
    amount_fen INTEGER CHECK (amount_fen IS NULL OR amount_fen >= 0),
    currency TEXT NOT NULL DEFAULT 'CNY',
    status TEXT NOT NULL
        CHECK (status IN (
            'authorized', 'committed', 'charged', 'delivered',
            'delivery_failed_charged', 'reversed', 'refunded'
        )),
    usage_json TEXT CHECK (usage_json IS NULL OR json_valid(usage_json)),
    authorized_by TEXT NOT NULL,
    authorized_at TEXT NOT NULL,
    parent_cost_id TEXT REFERENCES costs(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (piece_id, project_id) REFERENCES pieces(id, project_id) ON DELETE RESTRICT,
    UNIQUE (provider, request_hash)
) STRICT;

CREATE TABLE notifications (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    piece_id TEXT,
    confirmation_id TEXT,
    channel TEXT NOT NULL CHECK (channel IN ('in_app', 'feishu', 'sms', 'wechat', 'email')),
    recipient_ref TEXT NOT NULL,
    template_id TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'sent', 'delivered', 'failed', 'cancelled')),
    provider_message_id TEXT,
    sent_at TEXT,
    delivered_at TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (piece_id, project_id) REFERENCES pieces(id, project_id) ON DELETE CASCADE
) STRICT;

CREATE TABLE audit_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_type TEXT NOT NULL
        CHECK (actor_type IN ('client', 'internal_ops', 'internal_ops_impersonation', 'system')),
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    prev_hash TEXT CHECK (prev_hash IS NULL OR length(prev_hash) = 64),
    hash TEXT NOT NULL CHECK (length(hash) = 64),
    detail_json TEXT NOT NULL CHECK (json_valid(detail_json)),
    created_at TEXT NOT NULL,
    UNIQUE (project_id, hash)
) STRICT;

CREATE INDEX ix_audit_events_project_order ON audit_events(project_id, ts, id);

CREATE TRIGGER trg_audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

CREATE TRIGGER trg_audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

-- 补 node_runs.current_attempt_id 的循环外键；表定义顺序要求迁移尾部增加。
CREATE TRIGGER trg_node_runs_current_attempt_scope_insert
BEFORE INSERT ON node_runs
FOR EACH ROW
WHEN NEW.current_attempt_id IS NOT NULL
     AND NOT EXISTS (
         SELECT 1 FROM run_attempts
         WHERE id = NEW.current_attempt_id AND project_id = NEW.project_id
     )
BEGIN
    SELECT RAISE(ABORT, 'current_attempt_id scope mismatch');
END;

CREATE TRIGGER trg_node_runs_current_attempt_scope_update
BEFORE UPDATE OF current_attempt_id ON node_runs
FOR EACH ROW
WHEN NEW.current_attempt_id IS NOT NULL
     AND NOT EXISTS (
         SELECT 1 FROM run_attempts
         WHERE id = NEW.current_attempt_id AND project_id = NEW.project_id
     )
BEGIN
    SELECT RAISE(ABORT, 'current_attempt_id scope mismatch');
END;

UPDATE schema_version
SET version = 1,
    migration_id = '0001_platform_contracts',
    applied_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    checksum_sha256 = NULL
WHERE singleton_id = 1 AND version = 0;

DROP TABLE _migration_0001_guard;

PRAGMA user_version = 1;

COMMIT;
