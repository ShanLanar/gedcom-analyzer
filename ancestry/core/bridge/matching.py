"""
matching.py — Abgleich von DNA-Match-Ahnentafeln mit dem eigenen GEDCOM-Baum:
Einzel-/Bulk-Matching, Seiten-Ableitung, Verwandtschafts-Vergleich,
Endogamie-Übertragung und Herkunfts-Analyse.
"""

import json
import logging
from collections import defaultdict

from ._text import _norm, _koelner, _extract_region
from .scoring import compute_link_score, MIN_LINK_SCORE
from .gedcom_import import iter_unique_persons

log = logging.getLogger(__name__)


# ── Matching für einen Match ───────────────────────────────────────────────────

def _parse_ancestor_name(full_name: str) -> tuple[str, str]:
    """Teilt einen vollständigen Namen in (Vorname, Nachname).
    Unterstützt 'Vorname Nachname' und 'Nachname, Vorname'."""
    full_name = full_name.strip()
    if "," in full_name:
        parts = full_name.split(",", 1)
        return parts[1].strip(), parts[0].strip()
    parts = full_name.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]), parts[-1]
    return "", full_name


def run_match_for_match(db, test_guid: str, match_guid: str) -> list[dict]:
    """Findet GEDCOM-Kandidaten für alle Ahnen-Einträge eines DNA-Matches.
    Schreibt Treffer nach gedcom_links.
    Gibt eine sortierte Liste von Zeilen zurück (je ein Pedigree-Eintrag).
    Fallback: wenn keine Ahnentafel vorhanden, wird match_ancestors (Ancestry API)
    verwendet."""
    # Pedigree-Zeilen laden
    with db._cursor() as cur:
        ped_rows = [dict(r) for r in cur.execute(
            """SELECT given_name, surname, birth_year, birth_place,
                      generation, ahnen_path
               FROM match_pedigree
               WHERE test_guid=? AND match_guid=? AND generation>=2
               ORDER BY generation, ahnen_path""",
            (test_guid, match_guid),
        ).fetchall()]

    # Fallback: gemeinsame Vorfahren aus der Ancestry-API (match_ancestors)
    use_ancestors_api = not ped_rows
    if use_ancestors_api:
        anc_rows = db.get_ancestors_for_match(match_guid)
        if not anc_rows:
            return []
        # In pedigree-ähnliches Format umwandeln
        ped_rows = []
        for a in anc_rows:
            given, surname = _parse_ancestor_name(a.get("ancestor_name", ""))
            if not surname:
                continue
            ped_rows.append({
                "given_name":  given,
                "surname":     surname,
                "birth_year":  a.get("birth_year") or None,
                "birth_place": "",
                "generation":  0,
                "ahnen_path":  "",   # Pfad unbekannt bei API-Daten
            })
        if not ped_rows:
            return []

    # GEDCOM-Personen aus DB laden + in-memory-Index aufbauen
    with db._cursor() as cur:
        ged_all = [dict(r) for r in cur.execute(
            "SELECT * FROM gedcom_persons"
        ).fetchall()]

    if not ged_all:
        return []

    ged_by_sn:     dict[str, list] = defaultdict(list)
    ged_by_koelner: dict[str, list] = defaultdict(list)
    for g in ged_all:
        ged_by_sn[g["surname_norm"]].append(g)
        if g["koelner_code"]:
            ged_by_koelner[g["koelner_code"]].append(g)

    # Alte Links für diesen Match löschen
    with db._cursor() as cur:
        cur.execute(
            "DELETE FROM gedcom_links WHERE test_guid=? AND match_guid=?",
            (test_guid, match_guid),
        )

    new_links: dict[str, dict] = {}  # ahnen_path → bestes Link-Dict

    for ped in ped_rows:
        ped_sn = _norm(ped.get("surname", ""))
        if not ped_sn:
            continue
        ped_koe = _koelner(ped_sn)

        # Kandidaten zusammenstellen (Exact-first, dann Phonetik)
        seen: set = set()
        candidates = []
        for g in ged_by_sn.get(ped_sn, []):
            candidates.append(g); seen.add(g["ged_id"])
        for g in ged_by_koelner.get(ped_koe, []):
            if g["ged_id"] not in seen:
                candidates.append(g); seen.add(g["ged_id"])

        best_score, best_method, best_ged = 0.0, "none", None
        for ged in candidates:
            score, method = compute_link_score(
                ped.get("given_name", ""),
                ped.get("surname", ""),
                ped.get("birth_year"),
                ged,
                ped_place=ped.get("birth_place", ""),
                ged_place=ged.get("birth_place", ""),
            )
            if score > best_score:
                best_score, best_method, best_ged = score, method, ged

        if best_ged and best_score >= MIN_LINK_SCORE:
            link_row = {
                "test_guid":   test_guid,
                "match_guid":  match_guid,
                "ahnen_path":  ped.get("ahnen_path", ""),
                "ped_given":   ped.get("given_name", ""),
                "ped_surname": ped.get("surname", ""),
                "ped_year":    ped.get("birth_year"),
                "ged_id":      best_ged["ged_id"],
                "ged_given":   best_ged["given_name"],
                "ged_surname": best_ged["surname"],
                "ged_year":    best_ged["birth_year"],
                "match_method": f"api+{best_method}" if use_ancestors_api else best_method,
                "total_score": best_score,
            }
            with db._cursor() as cur:
                cur.execute(
                    """INSERT OR REPLACE INTO gedcom_links
                       (test_guid, match_guid, ahnen_path,
                        ped_given, ped_surname, ped_year,
                        ged_id, ged_given, ged_surname, ged_year,
                        match_method, total_score)
                       VALUES (:test_guid, :match_guid, :ahnen_path,
                               :ped_given, :ped_surname, :ped_year,
                               :ged_id, :ged_given, :ged_surname, :ged_year,
                               :match_method, :total_score)""",
                    link_row,
                )
            new_links[ped.get("ahnen_path", "")] = link_row

    # Ergebnisliste: jede Pedigree-Zeile, mit oder ohne Treffer
    result = []
    for ped in ped_rows:
        path = ped.get("ahnen_path", "")
        link = new_links.get(path)
        ped_name = f"{ped.get('given_name','')} {ped.get('surname','')}".strip()
        if link:
            ged_name = f"{link['ged_given']} {link['ged_surname']}".strip()
            score_str = f"{link['total_score']:.2f}"
            method = link["match_method"]
            icon = "✓" if link["total_score"] >= 0.80 else "~"
        else:
            ged_name  = "—"
            score_str = ""
            method    = ""
            icon      = ""
        result.append({
            "generation": ped.get("generation", ""),
            "ahnen_path": path,
            "ped_name":   ped_name,
            "ped_year":   str(ped.get("birth_year") or ""),
            "ged_name":   ged_name,
            "ged_year":   str(link["ged_year"] or "") if link else "",
            "ged_id":     link["ged_id"] if link else "",
            "score":      score_str,
            "method":     method,
            "icon":       icon,
        })
    return result


