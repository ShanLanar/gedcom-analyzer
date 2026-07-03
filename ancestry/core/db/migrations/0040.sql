-- 0040.sql — Sprint 6: Index-Redundanz bereinigen & Namenskollisionen reparieren
--
-- Zwei Migrationen definierten je einen Index unter EINEM Namen erneut mit
-- ABWEICHENDER Spaltenliste. Wegen CREATE INDEX IF NOT EXISTS gewann jeweils
-- die zuerst laufende Definition — die zweite (gewünschte) wurde still
-- verschluckt:
--   * idx_matches_test_guid: 0001 = (test_guid) VS 0035 = (test_guid, fetched_at DESC)
--   * idx_matches_test_cm:   0032 = (test_guid, shared_cm DESC) VS 0039 = (test_guid, shared_cm)
--
-- Ergebnis auf Bestands-DBs: der (test_guid, fetched_at DESC)-Index aus 0035
-- existiert NICHT, und idx_matches_test_guid ist bloß das einspaltige
-- (test_guid) — redundant, weil Präfix des Komposits idx_matches_test_cm.
--
-- Aufräumen: einspaltigen Redundanz-Index droppen, kanonisches Komposit
-- sicherstellen und den in 0035 beabsichtigten Index unter EINDEUTIGEM Namen
-- tatsächlich anlegen.

DROP INDEX IF EXISTS idx_matches_test_guid;

CREATE INDEX IF NOT EXISTS idx_matches_test_cm
    ON matches(test_guid, shared_cm DESC);

CREATE INDEX IF NOT EXISTS idx_matches_test_fetched
    ON matches(test_guid, fetched_at DESC);
