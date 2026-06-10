CREATE TABLE IF NOT EXISTS match_kit_membership (
    match_guid TEXT NOT NULL,
    test_guid  TEXT NOT NULL,
    PRIMARY KEY (match_guid, test_guid)
);
CREATE INDEX IF NOT EXISTS idx_mkm_test ON match_kit_membership(test_guid);
INSERT OR IGNORE INTO match_kit_membership (match_guid, test_guid)
SELECT match_guid, test_guid FROM matches
