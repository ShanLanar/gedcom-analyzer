#!/usr/bin/env python3
"""
import_wikitree.py — WikiTree-Ahnen → gedcom_persons (source='wikitree')

[DE] Importiert die Vorfahren einer WikiTree-Person in die Datenbank.
So findest du die WikiTree-ID:
  1. Auf wikitree.com die Person suchen (z. B. "Kovermann")
  2. Auf der Profilseite die ID aus der URL ablesen:
     wikitree.com/wiki/Kovermann-123  →  ID = Kovermann-123
  3. Import starten:
       python import_wikitree.py Kovermann-123
  Optional:
       python import_wikitree.py Kovermann-123 --depth 8   # bis 8 Generationen
       python import_wikitree.py Kovermann-123 --no-link   # keine Querbezüge anlegen

Die WikiTree-API ist öffentlich und erfordert keine Anmeldung.
Tiefe (--depth): Standard 6 = ca. 64 Vorfahren; 8 = bis 256 Vorfahren.

----

[EN] Imports the ancestors of a WikiTree person into the database.
How to find the WikiTree ID:
  1. Search for the person on wikitree.com (e.g. "Kovermann")
  2. Read the ID from the profile URL:
     wikitree.com/wiki/Kovermann-123  →  ID = Kovermann-123
  3. Start import:
       python import_wikitree.py Kovermann-123
  Optional:
       python import_wikitree.py Kovermann-123 --depth 8   # up to 8 generations
       python import_wikitree.py Kovermann-123 --no-link   # skip cross-references

The WikiTree API is public and requires no login.
Depth (--depth): default 6 = ~64 ancestors; 8 = up to 256 ancestors.
"""
import argparse
import sys
from pathlib import Path

ANCESTRY_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ANCESTRY_DIR / "ancestry_dna.db"
SOURCE = "wikitree"


def _year(s: str) -> str:
    import re
    m = re.search(r"\b(1[0-9]{3}|20[0-2][0-9])\b", s or "")
    return m.group(1) if m else ""


def map_profile(pr: dict) -> dict:
    """WikiTree-Profil -> Personen-Dict für import_external_persons."""
    return {
        "ext_id":      str(pr.get("Name") or pr.get("Id") or "").strip(),
        "given_name":  (pr.get("FirstName") or pr.get("RealName") or "").strip(),
        "surname":     (pr.get("LastNameAtBirth") or pr.get("LastNameCurrent") or "").strip(),
        "sex":         {"Male": "M", "Female": "F"}.get(pr.get("Gender", ""), ""),
        "birth_year":  _year(pr.get("BirthDate") or ""),
        "birth_place": (pr.get("BirthLocation") or "").strip(),
        "death_year":  _year(pr.get("DeathDate") or ""),
        "death_place": (pr.get("DeathLocation") or "").strip(),
    }


def run(key: str, depth: int, do_link: bool):
    from ancestry.core import bridge, wikitree
    from ancestry.core.database import Database

    print(f"Lade WikiTree-Ahnen von {key} (Tiefe {depth}) …")
    anc = wikitree.get_ancestors(key, depth=depth)
    # Startperson selbst zusätzlich holen (getAncestors liefert sie meist mit)
    persons = [map_profile(a) for a in anc if a]
    persons = [p for p in persons if p["ext_id"] and (p["given_name"] or p["surname"])]
    print(f"{len(persons)} Profile gelesen.")
    if not persons:
        print("Nichts importiert (kein Treffer / kein Netz?)."); return

    db = Database(str(DB_PATH))
    try:
        n = bridge.import_external_persons(db, persons, source=SOURCE)
        print(f"Importiert als source='{SOURCE}': {n}")
        if do_link:
            linked = bridge.link_duplicates(db, source=SOURCE,
                                            progress_cb=lambda m: print("  " + m))
            print(f"Querbezüge zu deinem GEDCOM: {linked}")
        with db._cursor() as cur:
            for src, cnt in cur.execute(
                "SELECT source, COUNT(*) FROM gedcom_persons GROUP BY source"):
                print(f"  gedcom_persons[{src}]: {cnt}")
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("key", help="WikiTree-ID der Startperson, z.B. Kovermann-123")
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--no-link", action="store_true")
    args = ap.parse_args()
    run(args.key, depth=args.depth, do_link=not args.no_link)
