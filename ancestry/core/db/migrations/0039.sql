-- Sprint 5: user_prefs-Tabelle + Performance-Indexes
CREATE TABLE IF NOT EXISTS user_prefs (
    key         TEXT NOT NULL PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Performance-Indexes
CREATE INDEX IF NOT EXISTS idx_matches_kit_cm
    ON matches(kit_id, total_cm);

CREATE INDEX IF NOT EXISTS idx_shared_test_match
    ON shared_matches(test_guid, match_guid);
