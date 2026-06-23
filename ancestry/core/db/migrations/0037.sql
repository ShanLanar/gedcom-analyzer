CREATE TABLE IF NOT EXISTS pipeline_runs (
    source      TEXT PRIMARY KEY,
    last_run    TEXT,
    n_items     INTEGER DEFAULT 0
);
