CREATE TABLE IF NOT EXISTS shared_matches (
    test_guid        TEXT NOT NULL,
    match_guid_a     TEXT NOT NULL,
    match_guid_b     TEXT NOT NULL,
    display_name_b   TEXT,
    shared_cm_b      REAL DEFAULT 0,
    shared_cm_ab     REAL DEFAULT 0,
    shared_segments_b INTEGER DEFAULT 0,
    relationship_b   TEXT,
    has_tree_b       INTEGER DEFAULT 0,
    fetched_at       TEXT,
    PRIMARY KEY (test_guid, match_guid_a, match_guid_b)
);

CREATE INDEX IF NOT EXISTS idx_sm_match_a
    ON shared_matches(test_guid, match_guid_a);
CREATE INDEX IF NOT EXISTS idx_sm_match_b
    ON shared_matches(test_guid, match_guid_b);
CREATE INDEX IF NOT EXISTS idx_sm_cm_b
    ON shared_matches(shared_cm_b DESC);

CREATE TABLE IF NOT EXISTS shared_matches_fetched (
    test_guid    TEXT NOT NULL,
    match_guid_a TEXT NOT NULL,
    fetched_at   TEXT,
    PRIMARY KEY (test_guid, match_guid_a)
)
