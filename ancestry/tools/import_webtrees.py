#!/usr/bin/env python3
"""
Gecrawlte webtrees-Personen (Anverwandte) in gedcom_persons importieren.

Liest die vom Crawler erzeugte webtrees_crawl.db (Tabelle wt_persons) und
importiert sie mit source='anverwandte' in ancestry_dna.db. Die eigenen
GEDCOM-Personen (source='gedcom') bleiben unberührt; Duplikate werden NICHT
zusammengeführt, sondern als Instanzen derselben Person über
gedcom_person_xref querverknüpft (dein GEDCOM bleibt führend).

Aufruf:
  python import_webtrees.py [webtrees_crawl.db]
  python import_webtrees.py --no-link        # nur importieren, nicht verknüpfen
"""
import sys
import sqlite3
import argparse
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
ANCESTRY_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(ANCESTRY_DIR))
sys.path.insert(0, str(ANCESTRY_DIR / "core"))

DB_PATH    = ANCESTRY_DIR / "ancestry_dna.db"
CRAWL_DB   = SCRIPT_DIR / "webtrees_crawl.db"
SOURCE     = "anverwandte"


def load_wt_persons(crawl_db: Path) -> list[dict]:
    if not crawl_db.exists():
        print(f"Crawl-DB nicht gefunden: {crawl_db}")
        sys.exit(1)
    c = sqlite3.connect(str(crawl_db)); c.row_factory = sqlite3.Row
    out = []
    for r in c.execute("SELECT * FROM wt_persons"):
        out.append({
            "ext_id":      r["id"],
            "given_name":  r["given_name"] or "",
            "surname":     r["surname"] or "",
            "sex":         r["sex"] or "",
            "birth_year":  r["birth_year"] or "",
            "birth_place": r["birth_place"] or "",
            "death_year":  r["death_year"] or "",
            "death_place": r["death_place"] or "",
        })
    c.close()
    return out


def run(crawl_db: Path, do_link: bool):
    persons = load_wt_persons(crawl_db)
    print(f"{len(persons)} Personen aus {crawl_db.name} gelesen.")

    from database import Database
    from core import bridge
    db = Database(str(DB_PATH))
    try:
        n = bridge.import_external_persons(db, persons, source=SOURCE)
        print(f"Importiert als source='{SOURCE}': {n}")
        if do_link:
            linked = bridge.link_duplicates(
                db, source=SOURCE,
                progress_cb=lambda m: print("  " + m))
            print(f"Querbezüge zu deinem GEDCOM: {linked}")
        # Übersicht
        with db._cursor() as cur:
            for src, cnt in cur.execute(
                "SELECT source, COUNT(*) FROM gedcom_persons GROUP BY source"):
                print(f"  gedcom_persons[{src}]: {cnt}")
    finally:
        db.close()
    print(f"Fertig. Datenbank: {DB_PATH}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("crawl_db", nargs="?", default=str(CRAWL_DB))
    ap.add_argument("--no-link", action="store_true",
                    help="nur importieren, keine Dedup-Querbezüge anlegen")
    args = ap.parse_args()
    run(Path(args.crawl_db), do_link=not args.no_link)
