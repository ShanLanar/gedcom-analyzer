"""Importiert FTDNA Family Finder Match-Liste aus CSV-Export.

Unterstützte FTDNA-Exportformate (automatische Erkennung):
  • Classic:  Name | Relationship Range | Suggested Relationship |
              Longest Block | Total Shared cM
  • Modern:   Full Name | Match Date | Relationship Range |
              Suggested Relationship | Longest Segment | Total Shared cM |
              X Match | FTDNA ID
  • Compact:  Name | Relationship | cM Shared | Longest Block | Date

Aufruf:
  python import_ftdna_matches.py [pfad/zur/matches.csv] [--kit FTDNA_KIT_ID]
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
ANCESTRY_DIR = SCRIPT_DIR.parent
DB_PATH      = ANCESTRY_DIR / "ancestry_dna.db"
DATA_DIR     = ANCESTRY_DIR / "data"

# Eigene FTDNA-Kit-ID (als test_guid); überschreibbar per --kit
FTDNA_KIT_ID = "FTDNA_DEFAULT"


def _float(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(str(v).replace(",", ".").replace(" cM", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _str(v) -> str:
    return str(v).strip() if v is not None else ""


def _make_guid(name: str, ftdna_id: str = "") -> str:
    """Stabile GUID: ftdna-{ftdna_id} oder ftdna-{name_hash}."""
    if ftdna_id:
        return f"ftdna-{ftdna_id}"
    h = hashlib.md5(name.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"ftdna-{h}"


# ── Format-Erkennung ──────────────────────────────────────────────────────────

def _detect_format(header: list[str]) -> str:
    h = [c.lower().strip() for c in header]
    if "ftdna id" in h or "ftdna_id" in h:
        return "modern"
    if "match date" in h or "date" in h:
        return "compact"
    return "classic"


def _parse_row_classic(row: dict) -> dict | None:
    name = _str(row.get("Name") or row.get("name"))
    if not name:
        return None
    return {
        "display_name":         name,
        "shared_cm":            _float(row.get("Total Shared cM") or row.get("Total_cM") or row.get("cM Shared")),
        "longest_segment":      _float(row.get("Longest Block")   or row.get("Longest Segment")),
        "predicted_relationship": _str(row.get("Suggested Relationship") or row.get("Relationship")),
        "relationship_range":   _str(row.get("Relationship Range") or ""),
        "ftdna_id":             "",
    }


def _parse_row_modern(row: dict) -> dict | None:
    name = _str(row.get("Full Name") or row.get("Name"))
    if not name:
        return None
    return {
        "display_name":         name,
        "shared_cm":            _float(row.get("Total Shared cM") or row.get("cM")),
        "longest_segment":      _float(row.get("Longest Segment") or row.get("Longest Block")),
        "predicted_relationship": _str(row.get("Suggested Relationship") or row.get("Relationship")),
        "relationship_range":   _str(row.get("Relationship Range") or ""),
        "ftdna_id":             _str(row.get("FTDNA ID") or row.get("FTDNA_ID") or ""),
    }


def parse_csv(path: Path) -> list[dict]:
    """Liest die FTDNA-CSV und liefert normalisierte Match-Dicts."""
    matches: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="", errors="replace") as fh:
        # Detect delimiter: FTDNA uses comma
        sample = fh.read(4096)
        fh.seek(0)
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
        reader = csv.DictReader(fh, delimiter=delimiter)
        if reader.fieldnames is None:
            return []
        fmt = _detect_format(list(reader.fieldnames))
        parse_fn = _parse_row_modern if fmt == "modern" else _parse_row_classic
        for row in reader:
            m = parse_fn(row)
            if m and m["shared_cm"] > 0:
                matches.append(m)
    return matches


# ── Import ────────────────────────────────────────────────────────────────────

def run(path: Path, kit_guid: str = FTDNA_KIT_ID,
        db_file: Path = DB_PATH) -> dict:
    """Importiert FTDNA-Matches in die DB.

    Returns: {"imported": int, "skipped": int, "source": "ftdna"}
    """
    from ancestry.core.database import Database
    from ancestry.models import DnaMatch

    matches = parse_csv(path)
    if not matches:
        return {"imported": 0, "skipped": 0, "source": "ftdna"}

    db = Database(db_file)
    now = datetime.now(timezone.utc).isoformat()
    imported = skipped = 0

    for m in matches:
        guid = _make_guid(m["display_name"], m.get("ftdna_id", ""))
        shared_cm = m["shared_cm"]
        # FTDNA-Matches unter 7 cM sind häufig IBS → überspringen
        if shared_cm < 7:
            skipped += 1
            continue
        dm = DnaMatch(
            match_guid=guid,
            test_guid=kit_guid,
            display_name=m["display_name"],
            shared_cm=shared_cm,
            longest_segment=m["longest_segment"],
            predicted_relationship=m["predicted_relationship"],
            relationship_range=m["relationship_range"],
            source="ftdna",
            fetched_at=now,
        )
        db.upsert_match(dm)
        imported += 1

    db.close()
    return {"imported": imported, "skipped": skipped, "source": "ftdna"}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_file", nargs="?", help="Pfad zur FTDNA matches.csv")
    parser.add_argument("--kit",    default=FTDNA_KIT_ID, help="FTDNA Kit-ID (test_guid)")
    parser.add_argument("--db",     default=str(DB_PATH),  help="Datenbankpfad")
    args = parser.parse_args()

    if args.csv_file:
        csv_path = Path(args.csv_file)
    else:
        candidates = sorted(DATA_DIR.glob("ftdna_matches*.csv")) + sorted(DATA_DIR.glob("matches*.csv"))
        if not candidates:
            print(f"❌  Keine FTDNA-Match-CSV gefunden. Lege sie in {DATA_DIR}/ ab.")
            sys.exit(1)
        csv_path = candidates[0]
        print(f"✓  Verwende: {csv_path}")

    result = run(csv_path, kit_guid=args.kit, db_file=Path(args.db))
    n = result["imported"]
    s = result["skipped"]
    print(f"✓  {n} Matches importiert, {s} übersprungen (<7 cM).")


if __name__ == "__main__":
    main()
