ALTER TABLE matches ADD COLUMN match_cluster_code TEXT DEFAULT '';
ALTER TABLE matches ADD COLUMN created_date INTEGER DEFAULT 0;
ALTER TABLE matches ADD COLUMN tag_surname TEXT DEFAULT '';
ALTER TABLE matches ADD COLUMN tag_gender TEXT DEFAULT '';
ALTER TABLE matches ADD COLUMN meiosis INTEGER DEFAULT 0;
ALTER TABLE matches ADD COLUMN ignored INTEGER DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_matches_cluster ON matches(match_cluster_code)
