"""Pedigree-Lücken-Analyse: welche Ahnen-Generationen fehlen einem Match noch?

Standard-Ahnentafel: Generation g hat 2**(g-1) Plätze
(Gen 1 = die Person selbst, Gen 2 = Eltern, Gen 3 = Großeltern, …).
Aus den pro Generation tatsächlich vorhandenen Personen lässt sich ablesen,
bis zu welcher Generation die Ahnentafel „voll" ist und wo die erste Lücke
(„Brick Wall"-Front) sitzt.
"""
from __future__ import annotations


def slots_in_generation(generation: int) -> int:
    """Anzahl Ahnenplätze in einer Generation (Gen 1 = 1, Gen 2 = 2, …)."""
    return 2 ** (generation - 1) if generation >= 1 else 0


def analyze_pedigree_gaps(gen_counts: dict, min_gen: int = 2) -> dict:
    """Analysiert die Generationen-Vollständigkeit einer Ahnentafel.

    Parameters
    ----------
    gen_counts:
        {generation: vorhandene_personen}. Schlüssel/Werte dürfen Strings sein
        (werden zu int gecastet); ungültige Einträge werden ignoriert.
    min_gen:
        Erste betrachtete Generation (Default 2 = Eltern; Gen 1 = die Person
        selbst ist für Lückenbetrachtungen meist uninteressant).

    Returns
    -------
    dict mit:
      - ``max_gen``: höchste Generation mit ≥1 Person (0 wenn leer)
      - ``per_gen``: Liste ``{generation, present, possible, missing, pct,
        complete}`` für min_gen..max_gen
      - ``complete_through``: höchste Generation, die lückenlos voll ist
        (min_gen-1 wenn schon die erste Generation Lücken hat)
      - ``first_gap_gen``: erste unvollständige Generation (None wenn keine)
      - ``total_present`` / ``total_possible`` / ``pct``: Gesamtsumme über
        min_gen..max_gen
    """
    clean: dict[int, int] = {}
    for g, c in (gen_counts or {}).items():
        try:
            gi, ci = int(g), int(c)
        except (TypeError, ValueError):
            continue
        if gi >= 1 and ci > 0:
            clean[gi] = ci

    if not clean:
        return {"max_gen": 0, "per_gen": [], "complete_through": min_gen - 1,
                "first_gap_gen": None, "total_present": 0,
                "total_possible": 0, "pct": 0.0}

    max_gen = max(clean)
    per_gen = []
    total_present = total_possible = 0
    complete_through = min_gen - 1
    first_gap_gen = None
    still_complete = True

    for g in range(min_gen, max_gen + 1):
        possible = slots_in_generation(g)
        # nie mehr als möglich zählen (doppelte/uneindeutige Einträge kappen)
        present = min(clean.get(g, 0), possible)
        missing = possible - present
        pct = round(present / possible * 100, 1) if possible else 0.0
        complete = missing == 0
        per_gen.append({"generation": g, "present": present, "possible": possible,
                        "missing": missing, "pct": pct, "complete": complete})
        total_present += present
        total_possible += possible
        if complete and still_complete:
            complete_through = g
        else:
            still_complete = False
            if first_gap_gen is None:
                first_gap_gen = g

    pct = round(total_present / total_possible * 100, 1) if total_possible else 0.0
    return {"max_gen": max_gen, "per_gen": per_gen,
            "complete_through": complete_through, "first_gap_gen": first_gap_gen,
            "total_present": total_present, "total_possible": total_possible,
            "pct": pct}


def summarize_match_gaps(matches: list, min_gen: int = 2) -> list:
    """Verdichtet get_pedigree_completeness_per_match()-Rohdaten zu einer
    sortierten Übersicht (vollständigste/tiefste Ahnentafeln zuerst).

    Erwartet pro Eintrag ``{match_guid, display_name, shared_cm, generations}``
    mit ``generations`` als {gen: count}. Gibt je Match die Kernkennzahlen der
    Lückenanalyse zurück.
    """
    out = []
    for m in matches or []:
        ana = analyze_pedigree_gaps(m.get("generations", {}), min_gen=min_gen)
        out.append({
            "match_guid":       m.get("match_guid", ""),
            "display_name":     m.get("display_name", ""),
            "shared_cm":        m.get("shared_cm", 0),
            "max_gen":          ana["max_gen"],
            "complete_through": ana["complete_through"],
            "first_gap_gen":    ana["first_gap_gen"],
            "pct":              ana["pct"],
            "total_present":    ana["total_present"],
            "total_possible":   ana["total_possible"],
        })
    out.sort(key=lambda r: (r["complete_through"], r["max_gen"], r["pct"]),
             reverse=True)
    return out
