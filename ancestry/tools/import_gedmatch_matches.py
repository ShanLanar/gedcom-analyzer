#!/usr/bin/env python3
"""
GEDmatch One-to-Many Matches importieren.

Liest eine TSV/CSV-Exportdatei von GEDmatch (One-to-Many-Vergleich) und
importiert alle Treffer in die Datenbank.

Aufruf:
  python import_gedmatch_matches.py [pfad/zur/datei.tsv]
  python import_gedmatch_matches.py    # sucht in ancestry/data/ nach gedmatch_*.tsv

Dateiformat (GEDmatch One-to-Many, Tab-getrennt):
  Kit_Number  Name  Email  Tags  Sex  Total_cM  Largest_Seg  Gen
  X-DNA_cM  X-DNA_Segs  [Rel_Type]  Source  SNPs  Overlap  mtDNA  YDNA
"""
import csv
import json
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
ANCESTRY_DIR = SCRIPT_DIR.parent
DB_PATH      = ANCESTRY_DIR / "ancestry_dna.db"
DATA_DIR     = ANCESTRY_DIR / "data"

OUR_KIT = "CM8449775"
KIT_NAME = "GEDmatch (Andreas Kovermann)"



def _float(v, default=0.0) -> float:
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _int(v, default=0) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _str(v, default="") -> str:
    return str(v).strip() if v is not None else default


# Kanonische Plattform-Bezeichnungen
PLATFORM_MAP = {
    "23andme":      "23andMe",
    "ancestry":     "Ancestry",
    "myheritage":   "MyHeritage",
    "ftdna":        "FTDNA",
    "familytreedna":"FTDNA",
    "livingdna":    "LivingDNA",
    "living dna":   "LivingDNA",
    "genotek":      "Genotek",
    "genera":       "Genera",
    "gedmatch":     "GEDmatch",
    "combined":     "Combined",
}


def normalize_platform(raw: str) -> str:
    key = raw.strip().lower()
    for pattern, canonical in PLATFORM_MAP.items():
        if pattern in key:
            return canonical
    return raw.strip() or "Unknown"


def find_input_file() -> Path:
    """Sucht nach GEDmatch-Datei in ancestry/data/."""
    candidates = sorted(DATA_DIR.glob("gedmatch_*.tsv")) + \
                 sorted(DATA_DIR.glob("gedmatch_*.csv")) + \
                 sorted(DATA_DIR.glob("gedmatch_*.txt"))
    if candidates:
        print(f"Gefunden: {candidates[-1]}")
        return candidates[-1]
    raise FileNotFoundError(
        f"Keine GEDmatch-Datei in {DATA_DIR} gefunden.\n"
        "Speichere die GEDmatch One-to-Many-Seite als:\n"
        "  ancestry/data/gedmatch_CM8449775.tsv\n"
        "und rufe das Script erneut auf."
    )


def detect_delimiter(path: Path) -> str:
    """Erkennt Trennzeichen (Tab oder Komma)."""
    sample = path.read_text(encoding="utf-8", errors="replace")[:4096]
    tabs   = sample.count("\t")
    commas = sample.count(",")
    return "\t" if tabs > commas else ","


# Bekannte Spaltenköpfe → interner Name
COLUMN_ALIASES = {
    "kit number":       "kit_id",
    "kit_number":       "kit_id",
    "kit":              "kit_id",
    "name":             "name",
    "e-mail":           "email",
    "email":            "email",
    "tags":             "tags",
    "sex":              "sex",
    "gender":           "sex",
    "total cm":         "shared_cm",
    "total_cm":         "shared_cm",
    "total shared cm":  "shared_cm",
    "largest seg":      "largest_segment",
    "largest_seg":      "largest_segment",
    "largest segment":  "largest_segment",
    "gen":              "gen_distance",
    "generations":      "gen_distance",
    "x-dna (cm)":       "x_cm",
    "x-dna cm":         "x_cm",
    "x-dna":            "x_cm",
    "x_cm":             "x_cm",
    "x cm":             "x_cm",
    "x-dna (segs)":     "x_segments",
    "x-dna segs":       "x_segments",
    "x segs":           "x_segments",
    "x_segments":       "x_segments",
    "relationship":     "relationship",
    "source":           "source_platform",
    "platform":         "source_platform",
    "snps":             "snps",
    "overlap":          "overlap",
    "mtdna":            "mt_haplogroup",
    "mt":               "mt_haplogroup",
    "mt haplogroup":    "mt_haplogroup",
    "ydna":             "y_haplogroup",
    "y":                "y_haplogroup",
    "y haplogroup":     "y_haplogroup",
    "y-dna":            "y_haplogroup",
}


def map_header(raw_headers: list) -> dict:
    """Mappt Rohspaltenköpfe auf interne Feldnamen, gibt {intern → col_index} zurück."""
    mapping = {}
    for i, h in enumerate(raw_headers):
        key = h.strip().lower().rstrip("*").strip()
        internal = COLUMN_ALIASES.get(key)
        if internal and internal not in mapping:
            mapping[internal] = i
    return mapping


