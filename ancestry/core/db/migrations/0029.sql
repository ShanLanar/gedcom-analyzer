-- Performance-Indexes für Cluster, Stats und Pedigree-Tiefe

-- shared_matches: test_guid + match_guid_a (Cluster-Abfragen, häufigste JOIN-Seite)
CREATE INDEX IF NOT EXISTS idx_sm_test_a
ON shared_matches(test_guid, match_guid_a);

-- shared_matches: test_guid + match_guid_b (Reverse-Lookup)
CREATE INDEX IF NOT EXISTS idx_sm_test_b
ON shared_matches(test_guid, match_guid_b);

-- match_pedigree: triple compound für Stats-Self-Join und Tiefen-Berechnung
CREATE INDEX IF NOT EXISTS idx_mp_test_match_gen
ON match_pedigree(test_guid, match_guid, generation);

-- matches: partial index für GROUP BY predicted_relationship (Stats-Tab)
CREATE INDEX IF NOT EXISTS idx_matches_rel_nonempty
ON matches(predicted_relationship)
WHERE predicted_relationship != '';

-- matches: first_seen_at für "Neu (7 Tage)"-Chip-Filter
CREATE INDEX IF NOT EXISTS idx_matches_first_seen
ON matches(first_seen_at)
