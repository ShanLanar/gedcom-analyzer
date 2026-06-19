-- Optimierter Index für entity_assignments: is_active + source_table wird häufig kombiniert gefiltert
CREATE INDEX IF NOT EXISTS idx_ea_active_source
ON entity_assignments(source_table, is_active, source_row_id);
