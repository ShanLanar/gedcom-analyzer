#!/usr/bin/env python3
"""
Entity Resolution Engine

Erzeugt entity_assignments (sichere Matches) und entity_candidates
(zu prüfende Vorschläge) aus den vorhandenen Source-Tabellen.

Quellen (Bäume):
  source_webtrees        – importierte GEDCOM/webtrees-Personen
  source_matrikula_entries – Kirchenbucheinträge (Taufe/Heirat/Tod)
  source_anverwandte     – gecrawlte Anverwandte-Profile

Quellen (DNA):
  matches                – Ancestry / MyHeritage / GEDmatch Matches
  gedmatch_matches       – GEDmatch-Kit-Matches
  gedmatch_bridge        – GEDmatch-Kit ↔ Ancestry/MH-Match-Verknüpfung

Verbindungsbrücken (bereits bekannt, Goldstandard):
  match_person_links     – manuell bestätigte Match→Person-Zuweisung
  persons.gedcom_id      – Ancestry-Person verknüpft mit webtrees/GEDCOM-ID
  matches.linked_in_tree – Match ist in eigenem Baum verlinkt

Lauf-Modi:
  dry-run    Nur Kandidaten zählen, nichts schreiben
  candidates Nur entity_candidates erzeugen, keine Assignments
  auto       Goldstandard-Assignments + Kandidaten schreiben
  full       auto + Transitivity-Closure

Start:
    python -m ancestry.core.entity_resolution
    python -m ancestry.core.entity_resolution --mode full --year-diff 3
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from tasks.names import koelner_phonetik as _kp, _levenshtein as _lev
except ImportError:
    _kp = _lev = None  # type: ignore[assignment]

DB_PATH = ROOT / "ancestry_dna.db"


# ── DB-Zugriff ─────────────────────────────────────────────────────────────────

def open_db(path: Path = DB_PATH) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def _ensure_schema(db: sqlite3.Connection) -> None:
    """Stellt sicher dass die nötigen Tabellen existieren (Migration-safe)."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS entities (
        entity_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        label       TEXT DEFAULT '',
        notes       TEXT DEFAULT '',
        merged_into INTEGER REFERENCES entities(entity_id),
        created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS entity_assignments (
        assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id     INTEGER NOT NULL REFERENCES entities(entity_id),
        source_table  TEXT NOT NULL,
        source_row_id TEXT NOT NULL,
        person_role   TEXT NOT NULL DEFAULT 'person',
        confidence    REAL DEFAULT 1.0,
        assigned_by   TEXT DEFAULT 'auto',
        is_active     INTEGER DEFAULT 1,
        created_at    TEXT DEFAULT (datetime('now')),
        UNIQUE (source_table, source_row_id, person_role)
    );

    CREATE TABLE IF NOT EXISTS entity_candidates (
        candidate_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        source_table_a  TEXT NOT NULL,
        source_row_id_a TEXT NOT NULL,
        person_role_a   TEXT DEFAULT 'person',
        source_table_b  TEXT NOT NULL,
        source_row_id_b TEXT NOT NULL,
        person_role_b   TEXT DEFAULT 'person',
        confidence      REAL NOT NULL,
        evidence        TEXT DEFAULT '{}',
        status          TEXT DEFAULT 'pending',
        reviewed_at     TEXT DEFAULT '',
        created_at      TEXT DEFAULT (datetime('now')),
        UNIQUE (source_table_a, source_row_id_a, person_role_a,
                source_table_b, source_row_id_b, person_role_b)
    );

    CREATE INDEX IF NOT EXISTS idx_ea_entity  ON entity_assignments(entity_id);
    CREATE INDEX IF NOT EXISTS idx_ea_source  ON entity_assignments(source_table, source_row_id);
    CREATE INDEX IF NOT EXISTS idx_ec_status  ON entity_candidates(status);
    CREATE INDEX IF NOT EXISTS idx_ec_conf    ON entity_candidates(confidence DESC);
    """)
    # merged_into nachrüsten falls alte Schema-Version
    try:
        db.execute("ALTER TABLE entities ADD COLUMN merged_into INTEGER REFERENCES entities(entity_id)")
        db.commit()
    except Exception:
        pass
    db.commit()


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _get_or_create_entity(db: sqlite3.Connection, label: str = "", notes: str = "") -> int:
    cur = db.execute(
        "INSERT INTO entities (label, notes) VALUES (?,?)", (label, notes)
    )
    return cur.lastrowid


def _assign(
    db: sqlite3.Connection,
    entity_id: int,
    source_table: str,
    source_row_id: str,
    person_role: str = "person",
    confidence: float = 1.0,
    assigned_by: str = "auto",
) -> bool:
    """
    Weist eine Source-Zeile einer Entity zu.
    Gibt False zurück wenn die Zuweisung bereits existiert (UNIQUE-Konflikt).
    """
    try:
        db.execute(
            """INSERT INTO entity_assignments
               (entity_id, source_table, source_row_id, person_role, confidence, assigned_by)
               VALUES (?,?,?,?,?,?)""",
            (entity_id, source_table, str(source_row_id), person_role, confidence, assigned_by),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def _add_candidate(
    db: sqlite3.Connection,
    src_a: tuple[str, str, str],  # (table, row_id, role)
    src_b: tuple[str, str, str],
    confidence: float,
    evidence: dict,
) -> bool:
    """Fügt einen Kandidaten hinzu. False bei Duplikat."""
    # Kanonische Reihenfolge (table_a < table_b lexikografisch)
    if src_a[0] > src_b[0] or (src_a[0] == src_b[0] and src_a[1] > src_b[1]):
        src_a, src_b = src_b, src_a
    try:
        db.execute(
            """INSERT INTO entity_candidates
               (source_table_a, source_row_id_a, person_role_a,
                source_table_b, source_row_id_b, person_role_b,
                confidence, evidence)
               VALUES (?,?,?,?,?,?,?,?)""",
            (*src_a, *src_b, confidence, json.dumps(evidence, ensure_ascii=False)),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def _entity_for_source(
    db: sqlite3.Connection, source_table: str, source_row_id: str, person_role: str = "person"
) -> Optional[int]:
    row = db.execute(
        """SELECT entity_id FROM entity_assignments
           WHERE source_table=? AND source_row_id=? AND person_role=? AND is_active=1""",
        (source_table, str(source_row_id), person_role),
    ).fetchone()
    return row["entity_id"] if row else None


# ── Phase 1a: Bootstrap aus persons-Tabelle ────────────────────────────────────

def phase1a_bootstrap_persons(db: sqlite3.Connection, dry_run: bool = False) -> dict:
    """
    Erstellt Entities für alle Einträge in der persons-Tabelle und verknüpft
    deren bekannte Quellen:
      - persons.gedcom_id      → source_webtrees.wt_id
      - match_person_links     → matches.match_guid
      - persons.gedmatch_kit_id → gedmatch_matches.kit_id (als eigenes Kit)
    """
    stats = {"persons": 0, "entities_new": 0, "assignments": 0}

    try:
        persons = db.execute(
            "SELECT * FROM persons ORDER BY person_id"
        ).fetchall()
    except sqlite3.OperationalError:
        return stats  # Tabelle existiert nicht

    for p in persons:
        stats["persons"] += 1
        pid = str(p["person_id"])

        # Existiert schon eine Entity für diese Person?
        existing = _entity_for_source(db, "persons", pid)
        if existing:
            entity_id = existing
        else:
            if not dry_run:
                label = f"{p['given_name'] or ''} {p['surname'] or ''}".strip() or f"Person-{pid}"
                entity_id = _get_or_create_entity(db, label=label)
                _assign(db, entity_id, "persons", pid)
                stats["entities_new"] += 1
            else:
                entity_id = -1

        if dry_run:
            continue

        # webtrees-Person via gedcom_id
        gedcom_id = p["gedcom_id"]
        if gedcom_id:
            wt_row = db.execute(
                "SELECT wt_id FROM source_webtrees WHERE wt_id=? LIMIT 1",
                (str(gedcom_id),),
            ).fetchone()
            if wt_row and _assign(db, entity_id, "source_webtrees", str(gedcom_id)):
                stats["assignments"] += 1

        # DNA-Matches via match_person_links
        try:
            links = db.execute(
                "SELECT match_guid FROM match_person_links WHERE person_id=?",
                (p["person_id"],),
            ).fetchall()
            for lnk in links:
                if _assign(db, entity_id, "matches", lnk["match_guid"], confidence=1.0,
                           assigned_by="match_person_links"):
                    stats["assignments"] += 1
        except sqlite3.OperationalError:
            pass

    if not dry_run:
        db.commit()
    return stats


# ── Phase 1b: GEDmatch-Bridge ──────────────────────────────────────────────────

def phase1b_gedmatch_bridge(db: sqlite3.Connection, dry_run: bool = False) -> dict:
    """
    gedmatch_bridge verknüpft GEDmatch-Kit-IDs mit Ancestry/MH-match_guids.
    Beide Seiten beziehen sich auf dieselbe Person → sicherer Link.
    """
    stats = {"bridges": 0, "assignments": 0, "new_entities": 0}

    try:
        bridges = db.execute("SELECT * FROM gedmatch_bridge").fetchall()
    except sqlite3.OperationalError:
        return stats

    for b in bridges:
        stats["bridges"] += 1
        kit_id    = str(b["gedmatch_kit_id"])
        match_guid = str(b["match_guid"])
        conf = float(b["confidence"]) if b["confidence"] else 1.0

        entity_kit   = _entity_for_source(db, "gedmatch_matches", kit_id)
        entity_match = _entity_for_source(db, "matches", match_guid)

        if entity_kit and entity_match:
            if entity_kit != entity_match and not dry_run:
                # Zwei Entities repräsentieren dieselbe Person → mergen
                _merge_entities(db, entity_match, entity_kit,
                                reason=f"gedmatch_bridge {kit_id}↔{match_guid}")
        elif entity_kit and not dry_run:
            if _assign(db, entity_kit, "matches", match_guid, confidence=conf,
                       assigned_by="gedmatch_bridge"):
                stats["assignments"] += 1
        elif entity_match and not dry_run:
            if _assign(db, entity_match, "gedmatch_matches", kit_id, confidence=conf,
                       assigned_by="gedmatch_bridge"):
                stats["assignments"] += 1
        else:
            if not dry_run:
                entity_id = _get_or_create_entity(
                    db, label=f"GEDmatch {kit_id}", notes=f"bridge→{match_guid}"
                )
                _assign(db, entity_id, "gedmatch_matches", kit_id, confidence=conf,
                        assigned_by="gedmatch_bridge")
                _assign(db, entity_id, "matches", match_guid, confidence=conf,
                        assigned_by="gedmatch_bridge")
                stats["new_entities"] += 1

    if not dry_run:
        db.commit()
    return stats


# ── Phase 1c: linked_in_tree → Kandidaten mit hoher Konfidenz ─────────────────

def phase1c_linked_in_tree(db: sqlite3.Connection, dry_run: bool = False) -> dict:
    """
    Matches mit linked_in_tree=1 sind manuell mit einer Baum-Person verknüpft.
    Wenn persons.gedcom_id vorhanden → direkte entity_assignment.
    Sonst → entity_candidate mit confidence=0.95.
    """
    stats = {"linked": 0, "assigned": 0, "candidates": 0}

    try:
        linked = db.execute("""
            SELECT m.match_guid, m.display_name, m.source,
                   p.person_id, p.gedcom_id, p.given_name, p.surname
            FROM   matches m
            LEFT JOIN match_person_links mpl ON mpl.match_guid = m.match_guid
            LEFT JOIN persons p ON p.person_id = mpl.person_id
            WHERE  m.linked_in_tree = 1
              AND  m.source = 'ancestry'
        """).fetchall()
    except sqlite3.OperationalError:
        return stats

    for row in linked:
        stats["linked"] += 1
        match_guid = row["match_guid"]
        gedcom_id  = row["gedcom_id"]

        if gedcom_id and not dry_run:
            # Direkte Zuweisung: Match → webtrees-Person (Goldstandard)
            entity_wt    = _entity_for_source(db, "source_webtrees", str(gedcom_id))
            entity_match = _entity_for_source(db, "matches", match_guid)

            if entity_wt and entity_match and entity_wt != entity_match:
                _merge_entities(db, entity_wt, entity_match,
                                reason=f"linked_in_tree {match_guid}→{gedcom_id}")
            elif entity_wt:
                if _assign(db, entity_wt, "matches", match_guid, confidence=1.0,
                           assigned_by="linked_in_tree"):
                    stats["assigned"] += 1
            elif entity_match:
                if _assign(db, entity_match, "source_webtrees", str(gedcom_id), confidence=1.0,
                           assigned_by="linked_in_tree"):
                    stats["assigned"] += 1
            else:
                label = f"{row['given_name'] or ''} {row['surname'] or ''}".strip()
                entity_id = _get_or_create_entity(db, label=label)
                _assign(db, entity_id, "matches", match_guid, confidence=1.0,
                        assigned_by="linked_in_tree")
                _assign(db, entity_id, "source_webtrees", str(gedcom_id), confidence=1.0,
                        assigned_by="linked_in_tree")
                stats["assigned"] += 2

        elif not gedcom_id:
            # Kein direkter GEDCOM-Link → Kandidat mit hoher Konfidenz
            evidence = {
                "type":        "linked_in_tree",
                "match_guid":  match_guid,
                "source":      row["source"],
                "match_name":  row["display_name"],
            }
            if not dry_run:
                _add_candidate(
                    db,
                    ("matches", match_guid, "person"),
                    ("source_webtrees", "__unresolved__", "person"),
                    confidence=0.95,
                    evidence=evidence,
                )
            stats["candidates"] += 1

    if not dry_run:
        db.commit()
    return stats


# ── Phase 2: Transitivity ──────────────────────────────────────────────────────

def phase2_transitivity(db: sqlite3.Connection, dry_run: bool = False) -> dict:
    """
    Schließt Transitivity-Lücken: Wenn eine bestätigte entity_candidate
    zwei bereits zugewiesene Quellen verbindet die verschiedene Entities haben,
    werden die Entities gemergt.
    """
    stats = {"merges": 0}

    confirmed = db.execute(
        """SELECT * FROM entity_candidates WHERE status='confirmed'"""
    ).fetchall()

    for cand in confirmed:
        eid_a = _entity_for_source(
            db, cand["source_table_a"], cand["source_row_id_a"], cand["person_role_a"]
        )
        eid_b = _entity_for_source(
            db, cand["source_table_b"], cand["source_row_id_b"], cand["person_role_b"]
        )
        if eid_a and eid_b and eid_a != eid_b:
            if not dry_run:
                _merge_entities(db, eid_a, eid_b,
                                reason=f"confirmed_candidate {cand['candidate_id']}")
            stats["merges"] += 1

    if not dry_run:
        db.commit()
    return stats


def _merge_entities(db: sqlite3.Connection, keep: int, drop: int, reason: str = "") -> None:
    """
    Merged Entity `drop` in `keep`.
    Alle Assignments von `drop` werden auf `keep` umgehängt (soweit kein Konflikt).
    `drop` wird als merged_into=keep markiert, alle Assignments inaktiv gesetzt.
    """
    assignments = db.execute(
        "SELECT * FROM entity_assignments WHERE entity_id=? AND is_active=1",
        (drop,),
    ).fetchall()

    for a in assignments:
        try:
            db.execute(
                """INSERT INTO entity_assignments
                   (entity_id, source_table, source_row_id, person_role,
                    confidence, assigned_by, is_active)
                   VALUES (?,?,?,?,?,?,1)""",
                (keep, a["source_table"], a["source_row_id"], a["person_role"],
                 a["confidence"], f"merge:{reason}"),
            )
        except sqlite3.IntegrityError:
            pass  # keep hat diesen Source bereits

    db.execute(
        "UPDATE entity_assignments SET is_active=0 WHERE entity_id=?", (drop,)
    )
    db.execute(
        "UPDATE entities SET merged_into=? WHERE entity_id=?", (keep, drop)
    )


# ── Phase 3: Heuristische Kandidaten ──────────────────────────────────────────

def phase3_name_candidates(
    db: sqlite3.Connection,
    max_year_diff: int = 5,
    min_confidence: float = 0.6,
    dry_run: bool = False,
) -> dict:
    """
    Erzeugt entity_candidates durch Namens- und Jahresvergleich zwischen:
      source_webtrees ↔ source_matrikula_entries
      source_webtrees ↔ source_anverwandte
      source_anverwandte ↔ source_matrikula_entries

    Verwendet Kölner Phonetik für Namens-Match, Levenshtein als Tiebreaker.
    Kein Kölner Code → einfaches case-insensitive Teilstring-Match.
    """
    stats = {"pairs_checked": 0, "candidates": 0}

    if not dry_run:
        _build_name_cache(db)

    pairs: list[tuple[str, str, str, str, str, str, float, dict]] = []

    # ── webtrees ↔ matrikula ───────────────────────────────────────────────────
    try:
        wt_rows = db.execute("""
            SELECT wt_id, given_name, surname, birth_date, death_date
            FROM source_webtrees
            WHERE wt_id NOT IN (
                SELECT source_row_id FROM entity_assignments
                WHERE source_table='source_webtrees' AND is_active=1
            )
        """).fetchall()
    except sqlite3.OperationalError:
        wt_rows = []

    try:
        mat_rows = db.execute("""
            SELECT entry_id, entry_type, person_name, father_name, mother_name,
                   event_year
            FROM source_matrikula_entries
            WHERE entry_id NOT IN (
                SELECT source_row_id FROM entity_assignments
                WHERE source_table='source_matrikula_entries' AND is_active=1
            )
        """).fetchall()
    except sqlite3.OperationalError:
        mat_rows = []

    for wt in wt_rows:
        wt_name = f"{wt['given_name'] or ''} {wt['surname'] or ''}".strip()
        wt_year = _extract_year(wt["birth_date"])
        if not wt_name:
            continue
        wt_code = _kp(wt_name) if _kp else None

        for mat in mat_rows:
            stats["pairs_checked"] += 1
            mat_name = mat["person_name"] or ""
            if not mat_name:
                continue
            mat_code = _kp(mat_name) if _kp else None
            mat_year = mat["event_year"]

            score, evidence = _score_match(
                wt_name, wt_code, wt_year,
                mat_name, mat_code, mat_year,
                max_year_diff=max_year_diff,
            )
            if score >= min_confidence:
                role = _role_for_entry_type(mat["entry_type"])
                pairs.append((
                    "source_webtrees", str(wt["wt_id"]), "person",
                    "source_matrikula_entries", str(mat["entry_id"]), role,
                    score, {**evidence, "type": "name_year_match",
                            "wt_name": wt_name, "mat_name": mat_name},
                ))

    # ── webtrees ↔ anverwandte ─────────────────────────────────────────────────
    try:
        anv_rows = db.execute("""
            SELECT anv_id, name_raw, birth_year, death_year
            FROM source_anverwandte
            WHERE anv_id NOT IN (
                SELECT source_row_id FROM entity_assignments
                WHERE source_table='source_anverwandte' AND is_active=1
            )
        """).fetchall()
    except sqlite3.OperationalError:
        anv_rows = []

    for wt in wt_rows:
        wt_name = f"{wt['given_name'] or ''} {wt['surname'] or ''}".strip()
        wt_year = _extract_year(wt["birth_date"])
        if not wt_name:
            continue
        wt_code = _kp(wt_name) if _kp else None

        for anv in anv_rows:
            stats["pairs_checked"] += 1
            anv_name = anv["name_raw"] or ""
            if not anv_name:
                continue
            anv_code = _kp(anv_name) if _kp else None
            anv_year = anv["birth_year"]

            score, evidence = _score_match(
                wt_name, wt_code, wt_year,
                anv_name, anv_code, anv_year,
                max_year_diff=max_year_diff,
            )
            if score >= min_confidence:
                pairs.append((
                    "source_webtrees", str(wt["wt_id"]), "person",
                    "source_anverwandte", str(anv["anv_id"]), "person",
                    score, {**evidence, "type": "name_year_match",
                            "wt_name": wt_name, "anv_name": anv_name},
                ))

    if not dry_run:
        for *src_pair, score, evidence in pairs:
            src_a = tuple(src_pair[:3])
            src_b = tuple(src_pair[3:6])
            if _add_candidate(db, src_a, src_b, score, evidence):
                stats["candidates"] += 1
        db.commit()
    else:
        stats["candidates"] = len(pairs)

    return stats


def _score_match(
    name_a: str, code_a: Optional[str], year_a: Optional[int],
    name_b: str, code_b: Optional[str], year_b: Optional[int],
    max_year_diff: int = 5,
) -> tuple[float, dict]:
    """
    Berechnet einen Konfidenz-Score [0..1] für zwei Personen.

    Kölner Code identisch   → 0.55 Basis
    + Levenshtein ≤ 2        → +0.15
    + Jahr ≤ max_year_diff   → +0.20 / +0.10 je nach Differenz
    + Jahr exakt gleich      → +0.10 zusätzlich
    """
    evidence: dict = {}
    score = 0.0

    # Namens-Score
    if code_a and code_b and code_a == code_b:
        score += 0.55
        evidence["koeln_code"] = code_a
        if _lev:
            dist = _lev(name_a.lower(), name_b.lower())
            evidence["levenshtein"] = dist
            if dist <= 2:
                score += 0.15
            elif dist <= 4:
                score += 0.05
    elif name_a.lower() in name_b.lower() or name_b.lower() in name_a.lower():
        score += 0.30
    else:
        return 0.0, {}

    # Jahres-Score
    if year_a and year_b:
        diff = abs(year_a - year_b)
        evidence["year_a"] = year_a
        evidence["year_b"] = year_b
        evidence["year_diff"] = diff
        if diff == 0:
            score += 0.30
        elif diff <= max_year_diff:
            score += 0.20 - (diff / max_year_diff) * 0.10
    elif not year_a or not year_b:
        # Ein Jahr fehlt → leichte Penalisierung
        score -= 0.05

    return round(min(score, 1.0), 3), evidence


def _role_for_entry_type(entry_type: str) -> str:
    return {"Taufe": "child", "Heirat": "groom", "Tod": "deceased"}.get(
        entry_type, "person"
    )


def _extract_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    import re
    m = re.search(r"\b(\d{4})\b", str(date_str))
    return int(m.group(1)) if m else None


def _build_name_cache(db: sqlite3.Connection) -> None:
    """Stellt sicher dass name_index für source_webtrees und source_anverwandte befüllt ist."""
    if _kp is None:
        return
    # source_webtrees
    try:
        missing = db.execute("""
            SELECT wt_id, given_name, surname FROM source_webtrees
            WHERE wt_id NOT IN (SELECT entry_id FROM name_index WHERE name_role='wt_person')
        """).fetchall()
        for row in missing:
            name = f"{row['given_name'] or ''} {row['surname'] or ''}".strip()
            if name:
                db.execute(
                    """INSERT OR IGNORE INTO name_index
                       (entry_id, book_id, page_nr, name_raw, name_norm, koeln_code, name_role)
                       VALUES (?,?,?,?,?,?,?)""",
                    (row["wt_id"], "source_webtrees", 0, name, name.lower(), _kp(name), "wt_person"),
                )
        db.commit()
    except Exception:
        pass


# ── Haupt-Lauf ─────────────────────────────────────────────────────────────────

def run(
    db: sqlite3.Connection,
    mode: str = "candidates",
    max_year_diff: int = 5,
    min_confidence: float = 0.6,
    dry_run: bool = False,
) -> dict:
    """
    Führt die Entity Resolution aus.

    mode:
      dry-run    – nichts schreiben, nur Statistiken
      candidates – nur entity_candidates erzeugen
      auto       – Phase 1 (Goldstandard) + Phase 3 (Kandidaten)
      full       – auto + Phase 2 (Transitivity)
    """
    if dry_run or mode == "dry-run":
        dry_run = True

    _ensure_schema(db)

    results: dict = {"mode": mode, "dry_run": dry_run}

    if mode in ("auto", "full") or dry_run:
        print("Phase 1a  Bootstrap persons …", end=" ", flush=True)
        r = phase1a_bootstrap_persons(db, dry_run)
        print(f"{r['entities_new']} neue Entities, {r['assignments']} Assignments")
        results["phase1a"] = r

        print("Phase 1b  GEDmatch-Bridge …", end=" ", flush=True)
        r = phase1b_gedmatch_bridge(db, dry_run)
        print(f"{r['bridges']} Brücken, {r['new_entities']} neu, {r['assignments']} Assignments")
        results["phase1b"] = r

        print("Phase 1c  linked_in_tree …", end=" ", flush=True)
        r = phase1c_linked_in_tree(db, dry_run)
        print(f"{r['linked']} verlinkte Matches → {r['assigned']} Assignments, {r['candidates']} Kandidaten")
        results["phase1c"] = r

    if mode == "full" and not dry_run:
        print("Phase 2   Transitivity …", end=" ", flush=True)
        r = phase2_transitivity(db, dry_run)
        print(f"{r['merges']} Entity-Merges")
        results["phase2"] = r

    if mode in ("candidates", "auto", "full") or dry_run:
        print(f"Phase 3   Namens-Kandidaten (Δ≤{max_year_diff}J, conf≥{min_confidence}) …",
              end=" ", flush=True)
        r = phase3_name_candidates(db, max_year_diff, min_confidence, dry_run)
        print(f"{r['pairs_checked']:,} Paare geprüft → {r['candidates']} Kandidaten")
        results["phase3"] = r

    # Zusammenfassung
    print()
    _print_summary(db)
    return results


def _print_summary(db: sqlite3.Connection) -> None:
    try:
        n_ent = db.execute(
            "SELECT COUNT(*) FROM entities WHERE merged_into IS NULL"
        ).fetchone()[0]
        n_asgn = db.execute(
            "SELECT COUNT(*) FROM entity_assignments WHERE is_active=1"
        ).fetchone()[0]
        n_cand = db.execute(
            "SELECT status, COUNT(*) AS n FROM entity_candidates GROUP BY status"
        ).fetchall()
        by_src = db.execute(
            """SELECT source_table, COUNT(*) AS n
               FROM entity_assignments WHERE is_active=1
               GROUP BY source_table ORDER BY n DESC"""
        ).fetchall()

        print(f"  Entities aktiv:      {n_ent:>6,}")
        print(f"  Assignments aktiv:   {n_asgn:>6,}")
        for row in n_cand:
            print(f"  Kandidaten [{row['status']:<9}]: {row['n']:>6,}")
        print()
        for row in by_src:
            print(f"  {row['source_table']:<35} {row['n']:>6,}")
    except Exception:
        pass


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Entity Resolution Engine — verknüpft DNA-Matches mit Baum- und Kirchenbuch-Einträgen"
    )
    ap.add_argument("--mode", default="candidates",
                    choices=["dry-run", "candidates", "auto", "full"],
                    help="Lauf-Modus (default: candidates)")
    ap.add_argument("--year-diff", type=int, default=5,
                    help="Maximale Jahresdifferenz für Namens-Kandidaten (default: 5)")
    ap.add_argument("--min-confidence", type=float, default=0.60,
                    help="Minimale Konfidenz für Kandidaten (default: 0.60)")
    ap.add_argument("--db", default=str(DB_PATH),
                    help=f"Pfad zur ancestry_dna.db (default: {DB_PATH})")
    args = ap.parse_args()

    db = open_db(Path(args.db))
    run(
        db,
        mode=args.mode,
        max_year_diff=args.year_diff,
        min_confidence=args.min_confidence,
        dry_run=(args.mode == "dry-run"),
    )