# ── Bulk-Matching (alle Matches) ──────────────────────────────────────────────

def run_match_all(db, test_guid: str, progress_cb=None) -> int:
    """Bulk-Abgleich aller Matches für einen test_guid.
    Gibt Gesamtanzahl gefundener Links zurück."""
    with db._cursor() as cur:
        match_guids = [r[0] for r in cur.execute(
            """SELECT DISTINCT match_guid FROM match_pedigree
               WHERE test_guid=? AND generation>=2""",
            (test_guid,),
        ).fetchall()]

    total_links = 0
    for i, mguid in enumerate(match_guids):
        rows = run_match_for_match(db, test_guid, mguid)
        total_links += sum(1 for r in rows if r["icon"])
        if progress_cb:
            progress_cb(i + 1, len(match_guids))
    return total_links


# ── Phase 2: Sosa + Seiten-Ableitung ─────────────────────────────────────────

def path_to_sosa(path: str) -> int:
    """Sosa-Stradonitz-Nummer aus Vorfahren-Pfad.
    '' → 1 (Proband), 'F' → 2, 'M' → 3, 'FF' → 4, 'FM' → 5, …"""
    sosa = 1
    for ch in path:
        sosa = sosa * 2 if ch == "F" else sosa * 2 + 1
    return sosa


