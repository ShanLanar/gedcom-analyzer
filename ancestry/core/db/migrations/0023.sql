-- Zeitstempel für inkrementellen Pedigree-/Ancestors-Refresh.
-- Bisher war pedigree_fetched/ancestors_fetched nur ein Boolean (0/1) ohne
-- Information, WANN geholt wurde. Damit ließ sich kein "älter als N Tage"-
-- Update bauen. Die *_at-Spalten halten den ISO-8601-UTC-Zeitstempel des
-- letzten erfolgreichen Abrufs (leer = nie geholt).
ALTER TABLE matches ADD COLUMN pedigree_fetched_at  TEXT DEFAULT '';
ALTER TABLE matches ADD COLUMN ancestors_fetched_at TEXT DEFAULT ''
