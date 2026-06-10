#!/usr/bin/env python3
"""
MyHeritage DNA-Matches importieren.

Liest mh_all_matches.json (aus download_all_matches.js) und importiert
alle Matches in die ancestry_dna.db mit source='myheritage'.

Aufruf:
  python import_mh_matches.py [pfad/zu/mh_all_matches.json]
"""
import json
import sys
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).resolve().parent
ANCESTRY_DIR = SCRIPT_DIR.parent

# ── Konfiguration ──────────────────────────────────────────────────────────────
DB_PATH   = ANCESTRY_DIR / "ancestry_dna.db"

from ancestry.paths import SNAPSHOT_DIR
JSON_FILE = SNAPSHOT_DIR / "mh_all_matches.json"
if not JSON_FILE.exists() and (SCRIPT_DIR / "mh_all_matches.json").exists():
    JSON_FILE = SCRIPT_DIR / "mh_all_matches.json"   # Alt-Lage vor data/-Umzug
if len(sys.argv) > 1:
    JSON_FILE = Path(sys.argv[1])

MH_SITE_KIT_ID  = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
MH_INTERNAL_KIT = "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2"
KIT_GUID        = MH_INTERNAL_KIT   # Primärschlüssel in dna_kits
KIT_NAME        = "MyHeritage (Shan)"

# ── Datenbank direkt öffnen (ohne Models-Klassen) ─────────────────────────────
conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=OFF")

def init_schema():
    """Schema initialisieren (alle Migrationen) über Database-Klasse."""
    try:
        from ancestry.core.database import Database
        db = Database(str(DB_PATH))
        db.close()
        print("Schema initialisiert (via Database-Klasse)")
    except Exception as e:
        print(f"Hinweis: Database-Klasse nicht geladen ({e}), manuelles Schema-Setup")
        _manual_schema()

def _manual_schema():
    """Minimales Schema-Setup falls Database-Klasse nicht verfügbar."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS dna_kits (
            guid TEXT PRIMARY KEY, name TEXT, test_type TEXT,
            created_date TEXT, is_owner INTEGER DEFAULT 1, last_sync TEXT,
            source TEXT DEFAULT 'ancestry'
        );
        CREATE TABLE IF NOT EXISTS matches (
            match_guid TEXT PRIMARY KEY, test_guid TEXT NOT NULL,
            display_name TEXT, shared_cm REAL DEFAULT 0,
            shared_segments INTEGER DEFAULT 0, longest_segment REAL DEFAULT 0,
            predicted_relationship TEXT, confidence TEXT, relationship_range TEXT,
            has_hint INTEGER DEFAULT 0, has_tree INTEGER DEFAULT 0,
            tree_size INTEGER DEFAULT 0, tree_id TEXT,
            starred INTEGER DEFAULT 0, note TEXT, custom_relationship TEXT,
            ethnicity_regions TEXT, last_login TEXT, fetched_at TEXT, raw_json TEXT,
            match_cluster_code TEXT DEFAULT '', created_date INTEGER DEFAULT 0,
            tag_surname TEXT DEFAULT '', tag_gender TEXT DEFAULT '',
            tag_path TEXT DEFAULT '', tags_json TEXT DEFAULT '',
            meiosis INTEGER DEFAULT 0, ignored INTEGER DEFAULT 0,
            tree_status TEXT DEFAULT '', has_common_ancestor INTEGER DEFAULT 0,
            match_ucdmid TEXT DEFAULT '', gender TEXT DEFAULT '',
            ancestors_fetched INTEGER DEFAULT 0, pedigree_fetched INTEGER DEFAULT 0,
            linked_in_tree INTEGER DEFAULT 0, name_attempts INTEGER DEFAULT 0,
            endogamy_cluster TEXT DEFAULT '', research_flags INTEGER DEFAULT 0,
            paternal_maternal TEXT DEFAULT '',
            source TEXT DEFAULT 'ancestry',
            country_code TEXT DEFAULT '',
            mh_confidence_level TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS match_kit_membership (
            match_guid TEXT NOT NULL, test_guid TEXT NOT NULL,
            PRIMARY KEY (match_guid, test_guid)
        );
        CREATE TABLE IF NOT EXISTS mh_match_relationships (
            match_guid TEXT NOT NULL,
            rel_set TEXT NOT NULL DEFAULT 'complete',
            relationship_type INTEGER,
            relationship_class TEXT DEFAULT '',
            relationship_degree TEXT DEFAULT '',
            path_type TEXT DEFAULT '',
            probability REAL DEFAULT 0.0,
            mrca_type INTEGER,
            mrca_class TEXT DEFAULT '',
            PRIMARY KEY (match_guid, rel_set, relationship_type)
        );
    """)
    conn.commit()

# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _str(v, default="") -> str:
    return str(v).strip() if v is not None else default

