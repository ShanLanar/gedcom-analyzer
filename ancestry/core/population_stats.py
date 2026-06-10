"""
population_stats.py — Bevölkerungsstatistiken aus GEDCOM + DNA-Match-Ahnentafeln.

Vier Analysen, alle quellenübergreifend (gedcom_persons + match_pedigree):

  birth_distribution      — Personen pro Jahrzehnt × Region
  migration_matrix        — Eltern-Region → Kind-Region (aus ahnen_path + Sosa)
  cm_histogram            — Verteilung geteilter cM über alle Matches
  surname_entropy_series  — Shannon-Entropie der Nachnamen pro Jahrzehnt
"""
from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict

from ancestry.core.bridge._text import _extract_region

log = logging.getLogger(__name__)

_MIN_YEAR = 1500
_MAX_YEAR = 2020

# cM-Bins: bewusst nicht gleichbreit — engmaschig für häufige niedrige Werte,
# grob für seltene hohe.
CM_BINS: list[tuple[int, int]] = [
    (0,    50),  (50,  100), (100, 150), (150, 200),
    (200,  300), (300, 400), (400, 600), (600, 900),
    (900, 1400), (1400, 2000), (2000, 4000),
]

# Ungefähre Verwandtschafts-Annotation für GUI-Labels je Bin
CM_BIN_REL: list[str] = [
    "4–5C+", "3–4C", "2–3C", "2C/1C2R",
    "2C/1C1R", "1C1R/GGE", "1C/Onkel", "Halb-1C/GE",
    "GE/Onkel", "GE/Geschwister", "Eltern/Geschwister",
]


def _region(place: str) -> str:
    return _extract_region(place or "") or ""


# ── 1. Geburtsverteilung (Jahrzehnt × Region) ─────────────────────────────────

