"""
bridge.py — Verknüpft den eigenen GEDCOM-Stammbaum mit der Ancestry-DNA-Datenbank.

Phase 1: Importiert GEDCOM-Personen in zwei neue SQLite-Tabellen
(gedcom_persons, gedcom_links) und sucht Kandidaten-Übereinstimmungen
zwischen Vorfahren aus DNA-Match-Ahnentafeln und dem eigenen Baum.

Ähnlichkeits-Hierarchie:
  1. Exact surname match             → score 1.0
  2. Kölner Phonetik match           → score 0.55–0.85
  3. Levenshtein ≤ 2 (≥ 4 Zeichen)  → score 0.40–0.50
  Bonus: Vorname ähnlich             → +0.10
  Bonus: Geburtsjahr ± 10 / ± 15    → +0.0–0.20

Minimaler Link-Score: 0.45
"""

import os
import re
import sys
import unicodedata
import logging
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Optional

log = logging.getLogger(__name__)

# Root des Repos in den Pfad, damit lib.gedcom / treematch erreichbar sind
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

MIN_LINK_SCORE = 0.45


# ── Normalisierung (standalone, kein Import aus treematch nötig) ──────────────

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _norm(s: str) -> str:
    """Lowercase, ß→ss, Diakritika weg, nur a-z0-9 Leerzeichen."""
    s = (s or "").lower().replace("ß", "ss")
    s = _strip_accents(s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ── Kölner Phonetik (standalone, keine externen Abhängigkeiten) ───────────────

def _koelner(name: str) -> str:
    if not name:
        return ""
    name = name.upper().strip()
    name = (name.replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE")
            .replace("ß", "SS").replace("PH", "F").replace("TH", "T"))
    name = re.sub(r"[^A-Z]", "", name)
    if not name:
        return ""
    codes = []
    n = len(name)
    for i, ch in enumerate(name):
        nxt  = name[i + 1] if i < n - 1 else ""
        prev = name[i - 1] if i > 0     else ""
        if ch in "AEIJOUY":   codes.append("0")
        elif ch == "H":        continue
        elif ch == "B":        codes.append("1")
        elif ch == "P":        codes.append("1" if nxt != "H" else "3")
        elif ch in "DT":       codes.append("2" if nxt not in "CSZ" else "8")
        elif ch in "FVW":      codes.append("3")
        elif ch in "GKQ":      codes.append("4")
        elif ch == "C":
            if i == 0:         codes.append("4" if nxt in "AHKLOQRUX" else "8")
            elif prev in "SZ": codes.append("8")
            elif nxt in "AHKOQUX": codes.append("4")
            else:              codes.append("8")
        elif ch == "X":        codes.extend(["4", "8"])
        elif ch == "L":        codes.append("5")
        elif ch in "MN":       codes.append("6")
        elif ch == "R":        codes.append("7")
        elif ch in "SZ":       codes.append("8")
    reduced: list[str] = []
    for c in codes:
        if not reduced or c != reduced[-1]:
            reduced.append(c)
    return "".join(reduced).lstrip("0") or "0"


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0: return lb
    if lb == 0: return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[lb]


# ── GEDCOM-Namen parsen ────────────────────────────────────────────────────────

def _parse_name_from_indi(ind: dict) -> tuple[str, str]:
    """Extrahiert (Vorname, Nachname) aus einem GEDCOM-Individual-Dict."""
    givn = (ind.get("_GIVN") or ind.get("GIVN") or "").strip()
    surn = (ind.get("_SURN") or ind.get("SURN") or "").strip()
    if givn or surn:
        return givn, surn
    raw = ind.get("NAME", "")
    m = re.search(r"/([^/]*)/", raw)
    if m:
        surname = m.group(1).strip()
        given   = raw[:m.start()].strip()
        return given, surname
    parts = raw.rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (raw, "")


# ── SQL-Schema ─────────────────────────────────────────────────────────────────

BRIDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS gedcom_persons (
    ged_id       TEXT PRIMARY KEY,
    given_name   TEXT NOT NULL DEFAULT '',
    surname      TEXT NOT NULL DEFAULT '',
    surname_norm TEXT NOT NULL DEFAULT '',
    koelner_code TEXT NOT NULL DEFAULT '',
    sex          TEXT DEFAULT '',
    birth_year   INTEGER,
    birth_qual   TEXT DEFAULT '',
    birth_place  TEXT DEFAULT '',
    death_year   INTEGER,
    death_place  TEXT DEFAULT '',
    ged_file     TEXT NOT NULL DEFAULT '',
    loaded_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gp_koelner_year
    ON gedcom_persons(koelner_code, birth_year);
CREATE INDEX IF NOT EXISTS idx_gp_surname_norm
    ON gedcom_persons(surname_norm);

CREATE TABLE IF NOT EXISTS gedcom_links (
    link_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    test_guid    TEXT NOT NULL,
    match_guid   TEXT NOT NULL,
    ahnen_path   TEXT NOT NULL DEFAULT '',
    ped_given    TEXT NOT NULL DEFAULT '',
    ped_surname  TEXT NOT NULL DEFAULT '',
    ped_year     INTEGER,
    ged_id       TEXT NOT NULL,
    ged_given    TEXT NOT NULL DEFAULT '',
    ged_surname  TEXT NOT NULL DEFAULT '',
    ged_year     INTEGER,
    match_method TEXT NOT NULL DEFAULT '',
    total_score  REAL NOT NULL DEFAULT 0.0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (test_guid, match_guid, ahnen_path, ged_id)
);
CREATE INDEX IF NOT EXISTS idx_gl_match ON gedcom_links(test_guid, match_guid);
CREATE INDEX IF NOT EXISTS idx_gl_score ON gedcom_links(total_score DESC);
"""


def ensure_tables(db) -> None:
    """Idempotent: legt gedcom_persons + gedcom_links an, falls fehlend."""
    with db._cursor() as cur:
        cur.executescript(BRIDGE_SCHEMA)


# ── Import ─────────────────────────────────────────────────────────────────────

def import_gedcom_persons(db, individuals: dict, ged_file: str = "") -> int:
    """Löscht und füllt gedcom_persons aus einem GEDCOM-Individuals-Dict.
    Gibt Anzahl importierter Personen zurück."""
    rows = []
    for ged_id, ind in individuals.items():
        given, surname = _parse_name_from_indi(ind)
        if not given and not surname:
            continue
        birt = ind.get("BIRT") or {}
        deat = ind.get("DEAT") or {}
        sn_norm = _norm(surname)
        rows.append({
            "ged_id":       ged_id,
            "given_name":   given,
            "surname":      surname,
            "surname_norm": sn_norm,
            "koelner_code": _koelner(sn_norm) if sn_norm else "",
            "sex":          ind.get("SEX", ""),
            "birth_year":   birt.get("YEAR") or None,
            "birth_qual":   birt.get("DATE_QUAL") or "",
            "birth_place":  (birt.get("PLAC") or "").strip(),
            "death_year":   deat.get("YEAR") or None,
            "death_place":  (deat.get("PLAC") or "").strip(),
            "ged_file":     ged_file,
        })
    with db._cursor() as cur:
        cur.execute("DELETE FROM gedcom_persons")
        cur.executemany(
            """INSERT OR REPLACE INTO gedcom_persons
               (ged_id, given_name, surname, surname_norm, koelner_code,
                sex, birth_year, birth_qual, birth_place,
                death_year, death_place, ged_file)
               VALUES (:ged_id, :given_name, :surname, :surname_norm, :koelner_code,
                       :sex, :birth_year, :birth_qual, :birth_place,
                       :death_year, :death_place, :ged_file)""",
            rows,
        )
    log.info("bridge: %d GEDCOM-Personen importiert", len(rows))
    return len(rows)


def get_gedcom_person_count(db) -> int:
    """Schnelle Zählung der importierten GEDCOM-Personen."""
    try:
        with db._cursor() as cur:
            return cur.execute("SELECT COUNT(*) FROM gedcom_persons").fetchone()[0]
    except Exception:
        return 0


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
