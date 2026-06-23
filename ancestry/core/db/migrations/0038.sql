-- 0038.sql — Cluster-Farb-Persistierung (Feature B1)
-- Speichert Cluster-Seiten-Zuordnungen (paternal/maternal) und Farben
-- je Kit über Neustarts hinweg.
-- Rein additiv (CREATE TABLE IF NOT EXISTS) — keine Breaking Changes.

CREATE TABLE IF NOT EXISTS cluster_colors (
    kit_id      TEXT NOT NULL,
    cluster_id  TEXT NOT NULL,
    side        TEXT NOT NULL DEFAULT '',   -- 'paternal' | 'maternal' | ''
    color       TEXT NOT NULL DEFAULT '',   -- Hex-Farbcode
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (kit_id, cluster_id)
);
