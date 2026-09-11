-- Finite declared repairs for a run (#27480 B). Numbering owned by seat 1/3.

CREATE TABLE run_repairs (
  run_id TEXT NOT NULL,
  repair_id TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  value_json TEXT NOT NULL,
  PRIMARY KEY (run_id, repair_id)
);
