-- 0041.sql — Sprint 7: IBD2-Kennzeichnung für Segmente
--
-- IBD2-Regionen (fully identical regions, FIR) treten auf, wenn BEIDE
-- Chromosomen-Kopien übereinstimmen — praktisch nur bei Vollgeschwistern.
-- GEDmatch liefert diese Info und wir speichern sie optional pro Segment, damit
-- Vollgeschwister eindeutig von Halbgeschwistern/Großeltern (nur IBD1)
-- unterschieden werden können. Default 0 = IBD1/unbekannt (rückwärtskompatibel).

ALTER TABLE dna_segments ADD COLUMN is_ibd2 INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_dna_seg_ibd2
    ON dna_segments(test_guid, is_ibd2);
