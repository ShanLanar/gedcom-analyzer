#!/usr/bin/env python3
"""
WikiTree-Vorfahren in gedcom_persons importieren (source='wikitree').

Holt über die öffentliche WikiTree-API die Ahnenlinie einer Start-Person
und importiert sie – genau wie der Anverwandte-Crawl – als eigene Quelle,
mit Duplikat-Querbezügen zu deinem GEDCOM (nichts wird überschrieben).

WikiTree-API ist nur mit Internet erreichbar (läuft lokal, nicht in der
gekapselten Sandbox).

Aufruf:
  python import_wikitree.py Einstein-1 --depth 6
  python import_wikitree.py Kovermann-123 --no-link
"""
import sys
import argparse
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
    from ancestry.core import wikitree
    from ancestry.core import bridge
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
