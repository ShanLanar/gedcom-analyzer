"""
wikitree.py — WikiTree-Anreicherung für das Bridge-Modul.
"""

import logging

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# WikiTree-Anreicherung — Match-Ahnenlinien über api.wikitree.com verlängern
# ─────────────────────────────────────────────────────────────────────────────

def wikitree_extend_match(db, test_guid: str, match_guid: str,
                          max_ancestors: int = 4, depth: int = 4,
                          progress_cb=None) -> list[dict]:
    """Sucht für die markantesten Ahnen eines Matches passende WikiTree-Profile
    und ruft deren Ahnenlinie ab, um den Match-Stammbaum zu verlängern.

    Wählt die tiefsten Generationen (beste Ansatzpunkte), entdoppelt nach
    Nachname+Ort und fragt höchstens `max_ancestors` Linien ab (schont das
    WikiTree-Rate-Limit).

    Rückgabe: Liste von find_ancestor_lineage()-Ergebnissen, eines pro Ahn.
    """
    try:
        from core.wikitree import find_ancestor_lineage
    except ImportError:
        from wikitree import find_ancestor_lineage

    def p(msg):
        if progress_cb:
            try: progress_cb(msg)
            except Exception as e: log.debug("progress_cb wikitree_extend: %s", e)

    rows = db.get_pedigree_for_match(test_guid, match_guid)
    # nur Ahnen mit Nachname; tiefste Generationen zuerst (beste Leads)
    cand = [r for r in rows if (r.get("surname") or "").strip()
            and int(r.get("generation") or 0) >= 2]
    cand.sort(key=lambda r: int(r.get("generation") or 0), reverse=True)

    seen, picks = set(), []
    for r in cand:
        sn = (r.get("surname") or "").strip()
        pl = (r.get("birth_place") or "").strip()
        kdup = (sn.lower(), pl.lower())
        if kdup in seen:
            continue
        seen.add(kdup)
        picks.append(r)
        if len(picks) >= max_ancestors:
            break

    results = []
    for i, r in enumerate(picks):
        sn = (r.get("surname") or "").strip()
        gn = (r.get("given_name") or "").strip()
        pl = (r.get("birth_place") or "").strip()
        by = r.get("birth_year") or ""
        p(f"WikiTree {i+1}/{len(picks)}: suche {gn} {sn} ({pl} {by}) …")
        try:
            res = find_ancestor_lineage(surname=sn, birth_place=pl,
                                        birth_year=by, first_name=gn, depth=depth)
        except Exception as e:
            res = {"query": {"surname": sn, "birth_place": pl, "birth_year": by},
                   "best": None, "candidates": [], "lineage": [], "error": str(e)}
        results.append(res)

    found = sum(1 for r in results if r.get("best"))
    p(f"WikiTree-Abgleich fertig: {found}/{len(picks)} Linien gefunden.")
    return results
