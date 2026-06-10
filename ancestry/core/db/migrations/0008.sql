ALTER TABLE matches ADD COLUMN pedigree_fetched INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS match_pedigree (
    test_guid     TEXT NOT NULL,
    match_guid    TEXT NOT NULL,
    generation    INTEGER,
    ahnen_path    TEXT,
    person_id     TEXT,
    given_name    TEXT,
    surname       TEXT,
    is_male       INTEGER DEFAULT 0,
    birth_year    TEXT,
    birth_date    TEXT,
    birth_place   TEXT,
    death_year    TEXT,
    death_date    TEXT,
    death_place   TEXT,
    PRIMARY KEY (test_guid, match_guid, ahnen_path)
);
CREATE INDEX IF NOT EXISTS idx_ped_match ON match_pedigree(match_guid);
CREATE INDEX IF NOT EXISTS idx_ped_surname ON match_pedigree(surname)
