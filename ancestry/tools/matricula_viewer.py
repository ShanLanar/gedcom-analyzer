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
import os
import sqlite3
import sys
from pathlib import Path

try:
    from flask import (Flask, abort, jsonify, render_template_string,
                       request, send_file)
except ImportError:
    print("Flask nicht installiert:  pip install flask")
    sys.exit(1)

ROOT          = Path(__file__).resolve().parent.parent.parent
PARISH_DB     = ROOT / "ancestry" / "tools" / "matricula_parishes.db"
MAIN_DB_PATH  = ROOT / "ancestry.db"
FALLBACK_DB   = PARISH_DB.parent / "matricula_entries.db"
DEFAULT_ARCHIVE = Path(os.environ.get(
    "MATRICULA_ARCHIVE",
    os.path.expanduser("~/matricula_images"),
))

app = Flask(__name__)


# ── DB ─────────────────────────────────────────────────────────────────────────

def _parish_db() -> sqlite3.Connection:
    if not PARISH_DB.exists():
        abort(503, f"Pfarrei-DB nicht gefunden: {PARISH_DB}")
    db = sqlite3.connect(str(PARISH_DB))
    db.row_factory = sqlite3.Row
    return db


def _main_db() -> sqlite3.Connection:
    path = MAIN_DB_PATH if MAIN_DB_PATH.exists() else FALLBACK_DB
    db = sqlite3.connect(str(path))
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
        SELECT s.page_nr, s.status, s.entry_count, s.image_path,
               COALESCE((SELECT COUNT(*) FROM source_matrikula_entries e
                         WHERE e.book_id=s.book_id AND e.page_nr=s.page_nr
                           AND e.corrected_by='human'), 0) AS n_corrected
        FROM   matricula_page_scans s
        WHERE  s.book_id=?
        ORDER  BY s.page_nr
    """, (book_id,)).fetchall()
    parish_id = "/".join(book_id.split("/")[:-1])
    parish    = pdb.execute(
        "SELECT * FROM parishes WHERE id=?", (parish_id,)
    ).fetchone()
    return render_template_string(
        _BASE + _TMPL_BOOK, book=book, pages=pages, parish=parish
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
        for e in data["entries"]:
            raw = e.get("raw_json") or json.dumps(
                {k: v for k, v in e.items()
                 if k not in ("entry_id", "corrected_by", "corrected_at", "created_at")},
                ensure_ascii=False,
            )
            yr = e.get("event_year")
            if isinstance(yr, str):
                yr = int(yr) if yr.strip().isdigit() else None
            mdb.execute("""
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
    return jsonify({"ok": True, "count": len(data["entries"])})


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
<nav class="crumb">Matricula Viewer</nav>
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
          <span class="badge b-human">✎ manuell</span>&nbsp;
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
      <button id="saveBtn" onclick="saveCorrections()">✓ Korrekturen speichern</button>
      <span id="saveStatus"></span>
    </div>
    {% else %}
    <div class="no-ent">Keine Einträge — Seite noch nicht transkribiert oder leer.</div>
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
