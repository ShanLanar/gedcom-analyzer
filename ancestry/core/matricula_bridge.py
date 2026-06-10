"""
Kirchenbuch-Brücke: verknüpft DNA-Match-Vorfahren mit Matricula-Einträgen.

Ablauf:
  1. Hole alle Nachnamen aus der Ahnentafel des Matches (match_pedigree)
  2. Berechne Kölner Phonetik für jeden Nachnamen
  3. Suche in name_index (Kirchenbücher) nach denselben Codes
  4. Reichere Treffer mit Buchdetails aus source_matrikula_entries an
  5. Gib sortierte Treffer zurück (exakt → phonetisch, dann nach Jahr)

Voraussetzung: scan_matricula_kirchspiel.py hat Einträge in die
               Haupt-ancestry_dna.db geschrieben (tables: source_matrikula_entries,
               name_index).

Öffentliche API:
    find_matricula_for_match(db, test_guid, match_guid, min_generation=2,
                             max_results=50) -> list[dict]
    find_matricula_for_names(db, surnames, max_results=50) -> list[dict]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ancestry.core.bridge._text import _koelner, _norm

if TYPE_CHECKING:
    from ancestry.core.database import Database


def find_matricula_for_match(
    db: "Database",
    test_guid: str,
    match_guid: str,
    min_generation: int = 2,
    max_results: int = 50,
) -> list[dict]:
    """Gibt Kirchenbuch-Treffer zurück, deren Namen in der Ahnentafel des Matches vorkommen."""
    surnames = _pedigree_surnames(db, test_guid, match_guid, min_generation)
    if not surnames:
        return []
    return find_matricula_for_names(db, surnames, max_results=max_results)


def find_matricula_for_names(
    db: "Database",
    surnames: list[str],
    max_results: int = 50,
) -> list[dict]:
    """Gibt Kirchenbuch-Treffer für eine Liste von Nachnamen zurück."""
    if not surnames:
        return []
    codes = list({_koelner(s) for s in surnames if _koelner(s)})
    norms = {_norm(s) for s in surnames}
    if not codes:
        return []
    qmarks = ",".join("?" * len(codes))
    try:
        with db._cursor() as cur:
            rows = cur.execute(f"""
                SELECT
                    ni.entry_id,  ni.book_id,  ni.page_nr,
                    ni.name_raw,  ni.name_norm, ni.koeln_code, ni.name_role,
                    e.entry_type, e.event_date, e.event_year,
                    e.person_name,  e.person2_name,
                    e.father_name,  e.mother_name,
                    e.village,      e.notes,
                    CASE WHEN ni.name_norm IN ({','.join('?' for _ in norms)})
                         THEN 1 ELSE 0 END AS exact_match
                FROM name_index ni
                LEFT JOIN source_matrikula_entries e
                       ON e.entry_id = ni.entry_id
                WHERE ni.koeln_code IN ({qmarks})
                ORDER BY exact_match DESC, e.event_year ASC
                LIMIT ?
            """, (*norms, *codes, max_results)).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


def _pedigree_surnames(
    db: "Database",
    test_guid: str,
    match_guid: str,
    min_generation: int,
) -> list[str]:
    """Holt Nachnamen aus der Ahnentafel (nur Generationen ≥ min_generation)."""
    try:
        rows = db.get_pedigree_for_match(test_guid, match_guid)
        seen: set[str] = set()
        out: list[str] = []
        for r in rows:
            gen = r.get("generation") or 0
            if gen < min_generation:
                continue
            sur = (r.get("surname") or "").strip()
            if sur and sur.lower() not in seen:
                seen.add(sur.lower())
                out.append(sur)
        return out
    except Exception:
        return []
