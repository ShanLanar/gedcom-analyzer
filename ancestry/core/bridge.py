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

import json
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
    sosa_number  INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'gedcom',   -- gedcom | anverwandte | wikitree
    loaded_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gp_koelner_year
    ON gedcom_persons(koelner_code, birth_year);
CREATE INDEX IF NOT EXISTS idx_gp_surname_norm
    ON gedcom_persons(surname_norm);
CREATE INDEX IF NOT EXISTS idx_gp_source ON gedcom_persons(source);

-- Verknüpft dieselbe reale Person über Quellen hinweg (Dedup/Überlagerung),
-- ohne Daten zu überschreiben. ged_id_primary = bevorzugt 'gedcom'-Eintrag.
CREATE TABLE IF NOT EXISTS gedcom_person_xref (
    ged_id_primary   TEXT NOT NULL,
    source_primary   TEXT NOT NULL DEFAULT 'gedcom',
    ged_id_other     TEXT NOT NULL,
    source_other     TEXT NOT NULL,
    score            REAL NOT NULL DEFAULT 0.0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ged_id_primary, ged_id_other)
);
CREATE INDEX IF NOT EXISTS idx_gx_other ON gedcom_person_xref(ged_id_other);

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
        # Migration: sosa_number für bestehende DBs ohne die Spalte
        try:
            cur.execute("ALTER TABLE gedcom_persons ADD COLUMN sosa_number INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # Spalte existiert bereits
        # Migration: source-Spalte für bestehende DBs
        try:
            cur.execute("ALTER TABLE gedcom_persons ADD COLUMN source TEXT NOT NULL DEFAULT 'gedcom'")
        except Exception:
            pass


# ── Import ─────────────────────────────────────────────────────────────────────

def _build_sosa_map(root_id: str, individuals: dict, families: dict) -> dict:
    """Sosa-Stradonitz-Nummern aller Vorfahren: {ged_id: sosa_number}.
    root_id erhält 1, Vater=2, Mutter=3, Vaters Vater=4, …"""
    result = {root_id: 1}
    queue = [(root_id, 1)]
    while queue:
        pid, sosa = queue.pop(0)
        for fam_id in (individuals.get(pid) or {}).get("FAMC", []):
            fam = families.get(fam_id) or {}
            for key, child_sosa in (("HUSB", sosa * 2), ("WIFE", sosa * 2 + 1)):
                pid2 = fam.get(key)
                if pid2 and pid2 not in result:
                    result[pid2] = child_sosa
                    queue.append((pid2, child_sosa))
    return result


def import_gedcom_persons(db, individuals: dict, ged_file: str = "",
                          root_id: str = "", families: dict | None = None) -> int:
    """Löscht und füllt gedcom_persons aus einem GEDCOM-Individuals-Dict.
    Falls root_id + families angegeben werden, enthält sosa_number die
    Sosa-Stradonitz-Nummer jeder Person (für spätere Verwandtschaftsberechnung).
    Gibt Anzahl importierter Personen zurück."""
    sosa_map: dict = {}
    if root_id and families:
        sosa_map = _build_sosa_map(root_id, individuals, families)

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
            "sosa_number":  sosa_map.get(ged_id, 0),
        })
    with db._cursor() as cur:
        # Nur die EIGENEN GEDCOM-Personen ersetzen – Anverwandte/WikiTree bleiben
        cur.execute("DELETE FROM gedcom_persons WHERE source='gedcom'")
        cur.executemany(
            """INSERT OR REPLACE INTO gedcom_persons
               (ged_id, given_name, surname, surname_norm, koelner_code,
                sex, birth_year, birth_qual, birth_place,
                death_year, death_place, ged_file, sosa_number)
               VALUES (:ged_id, :given_name, :surname, :surname_norm, :koelner_code,
                       :sex, :birth_year, :birth_qual, :birth_place,
                       :death_year, :death_place, :ged_file, :sosa_number)""",
            rows,
        )
    log.info("bridge: %d GEDCOM-Personen importiert (Sosa: %d)",
             len(rows), sum(1 for r in rows if r["sosa_number"]))
    return len(rows)


