CREATE TABLE IF NOT EXISTS dna_kits (
    guid          TEXT PRIMARY KEY,
    name          TEXT,
    test_type     TEXT,
    created_date  TEXT,
    is_owner      INTEGER DEFAULT 1,
    last_sync     TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    match_guid              TEXT PRIMARY KEY,
    test_guid               TEXT NOT NULL,
    display_name            TEXT,
    shared_cm               REAL DEFAULT 0,
    shared_segments         INTEGER DEFAULT 0,
    longest_segment         REAL DEFAULT 0,
    predicted_relationship  TEXT,
    confidence              TEXT,
    relationship_range      TEXT,
    has_hint                INTEGER DEFAULT 0,
    has_tree                INTEGER DEFAULT 0,
    tree_size               INTEGER DEFAULT 0,
    tree_id                 TEXT,
    starred                 INTEGER DEFAULT 0,
    note                    TEXT,
    custom_relationship     TEXT,
    ethnicity_regions       TEXT,
    last_login              TEXT,
    fetched_at              TEXT,
    raw_json                TEXT,
    match_cluster_code      TEXT DEFAULT '',
    created_date            INTEGER DEFAULT 0,
    tag_surname             TEXT DEFAULT '',
    tag_gender              TEXT DEFAULT '',
    tag_path                TEXT DEFAULT '',
    tags_json               TEXT DEFAULT '',
    meiosis                 INTEGER DEFAULT 0,
    ignored                 INTEGER DEFAULT 0,
    tree_status             TEXT    DEFAULT '',
    has_common_ancestor     INTEGER DEFAULT 0,
    match_ucdmid            TEXT    DEFAULT '',
    gender                  TEXT    DEFAULT '',
    ancestors_fetched       INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_matches_test_guid  ON matches(test_guid);
CREATE INDEX IF NOT EXISTS idx_matches_shared_cm  ON matches(shared_cm DESC);
CREATE INDEX IF NOT EXISTS idx_matches_relationship ON matches(predicted_relationship);
CREATE INDEX IF NOT EXISTS idx_matches_starred    ON matches(starred)
