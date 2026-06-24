-- Sprint 5: user_prefs-Tabelle + Performance-Index
CREATE TABLE IF NOT EXISTS user_prefs (
    key         TEXT NOT NULL PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Performance-Index auf matches (test_guid + shared_cm für Filter-Queries)
CREATE INDEX IF NOT EXISTS idx_matches_test_cm
    ON matches(test_guid, shared_cm);
