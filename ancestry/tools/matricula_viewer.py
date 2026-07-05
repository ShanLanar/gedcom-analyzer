#!/usr/bin/env python3
"""
Matricula-Viewer — lokaler Web-Browser für Kirchenbuch-Scans + Transkript

Zeigt archivierte Seiten-JPEGs und Claude-Transkription nebeneinander.
Ermöglicht händische Korrekturen (corrected_by='human'); diese werden beim
erneuten Scannen übersprungen.

Start:
    python matricula_viewer.py            # http://localhost:5000
    python matricula_viewer.py --port 5050
    python matricula_viewer.py --archive-dir ~/matricula_images

Voraussetzungen:
    pip install flask
    scrape_matricula_osnabrueck.py → fetch_matricula_books.py → scan_matricula_kirchspiel.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

try:
    from flask import Flask, abort, jsonify, render_template_string, request, send_file
except ImportError:
    print("Flask nicht installiert:  pip install flask")
    sys.exit(1)

from ancestry.paths import DB_PATH as MAIN_DB_PATH
from ancestry.paths import MATRICULA_ARCHIVE as DEFAULT_ARCHIVE

PARISH_DB   = Path(__file__).resolve().parent / "matricula_parishes.db"
FALLBACK_DB = PARISH_DB.parent / "matricula_entries.db"

# Kölner Phonetik aus tasks.names (Paket ist installiert, s. pyproject.toml)
try:
    from tasks.names import _levenshtein as _lev
    from tasks.names import koelner_phonetik as _kp
except ImportError:
    _kp = _lev = None  # type: ignore[assignment]

app = Flask(__name__)
app.config.setdefault("ARCHIVE_DIR", DEFAULT_ARCHIVE)


# ── DB ─────────────────────────────────────────────────────────────────────────

def _parish_db() -> sqlite3.Connection:
    if not PARISH_DB.exists():
        abort(503, f"Pfarrei-DB nicht gefunden: {PARISH_DB}")
    db = sqlite3.connect(str(PARISH_DB), timeout=30.0)  # 30s busy-timeout gg. Locks
    db.row_factory = sqlite3.Row
    return db


def _main_db() -> sqlite3.Connection:
    path = MAIN_DB_PATH if MAIN_DB_PATH.exists() else FALLBACK_DB
    db = sqlite3.connect(str(path), timeout=30.0)  # 30s busy-timeout gg. Locks
    db.row_factory = sqlite3.Row
    _ensure_correction_cols(db)
    return db


def _ensure_correction_cols(db: sqlite3.Connection) -> None:
    for col in ("corrected_by", "corrected_at"):
        try:
            db.execute(
                f"ALTER TABLE source_matrikula_entries ADD COLUMN {col} TEXT DEFAULT ''"
            )
            db.commit()
        except Exception:
            pass
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS name_index (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id    INTEGER NOT NULL,
            book_id     TEXT NOT NULL,
            page_nr     INTEGER NOT NULL,
            name_raw    TEXT NOT NULL,
            name_norm   TEXT NOT NULL,
            koeln_code  TEXT NOT NULL,
            name_role   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ni_koeln ON name_index(koeln_code);
        CREATE INDEX IF NOT EXISTS idx_ni_book  ON name_index(book_id);
        CREATE TABLE IF NOT EXISTS matrikula_ner (
            ner_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id    INTEGER NOT NULL,
            book_id     TEXT NOT NULL,
            event_year  INTEGER,
            name_raw    TEXT NOT NULL,
            name_norm   TEXT DEFAULT '',
            koeln_code  TEXT DEFAULT '',
            rolle       TEXT NOT NULL,
            beruf       TEXT DEFAULT '',
            ort         TEXT DEFAULT '',
            geburtsname TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_mner_entry  ON matrikula_ner(entry_id);
        CREATE INDEX IF NOT EXISTS idx_mner_koeln  ON matrikula_ner(koeln_code);
        CREATE INDEX IF NOT EXISTS idx_mner_rolle  ON matrikula_ner(rolle);
        CREATE INDEX IF NOT EXISTS idx_mner_year   ON matrikula_ner(event_year);
        CREATE INDEX IF NOT EXISTS idx_mner_book   ON matrikula_ner(book_id);
        """)
    except Exception:
        pass


import re as _re

_GEB_RE   = _re.compile(r'\b(?:geb\.?|geboren|née?)\s+([A-ZÄÖÜ][a-zäöüß\-]+)', _re.I)
_PAREN_RE = _re.compile(r'\(([A-ZÄÖÜ][a-zäöüß\-]+)\)')

_ROLLE_LABEL = {
    "person":           "Person",
    "person2":          "Person 2",
    "father":           "Vater",
    "mother":           "Mutter",
    "kind":             "Kind (Täufling)",
    "vater":            "Vater",
    "mutter":           "Mutter",
    "pate":             "Taufpate",
    "braeutigam":       "Bräutigam",
    "braeutigam_vater": "Vater d. Bräutigams",
    "braut":            "Braut",
    "braut_vater":      "Vater d. Braut",
    "zeuge":            "Zeuge",
    "verstorbener":     "Verstorbener",
    "elternteil":       "Elternteil",
}


def _split_geburtsname(name: str) -> tuple[str, str]:
    m = _GEB_RE.search(name)
    if m:
        return _GEB_RE.sub('', name).strip().rstrip(',').strip(), m.group(1)
    m = _PAREN_RE.search(name)
    if m:
        return _PAREN_RE.sub('', name).strip(), m.group(1)
    return name, ''


def _index_names(
    db: sqlite3.Connection,
    entry_id: int,
    book_id: str,
    page_nr: int,
    names: list[tuple[str, str]],
) -> None:
    """Schreibt Name → Kölner-Code in name_index (nur wenn Phonetik verfügbar)."""
    if _kp is None:
        return
    for name_raw, role in names:
        if not name_raw or not name_raw.strip():
            continue
        try:
            db.execute(
                """INSERT INTO name_index
                   (entry_id, book_id, page_nr, name_raw, name_norm, koeln_code, name_role)
                   VALUES (?,?,?,?,?,?,?)""",
                (entry_id, book_id, page_nr,
                 name_raw, name_raw.lower().strip(), _kp(name_raw), role),
            )
        except Exception:
            pass


