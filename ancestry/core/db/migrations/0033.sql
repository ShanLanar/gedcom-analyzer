-- 0033.sql — Research-To-Do-Manager (Scrum-Panel IV, Feature B1)
-- Aufgaben/Forschungsschritte pro Match, Ahn oder Ort. Persistenter
-- Workflow-Kern (bisher nur 5-Bit-Checkliste + Freitext-Notiz).

CREATE TABLE IF NOT EXISTS research_tasks (
    task_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type  TEXT NOT NULL DEFAULT '',   -- 'match' | 'ged_person' | 'place' | ''
    entity_key   TEXT NOT NULL DEFAULT '',   -- match_guid | ged_id | Ort
    entity_label TEXT NOT NULL DEFAULT '',   -- lesbarer Name für die Anzeige
    title        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open',  -- open | doing | done
    priority     INTEGER NOT NULL DEFAULT 2,    -- 1 hoch, 2 normal, 3 niedrig
    due_date     TEXT NOT NULL DEFAULT '',
    result       TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rt_entity ON research_tasks(entity_type, entity_key);
CREATE INDEX IF NOT EXISTS idx_rt_status ON research_tasks(status, priority);
