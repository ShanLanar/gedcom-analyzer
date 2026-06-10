#!/usr/bin/env python3
"""
DNA-Segmente aus CSV-Exporten importieren (Chromosome-Browser-Daten).

Erkennt das Format automatisch an der Kopfzeile:

  GEDmatch Segment Search CSV:
    PrimaryKit,MatchedKit,chr,B37 Start,B37 End,Segment cM,SNPs,MatchedName,...
    → match_guid = gm-<MatchedKit>  (Konvention aus import_gedmatch.py)

  MyHeritage "Shared DNA segments" CSV:
    Name,Match name,Chromosome,Start Location,End Location,
    Start RSID,End RSID,Centimorgans,SNPs
    → match_guid wird über den Anzeigenamen in der matches-Tabelle aufgelöst

  FTDNA Chromosome Browser CSV:
    Match Name,Chromosome,Start Location,End Location,Centimorgans,Matching SNPs
    → match_guid wird über den Anzeigenamen aufgelöst

X-Chromosom wird als Chromosom 23 gespeichert (Anzeige als "X" in der GUI).

Segmente sind die Grundlage der Segment-Triangulation (Analyse-Menü).

Aufruf:
  python import_segments.py datei.csv --kit KIT_GUID
  python import_segments.py gedmatch_segments.csv          (Kit aus PrimaryKit-Spalte)
"""
import sys
import csv
import argparse
from pathlib import Path
from datetime import datetime, timezone

from ancestry.core.database import Database


def _float(v, default=0.0) -> float:
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def _int(v, default=0) -> int:
    try:
        return int(float(str(v).strip().replace(".", "").replace(",", "")))
    except (TypeError, ValueError):
        return default


def parse_chromosome(v) -> int:
    """'1'-'22' → int, 'X'/'23' → 23, sonst 0 (= unbrauchbar)."""
    s = str(v).strip().upper().removeprefix("CHR")
    if s == "X":
        return 23
    try:
        n = int(s)
    except ValueError:
        return 0
    return n if 1 <= n <= 23 else 0


def _norm_header(fieldnames) -> list[str]:
    return [(f or "").strip().lower() for f in (fieldnames or [])]


def detect_format(fieldnames) -> str:
    """'gedmatch', 'myheritage', 'ftdna' oder '' (unbekannt)."""
    h = set(_norm_header(fieldnames))
    if "matchedkit" in h or "primarykit" in h:
        return "gedmatch"
    if "match name" in h and "start rsid" in h:
        return "myheritage"
    if "match name" in h and "matching snps" in h:
        return "ftdna"
    # MyHeritage ohne RSID-Spalten (ältere Exporte)
    if "match name" in h and "centimorgans" in h:
        return "myheritage"
    return ""


def _get(row: dict, *keys, default=""):
    """Case-insensitiver Spaltenzugriff."""
    low = {(k or "").strip().lower(): v for k, v in row.items()}
    for k in keys:
        if k in low and low[k] not in (None, ""):
            return low[k]
    return default


def parse_rows(reader: csv.DictReader, fmt: str):
    """Generator: (match_key, chrom, start, end, cm, snps).
    match_key ist bei GEDmatch die Kit-ID, sonst der Anzeigename."""
    for row in reader:
        if fmt == "gedmatch":
            key   = str(_get(row, "matchedkit")).strip()
            chrom = parse_chromosome(_get(row, "chr", "chromosome"))
            start = _int(_get(row, "b37 start", "b37 start pos'n", "start location"))
            end   = _int(_get(row, "b37 end", "b37 end pos'n", "end location"))
            cm    = _float(_get(row, "segment cm", "cm", "centimorgans"))
            snps  = _int(_get(row, "snps", "matching snps"))
        else:  # myheritage / ftdna
            key   = str(_get(row, "match name")).strip()
            chrom = parse_chromosome(_get(row, "chromosome", "chr"))
            start = _int(_get(row, "start location", "start point", "b37 start"))
            end   = _int(_get(row, "end location", "end point", "b37 end"))
            cm    = _float(_get(row, "centimorgans", "cm", "genetic distance"))
            snps  = _int(_get(row, "snps", "matching snps", "#snps"))
        if not key or not chrom or end <= start:
            continue
        yield key, chrom, start, end, cm, snps


def resolve_names(db: Database, test_guid: str, names: set[str]) -> dict[str, str]:
    """Anzeigename → match_guid (case-insensitiv, nur eindeutige Treffer)."""
    by_name: dict[str, list[str]] = {}
    for m in db.get_matches(test_guid):
        n = (m.display_name or "").strip().lower()
        if n:
            by_name.setdefault(n, []).append(m.match_guid)
    out = {}
    for name in names:
        guids = by_name.get(name.strip().lower(), [])
        if len(guids) == 1:
            out[name] = guids[0]
    return out


def run(path: Path, kit_guid: str = "", db_file: str = "") -> dict:
    if not path.exists():
        print(f"Fehler: {path} nicht gefunden.")
        sys.exit(1)

    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=delim)
        fmt = detect_format(reader.fieldnames)
        if not fmt:
            print(f"Unbekanntes Format. Kopfzeile: {reader.fieldnames}")
            sys.exit(1)
        rows = list(parse_rows(reader, fmt))

    if fmt == "gedmatch" and not kit_guid:
        kit_guid = "gedmatch-self"
    if not kit_guid:
        print("Fehler: --kit KIT_GUID erforderlich (Kit, zu dem die Segmente gehören).")
        sys.exit(1)

    db = Database(db_file) if db_file else Database()
    now = datetime.now(timezone.utc).isoformat()

    if fmt == "gedmatch":
        guid_of = {k: f"gm-{k}" for k, *_ in rows}
    else:
        guid_of = resolve_names(db, kit_guid, {k for k, *_ in rows})

    segs, unresolved = [], {}
    for key, chrom, start, end, cm, snps in rows:
        guid = guid_of.get(key)
        if not guid:
            unresolved[key] = unresolved.get(key, 0) + 1
            continue
        segs.append({
            "test_guid": kit_guid, "match_guid": guid,
            "chromosome": chrom, "start_location": start, "end_location": end,
            "length_cm": cm, "snp_count": snps, "fetched_at": now,
        })

    n = db.bulk_upsert_segments(segs)
    db.close()

    n_x = sum(1 for s in segs if s["chromosome"] == 23)
    print(f"Format: {fmt}  ·  Kit: {kit_guid}")
    print(f"Importiert: {n} Segmente ({n_x} auf X)")
    if unresolved:
        print(f"Nicht zugeordnet ({len(unresolved)} Namen – Match-Liste zuerst importieren?):")
        for name, cnt in sorted(unresolved.items(), key=lambda x: -x[1])[:15]:
            print(f"  {cnt:4d}×  {name}")
    return {"format": fmt, "imported": n, "unresolved": unresolved}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="Segment-CSV (GEDmatch / MyHeritage / FTDNA)")
    ap.add_argument("--kit", default="",
                    help="GUID des eigenen Kits (GEDmatch-Default: gedmatch-self)")
    ap.add_argument("--db", default="", help="Pfad zur Datenbank (Default: ancestry_dna.db)")
    args = ap.parse_args()
    run(Path(args.file), args.kit, args.db)