def _float(v, default=0.0) -> float:
    try: return float(v)
    except (TypeError, ValueError): return default

def _int(v, default=0) -> int:
    try: return int(v)
    except (TypeError, ValueError): return default

def map_match(m: dict, test_guid: str) -> dict:
    """Wandelt einen MH-Match-Dict in das matches-Tabellen-Schema um."""
    kit         = m.get("other_dna_kit") or {}
    member      = kit.get("member") or {}
    submitter   = kit.get("submitter") or {}
    assoc_ind   = kit.get("associated_individual") or {}
    tree        = assoc_ind.get("tree") or {}

    # Verwandtschaftsgrad: refined > complete[0]
    predicted   = ""
    refined     = m.get("refined_dna_relationships") or []
    if refined:
        predicted = _str(refined[0].get("relationship_degree"))
    if not predicted:
        complete = m.get("complete_dna_relationships") or []
        if complete:
            predicted = _str(complete[0].get("relationship_degree"))

    # Name: member > submitter
    name = _str(member.get("name") or submitter.get("name"))

    has_tree    = 1 if tree.get("id") else 0
    tree_size   = _int(tree.get("individual_count"), 0)
    gender_raw  = _str(member.get("gender")).upper()
    gender      = {"M": "male", "F": "female"}.get(gender_raw, "")

    return {
        "match_guid":            _str(m.get("id")),
        "test_guid":             test_guid,
        "display_name":          name,
        "shared_cm":             _float(m.get("total_shared_segments_length_in_cm")),
        "shared_segments":       _int(m.get("total_shared_segments")),
        "longest_segment":       _float(m.get("largest_shared_segment_length_in_cm")),
        "predicted_relationship": predicted,
        "confidence":            _str(m.get("confidence_level")),
        "relationship_range":    "",
        "has_hint":              0,
        "has_tree":              has_tree,
        "tree_size":             tree_size,
        "tree_id":               _str(tree.get("id")),
        "starred":               0,
        "note":                  "",
        "custom_relationship":   "",
        "ethnicity_regions":     "",
        "last_login":            "",
        "fetched_at":            datetime.now(timezone.utc).isoformat(),
        "raw_json":              json.dumps(m),
        "match_cluster_code":    "",
        "created_date":          0,
        "tag_surname":           "",
        "tag_gender":            gender_raw,
        "tag_path":              "",
        "tags_json":             "",
        "meiosis":               0,
        "ignored":               0,
        "tree_status":           "hasTree" if has_tree else "",
        "has_common_ancestor":   0,
        "match_ucdmid":          "",
        "gender":                gender,
        "ancestors_fetched":     0,
        "pedigree_fetched":      0,
        "linked_in_tree":        0,
        "name_attempts":         0,
        "endogamy_cluster":      "",
        "research_flags":        0,
        "paternal_maternal":     "",
        "source":                "myheritage",
        "country_code":          _str(member.get("country_code")),
        "mh_confidence_level":   _str(m.get("confidence_level")),
    }


def save_relationships(cur, match_guid: str, m: dict):
    """Speichert die Verwandtschafts-Wahrscheinlichkeiten in mh_match_relationships."""
    cur.execute("DELETE FROM mh_match_relationships WHERE match_guid=?", (match_guid,))
    rows = []

    # complete + refined Verwandtschaften (ohne Wahrscheinlichkeit)
    for rel_set, field in [
        ("complete",  "complete_dna_relationships"),
        ("refined",   "refined_dna_relationships"),
    ]:
        for rel in (m.get(field) or []):
            rows.append({
                "match_guid":        match_guid,
                "rel_set":           rel_set,
                "relationship_type": _int(rel.get("relationship_type")),
                "relationship_class": "",
                "relationship_degree": _str(rel.get("relationship_degree")),
                "path_type":         "",
                "probability":       0.0,
                "mrca_type":         None,
                "mrca_class":        "",
            })

    # dna_cm_explainer: Verwandtschaften MIT Wahrscheinlichkeit
    explainer = m.get("dna_cm_explainer") or {}
    for field in ["relationships", "most_probable_relationships"]:
        rel_set = "probable" if field == "most_probable_relationships" else "explainer"
        for rel in (explainer.get(field) or []):
            rows.append({
                "match_guid":        match_guid,
                "rel_set":           rel_set,
                "relationship_type": _int(rel.get("relationship_type")),
                "relationship_class": _str(rel.get("relationship_class")),
                "relationship_degree": "",
                "path_type":         _str(rel.get("path_type")),
                "probability":       _float(rel.get("probability")),
                "mrca_type":         rel.get("most_recent_common_ancestor_relationship_type"),
                "mrca_class":        _str(rel.get("most_recent_common_ancestor_relationship_class")),
            })

    for row in rows:
        try:
            cur.execute("""
                INSERT OR REPLACE INTO mh_match_relationships
                  (match_guid, rel_set, relationship_type, relationship_class,
                   relationship_degree, path_type, probability, mrca_type, mrca_class)
                VALUES
                  (:match_guid, :rel_set, :relationship_type, :relationship_class,
                   :relationship_degree, :path_type, :probability, :mrca_type, :mrca_class)
            """, row)
        except Exception:
            pass


