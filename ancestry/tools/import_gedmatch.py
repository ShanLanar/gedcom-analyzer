#!/usr/bin/env python3
"""
GEDmatch "One-to-many" Matches importieren.

Liest den Tab-getrennten Export der GEDmatch One-to-many-Liste und
importiert alle Treffer in die ancestry_dna.db mit source='gedmatch'.

Erwartete Spalten (Tab-getrennt, mit Kopfzeile):
  Kit  1:1  Name  Email  Notes  Largest Seg  Total cM  Gen  Overlap  Date Compared  Testing Company

Der grosse Mehrwert von GEDmatch: jeder Treffer traegt die Information,
von WELCHEM Dienst die getestete Person kommt (Spalte "Testing Company").
Das fuellt Luecken, die Ancestry/MyHeritage allein nicht abdecken
(23andMe, FTDNA, Living DNA, Genotek usw.).

Aufruf:
  python import_gedmatch.py [pfad/zur/gedmatch_export.txt] [--kit GEDMATCH_KIT_ID]
"""
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR   = Path(__file__).resolve().parent
ANCESTRY_DIR = SCRIPT_DIR.parent

DB_PATH = ANCESTRY_DIR / "ancestry_dna.db"

# Das eigene GEDmatch-Kit, gegen das die One-to-many-Liste gelaufen ist.
# Per --kit ueberschreibbar. Dient als test_guid / dna_kits.guid.
DEFAULT_KIT_GUID = "gedmatch-self"
KIT_NAME         = "GEDmatch (Shan)"


def _float(v, default=0.0) -> float:
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def _str(v, default="") -> str:
    return str(v).strip() if v is not None else default


def init_schema(conn):
    """Schema via Database-Klasse initialisieren (alle Migrationen)."""
    try:
        from ancestry.core.database import Database
        Database(str(DB_PATH)).close()
        print("Schema initialisiert (via Database-Klasse)")
    except Exception as e:
        print(f"Warnung: Database-Klasse nicht ladbar ({e}). "
              f"Bitte zuerst das Tool einmal starten, damit das Schema existiert.")


def parse_row(parts: list[str]) -> dict | None:
    """Eine Datenzeile -> Dict im matches-Schema. None wenn unbrauchbar."""
    if len(parts) < 7:
        return None
    kit_id = _str(parts[0])
    if not kit_id or kit_id.lower() == "kit":
        return None

    name        = _str(parts[2])
    email       = _str(parts[3]) if len(parts) > 3 else ""
    largest_seg = _float(parts[5]) if len(parts) > 5 else 0.0
    total_cm    = _float(parts[6]) if len(parts) > 6 else 0.0
    gen         = _str(parts[7]) if len(parts) > 7 else ""
    overlap     = _str(parts[8]) if len(parts) > 8 else ""
    date_cmp    = _str(parts[9]) if len(parts) > 9 else ""
    company     = _str(parts[10]) if len(parts) > 10 else ""

    raw = {
        "kit": kit_id, "name": name, "email": email,
        "largest_seg": largest_seg, "total_cm": total_cm,
        "estimated_generations": gen, "overlap": overlap,
        "date_compared": date_cmp, "testing_company": company,
    }

    return {
        "match_guid":            f"gm-{kit_id}",
        "display_name":          name,
        "shared_cm":             total_cm,
        "longest_segment":       largest_seg,
        "predicted_relationship": f"~{gen} gen" if gen else "",
        "country_code":          "",
        # "Testing Company" als herkunfts-relevante Quelle ablegen:
        "mh_confidence_level":   company,
        "raw_json":              json.dumps(raw, ensure_ascii=False),
    }


def run(path: Path, kit_guid: str):
    if not path.exists():
        print(f"Fehler: {path} nicht gefunden.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    init_schema(conn)

    conn.execute("""
        INSERT OR REPLACE INTO dna_kits (guid, name, test_type, is_owner, source)
        VALUES (?, ?, 'GEDmatch', 1, 'gedmatch')
    """, (kit_guid, KIT_NAME))
    conn.commit()
    print(f"Kit registriert: {kit_guid} ({KIT_NAME})")

    cur = conn.cursor()
    saved = skipped = 0
    companies: dict[str, int] = {}

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        if not line.strip():
            continue
        d = parse_row(line.split("\t"))
        if d is None:
            skipped += 1
            continue

        now = datetime.now(timezone.utc).isoformat()
        try:
            cur.execute("""
                INSERT INTO matches (
                    match_guid, test_guid, display_name, shared_cm, shared_segments,
                    longest_segment, predicted_relationship, fetched_at, raw_json,
                    source, country_code, mh_confidence_level
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, 'gedmatch', ?, ?)
                ON CONFLICT(match_guid) DO UPDATE SET
                    display_name        = excluded.display_name,
                    shared_cm           = excluded.shared_cm,
                    longest_segment     = excluded.longest_segment,
                    predicted_relationship = excluded.predicted_relationship,
                    mh_confidence_level = excluded.mh_confidence_level,
                    raw_json            = excluded.raw_json,
                    fetched_at          = excluded.fetched_at
            """, (
                d["match_guid"], kit_guid, d["display_name"], d["shared_cm"],
                d["longest_segment"], d["predicted_relationship"], now,
                d["raw_json"], d["country_code"], d["mh_confidence_level"],
            ))
            cur.execute("""
                INSERT OR IGNORE INTO match_kit_membership (match_guid, test_guid)
                VALUES (?, ?)
            """, (d["match_guid"], kit_guid))
            saved += 1
            c = d["mh_confidence_level"] or "(unbekannt)"
            companies[c] = companies.get(c, 0) + 1
        except Exception as e:
            print(f"  Fehler bei Kit {d['match_guid']}: {e}")
            skipped += 1

    conn.commit()
    conn.close()

    print(f"\nImport abgeschlossen:")
    print(f"  Gespeichert:  {saved}")
    print(f"  Uebersprungen:{skipped}")
    print(f"  Datenbank:    {DB_PATH}")
    print(f"\n  Top-Testdienste:")
    for comp, n in sorted(companies.items(), key=lambda x: -x[1])[:12]:
        print(f"    {n:5d}  {comp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", default=str(SCRIPT_DIR / "gedmatch_export.txt"))
    ap.add_argument("--kit", default=DEFAULT_KIT_GUID,
                    help="GUID des eigenen GEDmatch-Kits (Default: gedmatch-self)")
    args = ap.parse_args()
    run(Path(args.file), args.kit)