def birth_distribution(db, min_count: int = 3) -> list[dict]:
    """Personen pro Jahrzehnt × Region aus gedcom_persons + match_pedigree.

    Returns: [{"decade": 1850, "region": "Osnabrück", "count": 42}, ...]
    Sortiert nach Jahrzehnt, dann count absteigend.
    """
    counts: Counter[tuple[int, str]] = Counter()

    try:
        with db._cursor() as cur:
            for r in cur.execute(
                """SELECT birth_year, birth_place FROM gedcom_persons
                   WHERE birth_year BETWEEN ? AND ? AND TRIM(birth_place) != ''""",
                (_MIN_YEAR, _MAX_YEAR),
            ).fetchall():
                reg = _region(r["birth_place"])
                if reg:
                    counts[(int(r["birth_year"]) // 10 * 10, reg)] += 1
    except Exception as e:
        log.warning("birth_distribution gedcom_persons: %s", e)

    try:
        with db._cursor() as cur:
            for r in cur.execute(
                """SELECT birth_year, birth_place FROM match_pedigree
                   WHERE birth_year IS NOT NULL AND birth_year != ''
                     AND TRIM(birth_place) != '' AND generation >= 2"""
            ).fetchall():
                try:
                    yr = int(r["birth_year"])
                except (ValueError, TypeError):
                    continue
                if not (_MIN_YEAR <= yr <= _MAX_YEAR):
                    continue
                reg = _region(r["birth_place"])
                if reg:
                    counts[(yr // 10 * 10, reg)] += 1
    except Exception as e:
        log.debug("birth_distribution match_pedigree: %s", e)

    result = [
        {"decade": d, "region": reg, "count": cnt}
        for (d, reg), cnt in counts.items()
        if cnt >= min_count
    ]
    result.sort(key=lambda x: (x["decade"], -x["count"]))
    log.info("birth_distribution: %d Jahrzehnt×Region-Paare", len(result))
    return result


# ── 2. Migrations-Fluss-Matrix (Eltern-Region → Kind-Region) ─────────────────

def migration_matrix(db, top_n: int = 40) -> list[dict]:
    """Regionale Wanderung aus Eltern-Kind-Verknüpfungen.

    Quellen:
      - match_pedigree: ahnen_path-Präfix verknüpft Kind (Pfad XY) mit Elternteil (X).
      - gedcom_persons:  Sosa-Arithmetik — Kind N, Elternteil 2N / 2N+1.

    Returns top_n Flüsse:
      [{"from_region": "Osnabrück", "to_region": "Hamburg", "count": 17}, ...]
    """
    flows: Counter[tuple[str, str]] = Counter()

    # match_pedigree — ahnen_path-Präfix-Join
    try:
        with db._cursor() as cur:
            for r in cur.execute(
                """SELECT c.birth_place AS c_pl, p.birth_place AS p_pl
                   FROM match_pedigree c
                   JOIN match_pedigree p
                     ON  p.match_guid = c.match_guid
                     AND p.test_guid  = c.test_guid
                     AND c.ahnen_path != ''
                     AND p.ahnen_path = SUBSTR(c.ahnen_path, 1, LENGTH(c.ahnen_path)-1)
                   WHERE TRIM(c.birth_place) != ''
                     AND TRIM(p.birth_place) != ''
                     AND c.generation >= 3"""
            ).fetchall():
                fr, to = _region(r["p_pl"]), _region(r["c_pl"])
                if fr and to and fr != to:
                    flows[(fr, to)] += 1
    except Exception as e:
        log.warning("migration_matrix match_pedigree: %s", e)

    # gedcom_persons — Sosa-Join (direkte Ahnenlinie)
    try:
        with db._cursor() as cur:
            for r in cur.execute(
                """SELECT c.birth_place AS c_pl, p.birth_place AS p_pl
                   FROM gedcom_persons c
                   JOIN gedcom_persons p
                     ON (p.sosa_number = c.sosa_number * 2
                         OR p.sosa_number = c.sosa_number * 2 + 1)
                    AND p.sosa_number > 1 AND c.sosa_number > 0
                   WHERE TRIM(c.birth_place) != '' AND TRIM(p.birth_place) != ''"""
            ).fetchall():
                fr, to = _region(r["p_pl"]), _region(r["c_pl"])
                if fr and to and fr != to:
                    flows[(fr, to)] += 1
    except Exception as e:
        log.debug("migration_matrix gedcom sosa: %s", e)

    result = [
        {"from_region": fr, "to_region": to, "count": cnt}
        for (fr, to), cnt in flows.most_common(top_n)
    ]
    log.info("migration_matrix: %d eindeutige Flüsse, top %d", len(flows), top_n)
    return result


# ── 3. cM-Histogramm ─────────────────────────────────────────────────────────

def cm_histogram(db, test_guid: str) -> list[dict]:
    """Histogramm geteilter cM über alle Matches eines Kits.

    Returns: [{"bin_lo": 0, "bin_hi": 50, "label": "0–50", "observed": 1823,
               "rel_hint": "4–5C+"}, ...]
    """
    try:
        with db._cursor() as cur:
            values = [
                float(r["shared_cm"])
                for r in cur.execute(
                    "SELECT shared_cm FROM matches WHERE test_guid=? AND shared_cm > 0",
                    (test_guid,),
                ).fetchall()
            ]
    except Exception as e:
        log.warning("cm_histogram: %s", e)
        return []

    if not values:
        return []

    result = []
    for i, (lo, hi) in enumerate(CM_BINS):
        cnt = sum(1 for v in values if lo <= v < hi)
        lbl = f"{lo}–{hi}" if hi < 4000 else f"≥{lo}"
        result.append({
            "bin_lo": lo, "bin_hi": hi, "label": lbl,
            "observed": cnt,
            "rel_hint": CM_BIN_REL[i] if i < len(CM_BIN_REL) else "",
        })

    log.info("cm_histogram: %d Matches, %d Bins", len(values), len(result))
    return result


# ── 4. Nachnamen-Entropie als Zeitreihe ───────────────────────────────────────

def surname_entropy_series(db, decade_step: int = 10,
                           min_per_decade: int = 20) -> list[dict]:
    """Shannon-Entropie der Nachnamen pro Jahrzehnt (alle Quellen zusammen).

    Entropie H = −Σ p_i·log₂(p_i) — hohe Werte = große Diversität,
    Einbrüche zeigen Gründereffekte oder Datenlücken.

    Returns: [{"decade": 1800, "entropy": 3.42, "unique": 87, "total": 234}, ...]
    """
    decade_counts: dict[int, Counter[str]] = defaultdict(Counter)

    try:
        with db._cursor() as cur:
            for r in cur.execute(
                """SELECT birth_year, surname FROM gedcom_persons
                   WHERE birth_year BETWEEN ? AND ? AND TRIM(surname) != ''""",
                (_MIN_YEAR, _MAX_YEAR),
            ).fetchall():
                sn = (r["surname"] or "").strip().lower()
                if sn:
                    decade_counts[int(r["birth_year"]) // decade_step * decade_step][sn] += 1
    except Exception as e:
        log.warning("surname_entropy gedcom_persons: %s", e)

    try:
        with db._cursor() as cur:
            for r in cur.execute(
                """SELECT birth_year, surname FROM match_pedigree
                   WHERE birth_year IS NOT NULL AND birth_year != ''
                     AND TRIM(surname) != '' AND generation >= 2"""
            ).fetchall():
                try:
                    yr = int(r["birth_year"])
                except (ValueError, TypeError):
                    continue
                if not (_MIN_YEAR <= yr <= _MAX_YEAR):
                    continue
                sn = (r["surname"] or "").strip().lower()
                if sn:
                    decade_counts[yr // decade_step * decade_step][sn] += 1
    except Exception as e:
        log.debug("surname_entropy match_pedigree: %s", e)

    result = []
    for decade in sorted(decade_counts):
        ctr = decade_counts[decade]
        total = sum(ctr.values())
        if total < min_per_decade:
            continue
        entropy = -sum((c / total) * math.log2(c / total) for c in ctr.values())
        result.append({
            "decade": decade,
            "entropy": round(entropy, 3),
            "unique": len(ctr),
            "total": total,
        })

    log.info("surname_entropy: %d Jahrzehnte", len(result))
    return result
