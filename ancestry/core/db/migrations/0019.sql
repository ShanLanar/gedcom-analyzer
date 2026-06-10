CREATE TABLE IF NOT EXISTS gedmatch_bridge (
    gedmatch_kit_id TEXT NOT NULL,
    match_guid      TEXT NOT NULL,
    confidence      REAL DEFAULT 0.0,
    linked_at       TEXT DEFAULT '',
    PRIMARY KEY (gedmatch_kit_id, match_guid)
);
CREATE INDEX IF NOT EXISTS idx_gb_match
    ON gedmatch_bridge(match_guid)