def infer_side_from_links(db, test_guid: str, match_guid: str, amap: dict) -> str:
    """Leitet die väterliche/mütterliche Seite aus Bridge-Links + Ahnen-Map ab.
    amap = {ged_id: path_string} aus build_ancestor_map().
    Rückgabe: 'paternal', 'maternal', 'both' oder '' (unbekannt)."""
    try:
        with db._cursor() as cur:
            ged_ids = [r[0] for r in cur.execute(
                "SELECT ged_id FROM gedcom_links WHERE test_guid=? AND match_guid=?",
                (test_guid, match_guid),
            ).fetchall()]
    except Exception:
        return ""
    if not ged_ids:
        return ""
    sides: set = set()
    for gid in ged_ids:
        path = amap.get(gid, "")
        if path.startswith("F"):
            sides.add("paternal")
        elif path.startswith("M"):
            sides.add("maternal")
    if sides == {"paternal"}:
        return "paternal"
    if sides == {"maternal"}:
        return "maternal"
    if sides:
        return "both"
    return ""


# ── GEDCOM-Verwandtschafts-Vergleich ─────────────────────────────────────────

def get_gedcom_relationship_summary(db, test_guid: str) -> list[dict]:
    """Berechnet GEDCOM-basierte Verwandtschafts-Labels für alle verknüpften
    DNA-Matches und vergleicht sie mit der Ancestry/MyHeritage-Vorhersage.

    Voraussetzung: import_gedcom_persons() muss mit root_id + families
    aufgerufen worden sein, damit sosa_number befüllt ist.

    Rückgabe: Liste von Dicts, eine Zeile pro Match (beste Verknüpfung):
      display_name, shared_cm, ancestry_rel, ged_relationship, multiplier,
      link_count, best_score, ged_common_ancestor, ged_ancestor_year,
      root_gen_depth, match_gen_depth
    """
    import math

    try:
        from lib.helpers import relationship_label
    except ImportError:
        def relationship_label(rd, td, anc=False):
            return f"Grad {rd}+{td}" if rd and td else ""

    MULT_MAP = {2: "double", 3: "triple", 4: "quadruple",
                5: "quintuple", 6: "sextuple", 7: "septuple"}

    sql = """
        SELECT
            gl.match_guid,
            m.display_name,
            m.shared_cm,
            m.predicted_relationship,
            gl.ged_id,
            (gl.ged_given || ' ' || gl.ged_surname) AS ged_anc_name,
            gl.ged_year,
            gp.sosa_number,
            mp.generation  AS match_gen,
            gl.total_score,
            gl.ahnen_path
        FROM gedcom_links gl
        JOIN matches m ON m.match_guid = gl.match_guid
        JOIN gedcom_persons gp ON gp.ged_id = gl.ged_id
        LEFT JOIN match_pedigree mp
            ON  mp.match_guid  = gl.match_guid
            AND mp.ahnen_path  = gl.ahnen_path
            AND mp.test_guid   = gl.test_guid
        WHERE gl.test_guid = ?
        ORDER BY m.shared_cm DESC, gl.total_score DESC
    """
    try:
        with db._cursor() as cur:
            rows = [dict(r) for r in cur.execute(sql, (test_guid,)).fetchall()]
    except Exception as e:
        log.warning("get_gedcom_relationship_summary: %s", e)
        return []

    # Gruppieren nach match_guid (bestes Link = höchster Score)
    by_match: dict[str, list] = {}
    for r in rows:
        by_match.setdefault(r["match_guid"], []).append(r)

    result = []
    for match_guid, links in by_match.items():
        best = max(links, key=lambda x: x["total_score"])

        sosa = best["sosa_number"] or 0
        root_depth  = math.floor(math.log2(sosa)) if sosa >= 1 else 0
        match_depth = best["match_gen"] or len(best["ahnen_path"] or "")

        if root_depth > 0 and match_depth > 0:
            ged_rel = relationship_label(root_depth, match_depth)
        else:
            ged_rel = ""

        link_count = len(links)
        multiplier = MULT_MAP.get(link_count, "")

        result.append({
            "match_guid":           match_guid,
            "display_name":         best["display_name"],
            "shared_cm":            best["shared_cm"],
            "ancestry_rel":         best["predicted_relationship"] or "",
            "ged_relationship":     ged_rel,
            "multiplier":           multiplier,
            "link_count":           link_count,
            "best_score":           round(best["total_score"], 2),
            "ged_common_ancestor":  (best["ged_anc_name"] or "").strip(),
            "ged_ancestor_year":    best["ged_year"] or "",
            "root_gen_depth":       root_depth,
            "match_gen_depth":      match_depth,
        })

    return result


