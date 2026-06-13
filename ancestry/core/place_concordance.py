"""Ortskonkordanz: bildet Ortsnamen aus Fremdquellen (v. a. Anverwandte/Webtrees)
auf deine Standard-Ortsnamen (wie im eigenen GEDCOM) ab.

Workflow:
  1. export_distinct_places(db, datei)  → Liste aller (Fremd-)Orte + Häufigkeit.
     Diese Liste gibst du an eine KI: „mappe auf meine Standardorte".
  2. Das KI-Ergebnis (JSON {fremd: standard}) per import_mapping() hinterlegen.
  3. map_place(ort) liefert überall den Standardnamen – für Anzeige, bessere
     Pfarrei-Zuordnung (Matricula) und den Export.

Speicherort: ancestry/data/place_concordance.json (per GENEA_PLACE_CONCORDANCE
übersteuerbar). Reines JSON, kein Token/Dienst nötig.
"""
from __future__ import annotations

import json
import os

from ancestry.paths import ROOT

CONCORDANCE_PATH = os.environ.get(
    "GENEA_PLACE_CONCORDANCE",
    os.path.join(str(ROOT), "ancestry", "data", "place_concordance.json"))

_cache: dict | None = None


def _key(place: str) -> str:
    return (place or "").strip().lower()


def load(force: bool = False) -> dict:
    """{normalisierter_fremd_ort: standard_ort}."""
    global _cache
    if _cache is not None and not force:
        return _cache
    data = {}
    try:
        with open(CONCORDANCE_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        # Schlüssel normalisieren, Werte unverändert lassen
        data = {_key(k): str(v) for k, v in raw.items() if v}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    _cache = data
    return data


def map_place(place: str) -> str:
    """Standardort für einen Ort (oder der Originalort, wenn kein Mapping)."""
    if not place:
        return place
    return load().get(_key(place), place)


def save(mapping: dict) -> str:
    """Schreibt die Konkordanz (überschreibt). Gibt den Pfad zurück."""
    os.makedirs(os.path.dirname(CONCORDANCE_PATH), exist_ok=True)
    with open(CONCORDANCE_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1, sort_keys=True)
    load(force=True)
    return CONCORDANCE_PATH


def import_mapping(path: str) -> int:
    """Mergt ein KI-/Nutzer-Mapping (JSON {fremd: standard} oder CSV 'fremd;standard')
    in die Konkordanz. Gibt die Anzahl neuer/aktualisierter Einträge zurück."""
    new: dict = {}
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            new = {str(k): str(v) for k, v in json.load(f).items() if v}
    else:
        import csv
        with open(path, encoding="utf-8") as f:
            for row in csv.reader(f, delimiter=";"):
                if len(row) >= 2 and row[0].strip() and row[1].strip():
                    new[row[0].strip()] = row[1].strip()
    current = dict(load())
    # bestehende JSON liegt mit Originalschlüsseln vor – neu zusammenführen
    try:
        with open(CONCORDANCE_PATH, encoding="utf-8") as f:
            current = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        current = {}
    current.update(new)
    save(current)
    return len(new)


def export_distinct_places(db, out_path: str, source: str = "anverwandte") -> dict:
    """Schreibt alle distinkten Orte (Geburt+Tod) der gewählten Quelle mit
    Häufigkeit nach out_path – als Vorlage für die KI-Zuordnung. Bereits
    gemappte Orte werden markiert."""
    from collections import Counter
    cnt: Counter = Counter()
    with db._cursor() as cur:
        q = ("SELECT birth_place, death_place FROM gedcom_persons WHERE source=?"
             if source else "SELECT birth_place, death_place FROM gedcom_persons")
        rows = cur.execute(q, (source,) if source else ()).fetchall()
    for r in rows:
        for pl in (r["birth_place"], r["death_place"]):
            pl = (pl or "").strip()
            if pl:
                cnt[pl] += 1
    mapping = load()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Orte aus Quelle '%s' — bitte rechts den Standardort eintragen "
                "(oder als JSON {fremd: standard} an eine KI geben).\n" % source)
        f.write("# Format: <fremd_ort>  =>  <standard_ort>   (✓ = schon gemappt)\n\n")
        for place, n in cnt.most_common():
            mapped = mapping.get(_key(place), "")
            mark = f"  ✓ {mapped}" if mapped else ""
            f.write(f"{place}  ({n}×){mark}\n")
    return {"places": len(cnt), "mapped": sum(1 for p in cnt if _key(p) in mapping),
            "out": out_path}


def main():
    import argparse
    from ancestry.core.database import Database
    from ancestry.paths import DB_PATH
    ap = argparse.ArgumentParser(description="Ortskonkordanz (Anverwandte → Standard)")
    ap.add_argument("--export", nargs="?", const="", metavar="DATEI",
                    help="distinkte Orte einer Quelle als Vorlage exportieren")
    ap.add_argument("--import", dest="imp", metavar="DATEI",
                    help="KI-/Nutzer-Mapping (JSON oder CSV 'fremd;standard') importieren")
    ap.add_argument("--source", default="anverwandte")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()
    if args.imp:
        n = import_mapping(args.imp)
        print(f"📥 {n} Orts-Zuordnungen importiert → {CONCORDANCE_PATH}")
        return
    out = args.export or os.path.join(str(ROOT), "..", "output",
                                      f"orte_{args.source}.txt")
    info = export_distinct_places(Database(args.db), out, args.source)
    print(f"📤 {info['places']} Orte (davon {info['mapped']} schon gemappt) → {info['out']}")
    print("Liste/JSON an eine KI geben (linke Orte auf deine Standardorte mappen),"
          " Ergebnis als JSON mit --import zurueckspielen.")


if __name__ == "__main__":
    main()
