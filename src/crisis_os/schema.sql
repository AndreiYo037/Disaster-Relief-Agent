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
