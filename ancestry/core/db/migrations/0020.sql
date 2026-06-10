CREATE TABLE IF NOT EXISTS dna_segments (
    test_guid        TEXT NOT NULL,
    match_guid       TEXT NOT NULL,
    chromosome       INTEGER NOT NULL,
    start_location   INTEGER NOT NULL,
    end_location     INTEGER NOT NULL,
    length_cm        REAL NOT NULL DEFAULT 0.0,
    snp_count        INTEGER NOT NULL DEFAULT 0,
    fetched_at       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (test_guid, match_guid, chromosome, start_location)
);
CREATE INDEX IF NOT EXISTS idx_dna_seg_match
    ON dna_segments(test_guid, match_guid);
CREATE INDEX IF NOT EXISTS idx_dna_seg_chrom
    ON dna_segments(chromosome)
