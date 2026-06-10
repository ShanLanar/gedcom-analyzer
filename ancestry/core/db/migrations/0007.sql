ALTER TABLE matches ADD COLUMN ancestors_fetched INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS match_ancestors (
    test_guid               TEXT NOT NULL,
    match_guid              TEXT NOT NULL,
    ancestor_name           TEXT,
    birth_year              TEXT,
    death_year              TEXT,
    is_male                 INTEGER DEFAULT 0,
    relationship_to_sample  TEXT,
    relationship_to_match   TEXT,
    kinship_path_sample     TEXT,
    kinship_path_match      TEXT,
    in_match_tree           INTEGER DEFAULT 0,
    amt_gid                 TEXT,
    PRIMARY KEY (test_guid, match_guid, ancestor_name, kinship_path_sample)
);
CREATE INDEX IF NOT EXISTS idx_anc_match ON match_ancestors(match_guid);
CREATE INDEX IF NOT EXISTS idx_anc_name  ON match_ancestors(ancestor_name);

CREATE TABLE IF NOT EXISTS match_birthplaces (
    test_guid     TEXT NOT NULL,
    match_guid    TEXT NOT NULL,
    side          TEXT,
    place_name    TEXT,
    coords        TEXT,
    person_count  INTEGER DEFAULT 0,
    PRIMARY KEY (test_guid, match_guid, side, place_name)
);
CREATE INDEX IF NOT EXISTS idx_bp_match ON match_birthplaces(match_guid);
CREATE INDEX IF NOT EXISTS idx_bp_place ON match_birthplaces(place_name)