# ── GEDCOM-Endogamie → Endogamie-Cluster-Labels ──────────────────────────────

def apply_gedcom_endogamy_to_matches(
    db,
    test_guid: str,
    endogamy_results: list,
    min_score: float = 0.4,
    progress_cb=None,
) -> int:
    """Überträgt GEDCOM-Endogamie-Scores auf DNA-Matches via gemeinsame Geburtsorte.

    endogamy_results: Ausgabe von tasks.endogamy.compute_endogamy_with_detailed_places()
    Format: [[place, count, sn_div, score, klasse, …], …]

    Ablauf:
      1. Hochendogame Orte filtern (score >= min_score).
      2. match_ancestors-Tabelle nach Geburtsorten dieser Orte durchsuchen.
      3. Gefundene Matches mit set_endogamy_cluster(label) markieren.

    Gibt Anzahl der markierten Matches zurück.
    """
    p = progress_cb or (lambda *a: None)

    # Endogame Orte sammeln (Ort-String → Klassen-Label)
    hot_places: dict[str, str] = {}
    for row in endogamy_results:
        if len(row) >= 5 and isinstance(row[3], float) and row[3] >= min_score:
            place_key = str(row[0]).lower()
            hot_places[place_key] = str(row[4])  # Klassen-Label

    if not hot_places:
        p("Keine Orte mit Endogamie-Score ≥ {:.0%} gefunden.".format(min_score))
        return 0

    p(f"Endogamie-Marker: {len(hot_places)} Orte mit Score ≥ {min_score:.0%} …")

    # Alle Geburtsorte aus match_ancestors laden
    try:
        with db._cursor() as cur:
            rows = cur.execute(
                """SELECT ma.match_guid, ma.birth_place
                   FROM match_ancestors ma
                   JOIN matches m ON m.match_guid = ma.match_guid
                   WHERE m.test_guid = ? AND ma.birth_place != ''""",
                (test_guid,),
            ).fetchall()
    except Exception:
        rows = []

    marked: set = set()
    for r in rows:
        bp = (r["birth_place"] or "").lower()
        for place_key, label in hot_places.items():
            # Teilstring-Match: Ortsdaten in match_ancestors können Komma-getrennt sein
            if place_key in bp or any(
                part.strip() in bp for part in place_key.split(",") if len(part.strip()) >= 4
            ):
                guid = r["match_guid"]
                if guid not in marked:
                    db.set_endogamy_cluster(guid, label)
                    marked.add(guid)
                break

    p(f"Endogamie-Marker gesetzt: {len(marked)} Matches")
    return len(marked)