def import_external_persons(db, persons: list[dict], source: str) -> int:
    """Importiert Personen aus einer EXTERNEN Quelle (z.B. 'anverwandte',
    'wikitree') in gedcom_persons – ohne die eigenen GEDCOM-Daten zu berühren.

    Jede person braucht: ext_id und mindestens given_name/surname; optional
    sex, birth_year, birth_place, death_year, death_place.
    ged_id wird als '<source>:<ext_id>' gespeichert, damit es nicht mit den
    eigenen GEDCOM-IDs kollidiert. Vorhandene Einträge derselben Quelle werden
    ersetzt (idempotenter Re-Import); andere Quellen bleiben unberührt.
    """
    ensure_tables(db)

    def _int(v):
        try:
            return int(str(v)[:4])
        except (TypeError, ValueError):
            return None

    rows = []
    for p in persons:
        ext = str(p.get("ext_id") or "").strip()
        if not ext:
            continue
        surname = (p.get("surname") or "").strip()
        given   = (p.get("given_name") or "").strip()
        if not given and not surname:
            continue
        sn_norm = _norm(surname)
        rows.append({
            "ged_id":       f"{source}:{ext}",
            "given_name":   given,
            "surname":      surname,
            "surname_norm": sn_norm,
            "koelner_code": _koelner(sn_norm) if sn_norm else "",
            "sex":          (p.get("sex") or "").strip(),
            "birth_year":   _int(p.get("birth_year")),
            "birth_qual":   "",
            "birth_place":  (p.get("birth_place") or "").strip(),
            "death_year":   _int(p.get("death_year")),
            "death_place":  (p.get("death_place") or "").strip(),
            "ged_file":     source,
            "sosa_number":  0,
            "source":       source,
        })
    with db._cursor() as cur:
        cur.execute("DELETE FROM gedcom_persons WHERE source=?", (source,))
        cur.executemany(
            """INSERT OR REPLACE INTO gedcom_persons
               (ged_id, given_name, surname, surname_norm, koelner_code,
                sex, birth_year, birth_qual, birth_place,
                death_year, death_place, ged_file, sosa_number, source)
               VALUES (:ged_id, :given_name, :surname, :surname_norm, :koelner_code,
                       :sex, :birth_year, :birth_qual, :birth_place,
                       :death_year, :death_place, :ged_file, :sosa_number, :source)""",
            rows,
        )
    log.info("bridge: %d Personen aus '%s' importiert", len(rows), source)
    return len(rows)


