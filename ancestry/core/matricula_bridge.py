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
    """Gibt Kirchenbuch-Treffer für eine Liste von Nachnamen zurück.

    Suche-Strategie (zweigleisig, damit sowohl reine Nachnamen-Einträge
    als auch vollständige Namen wie "Heinrich Kovermann" gefunden werden):
      1. Kölner Phonetik: koeln_code IN (codes) — fängt Vollnamen ab,
         deren LETZTES Wort dem Nachnamen phonetisch ähnelt.
      2. Norm-LIKE: name_norm LIKE '%nachname%' — direkte Namenssuche.
    exact_match = 1, wenn der normierte Nachname als Teilstring enthalten.
    """
    if not surnames:
        return []
    norms = [_norm(s) for s in surnames if _norm(s)]
    if not norms:
        return []

    # Kölner Codes für Nachnamen UND typische Vollnamen-Endungen
    codes: set[str] = set()
    for s in surnames:
        c = _koelner(s)
        if c:
            codes.add(c)
        # Falls name_index Vollnamen hält: letztes Wort ist oft Nachname
        # → zusätzlich Code für "Vorname Nachname"-Variante nicht nötig,
        # aber wir decken den Fall über LIKE ab.

    # Kölner-Code Treffer: exakt (name_index-Einträge ohne Vornamen) ODER
    # Suffix (name_index hat "Vorname Nachname" → Code endet mit Nachname-Code).
    codes_list = list(codes)
    exact_code_q  = ",".join("?" * len(codes_list)) if codes_list else "NULL"
    suffix_parts  = " OR ".join("ni.koeln_code LIKE ?" for _ in codes_list)
    suffix_args   = [f"%{c}" for c in codes_list]
    like_name_q   = " OR ".join("ni.name_norm LIKE ?" for _ in norms)
    like_name_args = [f"%{n}%" for n in norms]

    try:
        with db._cursor() as cur:
            # name_index: klassische Rollen (person/father/mother/…)
            ni_rows = cur.execute(f"""
                SELECT
                    ni.entry_id,  ni.book_id,  e.page_nr,
                    ni.name_raw,  ni.name_norm, ni.koeln_code,
                    ni.name_role  AS found_rolle,
                    e.entry_type, e.event_date, e.event_year,
                    e.person_name,  e.person2_name,
                    e.father_name,  e.mother_name,
                    e.village,      e.notes,
                    CASE WHEN {like_name_q}
                         THEN 1 ELSE 0 END AS exact_match
                FROM name_index ni
                LEFT JOIN source_matrikula_entries e
                       ON e.entry_id = ni.entry_id
                WHERE ni.koeln_code IN ({exact_code_q})
                   OR ({suffix_parts})
                   OR ({like_name_q})
                ORDER BY exact_match DESC, e.event_year ASC
                LIMIT ?
            """, (*like_name_args, *codes_list, *suffix_args, *like_name_args, max_results)
            ).fetchall()

            # matrikula_ner: Paten, Zeugen, Väter der Braut/Bräutigam usw.
            # Nachnamen-Code (letztes Wort) ist in NER gespeichert
            surn_codes = list({_koelner(s.split()[-1]) for s in surnames if _koelner(s.split()[-1])})
            ner_rows: list = []
            if surn_codes:
                sc_ph = ",".join("?" * len(surn_codes))
                lk_ph = " OR ".join("n.name_norm LIKE ?" for _ in norms)
                try:
                    ner_rows = cur.execute(f"""
                        SELECT
                            n.entry_id,  n.book_id,  e.page_nr,
                            n.name_raw,  n.name_norm, n.koeln_code,
                            n.rolle      AS found_rolle,
                            e.entry_type, e.event_date, e.event_year,
                            e.person_name,  e.person2_name,
                            e.father_name,  e.mother_name,
                            e.village,      e.notes,
                            CASE WHEN {lk_ph}
                                 THEN 1 ELSE 0 END AS exact_match
                        FROM matrikula_ner n
                        LEFT JOIN source_matrikula_entries e
                               ON e.entry_id = n.entry_id
                        WHERE n.koeln_code IN ({sc_ph})
                           OR ({lk_ph})
                        ORDER BY exact_match DESC, e.event_year ASC
                        LIMIT ?
                    """, (*like_name_args, *surn_codes, *like_name_args, max_results)
                    ).fetchall()
                except Exception:
                    ner_rows = []

            # Zusammenführen, Duplikate nach (entry_id, name_raw) entfernen
            seen: set[tuple] = set()
            combined: list[dict] = []
            for r in list(ni_rows) + list(ner_rows):
                key = (r["entry_id"], r["name_raw"].lower())
                if key in seen:
                    continue
                seen.add(key)
                combined.append(dict(r))
            combined.sort(key=lambda x: (-x["exact_match"], x.get("event_year") or 9999))
            return combined[:max_results]
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