def infer_match_origins(
    db,
    test_guid: str,
    progress_cb=None,
    persist: bool = True,
) -> list[dict]:
    """Korreliert Nachnamen und Geburtsorte aus Match-Ahnentafeln mit dem GEDCOM-Baum,
    um die wahrscheinliche Herkunftsregion jedes DNA-Matches abzuleiten.

    Algorithmus:
      1. Aus gedcom_persons: pro Region (vorletzter Ortsteil) → Menge bekannter
         Nachnamen (surname_norm) und Kölner-Codes.
      2. Für jeden Match: Nachnamen aus match_pedigree gegen alle GEDCOM-Regionen
         gewichten. Frühgenerationen zählen stärker (1/generation).
      3. Regionsscore = Summe der gewichteten Übereinstimmungen:
           exact norm match → 1.0,  gleicher Kölner-Code → 0.7
      4. Bester Score → probable_origin gespeichert (JSON) in matches-Tabelle.

    Gibt Liste von Dicts zurück:
      {"match_guid", "match_name", "top_region", "score",
       "evidence_surnames", "evidence_places"}
    """
    p = progress_cb or (lambda *a: None)

    # ── 1. Regionen-Index aufbauen (quellenübergreifend, dedupliziert) ────────
    # Nutzt iter_unique_persons: GEDCOM + Anverwandte + WikiTree, jede reale
    # Person nur einmal (mehr Ortsabdeckung ohne Doppelzählung).
    try:
        ged_rows = [r for r in iter_unique_persons(db)
                    if (r.get("birth_place") or "") and (r.get("surname_norm") or "")]
    except Exception:
        p("GEDCOM-Tabelle nicht gefunden – bitte zuerst GEDCOM laden.")
        return []

    # region → {"norms": set, "koelner": set}
    region_index: dict[str, dict] = defaultdict(lambda: {"norms": set(), "koelner": set()})
    for row in ged_rows:
        region = _extract_region(row["birth_place"])
        if not region:
            continue
        if row["surname_norm"]:
            region_index[region]["norms"].add(row["surname_norm"])
        if row["koelner_code"]:
            region_index[region]["koelner"].add(row["koelner_code"])

    if not region_index:
        p("Keine GEDCOM-Personen mit Geburtsort und Nachnamen gefunden.")
        return []

    p(f"GEDCOM-Index: {len(region_index)} Regionen aus {len(ged_rows)} Personen …")

    # ── 2. Match-Ahnentafel-Daten laden ──────────────────────────────────────
    try:
        with db._cursor() as cur:
            ped_rows = cur.execute(
                """SELECT mp.match_guid, m.display_name,
                          mp.surname, mp.birth_place, mp.generation
                   FROM match_pedigree mp
                   JOIN matches m ON m.match_guid = mp.match_guid
                   WHERE m.test_guid = ? AND mp.surname != ''""",
                (test_guid,),
            ).fetchall()
    except Exception:
        p("match_pedigree-Tabelle nicht gefunden – bitte Ahnentafeln herunterladen.")
        return []

    if not ped_rows:
        p("Keine Pedigree-Daten vorhanden.")
        return []

    # Gruppieren nach Match
    match_data: dict[str, dict] = {}
    for row in ped_rows:
        guid = row["match_guid"]
        if guid not in match_data:
            match_data[guid] = {
                "name": row["display_name"] or guid,
                "ancestors": [],
            }
        match_data[guid]["ancestors"].append({
            "surname"   : row["surname"],
            "birth_place": row["birth_place"] or "",
            "generation": row["generation"] or 1,
        })

    p(f"Pedigree-Daten: {len(match_data)} Matches mit Ahnentafel-Nachnamen …")

    # ── 3. Scoring pro Match × Region ────────────────────────────────────────
    results: list[dict] = []

    for match_guid, mdata in match_data.items():
        region_scores: dict[str, float] = defaultdict(float)
        matched_surnames: dict[str, list] = defaultdict(list)
        matched_places: dict[str, list] = defaultdict(list)

        for anc in mdata["ancestors"]:
            sn_raw = anc["surname"]
            gen    = max(1, anc["generation"])
            weight = 1.0 / gen

            sn_norm   = _norm(sn_raw)
            sn_koelner = _koelner(sn_raw)

            for region, idx in region_index.items():
                score = 0.0
                if sn_norm and sn_norm in idx["norms"]:
                    score = 1.0
                elif sn_koelner and sn_koelner in idx["koelner"]:
                    score = 0.7

                if score > 0:
                    region_scores[region] += score * weight
                    matched_surnames[region].append(sn_raw)
                    if anc["birth_place"]:
                        matched_places[region].append(anc["birth_place"])

        if not region_scores:
            continue

        top_region = max(region_scores, key=lambda r: region_scores[r])
        top_score  = round(region_scores[top_region], 3)

        # Deduplicate evidence
        ev_sn  = list(dict.fromkeys(matched_surnames[top_region]))[:6]
        ev_pl  = list(dict.fromkeys(matched_places[top_region]))[:4]

        entry = {
            "match_guid"       : match_guid,
            "match_name"       : mdata["name"],
            "top_region"       : top_region.title(),
            "score"            : top_score,
            "evidence_surnames": ev_sn,
            "evidence_places"  : ev_pl,
        }
        results.append(entry)

        if persist:
            db.set_probable_origin(match_guid, json.dumps({
                "region"  : entry["top_region"],
                "score"   : top_score,
                "surnames": ev_sn,
                "places"  : ev_pl,
            }, ensure_ascii=False))

    results.sort(key=lambda r: r["score"], reverse=True)
    p(f"Herkunfts-Analyse: {len(results)} Matches mit Regionszuordnung abgeschlossen.")
    return results