# ── Haupt-Import ───────────────────────────────────────────────────────────────

def run():
    if not JSON_FILE.exists():
        print(f"Fehler: {JSON_FILE} nicht gefunden.")
        print("Bitte zuerst download_all_matches.js im Browser ausführen.")
        sys.exit(1)

    print(f"Lese {JSON_FILE} …")
    raw = json.loads(JSON_FILE.read_text(encoding="utf-8"))

    meta    = raw.get("meta", {})
    matches = raw.get("matches", [])
    total   = meta.get("downloaded_count", len(matches))
    print(f"  Kit:     {meta.get('kit_id','?')}")
    print(f"  Matches: {total} (in Datei: {len(matches)})")
    print()

    init_schema()

    # Kit registrieren
    conn.execute("""
        INSERT OR REPLACE INTO dna_kits (guid, name, test_type, is_owner, source)
        VALUES (?, ?, 'MyHeritageDNA', 1, 'myheritage')
    """, (KIT_GUID, KIT_NAME))
    conn.commit()
    print(f"Kit registriert: {KIT_GUID}")

    # Matches importieren
    saved = 0
    skipped = 0
    cur = conn.cursor()

    for i, m in enumerate(matches):
        if not m.get("id"):
            skipped += 1
            continue

        d = map_match(m, KIT_GUID)

        try:
            cur.execute("""
                INSERT INTO matches (
                    match_guid, test_guid, display_name, shared_cm, shared_segments,
                    longest_segment, predicted_relationship, confidence, relationship_range,
                    has_hint, has_tree, tree_size, tree_id, starred, note,
                    custom_relationship, ethnicity_regions, last_login, fetched_at,
                    raw_json, match_cluster_code, created_date, tag_surname, tag_gender,
                    tag_path, tags_json, meiosis, ignored, tree_status,
                    has_common_ancestor, match_ucdmid, gender, ancestors_fetched,
                    pedigree_fetched, linked_in_tree, name_attempts, endogamy_cluster,
                    research_flags, paternal_maternal, source, country_code,
                    mh_confidence_level
                ) VALUES (
                    :match_guid, :test_guid, :display_name, :shared_cm, :shared_segments,
                    :longest_segment, :predicted_relationship, :confidence, :relationship_range,
                    :has_hint, :has_tree, :tree_size, :tree_id, :starred, :note,
                    :custom_relationship, :ethnicity_regions, :last_login, :fetched_at,
                    :raw_json, :match_cluster_code, :created_date, :tag_surname, :tag_gender,
                    :tag_path, :tags_json, :meiosis, :ignored, :tree_status,
                    :has_common_ancestor, :match_ucdmid, :gender, :ancestors_fetched,
                    :pedigree_fetched, :linked_in_tree, :name_attempts, :endogamy_cluster,
                    :research_flags, :paternal_maternal, :source, :country_code,
                    :mh_confidence_level
                )
                ON CONFLICT(match_guid) DO UPDATE SET
                    display_name          = excluded.display_name,
                    shared_cm             = excluded.shared_cm,
                    shared_segments       = excluded.shared_segments,
                    longest_segment       = excluded.longest_segment,
                    predicted_relationship= excluded.predicted_relationship,
                    confidence            = excluded.confidence,
                    has_tree              = excluded.has_tree,
                    tree_size             = excluded.tree_size,
                    tree_id               = excluded.tree_id,
                    gender                = excluded.gender,
                    country_code          = excluded.country_code,
                    mh_confidence_level   = excluded.mh_confidence_level,
                    raw_json              = excluded.raw_json,
                    fetched_at            = excluded.fetched_at
            """, d)

            # kit_membership
            cur.execute("""
                INSERT OR IGNORE INTO match_kit_membership (match_guid, test_guid)
                VALUES (?, ?)
            """, (d["match_guid"], KIT_GUID))

            # Detaillierte Verwandtschaften
            save_relationships(cur, d["match_guid"], m)

            saved += 1

        except Exception as e:
            print(f"  Fehler bei Match {m.get('id','?')}: {e}")
            skipped += 1

        if (i + 1) % 500 == 0:
            conn.commit()
            pct = ((i + 1) / len(matches) * 100)
            print(f"  {i+1}/{len(matches)} ({pct:.1f}%) – {saved} gespeichert")

    conn.commit()
    conn.close()

    print()
    print(f"Import abgeschlossen:")
    print(f"  Gespeichert:  {saved}")
    print(f"  Übersprungen: {skipped}")
    print(f"  Datenbank:    {DB_PATH}")


if __name__ == "__main__":
    run()
