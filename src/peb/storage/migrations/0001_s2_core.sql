-- S2 core store. Migration numbering is owned by seat 1/3; this is 0001 because
-- S1 had no migrations. Changing the numbering scheme is an interface amendment.

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  subject_session_id TEXT NOT NULL,
  status TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  preaction_protocol TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  manifest_hash TEXT NOT NULL,
  stop_generation INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE events (
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  event_id TEXT NOT NULL UNIQUE,
  ts TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  prev_hash TEXT,
  event_hash TEXT NOT NULL,
  PRIMARY KEY (run_id, seq)
);

CREATE TABLE grants (
  run_id TEXT NOT NULL,
  grant_id TEXT NOT NULL,
  grant_version INTEGER NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0,
  body_json TEXT NOT NULL,
  PRIMARY KEY (run_id, grant_id)
);

CREATE TABLE resources (
  run_id TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  kind TEXT NOT NULL,
  value_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, resource_id, revision)
);

CREATE TABLE approvals (
  approval_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  nonce TEXT NOT NULL UNIQUE,
  action_digest TEXT NOT NULL,
  consumed_at TEXT,
  body_json TEXT NOT NULL
);

CREATE TABLE receipts (
  receipt_id TEXT PRIMARY KEY,
  proposal_id TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL
);

CREATE TABLE checkpoints (
  run_id TEXT NOT NULL,
  event_count INTEGER NOT NULL,
  head_hash TEXT NOT NULL,
  manifest_hash TEXT NOT NULL,
  key_id TEXT NOT NULL,
  signature TEXT NOT NULL,
  exported_at TEXT NOT NULL,
  body_json TEXT NOT NULL,
  PRIMARY KEY (run_id, event_count)
);

CREATE TABLE commitments (
  commitment_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  body_json TEXT NOT NULL
);

CREATE INDEX idx_resources_run ON resources (run_id, resource_id);
CREATE INDEX idx_receipts_run ON receipts (run_id);
