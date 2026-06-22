-- 0036.sql — F1: Endogamy Score Calculation
-- Pure additive migration: adds endogamy_score column to matches table
-- No breaking changes, backwards compatible

ALTER TABLE matches ADD COLUMN endogamy_score REAL DEFAULT 0.0;