def _lev(a: str, b: str, cap: int = 4) -> int:
    """Levenshtein-Distanz mit Früh-Abbruch bei > cap (Performance)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > cap:
        return cap + 1
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        row_min = cur[0]
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            row_min = min(row_min, cur[j])
        if row_min > cap:
            return cap + 1
        prev = cur
    return prev[lb]


def _name_sim(a: str, b: str) -> float:
    """0..1 Ähnlichkeit zweier Namen: kombiniert SequenceMatcher-Ratio und
    längen-normierte Levenshtein-Distanz."""
    a, b = (a or "").lower(), (b or "").lower()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    lev = _lev(a, b, cap=max(len(a), len(b)))
    lev_sim = 1.0 - lev / max(len(a), len(b))
    return max(seq, lev_sim)


def link_duplicates(db, source: str, primary_source: str = "gedcom",
                    year_tol: int = 3, min_score: float = 0.72,
                    progress_cb=None) -> int:
    """Verknüpft Personen aus `source` mit derselben realen Person in
    `primary_source` (Standard: eigener GEDCOM) in gedcom_person_xref.

    Fuzzy-Match (überschreibt KEINE Daten):
      * Blocking: Kandidaten teilen den Kölner-Code ODER die ersten 4 Zeichen
        des normalisierten Nachnamens (fängt Schreibvarianten wie
        Kovermann/Covermann, Röwekamp/Rowekamp).
      * Scoring: Nachnamen-Ähnlichkeit (Kölner + Levenshtein/SequenceMatcher),
        Vornamen-Ähnlichkeit (Levenshtein), Geburtsjahr-Nähe (±year_tol),
        kleiner Orts-Bonus. Verknüpft nur, wenn Gesamtscore >= min_score.
    Gibt Anzahl neuer Verknüpfungen zurück.
    """
    ensure_tables(db)

    def p(msg):
        if progress_cb:
            try: progress_cb(msg)
            except Exception: pass

    def _first(g):
        toks = (g or "").lower().split()
        return toks[0] if toks else ""

    def _region(place):
        return _extract_region(place or "")

    with db._cursor() as cur:
        prim = cur.execute(
            "SELECT ged_id, given_name, surname_norm, koelner_code, birth_year, "
            "birth_place FROM gedcom_persons WHERE source=?",
            (primary_source,)).fetchall()

        # zwei Blocking-Indizes: nach Kölner-Code und nach Nachname-Präfix
        idx_koel = defaultdict(list)
        idx_pref = defaultdict(list)
        for r in prim:
            entry = (r["ged_id"], _first(r["given_name"]), r["surname_norm"],
                     r["birth_year"], _region(r["birth_place"]))
            if r["koelner_code"]:
                idx_koel[r["koelner_code"]].append(entry)
            if r["surname_norm"]:
                idx_pref[r["surname_norm"][:4]].append(entry)

        others = cur.execute(
            "SELECT ged_id, given_name, surname_norm, koelner_code, birth_year, "
            "birth_place FROM gedcom_persons WHERE source=?", (source,)).fetchall()

        linked = 0
        for r in others:
            o_first  = _first(r["given_name"])
            o_sn     = r["surname_norm"] or ""
            o_year   = r["birth_year"]
            o_region = _region(r["birth_place"])

            # Kandidaten aus beiden Blocking-Buckets sammeln (dedupliziert)
            cands = {}
            for e in idx_koel.get(r["koelner_code"], []):
                cands[e[0]] = e
            if o_sn:
                for e in idx_pref.get(o_sn[:4], []):
                    cands[e[0]] = e
            if not cands:
                continue

            best, best_score = None, 0.0
            for pid, p_first, p_sn, p_year, p_region in cands.values():
                sn_sim = _name_sim(o_sn, p_sn)
                if sn_sim < 0.6:
                    continue
                score = 0.45 * sn_sim
                gn_sim = _name_sim(o_first, p_first) if (o_first and p_first) else 0.0
                score += 0.30 * gn_sim
                if o_year and p_year:
                    dy = abs(int(o_year) - int(p_year))
                    if dy > year_tol:
                        continue
                    score += 0.20 * (1 - dy / (year_tol + 1))
                elif not o_year and not p_year:
                    score += 0.05
                if o_region and p_region and o_region == p_region:
                    score += 0.05
                if score > best_score:
                    best, best_score = pid, score

            if best and best_score >= min_score:
                cur.execute(
                    """INSERT OR REPLACE INTO gedcom_person_xref
                       (ged_id_primary, source_primary, ged_id_other, source_other, score)
                       VALUES (?,?,?,?,?)""",
                    (best, primary_source, r["ged_id"], source, round(best_score, 3)))
                linked += 1
        p(f"{linked} Querbezüge {source}↔{primary_source} angelegt "
          f"(Fuzzy, Schwelle {min_score}).")
    return linked


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


# ── Ort-Nachnamen-Korrelation: wahrscheinliche Herkunftsregion ────────────────

def _extract_region(birth_place: str) -> str:
    """Extrahiert die Region (letzter nicht-leerer Teil nach Komma) aus einem Geburtsort."""
    if not birth_place:
        return ""
    parts = [p.strip() for p in birth_place.split(",") if p.strip()]
    if not parts:
        return ""
    # Last part is typically country, second-to-last is region/state
    if len(parts) >= 2:
        return parts[-2].lower()
    return parts[-1].lower()


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

    # ── 1. GEDCOM-Regionen-Index aufbauen ─────────────────────────────────────
    try:
        with db._cursor() as cur:
            ged_rows = cur.execute(
                "SELECT surname_norm, koelner_code, birth_place FROM gedcom_persons "
                "WHERE birth_place != '' AND surname_norm != ''"
            ).fetchall()
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
            except Exception: pass

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
