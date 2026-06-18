-- NER-Tabelle für Matricula: extrahierte Personen mit Rollen
-- Ergänzt source_matrikula_entries um Paten, Zeugen, Väter der Braut/Bräutigam etc.
CREATE TABLE IF NOT EXISTS matrikula_ner (
    ner_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id    INTEGER NOT NULL,
    book_id     TEXT NOT NULL,
    event_year  INTEGER,
    name_raw    TEXT NOT NULL,
    name_norm   TEXT DEFAULT '',
    koeln_code  TEXT DEFAULT '',
    rolle       TEXT NOT NULL,
    beruf       TEXT DEFAULT '',
    ort         TEXT DEFAULT '',
    geburtsname TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mner_entry  ON matrikula_ner(entry_id);
CREATE INDEX IF NOT EXISTS idx_mner_koeln  ON matrikula_ner(koeln_code);
CREATE INDEX IF NOT EXISTS idx_mner_rolle  ON matrikula_ner(rolle);
CREATE INDEX IF NOT EXISTS idx_mner_year   ON matrikula_ner(event_year);
CREATE INDEX IF NOT EXISTS idx_mner_book   ON matrikula_ner(book_id)