def _ner_add(db: sqlite3.Connection, entry_id: int, book_id: str, event_year,
             name_raw: str, rolle: str, ort: str = '') -> None:
    name_raw = (name_raw or '').strip()
    if not name_raw:
        return
    name_clean, geb = _split_geburtsname(name_raw)
    koeln = _kp(name_clean.split()[-1]) if (_kp and name_clean.split()) else ''
    try:
        db.execute(
            """INSERT INTO matrikula_ner
               (entry_id, book_id, event_year, name_raw, name_norm, koeln_code,
                rolle, ort, geburtsname)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (entry_id, book_id, event_year,
             name_raw, name_clean.lower().strip(), koeln,
             rolle, (ort or '').strip(), geb),
        )
    except Exception:
        pass


def _ner_from_entry(db: sqlite3.Connection, entry_id: int, book_id: str,
                    event_year, entry_type: str, raw_json: str) -> None:
    """Extrahiert NER-Personen aus raw_json und schreibt sie in matrikula_ner."""
    if not raw_json:
        return
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, ValueError):
        return

    def _add(name: str, rolle: str, ort: str = '') -> None:
        _ner_add(db, entry_id, book_id, event_year, name, rolle, ort)

    def _add_list(items, rolle: str) -> None:
        for item in (items or []):
            if isinstance(item, str):
                _add(item, rolle)
            elif isinstance(item, dict):
                _add(item.get('name', ''), rolle, ort=item.get('ort', ''))

    if entry_type == 'Taufe':
        ort = data.get('ort', '')
        _add(data.get('kind_name', ''),   'kind',   ort)
        _add(data.get('vater_name', ''),  'vater',  ort)
        _add(data.get('mutter_name', ''), 'mutter', ort)
        _add_list(data.get('taufpaten', []), 'pate')
    elif entry_type == 'Heirat':
        _add(data.get('braeutigam_name', ''),  'braeutigam',      data.get('braeutigam_ort', ''))
        _add(data.get('braeutigam_vater', ''), 'braeutigam_vater', '')
        _add(data.get('braut_name', ''),       'braut',            data.get('braut_ort', ''))
        _add(data.get('braut_vater', ''),      'braut_vater',      '')
        _add_list(data.get('zeugen', []), 'zeuge')
    elif entry_type == 'Tod':
        ort = data.get('ort', '')
        _add(data.get('name', ''),   'verstorbener', ort)
        _add(data.get('eltern', ''), 'elternteil',   ort)
        _add_list(data.get('zeugen', []), 'zeuge')


def _archive_path(book_id: str, page_nr: int) -> Path:
    archive_dir: Path = app.config["ARCHIVE_DIR"]
    parts       = book_id.split("/")
    parish_slug = parts[-2] if len(parts) >= 2 else book_id
    book_slug   = parts[-1]
    return archive_dir / parish_slug / book_slug / f"{page_nr:04d}.jpg"


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    db = _parish_db()
    parishes = db.execute("""
        SELECT p.id, p.name,
               COUNT(DISTINCT k.book_id)  AS n_books,
               MIN(k.year_from)           AS y_min,
               MAX(k.year_to)             AS y_max,
               COALESCE((SELECT COUNT(*) FROM matricula_page_scans s
                         JOIN kirchenbuecher k2 ON k2.book_id=s.book_id
                         WHERE k2.parish_id=p.id AND s.status='done'), 0) AS n_done
        FROM   parishes p
        LEFT JOIN kirchenbuecher k ON k.parish_id = p.id
        GROUP  BY p.id
        ORDER  BY p.name
    """).fetchall()
    return render_template_string(_BASE + _TMPL_INDEX, parishes=parishes)


@app.route("/parish/<path:parish_id>")
def parish_view(parish_id):
    db     = _parish_db()
    parish = db.execute("SELECT * FROM parishes WHERE id=?", (parish_id,)).fetchone()
    if not parish:
        abort(404)
    books = db.execute("""
        SELECT k.*,
               COALESCE((SELECT COUNT(*) FROM matricula_page_scans s
                         WHERE s.book_id=k.book_id AND s.status='done'), 0) AS done_pages,
               COALESCE((SELECT COUNT(*) FROM matricula_page_scans s
                         WHERE s.book_id=k.book_id), 0) AS total_pages
        FROM kirchenbuecher k
        WHERE k.parish_id=?
        ORDER BY k.year_from, k.book_type
    """, (parish_id,)).fetchall()
    return render_template_string(_BASE + _TMPL_PARISH, parish=parish, books=books)


@app.route("/book/<path:book_id>")
def book_view(book_id):
    pdb  = _parish_db()
    book = pdb.execute(
        "SELECT * FROM kirchenbuecher WHERE book_id=?", (book_id,)
    ).fetchone()
    if not book:
        abort(404)
    pages = pdb.execute("""
        SELECT s.page_nr, s.status, s.entry_count, s.image_path
        FROM   matricula_page_scans s
        WHERE  s.book_id=?
        ORDER  BY s.page_nr
    """, (book_id,)).fetchall()

    # correction counts live in the main DB, not the parish catalog
    mdb = _main_db()
    corrected: dict[int, int] = {}
    try:
        for row in mdb.execute(
            """SELECT page_nr, COUNT(*) FROM source_matrikula_entries
               WHERE book_id=? AND corrected_by='human' GROUP BY page_nr""",
            (book_id,),
        ).fetchall():
            corrected[row[0]] = row[1]
    except Exception:
        pass

    pages_enriched = [{**dict(p), "n_corrected": corrected.get(p["page_nr"], 0)}
                      for p in pages]

    parish_id = "/".join(book_id.split("/")[:-1])
    parish    = pdb.execute(
        "SELECT * FROM parishes WHERE id=?", (parish_id,)
    ).fetchone()
    return render_template_string(
        _BASE + _TMPL_BOOK, book=book, pages=pages_enriched, parish=parish
    )


@app.route("/view/<path:rest>")
def page_view(rest):
    # rest = "<book_id>/<page_nr>"  —  book_id kann Slashes enthalten
    parts = rest.rsplit("/", 1)
    if len(parts) != 2:
        abort(400)
    book_id, pg_str = parts
    try:
        page_nr = int(pg_str)
    except ValueError:
        abort(400)

    pdb  = _parish_db()
    book = pdb.execute(
        "SELECT * FROM kirchenbuecher WHERE book_id=?", (book_id,)
    ).fetchone()
    if not book:
        abort(404)

    scan = pdb.execute(
        "SELECT * FROM matricula_page_scans WHERE book_id=? AND page_nr=?",
        (book_id, page_nr),
    ).fetchone()

    mdb     = _main_db()
    entries = mdb.execute(
        """SELECT * FROM source_matrikula_entries
           WHERE book_id=? AND page_nr=? ORDER BY entry_id""",
        (book_id, page_nr),
    ).fetchall()

    # NER-Personen für diese Seite
    try:
        ner_persons = mdb.execute(
            """SELECT n.name_raw, n.rolle, n.ort, n.geburtsname, n.event_year,
                      n.entry_id
               FROM matrikula_ner n
               JOIN source_matrikula_entries e ON e.entry_id = n.entry_id
               WHERE e.book_id=? AND e.page_nr=?
               ORDER BY n.entry_id, n.rolle""",
            (book_id, page_nr),
        ).fetchall()
    except Exception:
        ner_persons = []

    max_page = pdb.execute(
        "SELECT MAX(page_nr) FROM matricula_page_scans WHERE book_id=?", (book_id,)
    ).fetchone()[0] or page_nr

    parish_id = "/".join(book_id.split("/")[:-1])
    parish    = pdb.execute("SELECT * FROM parishes WHERE id=?", (parish_id,)).fetchone()
    has_image = _archive_path(book_id, page_nr).exists()

    return render_template_string(
        _BASE + _TMPL_PAGE,
        book=book, parish=parish,
        book_id=book_id,
        page_nr=page_nr,
        max_page=max_page,
        scan=scan,
        entries=[dict(e) for e in entries],
        ner_persons=[dict(n) for n in ner_persons],
        rolle_label=_ROLLE_LABEL,
        has_image=has_image,
    )


@app.route("/img/<path:rest>")
def serve_image(rest):
    parts = rest.rsplit("/", 1)
    if len(parts) != 2:
        abort(400)
    book_id, pg_str = parts
    try:
        page_nr = int(pg_str)
    except ValueError:
        abort(400)
    path = _archive_path(book_id, page_nr)
    if not path.exists():
        abort(404)
    return send_file(str(path), mimetype="image/jpeg")


@app.route("/correct/<path:rest>", methods=["POST"])
def save_correction(rest):
    parts = rest.rsplit("/", 1)
    if len(parts) != 2:
        abort(400)
    book_id, pg_str = parts
    try:
        page_nr = int(pg_str)
    except ValueError:
        abort(400)

    data = request.get_json()
    if not data or "entries" not in data:
        abort(400)

    mdb = _main_db()
    with mdb:
        mdb.execute(
            "DELETE FROM source_matrikula_entries WHERE book_id=? AND page_nr=?",
            (book_id, page_nr),
        )
        for tbl in ("name_index", "matrikula_ner"):
            try:
                mdb.execute(f"DELETE FROM {tbl} WHERE book_id=? AND page_nr=?",
                            (book_id, page_nr))
            except Exception:
                pass
        for e in data["entries"]:
            raw = e.get("raw_json") or json.dumps(
                {k: v for k, v in e.items()
                 if k not in ("entry_id", "corrected_by", "corrected_at", "created_at")},
                ensure_ascii=False,
            )
            yr = e.get("event_year")
            if isinstance(yr, str):
                yr = int(yr) if yr.strip().isdigit() else None
            cur = mdb.execute("""
                INSERT INTO source_matrikula_entries
                    (book_id, page_nr, entry_type, event_date, event_year,
                     person_name, person2_name, father_name, mother_name,
                     village, notes, raw_json, corrected_by, corrected_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'human',datetime('now'))
            """, (
                book_id, page_nr,
                e.get("entry_type", ""),
                e.get("event_date", ""),
                yr,
                e.get("person_name", ""),
                e.get("person2_name", ""),
                e.get("father_name", ""),
                e.get("mother_name", ""),
                e.get("village", ""),
                e.get("notes", ""),
                raw,
            ))
            eid = cur.lastrowid
            _index_names(mdb, eid, book_id, page_nr, [
                (e.get("person_name",  ""), "person"),
                (e.get("person2_name", ""), "person2"),
                (e.get("father_name",  ""), "father"),
                (e.get("mother_name",  ""), "mother"),
            ])
            _ner_from_entry(mdb, eid, book_id, yr, e.get("entry_type", ""), raw)
    return jsonify({"ok": True, "count": len(data["entries"])})


@app.route("/search")
def search():
    q         = request.args.get("q", "").strip()
    role_filt = request.args.get("rolle", "").strip()
    if not q:
        return render_template_string(_BASE + _TMPL_SEARCH, q="", code=None,
                                      results=[], role_filt=role_filt)

    mdb   = _main_db()
    q_low = q.lower()

    if _kp:
        code       = _kp(q)
        # Surname-only code (letztes Wort) für NER-Treffer
        last_word  = q.split()[-1]
        code_surn  = _kp(last_word)

        # name_index: klassische Rollen (person/father/mother/…)
        ni_where = "ni.koeln_code = ?"
        ni_args  = [code]
        if role_filt:
            ni_where += " AND ni.name_role = ?"
            ni_args.append(role_filt)
        ni_rows = mdb.execute(f"""
            SELECT ni.entry_id, ni.book_id, ni.page_nr,
                   ni.name_raw, ni.name_role AS rolle, ni.koeln_code,
                   e.entry_type, e.event_date, e.event_year, e.corrected_by,
                   '' AS geburtsname, '' AS ort
            FROM   name_index ni
            JOIN   source_matrikula_entries e ON e.entry_id = ni.entry_id
            WHERE  {ni_where}
        """, ni_args).fetchall()

        # matrikula_ner: Paten, Zeugen, Väter usw.
        ner_where = "(n.koeln_code = ? OR n.koeln_code = ? OR n.name_norm LIKE ?)"
        ner_args  = [code, code_surn, f"%{q_low}%"]
        if role_filt:
            ner_where += " AND n.rolle = ?"
            ner_args.append(role_filt)
        try:
            ner_rows = mdb.execute(f"""
                SELECT n.entry_id, n.book_id,
                       e.page_nr,
                       n.name_raw, n.rolle, n.koeln_code,
                       e.entry_type, e.event_date, e.event_year, e.corrected_by,
                       n.geburtsname, n.ort
                FROM   matrikula_ner n
                JOIN   source_matrikula_entries e ON e.entry_id = n.entry_id
                WHERE  {ner_where}
            """, ner_args).fetchall()
        except Exception:
            ner_rows = []

        # Zusammenführen, Duplikate (selbe entry_id + name_raw) entfernen
        seen: set[tuple] = set()
        results = []
        for r in list(ni_rows) + list(ner_rows):
            key = (r["entry_id"], r["name_raw"].lower(), r["rolle"])
            if key in seen:
                continue
            seen.add(key)
            dist = _lev(q_low, r["name_raw"].lower()) if _lev else 0
            results.append({**dict(r), "dist": dist})
        results.sort(key=lambda x: (x["dist"], x["name_raw"].lower()))
    else:
        code = None
        rows = mdb.execute("""
            SELECT e.entry_id, e.book_id, e.page_nr,
                   e.person_name AS name_raw, 'person' AS rolle,
                   e.entry_type, e.event_date, e.event_year, e.corrected_by,
                   '' AS geburtsname, '' AS ort
            FROM   source_matrikula_entries e
            WHERE  lower(e.person_name) LIKE lower(?)
               OR  lower(e.person2_name) LIKE lower(?)
               OR  lower(e.father_name)  LIKE lower(?)
               OR  lower(e.mother_name)  LIKE lower(?)
            LIMIT  200
        """, (f"%{q}%",) * 4).fetchall()
        results = [{**dict(r), "dist": 0} for r in rows]

    return render_template_string(_BASE + _TMPL_SEARCH, q=q, code=code,
                                  results=results, role_filt=role_filt)


@app.route("/person")
def person_network():
    """Zeigt alle Kirchenbuch-Einträge einer Person (in allen Rollen)."""
    q = request.args.get("q", "").strip()
    if not q:
        return render_template_string(_BASE + _TMPL_PERSON_SEARCH, q="", results_by_rolle={})

    mdb   = _main_db()
    q_low = q.lower()

    if _kp:
        code      = _kp(q)
        code_surn = _kp(q.split()[-1])
        try:
            rows = mdb.execute("""
                SELECT n.ner_id, n.entry_id, n.book_id, n.event_year,
                       n.name_raw, n.rolle, n.ort, n.geburtsname,
                       e.page_nr, e.entry_type, e.event_date,
                       e.person_name, e.person2_name, e.father_name, e.mother_name
                FROM   matrikula_ner n
                JOIN   source_matrikula_entries e ON e.entry_id = n.entry_id
                WHERE  n.koeln_code = ? OR n.koeln_code = ? OR n.name_norm LIKE ?
                ORDER  BY n.event_year, n.rolle
            """, (code, code_surn, f"%{q_low}%")).fetchall()
        except Exception:
            rows = []
    else:
        try:
            rows = mdb.execute("""
                SELECT n.ner_id, n.entry_id, n.book_id, n.event_year,
                       n.name_raw, n.rolle, n.ort, n.geburtsname,
                       e.page_nr, e.entry_type, e.event_date,
                       e.person_name, e.person2_name, e.father_name, e.mother_name
                FROM   matrikula_ner n
                JOIN   source_matrikula_entries e ON e.entry_id = n.entry_id
                WHERE  n.name_norm LIKE ?
                ORDER  BY n.event_year, n.rolle
            """, (f"%{q_low}%",)).fetchall()
        except Exception:
            rows = []

    results_by_rolle: dict[str, list] = {}
    for r in rows:
        dist = (_lev(q_low, r["name_raw"].lower()) if _lev else 0)
        entry = {**dict(r), "dist": dist,
                 "rolle_label": _ROLLE_LABEL.get(r["rolle"], r["rolle"])}
        results_by_rolle.setdefault(r["rolle"], []).append(entry)

    return render_template_string(_BASE + _TMPL_PERSON_SEARCH, q=q,
                                  results_by_rolle=results_by_rolle)


# ── Templates ──────────────────────────────────────────────────────────────────

_BASE = """\
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Matricula Viewer</title>
<style>
:root{
  --bg:#f5f0e8;--card:#fffef8;--border:#c9b99a;
  --accent:#5a3e28;--text:#2a1f14;--muted:#8a7060;
  --done:#3a7d44;--error:#c0392b;--pending:#b07d20;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Georgia,serif;background:var(--bg);color:var(--text);font-size:15px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
h1{font-size:1.25rem;margin-bottom:.7rem}
nav.crumb{padding:.45rem 1rem;background:var(--accent);color:#fff;font-size:.85rem;
          display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
nav.crumb a{color:#f5d9b5}
nav.crumb .sep{opacity:.5}
.wrap{padding:.9rem 1rem}
table.data{width:100%;border-collapse:collapse}
table.data th{background:var(--accent);color:#fff;padding:.35rem .6rem;
              text-align:left;font-weight:normal;font-size:.85rem}
table.data td{padding:.35rem .6rem;border-bottom:1px solid var(--border)}
table.data tr:hover td{background:#ede5d8}
.badge{display:inline-block;padding:.1rem .35rem;border-radius:3px;font-size:.72rem;font-weight:bold}
.b-done{background:#d4edda;color:var(--done)}
.b-err{background:#fde;color:var(--error)}
.b-pend{background:#fef3cd;color:var(--pending)}
.b-human{background:#dde;color:#335}
.muted{color:var(--muted)}
</style>
</head>
<body>
"""

# ── Index ──────────────────────────────────────────────────────────────────────

_TMPL_INDEX = """\
<nav class="crumb">Matricula Viewer
  <span class="spacer" style="flex:1"></span>
  <form action="/search" method="get" style="display:flex;gap:.35rem">
    <input name="q" placeholder="Name suchen …" style="
      border:1px solid #c9a880;border-radius:3px;padding:.15rem .45rem;
      background:rgba(255,255,255,.18);color:#fff;font-family:inherit;font-size:.85rem;width:180px"
      autocomplete="off">
    <button type="submit" style="
      background:rgba(255,255,255,.22);border:1px solid #c9a880;border-radius:3px;
      color:#fff;padding:.15rem .6rem;cursor:pointer;font-family:inherit;font-size:.85rem">
      ⌕
    </button>
  </form>
</nav>
<div class="wrap">
<h1>Pfarreien</h1>
{% if not parishes %}
<p class="muted">Keine Pfarreien — bitte zuerst
  <code>scrape_matricula_osnabrueck.py</code> und
  <code>fetch_matricula_books.py</code> ausführen.</p>
{% else %}
<table class="data">
<thead><tr><th>Pfarrei</th><th>Bücher</th><th>Jahre</th><th>Seiten fertig</th></tr></thead>
<tbody>
{% for p in parishes %}
<tr>
  <td><a href="/parish/{{ p['id'] }}">{{ p['name'] }}</a></td>
  <td>{{ p['n_books'] or 0 }}</td>
  <td>{{ p['y_min'] or '?' }} – {{ p['y_max'] or '?' }}</td>
  <td>{{ p['n_done'] or 0 }}</td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
</div>
</body></html>
"""

# ── Search results ──────────────────────────────────────────────────────────────

_TMPL_SEARCH = """\
<nav class="crumb">
  <a href="/">Pfarreien</a><span class="sep">›</span>
  Suche
  <span class="spacer" style="flex:1"></span>
  <form action="/search" method="get" style="display:flex;gap:.35rem">
    <input name="q" value="{{ q | e }}" placeholder="Name …" style="
      border:1px solid #c9a880;border-radius:3px;padding:.15rem .45rem;
      background:rgba(255,255,255,.18);color:#fff;font-family:inherit;font-size:.85rem;width:180px"
      autocomplete="off">
    <select name="rolle" style="
      border:1px solid #c9a880;border-radius:3px;padding:.15rem .3rem;
      background:rgba(255,255,255,.15);color:#fff;font-family:inherit;font-size:.82rem">
      <option value="" {% if not role_filt %}selected{% endif %}>Alle Rollen</option>
      <option value="kind"             {% if role_filt=='kind'             %}selected{% endif %}>Täufling</option>
      <option value="pate"             {% if role_filt=='pate'             %}selected{% endif %}>Taufpate</option>
      <option value="vater"            {% if role_filt=='vater'            %}selected{% endif %}>Vater</option>
      <option value="mutter"           {% if role_filt=='mutter'           %}selected{% endif %}>Mutter</option>
      <option value="braeutigam"       {% if role_filt=='braeutigam'       %}selected{% endif %}>Bräutigam</option>
      <option value="braut"            {% if role_filt=='braut'            %}selected{% endif %}>Braut</option>
      <option value="braeutigam_vater" {% if role_filt=='braeutigam_vater' %}selected{% endif %}>Vater d. Bräutigams</option>
      <option value="braut_vater"      {% if role_filt=='braut_vater'      %}selected{% endif %}>Vater d. Braut</option>
      <option value="zeuge"            {% if role_filt=='zeuge'            %}selected{% endif %}>Zeuge</option>
      <option value="verstorbener"     {% if role_filt=='verstorbener'     %}selected{% endif %}>Verstorbener</option>
    </select>
    <button type="submit" style="
      background:rgba(255,255,255,.22);border:1px solid #c9a880;border-radius:3px;
      color:#fff;padding:.15rem .6rem;cursor:pointer;font-family:inherit;font-size:.85rem">
      ⌕
    </button>
  </form>
</nav>
<div class="wrap">
{% if q %}
<h1>
  „{{ q | e }}"
  {% if role_filt %}<span class="muted" style="font-size:.9rem"> · Rolle: {{ role_filt }}</span>{% endif %}
  {% if code %}<span class="muted" style="font-size:.85rem"> · Code <code>{{ code }}</code></span>{% endif %}
</h1>
{% if results %}
<p class="muted" style="margin-bottom:.6rem">
  {{ results | length }} Treffer
  — auch als <a href="/person?q={{ q | urlencode }}">Personen-Netzwerk</a>
</p>
<table class="data">
<thead>
  <tr>
    <th>Name</th><th>Rolle</th><th>Typ</th>
    <th>Datum</th><th>Kirchenbuch</th><th>Seite</th>
  </tr>
</thead>
<tbody>
{% for r in results %}
<tr>
  <td>
    <a href="/view/{{ r.book_id }}/{{ r.page_nr }}">{{ r.name_raw }}</a>
    {% if r.get('corrected_by') == 'human' %}<span class="badge b-human">✎</span>{% endif %}
    {% if r.get('geburtsname') %}
      <span class="muted" style="font-size:.75rem">geb. {{ r.geburtsname }}</span>
    {% endif %}
    {% if r.get('dist', 0) > 0 %}
      <span class="muted" style="font-size:.75rem">(Δ{{ r.dist }})</span>
    {% endif %}
  </td>
  <td>
    <span class="badge" style="background:#e8e0d4;color:#5a3e28">
      {{ r.rolle }}
    </span>
  </td>
  <td>{{ r.entry_type }}</td>
  <td>{{ r.event_date or (r.event_year | string if r.event_year else '?') }}</td>
  <td style="font-size:.8rem;font-family:monospace">{{ r.book_id.split('/')[-1] }}</td>
  <td><a href="/view/{{ r.book_id }}/{{ r.page_nr }}">{{ r.page_nr }}</a></td>
</tr>
{% endfor %}
</tbody>
</table>
{% else %}
<p class="muted">Keine Treffer{% if not code %} — Phonetik nicht verfügbar, LIKE-Suche verwendet{% endif %}.</p>
{% endif %}
{% else %}
<p class="muted">Bitte einen Namen eingeben.</p>
{% endif %}
</div>
</body></html>
"""

_TMPL_PERSON_SEARCH = """\
<nav class="crumb">
  <a href="/">Pfarreien</a><span class="sep">›</span>
  Personen-Netzwerk
  <span class="spacer" style="flex:1"></span>
  <form action="/person" method="get" style="display:flex;gap:.35rem">
    <input name="q" value="{{ q | e }}" placeholder="Name …" style="
      border:1px solid #c9a880;border-radius:3px;padding:.15rem .45rem;
      background:rgba(255,255,255,.18);color:#fff;font-family:inherit;font-size:.85rem;width:180px"
      autocomplete="off">
    <button type="submit" style="
      background:rgba(255,255,255,.22);border:1px solid #c9a880;border-radius:3px;
      color:#fff;padding:.15rem .6rem;cursor:pointer;font-family:inherit;font-size:.85rem">
      ⌕
    </button>
  </form>
</nav>
<div class="wrap">
{% if q %}
<h1>Netzwerk: „{{ q | e }}"</h1>
{% if results_by_rolle %}
<p class="muted" style="margin-bottom:.8rem">
  {{ results_by_rolle.values() | sum(start=[]) | list | length }} Einträge in
  {{ results_by_rolle | length }} Rollen
  — <a href="/search?q={{ q | urlencode }}">Normale Suche</a>
</p>
<style>
.rolle-section{margin-bottom:1.2rem}
.rolle-hd{font-size:.95rem;font-weight:bold;color:var(--accent);
          border-bottom:1px solid var(--border);padding-bottom:.25rem;margin-bottom:.4rem}
.rolle-badge{display:inline-block;background:#e8e0d4;color:#5a3e28;
             padding:.1rem .4rem;border-radius:3px;font-size:.78rem;margin-right:.4rem}
</style>
{% for rolle, entries in results_by_rolle.items() %}
<div class="rolle-section">
  <div class="rolle-hd">
    <span class="rolle-badge">{{ rolle }}</span>
    {{ entries[0].get('rolle_label', rolle) }}
    <span class="muted" style="font-weight:normal;font-size:.85rem">
      · {{ entries | length }} Eintrag{% if entries | length != 1 %}&#xE4;ge{% endif %}
    </span>
  </div>
  <table class="data">
  <thead>
    <tr><th>Name</th><th>Typ</th><th>Datum</th><th>Ort</th><th>Kirchenbuch</th><th>Seite</th></tr>
  </thead>
  <tbody>
  {% for e in entries %}
  <tr>
    <td>
      <a href="/view/{{ e.book_id }}/{{ e.page_nr }}">{{ e.name_raw }}</a>
      {% if e.get('geburtsname') %}
        <span class="muted" style="font-size:.75rem">geb. {{ e.geburtsname }}</span>
      {% endif %}
      {% if e.get('dist', 0) > 0 %}
        <span class="muted" style="font-size:.72rem">(Δ{{ e.dist }})</span>
      {% endif %}
    </td>
    <td>{{ e.entry_type }}</td>
    <td>{{ e.event_date or (e.event_year | string if e.event_year else '?') }}</td>
    <td class="muted" style="font-size:.82rem">{{ e.ort or '' }}</td>
    <td style="font-size:.8rem;font-family:monospace">{{ e.book_id.split('/')[-1] }}</td>
    <td><a href="/view/{{ e.book_id }}/{{ e.page_nr }}">{{ e.page_nr }}</a></td>
  </tr>
  {% endfor %}
  </tbody>
  </table>
</div>
{% endfor %}
{% else %}
<p class="muted">Keine Einträge gefunden{% if not results_by_rolle %} — NER-Tabelle noch leer?
  Bitte <code>extract_matrikula_ner.py</code> ausführen.{% endif %}</p>
{% endif %}
{% else %}
<p class="muted">Name eingeben um alle Rollen einer Person anzuzeigen
  (Täufling, Pate, Zeuge, Vater, Mutter, …).</p>
{% endif %}
</div>
</body></html>
"""

# ── Parish ─────────────────────────────────────────────────────────────────────

_TMPL_PARISH = """\
<nav class="crumb">
  <a href="/">Pfarreien</a>
  <span class="sep">›</span>
  {{ parish['name'] }}
</nav>
<div class="wrap">
<h1>{{ parish['name'] }}</h1>
<table class="data">
<thead><tr><th>Signatur</th><th>Typ</th><th>Jahre</th><th>Seiten</th></tr></thead>
<tbody>
{% for b in books %}
<tr>
  <td><a href="/book/{{ b['book_id'] }}">{{ b['book_id'].split('/')[-1] }}</a>
      &nbsp;<span class="muted" style="font-size:.8rem">{{ b['label'] or '' }}</span></td>
  <td>{{ b['book_type'] }}</td>
  <td>{{ b['year_from'] or '?' }} – {{ b['year_to'] or '?' }}</td>
  <td>{{ b['done_pages'] }} / {{ b['total_pages'] }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
</body></html>
"""

# ── Book (page grid) ───────────────────────────────────────────────────────────

_TMPL_BOOK = """\
<nav class="crumb">
  <a href="/">Pfarreien</a><span class="sep">›</span>
  {% if parish %}<a href="/parish/{{ parish['id'] }}">{{ parish['name'] }}</a>
  <span class="sep">›</span>{% endif %}
  {{ book['book_id'].split('/')[-1] }}
</nav>
<div class="wrap">
<h1>{{ book['book_id'].split('/')[-1] }}
  &nbsp;<span class="muted">{{ book['book_type'] }}
  &nbsp;{{ book['year_from'] or '?' }}–{{ book['year_to'] or '?' }}</span>
</h1>
<style>
.pgrid{display:flex;flex-wrap:wrap;gap:5px;margin-top:.7rem}
.pgrid a{
  display:inline-flex;flex-direction:column;align-items:center;justify-content:center;
  width:58px;height:50px;border:1px solid var(--border);border-radius:4px;
  font-size:.78rem;background:var(--card);text-decoration:none;color:var(--text);
  transition:background .12s;line-height:1.2
}
.pgrid a:hover{background:#e5d8c8}
.pgrid a.done{border-color:var(--done);background:#ebf5ee}
.pgrid a.error{border-color:var(--error);background:#fef0ee}
.pgrid a.human{border-color:#668;background:#eeeeff}
.pgrid a .nr{font-size:.88rem;font-weight:bold}
.pgrid a .ct{font-size:.68rem;color:var(--muted)}
</style>
<div class="pgrid">
{% for p in pages %}
  <a href="/view/{{ book['book_id'] }}/{{ p['page_nr'] }}"
     class="{{ 'human' if p['n_corrected'] else p['status'] }}"
     title="Seite {{ p['page_nr'] }} · {{ p['entry_count'] or 0 }} Einträge{% if p['n_corrected'] %} · manuell korrigiert{% endif %}">
    <span class="nr">{{ p['page_nr'] }}</span>
    <span class="ct">{{ p['entry_count'] or '' }}</span>
  </a>
{% else %}
  <p class="muted">Noch keine gescannten Seiten.</p>
{% endfor %}
</div>
</div>
</body></html>
"""

# ── Page viewer ────────────────────────────────────────────────────────────────

_TMPL_PAGE = """\
<style>
html,body{height:100%;overflow:hidden}
.topbar{
  background:var(--accent);color:#fff;padding:.3rem .7rem;
  display:flex;align-items:center;gap:.5rem;font-size:.85rem;
  white-space:nowrap;overflow:hidden;height:38px;flex-shrink:0
}
.topbar a{color:#f5d9b5;flex-shrink:0}
.topbar .sep{opacity:.5;flex-shrink:0}
.topbar .spacer{flex:1}
.nav-btns{display:flex;align-items:center;gap:.35rem;flex-shrink:0}
.nav-btns input[type=number]{
  width:50px;text-align:center;border:1px solid #c9a880;border-radius:3px;
  padding:.1rem .2rem;background:rgba(255,255,255,.15);color:#fff;
  font-family:inherit;font-size:.85rem
}
.nav-btns a{
  background:rgba(255,255,255,.2);padding:.1rem .55rem;border-radius:3px;
  text-decoration:none;color:#f5d9b5
}
.nav-btns a:hover{background:rgba(255,255,255,.35)}
.nav-btns .dim{opacity:.3;padding:.1rem .55rem}

.viewer{
  display:grid;grid-template-columns:1fr 1fr;
  height:calc(100vh - 38px);overflow:hidden
}

/* ── Image panel ── */
.img-panel{
  position:relative;background:#1a1a1a;
  border-right:2px solid var(--border);overflow:hidden
}
.img-scroll{width:100%;height:100%;overflow:auto}
#scanImg{display:block;width:100%;max-width:none;transform-origin:top left}
.zoom-bar{
  position:absolute;bottom:8px;left:50%;transform:translateX(-50%);
  background:rgba(0,0,0,.6);padding:4px 12px;border-radius:20px;
  display:flex;align-items:center;gap:8px
}
.zoom-bar label{color:#ddd;font-size:.78rem}
.zoom-bar input{width:90px;accent-color:#f5d9b5}
.no-img{
  display:flex;align-items:center;justify-content:center;
  height:100%;color:#666;font-style:italic
}

/* ── Entry panel ── */
.ent-panel{overflow-y:auto;background:var(--bg)}
.entry-card{
  background:var(--card);border:1px solid var(--border);
  border-radius:5px;margin:.55rem;padding:.55rem
}
.entry-hd{
  display:flex;justify-content:space-between;align-items:center;
  margin-bottom:.4rem;padding-bottom:.3rem;
  border-bottom:1px solid var(--border);font-size:.85rem
}
.entry-hd .typ{font-weight:bold;font-size:.95rem}
.frow{
  display:grid;grid-template-columns:105px 1fr;
  align-items:center;gap:.25rem;margin:.18rem 0
}
.frow label{font-size:.78rem;color:var(--muted)}
.frow input{
  width:100%;border:1px solid var(--border);border-radius:3px;
  padding:.18rem .35rem;font-size:.83rem;background:#fffef8;font-family:inherit
}
.frow input:focus{outline:none;border-color:var(--accent);background:#fff}
details{margin-top:.35rem}
details summary{font-size:.73rem;color:var(--muted);cursor:pointer;user-select:none}
details textarea{
  width:100%;height:72px;font-size:.73rem;font-family:monospace;
  border:1px solid var(--border);border-radius:3px;padding:.3rem;
  margin-top:.25rem;resize:vertical;background:#f8f4ee
}
.save-bar{
  position:sticky;bottom:0;padding:.45rem .55rem;
  border-top:1px solid var(--border);background:var(--card);
  display:flex;align-items:center;gap:.6rem
}
#saveBtn{
  background:var(--accent);color:#fff;border:none;
  padding:.35rem 1.1rem;border-radius:4px;cursor:pointer;
  font-family:inherit;font-size:.88rem
}
#saveBtn:hover{background:#7a5e40}
#saveBtn:disabled{opacity:.5;cursor:default}
#saveStatus{font-size:.83rem;color:var(--muted)}
.no-ent{padding:1rem;color:var(--muted);font-style:italic}
</style>

<div class="topbar">
  <a href="/">◂</a>
  {% if parish %}
  <a href="/parish/{{ parish['id'] }}" title="{{ parish['id'] }}">{{ parish['name'] }}</a>
  <span class="sep">›</span>
  {% endif %}
  <a href="/book/{{ book_id }}" title="{{ book_id }}">{{ book_id.split('/')[-1] }}</a>
  <span class="sep">›</span>
  <span>Seite {{ page_nr }} / {{ max_page }}</span>
  <span class="spacer"></span>
  <div class="nav-btns">
    {% if page_nr > 1 %}<a href="/view/{{ book_id }}/{{ page_nr - 1 }}">←</a>
    {% else %}<span class="dim">←</span>{% endif %}
    <input type="number" id="jumpPg" value="{{ page_nr }}" min="1" max="{{ max_page }}"
           title="Zu Seite springen">
    {% if page_nr < max_page %}<a href="/view/{{ book_id }}/{{ page_nr + 1 }}">→</a>
    {% else %}<span class="dim">→</span>{% endif %}
  </div>
</div>

<div class="viewer">

  <div class="img-panel">
    {% if has_image %}
    <div class="img-scroll" id="imgScroll">
      <img id="scanImg" src="/img/{{ book_id }}/{{ page_nr }}" alt="Seite {{ page_nr }}">
    </div>
    <div class="zoom-bar">
      <label>Zoom</label>
      <input type="range" id="zoomSlider" min="50" max="400" value="100" step="5">
      <label id="zoomVal" style="min-width:3rem">100 %</label>
    </div>
    {% else %}
    <div class="no-img">Kein Bild archiviert</div>
    {% endif %}
  </div>

  <div class="ent-panel">
    {% if entries %}
    <div id="entryCards">
    {% for e in entries %}
    <div class="entry-card" data-idx="{{ loop.index0 }}">
      <div class="entry-hd">
        <span class="typ">{{ e.get('entry_type', '') }}</span>
        <span>
          {% if e.get('corrected_by') == 'human' %}
          <span class="badge b-human">✎ OCR-Korrektur</span>&nbsp;
          {% endif %}
          {{ e.get('event_date') or '' }}
        </span>
      </div>

      {% set et = e.get('entry_type','') %}
      <div class="frow">
        <label>{{ 'Kind' if et=='Taufe' else 'Bräutigam' if et=='Heirat' else 'Verstorbener' }}</label>
        <input data-field="person_name" value="{{ e.get('person_name','') }}">
      </div>
      {% if et == 'Heirat' %}
      <div class="frow">
        <label>Braut</label>
        <input data-field="person2_name" value="{{ e.get('person2_name','') }}">
      </div>
      {% endif %}
      <div class="frow">
        <label>Datum</label>
        <input data-field="event_date" value="{{ e.get('event_date','') }}">
      </div>
      <div class="frow">
        <label>Jahr</label>
        <input data-field="event_year" value="{{ e.get('event_year') or '' }}">
      </div>
      <div class="frow">
        <label>{{ 'Vater' if et in ('Taufe','Heirat') else 'Eltern' }}</label>
        <input data-field="father_name" value="{{ e.get('father_name','') }}">
      </div>
      {% if et == 'Taufe' %}
      <div class="frow">
        <label>Mutter</label>
        <input data-field="mother_name" value="{{ e.get('mother_name','') }}">
      </div>
      {% endif %}
      <div class="frow">
        <label>Ort</label>
        <input data-field="village" value="{{ e.get('village','') }}">
      </div>
      <div class="frow">
        <label>Notiz</label>
        <input data-field="notes" value="{{ e.get('notes','') }}">
      </div>
      <details>
        <summary>JSON (Claude-Rohtext)</summary>
        <textarea data-field="raw_json">{{ e.get('raw_json','') }}</textarea>
      </details>
    </div>
    {% endfor %}
    </div>
    <div class="save-bar">
      <button id="saveBtn" onclick="saveCorrections()">✓ OCR-Korrektur speichern</button>
      <span id="saveStatus"></span>
      <span style="font-size:.72rem;color:var(--muted);margin-left:auto">
        ✎ Nur Transkription editierbar — Scans sind Quelldaten (read-only)
      </span>
    </div>
    {% else %}
    <div class="no-ent">Keine Einträge — Seite noch nicht transkribiert oder leer.</div>
    {% endif %}

    {% if ner_persons %}
    <div style="margin:.6rem;padding:.5rem .6rem;background:#f0ebe0;
                border:1px solid var(--border);border-radius:5px;font-size:.82rem">
      <div style="font-weight:bold;margin-bottom:.35rem;color:var(--accent)">
        Alle Personen auf dieser Seite (NER)
      </div>
      {% for n in ner_persons %}
      <div style="display:flex;gap:.4rem;padding:.15rem 0;border-bottom:1px solid #e0d8cc">
        <span class="badge" style="background:#e8e0d4;color:#5a3e28;min-width:120px;text-align:center">
          {{ rolle_label.get(n.rolle, n.rolle) }}
        </span>
        <a href="/person?q={{ n.name_raw | urlencode }}" style="color:var(--accent)">
          {{ n.name_raw }}
        </a>
        {% if n.geburtsname %}
          <span class="muted">geb. {{ n.geburtsname }}</span>
        {% endif %}
        {% if n.ort %}
          <span class="muted">· {{ n.ort }}</span>
        {% endif %}
      </div>
      {% endfor %}
    </div>
    {% endif %}
  </div>

</div>

<script>
const BOOK_ID = {{ book_id | tojson }};
const PAGE_NR = {{ page_nr }};
const MAX_PG  = {{ max_page }};

// ── Zoom ─────────────────────────────────────────────────────────────
const img = document.getElementById('scanImg');
const zsl = document.getElementById('zoomSlider');
const zvl = document.getElementById('zoomVal');
if (img && zsl) {
  zsl.addEventListener('input', () => {
    const z = parseInt(zsl.value);
    img.style.width = z + '%';
    zvl.textContent = z + ' %';
  });
  // Double-click resets zoom
  img.addEventListener('dblclick', () => {
    zsl.value = 100;
    img.style.width = '100%';
    zvl.textContent = '100 %';
  });
}

// ── Jump to page ─────────────────────────────────────────────────────
const jumpEl = document.getElementById('jumpPg');
if (jumpEl) {
  jumpEl.addEventListener('change', () => {
    const n = parseInt(jumpEl.value);
    if (n >= 1 && n <= MAX_PG) {
      location.href = '/view/' + BOOK_ID + '/' + n;
    }
  });
}

// ── Keyboard navigation (disabled while editing) ─────────────────────
document.addEventListener('keydown', e => {
  if (['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)) return;
  if (e.key === 'ArrowLeft'  && PAGE_NR > 1)      location.href = '/view/' + BOOK_ID + '/' + (PAGE_NR - 1);
  if (e.key === 'ArrowRight' && PAGE_NR < MAX_PG) location.href = '/view/' + BOOK_ID + '/' + (PAGE_NR + 1);
});

// ── Save corrections ─────────────────────────────────────────────────
function saveCorrections() {
  const cards  = document.querySelectorAll('#entryCards .entry-card');
  const orig   = {{ entries | tojson }};
  const entries = [];

  cards.forEach((card, idx) => {
    const e = Object.assign({}, orig[idx] || {});
    card.querySelectorAll('[data-field]').forEach(el => {
      const f = el.dataset.field;
      const v = el.tagName === 'TEXTAREA' ? el.value : el.value;
      if (f === 'event_year') {
        e[f] = (v && v.trim() !== '') ? parseInt(v) : null;
      } else {
        e[f] = v;
      }
    });
    entries.push(e);
  });

  const btn = document.getElementById('saveBtn');
  const st  = document.getElementById('saveStatus');
  btn.disabled = true;
  st.textContent = 'Speichern …';

  fetch('/correct/' + BOOK_ID + '/' + PAGE_NR, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({entries}),
  })
  .then(r => r.json())
  .then(d => {
    btn.disabled = false;
    if (d.ok) {
      st.textContent = '✓ ' + d.count + ' Einträge gespeichert';
      // Mark all entry headers as human-corrected
      document.querySelectorAll('.entry-hd span:last-child').forEach(span => {
        if (!span.querySelector('.b-human')) {
          const b = document.createElement('span');
          b.className = 'badge b-human';
          b.textContent = '✎ manuell';
          span.prepend(b, ' ');
        }
      });
    } else {
      st.textContent = '⚠ Fehler beim Speichern';
    }
  })
  .catch(err => {
    st.textContent = '⚠ ' + err;
    btn.disabled = false;
  });
}
</script>
</body></html>
"""


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Matricula-Viewer: lokaler Web-Browser für Kirchenbuch-Scans"
    )
    ap.add_argument("--port",        type=int,  default=5000,
                    help="HTTP-Port (default: 5000)")
    ap.add_argument("--host",        default="127.0.0.1",
                    help="Bind-Adresse (default: 127.0.0.1)")
    ap.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE),
                    help=f"Bild-Archiv-Verzeichnis (default: {DEFAULT_ARCHIVE})")
    ap.add_argument("--debug",       action="store_true",
                    help="Flask-Debug-Modus")
    args = ap.parse_args()

    app.config["ARCHIVE_DIR"] = Path(args.archive_dir)

    print(f"Matricula-Viewer  →  http://{args.host}:{args.port}/")
    print(f"Pfarrei-DB : {PARISH_DB}")
    print(f"Einträge-DB: {MAIN_DB_PATH if MAIN_DB_PATH.exists() else FALLBACK_DB}")
    print(f"Bild-Archiv: {app.config['ARCHIVE_DIR']}")
    app.run(host=args.host, port=args.port, debug=args.debug)
