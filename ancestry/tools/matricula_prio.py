#!/usr/bin/env python3
"""
matricula_prio.py — Pfarrei-Prioritätsliste aus Anverwandte-Matricula-Links

Wertet webtrees_crawl.db aus und zählt, wie häufig jede Kirchengemeinde
in den Matricula-Online-Belegen der Anverwandte-Personen auftaucht.
Ergebnis: Rangliste der Pfarreien — Pfarreien oben = größter Nutzen bei
Transkription, weil viele Anverwandte-Personen dort Einträge haben.

Aufruf:
  python matricula_prio.py
  python matricula_prio.py webtrees_anverwandte.db
  python matricula_prio.py --csv prio.csv
  python matricula_prio.py --diocese osnabrueck   # nur eine Diözese
  python matricula_prio.py --top 20               # nur Top-N
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
ANCESTRY_DIR = SCRIPT_DIR.parent

_CRAWL_DB_DEFAULT = SCRIPT_DIR / "webtrees_crawl.db"

# Band-Slug aus Matricula-URL extrahieren
# https://data.matricula-online.eu/de/deutschland/osnabrueck/bad-essen/kb-01/?pg=5
#                                                              ^^^^^^^^^ ^^^^
_BAND_RE = re.compile(
    r"matricula-online\.eu/[^/]+/[^/]+/([^/]+)/([^/]+)/([^/?]+)"
)


def _parse_band(url: str) -> tuple[str, str, str]:
    """Gibt (diocese, parish, band) aus einer Matricula-URL zurück."""
    m = _BAND_RE.search(url or "")
    if m:
        return m.group(1), m.group(2), m.group(3)
    return "", "", ""


def analyse(crawl_db: Path,
            filter_diocese: str = "",
            progress_cb=None) -> dict:
    """Liest webtrees_crawl.db und erstellt Pfarrei-Statistik.

    Returns
    -------
    dict mit 'parishes', 'dioceses', 'total_refs', 'total_persons'
      parishes: list[dict] sortiert nach ref_count absteigend
        {diocese, parish, ref_count, person_count, band_count, bands}
      dioceses: list[dict] sortiert nach ref_count absteigend
        {diocese, ref_count, parish_count}
    """
    p = progress_cb or (lambda m, **kw: print(m, flush=True))

    if not crawl_db.exists():
        raise FileNotFoundError(f"Crawl-DB nicht gefunden: {crawl_db}")

    conn = sqlite3.connect(str(crawl_db))
    conn.row_factory = sqlite3.Row

    # parish → {ref_count, persons, bands}
    parish_refs:   dict[tuple, int]      = defaultdict(int)   # (diocese,parish) → count
    parish_persons: dict[tuple, set]     = defaultdict(set)   # (diocese,parish) → set(person_ids)
    parish_bands:  dict[tuple, set]      = defaultdict(set)   # (diocese,parish) → set(band_slugs)

    total_refs    = 0
    total_persons = 0

    rows = conn.execute(
        "SELECT id, matricula_json FROM wt_persons "
        "WHERE COALESCE(matricula_json, '') NOT IN ('', '[]')"
    ).fetchall()
    conn.close()

    p(f"  {len(rows):,} Personen mit Matricula-Belegen gefunden")

    for r in rows:
        pid = r["id"]
        try:
            entries = json.loads(r["matricula_json"] or "[]")
        except (ValueError, TypeError):
            continue
        if not isinstance(entries, list):
            continue

        person_counted = False
        for e in entries:
            url = (e.get("url_old") or "").strip()
            if not url:
                continue
            diocese, parish, band = _parse_band(url)
            if not diocese and not parish:
                diocese = (e.get("diocese")    or "").strip()
                parish  = (e.get("parish_old") or "").strip()
            if not diocese and not parish:
                continue
            if filter_diocese and diocese != filter_diocese:
                continue

            key = (diocese, parish)
            parish_refs[key] += 1
            parish_persons[key].add(pid)
            if band:
                parish_bands[key].add(band)
            total_refs += 1
            if not person_counted:
                total_persons += 1
                person_counted = True

    # ── Pfarrei-Liste aufbauen ────────────────────────────────────────────────
    parishes = []
    for (diocese, parish), ref_count in sorted(
            parish_refs.items(), key=lambda x: -x[1]):
        bands = sorted(parish_bands[(diocese, parish)])
        parishes.append({
            "diocese":      diocese,
            "parish":       parish,
            "ref_count":    ref_count,
            "person_count": len(parish_persons[(diocese, parish)]),
            "band_count":   len(bands),
            "bands":        ", ".join(bands),
        })

    # ── Diözesen-Zusammenfassung ──────────────────────────────────────────────
    dio_refs:     dict[str, int] = defaultdict(int)
    dio_parishes: dict[str, set] = defaultdict(set)
    for row in parishes:
        d = row["diocese"]
        dio_refs[d]     += row["ref_count"]
        dio_parishes[d].add(row["parish"])

    dioceses = [
        {"diocese": d, "ref_count": dio_refs[d],
         "parish_count": len(dio_parishes[d])}
        for d in sorted(dio_refs, key=lambda x: -dio_refs[x])
    ]

    return {
        "parishes":      parishes,
        "dioceses":      dioceses,
        "total_refs":    total_refs,
        "total_persons": total_persons,
    }


def print_report(result: dict, top: int = 0):
    parishes = result["parishes"]
    dioceses = result["dioceses"]
    if top:
        parishes = parishes[:top]

    print(f"\n{'─'*72}")
    print("  Matricula-Priorität: Anverwandte → Pfarreistatistik")
    print(f"{'─'*72}")
    print(f"  Gesamt: {result['total_refs']:,} Belege  |  "
          f"{result['total_persons']:,} Personen mit Matricula-Links")
    print(f"{'─'*72}\n")

    # ── Pfarrei-Rangliste ─────────────────────────────────────────────────────
    hdr = f"{'Rang':>4}  {'Diözese':<18}  {'Pfarrei':<28}  {'Belege':>6}  {'Pers.':>5}  Bände"
    print(hdr)
    print("─" * len(hdr))
    for i, row in enumerate(parishes, 1):
        bands_short = row["bands"][:35] + "…" if len(row["bands"]) > 36 else row["bands"]
        print(f"{i:>4}  {row['diocese']:<18}  {row['parish']:<28}  "
              f"{row['ref_count']:>6}  {row['person_count']:>5}  {bands_short}")

    if top and len(result["parishes"]) > top:
        print(f"  … {len(result['parishes']) - top} weitere Pfarreien")

    # ── Diözesen-Übersicht ────────────────────────────────────────────────────
    print(f"\n{'─'*50}")
    print("  Diözesen-Übersicht:")
    total = result["total_refs"] or 1
    for d in dioceses:
        pct = d["ref_count"] / total * 100
        bar = "█" * int(pct / 2)
        print(f"  {d['diocese']:<20}  {d['ref_count']:>6} Belege  "
              f"({pct:5.1f}%)  {d['parish_count']} Pfarreien  {bar}")
    print()


def write_csv(result: dict, csv_path: Path):
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "rang", "diocese", "parish", "ref_count", "person_count",
            "band_count", "bands"])
        w.writeheader()
        for i, row in enumerate(result["parishes"], 1):
            w.writerow({"rang": i, **row})
    print(f"CSV gespeichert: {csv_path}")


def run(
    crawl_db: str | None = None,
    filter_diocese: str = "",
    top: int = 0,
    csv_path: str | None = None,
    progress_cb=None,
) -> dict:
    """Öffentliche API für GUI-Aufruf."""
    db = Path(crawl_db) if crawl_db else _CRAWL_DB_DEFAULT
    result = analyse(db, filter_diocese=filter_diocese, progress_cb=progress_cb)
    print_report(result, top=top)
    if csv_path:
        write_csv(result, Path(csv_path))
    return result


def main():
    ap = argparse.ArgumentParser(
        description="Pfarrei-Priorität aus Anverwandte-Matricula-Links")
    ap.add_argument("crawl_db", nargs="?", default=None,
                    help="webtrees_crawl.db (Standard: tools/webtrees_crawl.db)")
    ap.add_argument("--diocese", default="",
                    help="Nur eine Diözese zeigen (z.B. 'osnabrueck')")
    ap.add_argument("--top", type=int, default=0,
                    help="Nur Top-N Pfarreien anzeigen (0 = alle)")
    ap.add_argument("--csv", default=None,
                    help="Ergebnis als CSV speichern")
    args = ap.parse_args()

    run(
        crawl_db=args.crawl_db,
        filter_diocese=args.diocese,
        top=args.top,
        csv_path=args.csv,
    )


if __name__ == "__main__":
    main()