def parse_rows(path: Path) -> list[dict]:
    """Liest alle Zeilen und gibt bereinigte Dicts zurück."""
    delim = detect_delimiter(path)
    rows  = []

    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=delim)
        headers_raw = None
        col_map = {}

        for line in reader:
            # Erste nicht-leere Zeile als Kopfzeile erkennen
            if headers_raw is None:
                if not line or all(c.strip() == "" for c in line):
                    continue
                # GEDmatch fügt manchmal Leerzeichen oder BOM vor der ersten Spalte ein
                line[0] = line[0].lstrip("﻿").strip()
                headers_raw = line
                col_map = map_header(headers_raw)
                if "kit_id" not in col_map:
                    # Fallback: erste Spalte = kit_id
                    col_map["kit_id"] = 0
                continue

            if not line or all(c.strip() == "" for c in line):
                continue

            def get(field, default=""):
                idx = col_map.get(field)
                return line[idx].strip() if idx is not None and idx < len(line) else default

            kit_id = get("kit_id")
            if not kit_id or kit_id.lower().startswith("kit"):
                continue  # Überspringe weitere Kopfzeilen

            rows.append({
                "kit_id":          kit_id,
                "name":            get("name"),
                "email":           get("email"),
                "tags":            get("tags"),
                "sex":             get("sex"),
                "shared_cm":       _float(get("shared_cm", "0")),
                "largest_segment": _float(get("largest_segment", "0")),
                "gen_distance":    _float(get("gen_distance", "0")),
                "x_cm":            _float(get("x_cm", "0")),
                "x_segments":      _int(get("x_segments", "0")),
                "source_platform": normalize_platform(get("source_platform")),
                "snps":            _int(get("snps", "0")),
                "overlap":         _int(get("overlap", "0")),
                "mt_haplogroup":   get("mt_haplogroup"),
                "y_haplogroup":    get("y_haplogroup"),
            })

    return rows


def init_schema():
    try:
        from ancestry.core.database import Database
        db = Database(str(DB_PATH))
        db.close()
        print("Schema initialisiert (v15)")
    except Exception as e:
        print(f"Hinweis: Database-Klasse nicht geladen ({e})")


def run(input_file: Path):
    print(f"Lese {input_file} …")
    rows = parse_rows(input_file)
    print(f"  {len(rows)} Zeilen geparst")

    init_schema()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # GEDmatch-Kit registrieren
    cur.execute("""
        INSERT OR REPLACE INTO dna_kits (guid, name, test_type, is_owner, source)
        VALUES (?, ?, 'GEDmatch', 1, 'gedmatch')
    """, (OUR_KIT, KIT_NAME))

    fetched_at = datetime.now(timezone.utc).isoformat()
    saved = skipped = 0

    for r in rows:
        if not r["kit_id"]:
            skipped += 1
            continue
        try:
            cur.execute("""
                INSERT INTO gedmatch_matches (
                    kit_id, our_kit, name, email, tags, sex,
                    shared_cm, largest_segment, gen_distance,
                    x_cm, x_segments, source_platform,
                    snps, overlap, mt_haplogroup, y_haplogroup, fetched_at
                ) VALUES (
                    :kit_id, :our_kit, :name, :email, :tags, :sex,
                    :shared_cm, :largest_segment, :gen_distance,
                    :x_cm, :x_segments, :source_platform,
                    :snps, :overlap, :mt_haplogroup, :y_haplogroup, :fetched_at
                )
                ON CONFLICT(kit_id, our_kit) DO UPDATE SET
                    name            = excluded.name,
                    email           = excluded.email,
                    shared_cm       = excluded.shared_cm,
                    largest_segment = excluded.largest_segment,
                    gen_distance    = excluded.gen_distance,
                    x_cm            = excluded.x_cm,
                    x_segments      = excluded.x_segments,
                    source_platform = excluded.source_platform,
                    snps            = excluded.snps,
                    overlap         = excluded.overlap,
                    mt_haplogroup   = excluded.mt_haplogroup,
                    y_haplogroup    = excluded.y_haplogroup,
                    fetched_at      = excluded.fetched_at
            """, {**r, "our_kit": OUR_KIT, "fetched_at": fetched_at})
            saved += 1
        except Exception as e:
            print(f"  Fehler bei Kit {r['kit_id']}: {e}")
            skipped += 1

    conn.commit()

    # Statistik nach Plattform
    cur.execute("""
        SELECT source_platform, COUNT(*) AS cnt, ROUND(SUM(shared_cm),1) AS total_cm
        FROM gedmatch_matches WHERE our_kit=?
        GROUP BY source_platform ORDER BY cnt DESC
    """, (OUR_KIT,))
    print("\nPlattform-Statistik:")
    for row in cur.fetchall():
        print(f"  {row['source_platform']:15s} {row['cnt']:5d} Matches  {row['total_cm']} cM gesamt")

    # Haplogruppen
    cur.execute("""
        SELECT mt_haplogroup, COUNT(*) AS cnt
        FROM gedmatch_matches WHERE our_kit=? AND mt_haplogroup != ''
        GROUP BY mt_haplogroup ORDER BY cnt DESC LIMIT 10
    """, (OUR_KIT,))
    rows_mt = cur.fetchall()
    if rows_mt:
        print("\nTop mtDNA-Haplogruppen:")
        for row in rows_mt:
            print(f"  {row['mt_haplogroup']:12s} {row['cnt']}")

    cur.execute("""
        SELECT y_haplogroup, COUNT(*) AS cnt
        FROM gedmatch_matches WHERE our_kit=? AND y_haplogroup != ''
        GROUP BY y_haplogroup ORDER BY cnt DESC LIMIT 10
    """, (OUR_KIT,))
    rows_y = cur.fetchall()
    if rows_y:
        print("\nTop Y-DNA-Haplogruppen:")
        for row in rows_y:
            print(f"  {row['y_haplogroup']:12s} {row['cnt']}")

    conn.close()

    print(f"\nImport abgeschlossen:")
    print(f"  Gespeichert:  {saved}")
    print(f"  Übersprungen: {skipped}")
    print(f"  Datenbank:    {DB_PATH}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
    else:
        input_path = find_input_file()

    run(input_path)
