-- Compound index for entity_assignments (source+role lookup)
CREATE INDEX IF NOT EXISTS idx_ea_source_role
ON entity_assignments(source_table, source_row_id, person_role);

-- match_pedigree: test_guid + generation filter (Kirchenbuch-Brücke)
CREATE INDEX IF NOT EXISTS idx_mp_guid_gen
ON match_pedigree(test_guid, generation);

-- gedcom_persons: surname + birth_year (NER-Namensvergleich, Dedup)
CREATE INDEX IF NOT EXISTS idx_gp_surname_year
ON gedcom_persons(surname, birth_year)
