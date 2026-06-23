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
    find_matricula_dna_links(db, min_score=0.6, limit=100) -> list[dict]
    find_place_links(db, limit=100) -> list[dict]
"""

from __future__ import annotations

import re
import logging
from typing import TYPE_CHECKING

from ancestry.core.bridge._text import _koelner, _norm

if TYPE_CHECKING:
    from ancestry.core.database import Database

log = logging.getLogger(__name__)


def _normalize(name: str) -> str:
    """Normalisiert einen Namen für unscharfen Vergleich."""
    if not name:
        return ""
    name = name.lower().strip()
    # Entferne Sonderzeichen, normalisiere Umlaute
    name = name.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    name = name.replace("ß", "ss")
    name = re.sub(r"[^a-z ]", "", name)
    return " ".join(name.split())


def _name_score(a: str, b: str) -> float:
    """Einfacher Ähnlichkeits-Score (0–1) zwischen zwei Namen."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Token overlap
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb) / max(len(ta), len(tb))
    return overlap


def find_matricula_dna_links(db, min_score: float = 0.6, limit: int = 100) -> list[dict]:
    """Findet potenzielle Verbindungen zwischen Kirchenbucheinträgen und DNA-Matches.

    Parameters
    ----------
    db:
        DB-Objekt mit `_cursor()` Kontextmanager und `_conn`.
    min_score:
        Mindestscore (0–1) für Namensübereinstimmung.
    limit:
        Maximale Anzahl zurückgegebener Kandidaten.

    Returns
    -------
    List of dicts with keys:
        entry_id, entry_type, matricula_name, event_date,
        match_guid, match_name, match_cm, score
    """
    results: list[dict] = []
    try:
        with db._cursor() as cur:
            # Kirchenbucheinträge laden
            mat_rows = cur.execute(
                "SELECT entry_id, entry_type, person_name, event_date "
                "FROM source_matrikula_entries "
                "WHERE person_name IS NOT NULL AND person_name != '' "
                "LIMIT 500"
            ).fetchall()
    except Exception as e:
        log.debug("source_matrikula_entries nicht verfügbar: %s", e)
        return []

    try:
        with db._cursor() as cur:
            match_rows = cur.execute(
                "SELECT guid, name, cm FROM matches "
                "WHERE name IS NOT NULL AND name != '' "
                "ORDER BY cm DESC LIMIT 1000"
            ).fetchall()
    except Exception as e:
        log.debug("matches nicht verfügbar: %s", e)
        return []

    # Cross-Match Namensvergleich
    for mat in mat_rows:
        mat_name = mat["person_name"] if hasattr(mat, "__getitem__") else mat[2]
        entry_id = mat["entry_id"] if hasattr(mat, "__getitem__") else mat[0]
        entry_type = mat["entry_type"] if hasattr(mat, "__getitem__") else mat[1]
        event_date = mat["event_date"] if hasattr(mat, "__getitem__") else mat[3]

        for m in match_rows:
            match_name = m["name"] if hasattr(m, "__getitem__") else m[1]
            match_guid = m["guid"] if hasattr(m, "__getitem__") else m[0]
            match_cm = m["cm"] if hasattr(m, "__getitem__") else m[2]
            score = _name_score(mat_name, match_name)
            if score >= min_score:
                results.append({
                    "entry_id": entry_id,
                    "entry_type": entry_type,
                    "matricula_name": mat_name,
                    "event_date": event_date,
                    "match_guid": match_guid,
                    "match_name": match_name,
                    "match_cm": match_cm,
                    "score": score,
                })
                if len(results) >= limit:
                    break
        if len(results) >= limit:
            break

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def find_place_links(db, limit: int = 100) -> list[dict]:
    """Findet GEDCOM-Personen, deren Geburtsort in Matricula-Büchern vorkommt.

    Returns dicts with: ged_id, name, birth_place, parish, book_type
    """
    results: list[dict] = []
    try:
        with db._cursor() as cur:
            # Geburtsörter aus GEDCOM
            ged_rows = cur.execute(
                "SELECT ged_id, given_name, surname, birth_place "
                "FROM gedcom_persons "
                "WHERE birth_place IS NOT NULL AND birth_place != '' "
                "LIMIT 500"
            ).fetchall()
            # Pfarreien aus Matricula (falls Tabelle existiert)
            try:
                par_rows = cur.execute(
                    "SELECT DISTINCT parish_name, book_type FROM matricula_books "
                    "WHERE parish_name IS NOT NULL LIMIT 200"
                ).fetchall()
            except Exception:
                par_rows = []
    except Exception as e:
        log.debug("find_place_links Fehler: %s", e)
        return []

    parish_names = [
        (r["parish_name"] if hasattr(r, "__getitem__") else r[0],
         r["book_type"] if hasattr(r, "__getitem__") else r[1])
        for r in par_rows
    ]

    for g in ged_rows:
        bp = (g["birth_place"] if hasattr(g, "__getitem__") else g[3] or "").lower()
        gid = g["ged_id"] if hasattr(g, "__getitem__") else g[0]
        gname = (
            f"{g['given_name'] or ''} {g['surname'] or ''}".strip()
            if hasattr(g, "__getitem__")
            else ""
        )
        for pname, btype in parish_names:
            if pname and pname.lower() in bp:
                results.append({
                    "ged_id": gid,
                    "name": gname,
                    "birth_place": bp,
                    "parish": pname,
                    "book_type": btype,
                })
                break
        if len(results) >= limit:
            break

    return results


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
