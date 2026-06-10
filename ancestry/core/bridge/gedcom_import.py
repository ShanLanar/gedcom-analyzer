"""
gedcom_import.py — SQL-Schema, GEDCOM-/Extern-Import, Sosa-Nummern und
Quellen-Deduplikation (gedcom_person_xref) für das Bridge-Modul.
"""

import re
import logging
from collections import defaultdict

from ._text import _norm, _koelner, _name_sim, _place_sim, _extract_region

log = logging.getLogger(__name__)


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
    status           TEXT NOT NULL DEFAULT 'auto',   -- auto | confirmed | rejected
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
        # Migration: status-Spalte der Xref-Tabelle
        try:
            cur.execute("ALTER TABLE gedcom_person_xref ADD COLUMN status TEXT NOT NULL DEFAULT 'auto'")
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


def link_duplicates(db, source: str, primary_source: str = "gedcom",
                    year_tol: int = 3, min_score: float = 0.72,
                    progress_cb=None) -> int:
    """Verknüpft Personen aus `source` mit derselben realen Person in
    `primary_source` (Standard: eigener GEDCOM) in gedcom_person_xref.

    Fuzzy-Match (überschreibt KEINE Daten):
      * Blocking: Kandidaten teilen den Kölner-Code ODER die ersten 4 Zeichen
        des normalisierten Nachnamens (fängt Schreibvarianten wie
        Kovermann/Covermann, Röwekamp/Rowekamp).
      * Scoring (vornamen-arme Region!): Lebensdaten (Geburts- UND Sterbejahr)
        sowie Geburts-/Sterbeort sind TRAGEND; der Nachname ist Pflicht, der
        Vorname nur schwach positiv – ein Vornamen-WIDERSPRUCH schließt aus.
      * Pflicht-Beleg: Ohne mindestens eine Daten-/Ortsübereinstimmung wird
        NICHT verknüpft (sonst würden gleichnamige Personen verschmelzen).
    Verknüpft nur, wenn Gesamtscore >= min_score.
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

    cols = ("ged_id, given_name, surname_norm, koelner_code, "
            "birth_year, death_year, birth_place, death_place")

    def _yr(dy_a, dy_b):
        """Jahr-Ähnlichkeit 0..1 innerhalb year_tol, sonst -1 (= Widerspruch)."""
        if not dy_a or not dy_b:
            return None
        dy = abs(int(dy_a) - int(dy_b))
        if dy > year_tol:
            return -1.0
        return 1.0 - dy / (year_tol + 1)

    with db._cursor() as cur:
        prim = cur.execute(
            f"SELECT {cols} FROM gedcom_persons WHERE source=?",
            (primary_source,)).fetchall()

        idx_koel = defaultdict(list)
        idx_pref = defaultdict(list)
        for r in prim:
            entry = dict(r)
            if r["koelner_code"]:
                idx_koel[r["koelner_code"]].append(entry)
            if r["surname_norm"]:
                idx_pref[r["surname_norm"][:4]].append(entry)

        others = cur.execute(
            f"SELECT {cols} FROM gedcom_persons WHERE source=?", (source,)).fetchall()

        linked = 0
        for r in others:
            o_first = _first(r["given_name"]); o_sn = r["surname_norm"] or ""

            cands = {}
            for e in idx_koel.get(r["koelner_code"], []):
                cands[e["ged_id"]] = e
            if o_sn:
                for e in idx_pref.get(o_sn[:4], []):
                    cands[e["ged_id"]] = e
            if not cands:
                continue

            best, best_score = None, 0.0
            for e in cands.values():
                sn_sim = _name_sim(o_sn, e["surname_norm"] or "")
                if sn_sim < 0.6:
                    continue

                # Vorname: schwach positiv, aber Widerspruch schließt aus
                p_first = _first(e["given_name"])
                gn_sim = _name_sim(o_first, p_first) if (o_first and p_first) else None
                if gn_sim is not None and gn_sim < 0.4:
                    continue   # anderer Vorname -> andere Person

                # Lebensdaten (tragend) – Widerspruch (-1) schließt aus
                by = _yr(r["birth_year"], e["birth_year"])
                dyr = _yr(r["death_year"], e["death_year"])
                if by == -1 or dyr == -1:
                    continue
                bp = _place_sim(r["birth_place"], e["birth_place"])
                dp = _place_sim(r["death_place"], e["death_place"])

                # Pflicht-Beleg: mind. eine Daten-/Ortsübereinstimmung
                corro = [v for v in (by, dyr) if v and v > 0] + \
                        [v for v in (bp, dp) if v >= 0.6]
                if not corro:
                    continue

                score = (0.28 * sn_sim
                         + 0.12 * (gn_sim or 0.0)
                         + 0.22 * (by if by and by > 0 else 0.0)
                         + 0.16 * (dyr if dyr and dyr > 0 else 0.0)
                         + 0.14 * bp
                         + 0.08 * dp)
                if score > best_score:
                    best, best_score = e["ged_id"], score

            if best and best_score >= min_score:
                # Score aktualisieren, aber manuell gesetzten status erhalten
                cur.execute(
                    """INSERT INTO gedcom_person_xref
                       (ged_id_primary, source_primary, ged_id_other, source_other, score)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(ged_id_primary, ged_id_other)
                       DO UPDATE SET score=excluded.score""",
                    (best, primary_source, r["ged_id"], source, round(best_score, 3)))
                linked += 1
        p(f"{linked} Querbezüge {source}↔{primary_source} angelegt "
          f"(Lebensdaten+Orte gewichtet, Schwelle {min_score}).")
    return linked


def get_xref_pairs(db, status: str = "", lo: float = 0.0, hi: float = 1.0,
                   source: str = "") -> list[dict]:
    """Querbezüge mit beiden Personendetails – für Review/Anzeige.
    Filter: status, Score-Bereich [lo,hi], source_other."""
    ensure_tables(db)
    sql = """
        SELECT x.ged_id_primary, x.ged_id_other, x.source_other, x.score, x.status,
               a.given_name AS a_given, a.surname AS a_surname,
               a.birth_year AS a_by, a.death_year AS a_dy,
               a.birth_place AS a_bp, a.death_place AS a_dp,
               b.given_name AS b_given, b.surname AS b_surname,
               b.birth_year AS b_by, b.death_year AS b_dy,
               b.birth_place AS b_bp, b.death_place AS b_dp
        FROM gedcom_person_xref x
        JOIN gedcom_persons a ON a.ged_id = x.ged_id_primary
        JOIN gedcom_persons b ON b.ged_id = x.ged_id_other
        WHERE x.score BETWEEN ? AND ?
    """
    args = [lo, hi]
    if status:
        sql += " AND x.status=?"; args.append(status)
    if source:
        sql += " AND x.source_other=?"; args.append(source)
    sql += " ORDER BY x.score ASC"
    with db._cursor() as cur:
        return [dict(r) for r in cur.execute(sql, args).fetchall()]


def set_xref_status(db, ged_id_primary: str, ged_id_other: str, status: str) -> None:
    """Querbezug bestätigen/ablehnen (status: confirmed|rejected|auto)."""
    with db._cursor() as cur:
        cur.execute("UPDATE gedcom_person_xref SET status=? "
                    "WHERE ged_id_primary=? AND ged_id_other=?",
                    (status, ged_id_primary, ged_id_other))


def iter_unique_persons(db, sources=None) -> list[dict]:
    """Personen quellenübergreifend dedupliziert: jede reale Person genau
    einmal. Verknüpfte Duplikate (status != 'rejected') werden durch ihren
    Primär-Eintrag (i.d.R. eigener GEDCOM) repräsentiert; die anderen
    Instanzen entfallen. So zählt dieselbe Person nicht mehrfach (z.B. fürs
    ML-Training oder die Orts-Statistik).

    sources: optionale Liste zugelassener Quellen (None = alle).
    """
    ensure_tables(db)
    with db._cursor() as cur:
        absorbed = {r["ged_id_other"] for r in cur.execute(
            "SELECT ged_id_other FROM gedcom_person_xref WHERE status!='rejected'")}
        rows = cur.execute(
            "SELECT ged_id, given_name, surname, surname_norm, koelner_code, "
            "sex, birth_year, birth_place, death_year, death_place, source "
            "FROM gedcom_persons").fetchall()
    out = []
    for r in rows:
        if r["ged_id"] in absorbed:
            continue                      # Duplikat -> durch Primär vertreten
        if sources and r["source"] not in sources:
            continue
        out.append(dict(r))
    return out


def get_gedcom_person_count(db) -> int:
    """Schnelle Zählung der importierten GEDCOM-Personen."""
    try:
        with db._cursor() as cur:
            return cur.execute("SELECT COUNT(*) FROM gedcom_persons").fetchone()[0]
    except Exception:
        return 0
