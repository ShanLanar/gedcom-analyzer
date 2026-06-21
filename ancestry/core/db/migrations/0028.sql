-- Performance-Indexes für 300k+ Zeilen
-- matches.source: GROUP BY source für Pipeline-Status und Quellenfilter
CREATE INDEX IF NOT EXISTS idx_matches_source
ON matches(source);

-- gedcom_persons.source: GROUP BY source für Pipeline-Status
CREATE INDEX IF NOT EXISTS idx_gedcom_persons_source
ON gedcom_persons(source);

-- match_pedigree: compound (test_guid, match_guid) für Pedigree-Lookups
CREATE INDEX IF NOT EXISTS idx_ped_test_match
ON match_pedigree(test_guid, match_guid);

-- shared_matches: reverse-lookup über match_guid_b
CREATE INDEX IF NOT EXISTS idx_sm_match_b_test
ON shared_matches(test_guid, match_guid_b)
