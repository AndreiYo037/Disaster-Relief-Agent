CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT,
    geometry TEXT,
    attributes TEXT,
    aliases TEXT
);
CREATE TABLE IF NOT EXISTS relationships (
    from_entity TEXT NOT NULL,
    to_entity TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS entity_states (
    state_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    state TEXT NOT NULL,
    attributes TEXT,
    valid_from TEXT NOT NULL,
    valid_until TEXT,
    source_event_id TEXT,
    confidence REAL DEFAULT 1.0,
    label TEXT DEFAULT 'known',
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_states_entity ON entity_states(entity_id);
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT, action TEXT, object_type TEXT, object_id TEXT, at TEXT, doc TEXT
);
CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY, source_id TEXT, raw_content TEXT, at TEXT, doc TEXT
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY, observation_id TEXT, subject TEXT, predicate TEXT, value TEXT, doc TEXT
);
CREATE TABLE IF NOT EXISTS verification_records (
    record_id TEXT PRIMARY KEY, subject TEXT, status TEXT, n_sources INTEGER, doc TEXT
);
CREATE TABLE IF NOT EXISTS permits (
    permit_id TEXT PRIMARY KEY, plan_id TEXT, status TEXT, approved_by TEXT, doc TEXT
);
CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY, status TEXT, via TEXT, doc TEXT
);
CREATE TABLE IF NOT EXISTS episodes (
    crisis_id TEXT PRIMARY KEY, started_at TEXT, doc TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    artifact_ref TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verification_runs (
    verification_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    support REAL NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    total_score INTEGER NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    confidence REAL NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS work_items (
    work_item_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_runs (
    agent_run_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    stage TEXT NOT NULL,
    retry_count INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    token_input INTEGER NOT NULL DEFAULT 0,
    token_output INTEGER NOT NULL DEFAULT 0,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_errors (
    error_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    stage TEXT NOT NULL,
    error_class TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    final_disposition TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback_requests (
    feedback_request_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    target_source_lane TEXT NOT NULL,
    cycle_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT NOT NULL DEFAULT 'json',
    checkpoint BLOB NOT NULL,
    metadata BLOB NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
CREATE TABLE IF NOT EXISTS writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT NOT NULL,
    value BLOB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
CREATE TABLE IF NOT EXISTS agent_checkpoints (
    run_id TEXT PRIMARY KEY,
    keyframe_id TEXT NOT NULL,
    state_json BLOB NOT NULL,
    recorded_at TEXT NOT NULL
);
