-- V36: Endogamie-Score für DNA-Matches (F1)
-- Additive Migration: neue Spalte endogamy_score für Endogamie-Flagging

ALTER TABLE matches ADD COLUMN endogamy_score REAL DEFAULT 0.0;

-- Index für Endogamie-Abfragen
CREATE INDEX IF NOT EXISTS idx_matches_endogamy_score
    ON matches(endogamy_score DESC, shared_cm DESC);
