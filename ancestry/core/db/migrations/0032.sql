-- 0032.sql — Performance-Indizes (Scrum-Panel III, 2026-06-21)

-- shared_matches: Bereichs-Filter + Sortierung auf shared_cm_b je Primär-Match
-- (get_shared_matches, get_shared_pairs_set) — vermeidet Filesort auf der
-- match_guid_a-Partition und ermöglicht einen Index-Range-Scan.
CREATE INDEX IF NOT EXISTS idx_sm_a_cmb
ON shared_matches(test_guid, match_guid_a, shared_cm_b DESC);

-- matches: Kit-Partition vorsortiert nach shared_cm
-- (get_endogamy_candidates, get_unfetched_match_guids, get_matches-Kit-Pfad,
--  get_matches_needing_pedigree/ancestors) — Range-Skip + kein Filesort.
CREATE INDEX IF NOT EXISTS idx_matches_test_cm
ON matches(test_guid, shared_cm DESC);

-- Doppelte Indizes entfernen (identische Spalten, nur Schreib-/Speicher-Overhead)
DROP INDEX IF EXISTS idx_mkm_test_guid;        -- identisch zu idx_mkm_test
DROP INDEX IF EXISTS idx_gedcom_persons_source; -- identisch zu idx_gp_source
