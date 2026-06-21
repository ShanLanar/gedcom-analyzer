-- Zusätzliche Performance-Indexes für Stats-Abfragen

-- match_kit_membership: test_guid (kit-breakdown JOIN in StatsRepo)
CREATE INDEX IF NOT EXISTS idx_mkm_test_guid
ON match_kit_membership(test_guid);

-- matches: paternal_maternal (GROUP BY Seitenverteilung in StatsRepo)
CREATE INDEX IF NOT EXISTS idx_matches_pat_mat
ON matches(paternal_maternal);
