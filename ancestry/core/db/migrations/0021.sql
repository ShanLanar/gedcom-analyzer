CREATE TABLE IF NOT EXISTS entities (
    entity_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT DEFAULT '',
    notes       TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS source_webtrees (
    wt_id           TEXT PRIMARY KEY,
    given_name      TEXT DEFAULT '',
    surname         TEXT DEFAULT '',
    gender          TEXT DEFAULT '',
    birth_date      TEXT DEFAULT '',
    birth_place     TEXT DEFAULT '',
    death_date      TEXT DEFAULT '',
    death_place     TEXT DEFAULT '',
    father_wt_id    TEXT DEFAULT '',
    mother_wt_id    TEXT DEFAULT '',
    spouse_wt_ids   TEXT DEFAULT '',
    notes           TEXT DEFAULT '',
    raw_json        TEXT DEFAULT '',
    imported_at     TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_swt_name
    ON source_webtrees(surname, given_name);
CREATE INDEX IF NOT EXISTS idx_swt_birth
    ON source_webtrees(birth_place, birth_date);

CREATE TABLE IF NOT EXISTS source_matrikula_books (
    book_id     TEXT PRIMARY KEY,
    parish_id   TEXT NOT NULL,
    book_type   TEXT NOT NULL DEFAULT 'unbekannt',
    year_from   INTEGER,
    year_to     INTEGER,
    label       TEXT DEFAULT '',
    url         TEXT DEFAULT '',
    synced_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_smb_parish
    ON source_matrikula_books(parish_id);
CREATE INDEX IF NOT EXISTS idx_smb_years
    ON source_matrikula_books(year_from, year_to);

CREATE TABLE IF NOT EXISTS source_matrikula_entries (
    entry_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     TEXT NOT NULL,
    page_nr     INTEGER,
    entry_type  TEXT NOT NULL,
    event_date  TEXT DEFAULT '',
    event_year  INTEGER,
    person_name TEXT DEFAULT '',
    person2_name TEXT DEFAULT '',
    father_name TEXT DEFAULT '',
    mother_name TEXT DEFAULT '',
    village     TEXT DEFAULT '',
    notes       TEXT DEFAULT '',
    image_url   TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sme_book
    ON source_matrikula_entries(book_id);
CREATE INDEX IF NOT EXISTS idx_sme_year
    ON source_matrikula_entries(event_year);
CREATE INDEX IF NOT EXISTS idx_sme_name
    ON source_matrikula_entries(person_name);

CREATE TABLE IF NOT EXISTS source_anverwandte (
    anv_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_url TEXT DEFAULT '',
    name_raw    TEXT DEFAULT '',
    birth_year  INTEGER,
    death_year  INTEGER,
    relation    TEXT DEFAULT '',
    linked_to   TEXT DEFAULT '',
    extra_json  TEXT DEFAULT '',
    crawled_at  TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sanv_url
    ON source_anverwandte(profile_url)
    WHERE profile_url != '';
CREATE INDEX IF NOT EXISTS idx_sanv_name
    ON source_anverwandte(name_raw);

CREATE TABLE IF NOT EXISTS entity_assignments (
    assignment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       INTEGER NOT NULL,
    source_table    TEXT NOT NULL,
    source_row_id   TEXT NOT NULL,
    person_role     TEXT NOT NULL DEFAULT 'person',
    confidence      REAL DEFAULT 1.0,
    assigned_by     TEXT DEFAULT 'auto',
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE (source_table, source_row_id, person_role)
);
CREATE INDEX IF NOT EXISTS idx_ea_entity
    ON entity_assignments(entity_id);
CREATE INDEX IF NOT EXISTS idx_ea_source
    ON entity_assignments(source_table, source_row_id);
CREATE INDEX IF NOT EXISTS idx_ea_active
    ON entity_assignments(is_active);

CREATE TABLE IF NOT EXISTS entity_candidates (
    candidate_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table_a  TEXT NOT NULL,
    source_row_id_a TEXT NOT NULL,
    person_role_a   TEXT NOT NULL DEFAULT 'person',
    source_table_b  TEXT NOT NULL,
    source_row_id_b TEXT NOT NULL,
    person_role_b   TEXT NOT NULL DEFAULT 'person',
    confidence      REAL DEFAULT 0.0,
    evidence        TEXT DEFAULT '',
    status          TEXT DEFAULT 'pending',
    reviewed_at     TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE (source_table_a, source_row_id_a, person_role_a,
            source_table_b, source_row_id_b, person_role_b)
);
CREATE INDEX IF NOT EXISTS idx_ec_status
    ON entity_candidates(status)
