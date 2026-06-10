ALTER TABLE persons ADD COLUMN gedmatch_kit_id TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_persons_gedmatch ON persons(gedmatch_kit_id);

CREATE TABLE IF NOT EXISTS gedmatch_matches (
    kit_id          TEXT NOT NULL,
    our_kit         TEXT NOT NULL,
    name            TEXT DEFAULT '',
    email           TEXT DEFAULT '',
    tags            TEXT DEFAULT '',
    sex             TEXT DEFAULT '',
    shared_cm       REAL DEFAULT 0,
    largest_segment REAL DEFAULT 0,
    gen_distance    REAL DEFAULT 0,
    x_cm            REAL DEFAULT 0,
    x_segments      INTEGER DEFAULT 0,
    source_platform TEXT DEFAULT '',
    snps            INTEGER DEFAULT 0,
    overlap         INTEGER DEFAULT 0,
    mt_haplogroup   TEXT DEFAULT '',
    y_haplogroup    TEXT DEFAULT '',
    fetched_at      TEXT DEFAULT '',
    PRIMARY KEY (kit_id, our_kit)
);
CREATE INDEX IF NOT EXISTS idx_gm_our_kit ON gedmatch_matches(our_kit);
CREATE INDEX IF NOT EXISTS idx_gm_platform ON gedmatch_matches(source_platform);
CREATE INDEX IF NOT EXISTS idx_gm_shared_cm ON gedmatch_matches(shared_cm DESC);
CREATE INDEX IF NOT EXISTS idx_gm_name ON gedmatch_matches(name)
