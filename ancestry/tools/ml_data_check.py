#!/usr/bin/env python3
"""
ML-Datencheck — prüft, ob genug gelabelte Daten für ein Herkunftsmodell da sind.

Zählt in ancestry_dna.db:
  * Matches gesamt / je Quelle
  * Matches mit Pedigree-Nachnamen (Feature-Grundlage)
  * Matches mit probable_origin-Label (Trainings-Ziel)
  * Verteilung der gelabelten Regionen

Faustregel: für ein brauchbares Modell sollten pro Region >= ~30 gelabelte
Matches vorliegen und insgesamt >= ~300 Labels.

Aufruf:
  python ml_data_check.py
"""
import sys
import json
import sqlite3
from pathlib import Path
from collections import Counter

ANCESTRY_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ANCESTRY_DIR / "ancestry_dna.db"


def main():
    if not DB_PATH.exists():
        print(f"DB nicht gefunden: {DB_PATH}")
        sys.exit(1)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row

    def count(sql, *a):
        try:
            return c.execute(sql, a).fetchone()[0]
        except Exception:
            return None

    total = count("SELECT COUNT(*) FROM matches")
    print(f"Matches gesamt: {total}")

    print("\nJe Quelle:")
    for r in c.execute("SELECT source, COUNT(*) n FROM matches GROUP BY source ORDER BY n DESC"):
        print(f"  {r['source'] or '(leer)':12} {r['n']}")

    # ── GEDCOM-Trainingskorpus (der eigentliche gelabelte Datensatz) ──────────
    print("\n── GEDCOM-Trainingskorpus ──")
    gp_total = count("SELECT COUNT(*) FROM gedcom_persons")
    gp_named = count("SELECT COUNT(*) FROM gedcom_persons WHERE TRIM(surname)<>''")
    gp_place = count("SELECT COUNT(*) FROM gedcom_persons "
                     "WHERE TRIM(surname)<>'' AND TRIM(birth_place)<>''")
    print(f"  Personen gesamt:                {gp_total}")
    print(f"  mit Nachname:                   {gp_named}")
    print(f"  mit Nachname + Geburtsort:      {gp_place}  ← Trainings-Paare")

    # Regionsverteilung im GEDCOM (Ground Truth für das Modell)
    try:
        from ancestry.core.bridge import _extract_region
    except Exception:
        _extract_region = lambda s: (s or "").split(",")[-1].strip()

    ged_regions = Counter()
    for r in c.execute("SELECT birth_place FROM gedcom_persons "
                       "WHERE TRIM(surname)<>'' AND TRIM(birth_place)<>''"):
        reg = _extract_region(r["birth_place"])
        if reg:
            ged_regions[reg] += 1
    big_ged = sum(1 for n in ged_regions.values() if n >= 30)
    print(f"  unterscheidbare Regionen:       {len(ged_regions)} "
          f"(davon {big_ged} mit >=30 Personen)")
    print("  Top-Regionen:")
    for reg, n in ged_regions.most_common(12):
        print(f"    {reg:28} {n}")
    if gp_place and gp_place >= 1000 and big_ged >= 5:
        print("  → Starker Trainingskorpus. scikit-learn Random Forest klar empfohlen.")

    ped = count("SELECT COUNT(DISTINCT match_guid) FROM match_pedigree WHERE TRIM(surname)<>''")
    print(f"\nMatches mit Pedigree-Nachnamen: {ped}")

    labeled = count("SELECT COUNT(*) FROM matches WHERE COALESCE(probable_origin,'')<>''")
    print(f"Matches mit Herkunfts-Label:    {labeled}")

    if not labeled:
        print("\n→ Noch keine Labels. Zuerst im Tool '🗺 Herkunft ableiten' laufen lassen,")
        print("  dann diesen Check erneut ausführen.")
        return

    regions = Counter()
    for r in c.execute("SELECT probable_origin FROM matches WHERE COALESCE(probable_origin,'')<>''"):
        try:
            regions[json.loads(r["probable_origin"]).get("region", "?")] += 1
        except Exception:
            regions["?"] += 1

    print(f"\nRegionen ({len(regions)} verschiedene):")
    for reg, n in regions.most_common():
        flag = "✓" if n >= 30 else "·"
        print(f"  {flag} {reg:28} {n}")

    big = sum(1 for n in regions.values() if n >= 30)
    print("\n── Einschätzung ──")
    print(f"  Labels gesamt:        {labeled}")
    print(f"  Regionen mit >=30:    {big}")
    if labeled >= 300 and big >= 3:
        print("  → Genug für ein ML-Modell (scikit-learn empfohlen).")
    elif labeled >= 100:
        print("  → Grenzwertig. Reines-Python-k-NN sinnvoller als Random Forest.")
    else:
        print("  → Zu wenig. Erst mehr Pedigrees/Orte laden, dann erneut.")


if __name__ == "__main__":
    main()
