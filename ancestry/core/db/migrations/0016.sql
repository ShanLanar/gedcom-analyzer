CREATE INDEX IF NOT EXISTS idx_matches_pedigree ON matches(test_guid, pedigree_fetched, shared_cm DESC);
CREATE INDEX IF NOT EXISTS idx_matches_ancestors ON matches(test_guid, ancestors_fetched, shared_cm DESC)
