#!/usr/bin/env python3
"""
MyHeritage DNA-Matches aus CSV importieren (Genealogy-Assistant-Export).

Erwartete Spalten (mit Kopfzeile, kommagetrennt, Felder ggf. in "..."):
  Match Name, Estimated Relationship, Shared cM, Shared Percentage,
  Shared Segments, Largest Segment, Tree Size, Location, Groups,
  Star Status, GUID, URL

Die eigene Kit-GUID wird aus der URL der ersten Datenzeile abgeleitet
(MyHeritage-URLs haben das Format .../match/<KIT>-<MATCH>), kann aber per
--kit überschrieben werden.

Aufruf:
  python import_mh_csv.py [pfad/zur/MyHeritage_Match_List.csv] [--kit KIT_GUID]
"""
import sys
import csv
import json
import sqlite3
import argparse
import re
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR   = Path(__file__).resolve().parent
ANCESTRY_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(ANCESTRY_DIR))
sys.path.insert(0, str(ANCESTRY_DIR / "core"))

DB_PATH  = ANCESTRY_DIR / "ancestry_dna.db"
KIT_NAME = "MyHeritage (Shan)"

# MyHeritage-GUIDs sind D-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
_GUID_RE = re.compile(r"D-[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
                      r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")


def _float(v, default=0.0) -> float:
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def _int(v, default=0) -> int:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _str(v, default="") -> str:
    return str(v).strip() if v is not None else default


def kit_from_url(url: str) -> str:
    """Holt die erste (=Kit-)GUID aus einer MyHeritage-Match-URL."""
    guids = _GUID_RE.findall(url or "")
    return guids[0] if guids else ""


def init_schema(conn):
    try:
        from database import Database
        Database(str(DB_PATH)).close()
        print("Schema initialisiert (via Database-Klasse)")
    except Exception as e:
        print(f"Warnung: Database-Klasse nicht ladbar ({e}). "
              f"Bitte das Tool einmal starten, damit das Schema existiert.")


def run(path: Path, kit_override: str = ""):
    if not path.exists():
        print(f"Fehler: {path} nicht gefunden.")
        sys.exit(1)

    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    if not rows:
        print("Keine Datenzeilen gefunden.")
        sys.exit(1)

    # Kit-GUID bestimmen
    kit_guid = kit_override or kit_from_url(rows[0].get("URL", ""))
    if not kit_guid:
        kit_guid = "myheritage-self"
    print(f"Kit-GUID: {kit_guid}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    init_schema(conn)

    conn.execute("""
        INSERT OR REPLACE INTO dna_kits (guid, name, test_type, is_owner, source)
        VALUES (?, ?, 'MyHeritageDNA', 1, 'myheritage')
    """, (kit_guid, KIT_NAME))
    conn.commit()
    print(f"Kit registriert: {kit_guid} ({KIT_NAME})")

    cur = conn.cursor()
    saved = skipped = 0

    for i, r in enumerate(rows):
        guid = _str(r.get("GUID")) or kit_from_url(_str(r.get("URL")))
        if not guid:
            skipped += 1
            continue

        tree_size = _int(r.get("Tree Size"))
        location  = _str(r.get("Location"))
        star      = 1 if _str(r.get("Star Status")).lower() in ("1", "true", "yes", "ja", "starred") else 0

        raw = {
            "name":               _str(r.get("Match Name")),
            "estimated_relationship": _str(r.get("Estimated Relationship")),
            "shared_cm":          _float(r.get("Shared cM")),
            "shared_percentage":  _float(r.get("Shared Percentage")),
            "shared_segments":    _int(r.get("Shared Segments")),
            "largest_segment":    _float(r.get("Largest Segment")),
            "tree_size":          tree_size,
            "location":           location,
            "groups":             _str(r.get("Groups")),
            "url":                _str(r.get("URL")),
        }

        now = datetime.now(timezone.utc).isoformat()
        try:
            cur.execute("""
                INSERT INTO matches (
                    match_guid, test_guid, display_name, shared_cm, shared_segments,
                    longest_segment, predicted_relationship, has_tree, tree_size,
                    starred, fetched_at, raw_json, source, country_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'myheritage', ?)
                ON CONFLICT(match_guid) DO UPDATE SET
                    display_name           = excluded.display_name,
                    shared_cm              = excluded.shared_cm,
                    shared_segments        = excluded.shared_segments,
                    longest_segment        = excluded.longest_segment,
                    predicted_relationship = excluded.predicted_relationship,
                    has_tree               = excluded.has_tree,
                    tree_size              = excluded.tree_size,
                    starred                = excluded.starred,
                    country_code           = excluded.country_code,
                    raw_json               = excluded.raw_json,
                    fetched_at             = excluded.fetched_at
            """, (
                guid, kit_guid, raw["name"], raw["shared_cm"], raw["shared_segments"],
                raw["largest_segment"], raw["estimated_relationship"],
                1 if tree_size > 0 else 0, tree_size, star, now,
                json.dumps(raw, ensure_ascii=False), location,
            ))
            cur.execute("""
                INSERT OR IGNORE INTO match_kit_membership (match_guid, test_guid)
                VALUES (?, ?)
            """, (guid, kit_guid))
            saved += 1
        except Exception as e:
            print(f"  Fehler bei {guid}: {e}")
            skipped += 1

        if (i + 1) % 1000 == 0:
            conn.commit()
            print(f"  {i+1}/{len(rows)} … {saved} gespeichert")

    conn.commit()
    conn.close()

    print(f"\nImport abgeschlossen:")
    print(f"  Gespeichert:   {saved}")
    print(f"  Uebersprungen: {skipped}")
    print(f"  Datenbank:     {DB_PATH}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?",
                    default=str(SCRIPT_DIR / "MyHeritage_Match_List.csv"))
    ap.add_argument("--kit", default="", help="Kit-GUID überschreiben")
    args = ap.parse_args()
    run(Path(args.file), args.kit)
