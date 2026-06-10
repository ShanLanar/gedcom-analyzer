"""
scoring.py — Link-Scoring zwischen Ahnentafel-Einträgen und GEDCOM-Personen.
"""

import os
from difflib import SequenceMatcher

from ._text import _norm, _koelner, _levenshtein

# Per Umgebungsvariable übersteuerbar (z. B. 0.55 bei stark endogamen Daten,
# 0.35 für explorative Läufe mit anschließender manueller Prüfung).
try:
    MIN_LINK_SCORE = float(os.environ.get("ANCESTRY_MIN_LINK_SCORE", "0.45"))
except ValueError:
    MIN_LINK_SCORE = 0.45


# ── Scoring ────────────────────────────────────────────────────────────────────

def compute_link_score(ped_given: str, ped_surname: str, ped_year,
                       ged_row: dict) -> tuple[float, str]:
    """Berechnet einen Übereinstimmungs-Score zwischen einem Ahnen aus
    einer DNA-Match-Ahnentafel und einer GEDCOM-Person.
    Gibt (total_score, methode) zurück. Score 0.0 = kein Treffer."""
    ped_sn = _norm(ped_surname)
    ped_gn = _norm(ped_given)
    ged_sn = ged_row.get("surname_norm") or ""
    ged_koe = ged_row.get("koelner_code") or ""
    ged_gn = _norm(ged_row.get("given_name", ""))

    if not ped_sn or not ged_sn:
        return 0.0, "none"

    # ── Nachname ──
    if ped_sn == ged_sn:
        name_score, method = 1.0, "exact"
    else:
        ped_koe = _koelner(ped_sn)
        if ped_koe and ged_koe and ped_koe == ged_koe and ped_koe not in ("", "0"):
            lev = _levenshtein(ped_sn, ged_sn)
            if   lev == 0: name_score, method = 1.0,  "exact"
            elif lev <= 2: name_score, method = 0.85 - lev * 0.10, "phonetic"
            elif lev <= 4: name_score, method = 0.55, "phonetic"
            else:          return 0.0, "none"
        elif len(ped_sn) >= 4:
            lev = _levenshtein(ped_sn, ged_sn)
            if lev <= 2:
                name_score, method = 0.60 - lev * 0.10, "levenshtein"
            else:
                return 0.0, "none"
        else:
            return 0.0, "none"

    # ── Vorname-Bonus +0.10 ──
    if ped_gn and ged_gn:
        ratio = SequenceMatcher(None, ped_gn, ged_gn).ratio()
        if ratio >= 0.80:
            name_score = min(1.0, name_score + 0.10)

    # ── Geburtsjahr ──
    year_bonus = 0.0
    ged_year = ged_row.get("birth_year")
    ged_qual = ged_row.get("birth_qual") or ""
    try:
        py = int(str(ped_year)[:4]) if ped_year else None
        gy = int(ged_year)           if ged_year else None
    except (ValueError, TypeError):
        py = gy = None

    if py and gy:
        tol  = 15 if ged_qual in ("about", "estimated", "abt") else 10
        diff = abs(py - gy)
        if diff == 0:
            year_bonus = 0.20
        elif diff <= tol:
            year_bonus = round(0.20 * (1.0 - diff / (tol + 1)), 3)
        elif name_score < 0.85:
            # Jahresdifferenz zu groß + kein sehr hoher Namens-Score → verwerfen
            return 0.0, "none"

    total = min(1.0, round(name_score + year_bonus, 3))
    return total, method
