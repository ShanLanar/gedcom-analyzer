CREATE TABLE IF NOT EXISTS user_notes (
    match_guid  TEXT PRIMARY KEY,
    note        TEXT,
    updated_at  TEXT,
    FOREIGN KEY (match_guid) REFERENCES matches(match_guid)
)
