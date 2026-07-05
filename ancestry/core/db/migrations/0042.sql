-- 0042.sql — Sprint-Review P2: Segment-Indizes optimieren

-- get_x_dna_matches filtert WHERE test_guid=? AND chromosome=23. Bisher gab es
-- nur idx_dna_seg_chrom(chromosome) (einspaltig) → alle X-Segmente ALLER Kits
-- wurden selektiert und dann nach test_guid gefiltert. Ein zusammengesetzter
-- Index bedient die Query direkt.
CREATE INDEX IF NOT EXISTS idx_dna_seg_test_chrom
    ON dna_segments(test_guid, chromosome);

-- is_ibd2 ist quasi-binär und in ~99,9% der Segmente 0. Der volle Index aus
-- 0041 (test_guid, is_ibd2) bläht bei Millionen Segmenten unnötig auf.
-- get_ibd2_matches sucht nur is_ibd2=1 → partieller Index ist viel kleiner.
DROP INDEX IF EXISTS idx_dna_seg_ibd2;
CREATE INDEX IF NOT EXISTS idx_dna_seg_ibd2
    ON dna_segments(test_guid) WHERE is_ibd2 = 1;
