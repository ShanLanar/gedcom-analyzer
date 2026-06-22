-- P1: Index-Strategie für häufig gefilterte/gejointe Spalten
-- Optimiert Queries auf matches, segments, gedcom_links, shared
-- KEINE Änderungen an webtrees-Tabellen (read-only, Nutzer-Daten-Schutz)

CREATE INDEX IF NOT EXISTS idx_matches_test_guid ON matches(test_guid, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_segments_match_guid ON segments(match_guid, segment_id);
CREATE INDEX IF NOT EXISTS idx_segments_cluster ON segments(cluster_id, match_guid);
CREATE INDEX IF NOT EXISTS idx_gedcom_links_test_match ON gedcom_links(test_guid, match_guid);
CREATE INDEX IF NOT EXISTS idx_shared_test_match ON shared(test_guid, match_guid);
