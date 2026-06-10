ALTER TABLE dna_kits ADD COLUMN source TEXT DEFAULT 'ancestry';
ALTER TABLE matches ADD COLUMN source TEXT DEFAULT 'ancestry';
ALTER TABLE matches ADD COLUMN country_code TEXT DEFAULT '';
ALTER TABLE matches ADD COLUMN mh_confidence_level TEXT DEFAULT '';

CREATE TABLE IF NOT EXISTS persons (
    person_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name  TEXT NOT NULL DEFAULT '',
    given_name      TEXT DEFAULT '',
    surname         TEXT DEFAULT '',
    gender          TEXT DEFAULT '',
    country_code    TEXT DEFAULT '',
    birth_year_est  INTEGER,
    gedcom_id       TEXT DEFAULT '',
    ancestry_uid    TEXT DEFAULT '',
    mh_member_id    TEXT DEFAULT '',
    identity_confidence REAL DEFAULT 1.0,
    identity_source     TEXT DEFAULT 'manual',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(canonical_name);
CREATE INDEX IF NOT EXISTS idx_persons_gedcom ON persons(gedcom_id);
CREATE INDEX IF NOT EXISTS idx_persons_mh ON persons(mh_member_id);

CREATE TABLE IF NOT EXISTS match_person_links (
    match_guid      TEXT NOT NULL,
    person_id       INTEGER NOT NULL,
    source          TEXT NOT NULL DEFAULT 'ancestry',
    confidence      REAL DEFAULT 1.0,
    linked_by       TEXT DEFAULT 'name',
    created_at      TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (match_guid, person_id)
);
CREATE INDEX IF NOT EXISTS idx_mpl_person ON match_person_links(person_id);
CREATE INDEX IF NOT EXISTS idx_mpl_source ON match_person_links(source);

CREATE TABLE IF NOT EXISTS person_shared_dna (
    person_id_a     INTEGER NOT NULL,
    person_id_b     INTEGER NOT NULL,
    source          TEXT NOT NULL,
    kit_guid        TEXT NOT NULL,
    shared_cm       REAL DEFAULT 0,
    shared_segments INTEGER DEFAULT 0,
    PRIMARY KEY (person_id_a, person_id_b, source, kit_guid)
);
CREATE INDEX IF NOT EXISTS idx_psd_a ON person_shared_dna(person_id_a);
CREATE INDEX IF NOT EXISTS idx_psd_b ON person_shared_dna(person_id_b);

CREATE TABLE IF NOT EXISTS mh_match_relationships (
    match_guid              TEXT NOT NULL,
    rel_set                 TEXT NOT NULL DEFAULT 'complete',
    relationship_type       INTEGER,
    relationship_class      TEXT DEFAULT '',
    relationship_degree     TEXT DEFAULT '',
    path_type               TEXT DEFAULT '',
    probability             REAL DEFAULT 0.0,
    mrca_type               INTEGER,
    mrca_class              TEXT DEFAULT '',
    PRIMARY KEY (match_guid, rel_set, relationship_type)
);
CREATE INDEX IF NOT EXISTS idx_mhr_match ON mh_match_relationships(match_guid)
