-- 0034.sql — Cluster→Ahn-Hypothesen (Scrum-Panel IV, Feature B3)
-- Strukturierte, an einen GEDCOM-Ahn gebundene Hypothese je Cluster:
-- "von welchem gemeinsamen Vorfahren stammt dieser DNA-Cluster ab?"
-- Rein additiv (CREATE TABLE IF NOT EXISTS) — bestehende Daten (inkl.
-- source_webtrees) bleiben unberührt.

CREATE TABLE IF NOT EXISTS cluster_hypotheses (
    kit_guid     TEXT NOT NULL DEFAULT '',
    cluster_id   INTEGER NOT NULL,
    mrca_ged_id  TEXT NOT NULL DEFAULT '',
    mrca_label   TEXT NOT NULL DEFAULT '',
    confidence   TEXT NOT NULL DEFAULT '',   -- hoch | mittel | niedrig
    evidence     TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (kit_guid, cluster_id)
);
