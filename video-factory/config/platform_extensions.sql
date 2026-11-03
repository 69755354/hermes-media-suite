PRAGMA foreign_keys = ON;
-- > 执行者：codex

CREATE TABLE IF NOT EXISTS client_project_access (
    account_name TEXT NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY(account_name, project_id)
) STRICT;

CREATE TABLE IF NOT EXISTS project_billing (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE RESTRICT,
    billing_customer_id INTEGER NOT NULL CHECK (billing_customer_id > 0),
    billing_account_id INTEGER NOT NULL CHECK (billing_account_id > 0),
    billing_task_id INTEGER NOT NULL UNIQUE CHECK (billing_task_id > 0),
    task_type TEXT NOT NULL CHECK (task_type IN ('video','graphic','text','review','image','search')),
    estimated_points TEXT NOT NULL,
    settled_points TEXT,
    status TEXT NOT NULL CHECK (status IN ('created','reserved','settled','cancelled','settlement_failed','delivered')),
    delivery_id INTEGER,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS remote_production_jobs (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    remote_job_id TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
    remote_result_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE RESTRICT,
    quote_version INTEGER NOT NULL DEFAULT 1 CHECK (quote_version >= 1),
    quote_snapshot_json TEXT NOT NULL CHECK (json_valid(quote_snapshot_json)),
    service_scope_json TEXT NOT NULL CHECK (json_valid(service_scope_json)),
    revise_quota INTEGER NOT NULL DEFAULT 2 CHECK (revise_quota >= 0),
    revise_used INTEGER NOT NULL DEFAULT 0 CHECK (revise_used >= 0),
    amount_fen INTEGER NOT NULL DEFAULT 0 CHECK (amount_fen >= 0),
    currency TEXT NOT NULL DEFAULT 'CNY',
    status TEXT NOT NULL CHECK (status IN ('quoted','accepted','deposit_paid','fully_paid','refunding','refunded','cancelled','written_off','internal_test_exempt')),
    accepted_at TEXT,
    accepted_by TEXT,
    payment_evidence_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS authorizations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    person_ref TEXT,
    asset_ref TEXT,
    purpose TEXT NOT NULL,
    platforms_json TEXT NOT NULL CHECK (json_valid(platforms_json)),
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    revoked_at TEXT,
    reviewer TEXT,
    credential_no TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','verified','rejected','revoked')),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS facts_revisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rev_no INTEGER NOT NULL CHECK (rev_no >= 1),
    content_json TEXT NOT NULL CHECK (json_valid(content_json)),
    content_sha TEXT NOT NULL CHECK (length(content_sha) = 64),
    frozen_at TEXT,
    frozen_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, rev_no)
) STRICT;

CREATE TABLE IF NOT EXISTS confirmations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    piece_id TEXT NOT NULL,
    confirm_id TEXT NOT NULL CHECK (confirm_id IN ('C1','C2')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    target_sha_manifest TEXT NOT NULL CHECK (json_valid(target_sha_manifest)),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ok','revise','pause','invalidated')),
    deadline_at TEXT,
    decided_at TEXT,
    attribution TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (piece_id, project_id) REFERENCES pieces(id, project_id) ON DELETE CASCADE,
    UNIQUE(project_id, piece_id, confirm_id, revision)
) STRICT;

CREATE TABLE IF NOT EXISTS gate_checks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    gate_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
    manifest_json TEXT NOT NULL CHECK (json_valid(manifest_json)),
    legacy_rc INTEGER NOT NULL CHECK (legacy_rc IN (0,2,3)),
    legacy_stdout TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS idempotency_keys (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    response_json TEXT NOT NULL CHECK (json_valid(response_json)),
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(scope, key)
) STRICT;

CREATE TABLE IF NOT EXISTS download_tokens (
    token_hash TEXT PRIMARY KEY CHECK (length(token_hash) = 64),
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    artifact_row_id TEXT,
    relative_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS verification_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    field_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','cancelled')),
    note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS asset_evidence_bindings (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    planned_asset_id TEXT NOT NULL,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('menu_photo','price_board_photo','storefront_photo','interior_photo','product_photo','dish_photo','service_process_photo','drama_scene_reference','character_reference','presenter_portrait','alcohol_evidence','other')),
    created_at TEXT NOT NULL,
    PRIMARY KEY(project_id, planned_asset_id),
    UNIQUE(project_id, asset_id)
) STRICT;

CREATE TABLE IF NOT EXISTS insights (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    finding TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    imported_by TEXT NOT NULL,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS asset_usage (
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    artifact_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(asset_id, artifact_id)
) STRICT;

CREATE INDEX IF NOT EXISTS ix_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS ix_client_project_access_project ON client_project_access(project_id);
CREATE INDEX IF NOT EXISTS ix_project_billing_customer ON project_billing(billing_customer_id, created_at);
CREATE INDEX IF NOT EXISTS ix_remote_production_status ON remote_production_jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS ix_authorizations_project ON authorizations(project_id, status);
CREATE INDEX IF NOT EXISTS ix_confirmations_pending ON confirmations(project_id, status, confirm_id);
CREATE INDEX IF NOT EXISTS ix_gate_checks_pending ON gate_checks(project_id, gate_id, consumed_at);
CREATE INDEX IF NOT EXISTS ix_attempts_lease ON run_attempts(status, lease_expires_at, created_at);
CREATE INDEX IF NOT EXISTS ix_outbox_due ON events_outbox(delivery_status, scheduled_at);
