ALTER TABLE matches ADD COLUMN first_seen_at TEXT NOT NULL DEFAULT '';
UPDATE matches SET first_seen_at = COALESCE(fetched_at, '') WHERE first_seen_at = '';
