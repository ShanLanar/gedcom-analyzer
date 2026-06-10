#!/usr/bin/env python3
"""
Entity Browser — Unified View für Entity Resolution

Zeigt alle Entities mit ihren zugewiesenen Quellen (DNA-Matches, Baum, Kirchenbuch,
Anverwandte) und ermöglicht das Bestätigen/Ablehnen von Kandidaten.

Start:
    python entity_browser.py            # http://localhost:5001
    python entity_browser.py --port 5002

Voraussetzungen:
    pip install flask
    entity_resolution.py mindestens einmal ausgeführt (--mode candidates oder auto)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

try:
    from flask import Flask, abort, jsonify, redirect, render_template_string, request, url_for
except ImportError:
    print("Flask nicht installiert:  pip install flask")
    sys.exit(1)

ROOT     = Path(__file__).resolve().parent.parent.parent
DB_PATH  = ROOT / "ancestry_dna.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from ancestry.core.entity_resolution import (
        _assign, _get_or_create_entity, _merge_entities, _entity_for_source,
        _ensure_schema,
    )
except ImportError:
    _assign = _get_or_create_entity = _merge_entities = _entity_for_source = _ensure_schema = None  # type: ignore

app = Flask(__name__)


# ── DB ──────────────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    path = Path(app.config.get("DB_PATH", DB_PATH))
    if not path.exists():
        abort(503, f"DB nicht gefunden: {path}")
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    if _ensure_schema:
        _ensure_schema(db)
    return db


# ── Source-Detail ───────────────────────────────────────────────────────────────

_SOURCE_ICONS = {
    "matches":                   ("🧬", "b-dna",    "DNA"),
    "gedmatch_matches":          ("🧬", "b-dna",    "GEDmatch"),
    "source_webtrees":           ("🌳", "b-tree",   "Baum"),
    "source_matrikula_entries":  ("⛪", "b-church", "Kirchenbuch"),
    "source_anverwandte":        ("👤", "b-anv",    "Anverwandte"),
    "persons":                   ("👤", "b-anv",    "Person"),
}

def _source_icon(source_table: str) -> tuple[str, str, str]:
    return _SOURCE_ICONS.get(source_table, ("📄", "b-other", source_table))


def _fetch_source(db: sqlite3.Connection, source_table: str, row_id: str) -> Optional[dict]:
    """Lädt einen Source-Datensatz und gibt ein normalisiertes Dict zurück."""
    try:
        if source_table == "matches":
            r = db.execute(
                "SELECT * FROM matches WHERE match_guid=?", (row_id,)
            ).fetchone()
            if not r:
                return None
            platform = str(r["source"] or "").capitalize()
            return {
                "title":    r["display_name"] or row_id,
                "subtitle": f"{r['shared_cm'] or '?'} cM · {r['predicted_relationship'] or '?'} · {platform}",
                "fields": [
                    ("Plattform",       platform),
                    ("Gemeinsame cM",   r["shared_cm"]),
                    ("Beziehung",       r["predicted_relationship"]),
                    ("Baum",            "Ja" if r["has_tree"] else "Nein"),
                    ("Im Baum verlinkt","Ja" if r["linked_in_tree"] else "Nein"),
                    ("Gemeinsame Ahnen","Ja" if r["has_common_ancestor"] else "Nein"),
                    ("match_guid",      row_id),
                ],
                "link":     None,
                "platform": str(r["source"] or "dna"),
            }

        if source_table == "gedmatch_matches":
            r = db.execute(
                "SELECT * FROM gedmatch_matches WHERE kit_id=? LIMIT 1", (row_id,)
            ).fetchone()
            if not r:
                return None
            return {
                "title":    r["name"] or row_id,
                "subtitle": f"{r['shared_cm'] or '?'} cM · {r['source_platform'] or 'GEDmatch'}",
                "fields": [
                    ("Kit-ID",        row_id),
                    ("Gemeinsame cM", r["shared_cm"]),
                    ("Plattform",     r["source_platform"]),
                    ("Y-Haplotyp",    r["y_haplogroup"]),
                    ("mt-Haplotyp",   r["mt_haplogroup"]),
                ],
                "link":     None,
                "platform": "gedmatch",
            }

        if source_table == "source_webtrees":
            r = db.execute(
                "SELECT * FROM source_webtrees WHERE wt_id=?", (row_id,)
            ).fetchone()
            if not r:
                return None
            name = f"{r['given_name'] or ''} {r['surname'] or ''}".strip() or row_id
            return {
                "title":    name,
                "subtitle": f"* {r['birth_date'] or '?'} {r['birth_place'] or ''}".strip(),
                "fields": [
                    ("Vorname",   r["given_name"]),
                    ("Nachname",  r["surname"]),
                    ("Geschlecht",r["gender"]),
                    ("Geburt",    f"{r['birth_date'] or ''} {r['birth_place'] or ''}".strip()),
                    ("Tod",       f"{r['death_date'] or ''} {r['death_place'] or ''}".strip()),
                    ("wt_id",     row_id),
                ],
                "link":     None,
                "platform": "webtrees",
            }

        if source_table == "source_matrikula_entries":
            r = db.execute(
                "SELECT * FROM source_matrikula_entries WHERE entry_id=?", (row_id,)
            ).fetchone()
            if not r:
                return None
            book_id  = r["book_id"]
            page_nr  = r["page_nr"]
            mat_link = f"http://localhost:{app.config.get('MATRICULA_PORT', 5000)}/view/{book_id}/{page_nr}"
            return {
                "title":    r["person_name"] or row_id,
                "subtitle": f"{r['entry_type']} · {r['event_date'] or r['event_year'] or '?'}",
                "fields": [
                    ("Typ",      r["entry_type"]),
                    ("Datum",    r["event_date"] or r["event_year"]),
                    ("Person",   r["person_name"]),
                    ("Person 2", r["person2_name"]),
                    ("Vater",    r["father_name"]),
                    ("Mutter",   r["mother_name"]),
                    ("Ort",      r["village"]),
                    ("Buch",     book_id),
                    ("Seite",    page_nr),
                ],
                "link":     mat_link,
                "platform": "matricula",
            }

        if source_table == "source_anverwandte":
            r = db.execute(
                "SELECT * FROM source_anverwandte WHERE anv_id=?", (row_id,)
            ).fetchone()
            if not r:
                return None
            return {
                "title":    r["name_raw"] or row_id,
                "subtitle": f"* {r['birth_year'] or '?'} † {r['death_year'] or '?'} · {r['relation'] or ''}",
                "fields": [
                    ("Name",      r["name_raw"]),
                    ("Geburt",    r["birth_year"]),
                    ("Tod",       r["death_year"]),
                    ("Relation",  r["relation"]),
                    ("Verknüpft", r["linked_to"]),
                    ("URL",       r["profile_url"]),
                ],
                "link":     r["profile_url"],
                "platform": "anverwandte",
            }

        if source_table == "persons":
            r = db.execute(
                "SELECT * FROM persons WHERE person_id=?", (row_id,)
            ).fetchone()
            if not r:
                return None
            return {
                "title":    r["canonical_name"] or f"{r['given_name'] or ''} {r['surname'] or ''}".strip() or row_id,
                "subtitle": f"* {r['birth_year_est'] or '?'}",
                "fields": [
                    ("Vorname",     r["given_name"]),
                    ("Nachname",    r["surname"]),
                    ("Geb. Jahr",   r["birth_year_est"]),
                    ("GEDCOM-ID",   r["gedcom_id"]),
                    ("Ancestry-UID",r["ancestry_uid"]),
                    ("MH-ID",       r["mh_member_id"]),
                    ("GEDmatch-Kit",r["gedmatch_kit_id"]),
                ],
                "link":     None,
                "platform": "persons",
            }

    except sqlite3.OperationalError:
        pass
    return {"title": row_id, "subtitle": source_table, "fields": [], "link": None, "platform": "unknown"}


# ── Routes ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    db = _db()
    q = request.args.get("q", "").strip()

    base = """
        SELECT e.entity_id, e.label,
               COUNT(DISTINCT a.assignment_id) AS n_sources,
               GROUP_CONCAT(DISTINCT a.source_table) AS tables
        FROM entities e
        LEFT JOIN entity_assignments a ON a.entity_id=e.entity_id AND a.is_active=1
        WHERE e.merged_into IS NULL
    """
    if q:
        rows = db.execute(
            base + " AND (lower(e.label) LIKE lower(?) ) GROUP BY e.entity_id ORDER BY n_sources DESC LIMIT 200",
            (f"%{q}%",),
        ).fetchall()
    else:
        rows = db.execute(
            base + " GROUP BY e.entity_id ORDER BY n_sources DESC, e.entity_id DESC LIMIT 500"
        ).fetchall()

    # Statistiken
    stats = {}
    for tbl in ("entities", "entity_assignments", "entity_candidates"):
        try:
            stats[tbl] = db.execute(
                f"SELECT COUNT(*) FROM {tbl}" +
                (" WHERE merged_into IS NULL" if tbl == "entities" else
                 " WHERE is_active=1"          if tbl == "entity_assignments" else
                 " WHERE status='pending'")
            ).fetchone()[0]
        except Exception:
            stats[tbl] = "–"

    return render_template_string(_BASE + _TMPL_INDEX, entities=rows, q=q, stats=stats)


@app.route("/entity/<int:eid>")
def entity_detail(eid):
    db = _db()
    entity = db.execute("SELECT * FROM entities WHERE entity_id=?", (eid,)).fetchone()
    if not entity:
        abort(404)

    assignments = db.execute(
        """SELECT * FROM entity_assignments WHERE entity_id=? AND is_active=1
           ORDER BY source_table, assignment_id""",
        (eid,),
    ).fetchall()

    sources = []
    for a in assignments:
        detail = _fetch_source(db, a["source_table"], a["source_row_id"])
        icon, badge_cls, badge_label = _source_icon(a["source_table"])
        sources.append({
            "assignment": dict(a),
            "detail": detail,
            "icon": icon,
            "badge_cls": badge_cls,
            "badge_label": badge_label,
        })

    # Verwandte Kandidaten (noch offen)
    pending = db.execute("""
        SELECT * FROM entity_candidates
        WHERE status='pending'
          AND (source_row_id_a IN (SELECT source_row_id FROM entity_assignments WHERE entity_id=? AND is_active=1)
           OR source_row_id_b IN (SELECT source_row_id FROM entity_assignments WHERE entity_id=? AND is_active=1))
        ORDER BY confidence DESC LIMIT 20
    """, (eid, eid)).fetchall()

    return render_template_string(
        _BASE + _TMPL_ENTITY,
        entity=dict(entity), sources=sources, pending=pending,
    )


@app.route("/entity/<int:eid>/label", methods=["POST"])
def update_label(eid):
    db = _db()
    label = request.get_json().get("label", "")
    with db:
        db.execute("UPDATE entities SET label=? WHERE entity_id=?", (label, eid))
    return jsonify({"ok": True})


@app.route("/candidates")
def candidates():
    db = _db()
    status  = request.args.get("status", "pending")
    src_tbl = request.args.get("src", "")

    where  = ["status=?"]
    params = [status]
    if src_tbl:
        where.append("(source_table_a=? OR source_table_b=?)")
        params += [src_tbl, src_tbl]

    rows = db.execute(
        f"""SELECT * FROM entity_candidates
            WHERE {' AND '.join(where)}
            ORDER BY confidence DESC LIMIT 300""",
        params,
    ).fetchall()

    # Kurz-Infos für jede Zeile ohne volle Detail-Abfragen
    enriched = []
    for r in rows:
        ev = {}
        try:
            ev = json.loads(r["evidence"] or "{}")
        except Exception:
            pass
        enriched.append({"row": dict(r), "ev": ev})

    counts = {}
    for s in ("pending", "confirmed", "rejected"):
        try:
            counts[s] = db.execute(
                "SELECT COUNT(*) FROM entity_candidates WHERE status=?", (s,)
            ).fetchone()[0]
        except Exception:
            counts[s] = 0

    return render_template_string(
        _BASE + _TMPL_CANDIDATES,
        rows=enriched, status=status, src_tbl=src_tbl, counts=counts,
    )


@app.route("/candidates/<int:cid>")
def candidate_review(cid):
    db = _db()
    cand = db.execute(
        "SELECT * FROM entity_candidates WHERE candidate_id=?", (cid,)
    ).fetchone()
    if not cand:
        abort(404)

    src_a = _fetch_source(db, cand["source_table_a"], cand["source_row_id_a"])
    src_b = _fetch_source(db, cand["source_table_b"], cand["source_row_id_b"])

    icon_a, cls_a, lbl_a = _source_icon(cand["source_table_a"])
    icon_b, cls_b, lbl_b = _source_icon(cand["source_table_b"])

    ev = {}
    try:
        ev = json.loads(cand["evidence"] or "{}")
    except Exception:
        pass

    # Prev / Next pending
    nav = db.execute("""
        SELECT MIN(CASE WHEN candidate_id > ? THEN candidate_id END) AS nxt,
               MAX(CASE WHEN candidate_id < ? THEN candidate_id END) AS prv
        FROM entity_candidates WHERE status='pending'
    """, (cid, cid)).fetchone()

    return render_template_string(
        _BASE + _TMPL_REVIEW,
        cand=dict(cand), src_a=src_a, src_b=src_b,
        icon_a=icon_a, cls_a=cls_a, lbl_a=lbl_a,
        icon_b=icon_b, cls_b=cls_b, lbl_b=lbl_b,
        ev=ev,
        prev_id=nav["prv"], next_id=nav["nxt"],
    )


@app.route("/candidates/<int:cid>/decide", methods=["POST"])
def decide_candidate(cid):
    db = _db()
    cand = db.execute(
        "SELECT * FROM entity_candidates WHERE candidate_id=?", (cid,)
    ).fetchone()
    if not cand:
        abort(404)

    action = request.get_json().get("action")  # confirm | reject | skip
    if action not in ("confirm", "reject", "skip"):
        abort(400)

    with db:
        if action == "confirm":
            db.execute(
                "UPDATE entity_candidates SET status='confirmed', reviewed_at=datetime('now') WHERE candidate_id=?",
                (cid,),
            )
            # Entity-Zuweisung durchführen
            if _assign and _get_or_create_entity and _merge_entities and _entity_for_source:
                _do_confirm(
                    db,
                    cand["source_table_a"], cand["source_row_id_a"], cand["person_role_a"],
                    cand["source_table_b"], cand["source_row_id_b"], cand["person_role_b"],
                )
        elif action == "reject":
            db.execute(
                "UPDATE entity_candidates SET status='rejected', reviewed_at=datetime('now') WHERE candidate_id=?",
                (cid,),
            )
        # skip: Status bleibt 'pending'

    # Nächsten pending Kandidaten suchen
    nxt = db.execute(
        "SELECT candidate_id FROM entity_candidates WHERE status='pending' AND candidate_id>? ORDER BY candidate_id LIMIT 1",
        (cid,),
    ).fetchone()
    next_id = nxt["candidate_id"] if nxt else None
    return jsonify({"ok": True, "next_id": next_id})


@app.route("/candidates/bulk-confirm", methods=["POST"])
def bulk_confirm():
    """Bestätigt alle pending Kandidaten über einem Konfidenz-Schwellwert."""
    data      = request.get_json()
    threshold = float(data.get("threshold", 0.90))
    db        = _db()

    rows = db.execute(
        "SELECT * FROM entity_candidates WHERE status='pending' AND confidence >= ?",
        (threshold,),
    ).fetchall()

    confirmed = 0
    with db:
        for cand in rows:
            db.execute(
                "UPDATE entity_candidates SET status='confirmed', reviewed_at=datetime('now') WHERE candidate_id=?",
                (cand["candidate_id"],),
            )
            if _assign and _get_or_create_entity:
                _do_confirm(
                    db,
                    cand["source_table_a"], cand["source_row_id_a"], cand["person_role_a"],
                    cand["source_table_b"], cand["source_row_id_b"], cand["person_role_b"],
                )
            confirmed += 1

    return jsonify({"ok": True, "confirmed": confirmed})


def _do_confirm(db, tbl_a, row_a, role_a, tbl_b, row_b, role_b):
    """Erzeugt entity_assignments für ein bestätigtes Kandidaten-Paar."""
    eid_a = _entity_for_source(db, tbl_a, row_a, role_a)
    eid_b = _entity_for_source(db, tbl_b, row_b, role_b)

    if eid_a and eid_b and eid_a != eid_b:
        _merge_entities(db, eid_a, eid_b, reason=f"confirmed {tbl_a}/{row_a}↔{tbl_b}/{row_b}")
    elif eid_a:
        _assign(db, eid_a, tbl_b, row_b, role_b, confidence=1.0, assigned_by="confirmed")
    elif eid_b:
        _assign(db, eid_b, tbl_a, row_a, role_a, confidence=1.0, assigned_by="confirmed")
    else:
        eid = _get_or_create_entity(db, label=f"{tbl_a}/{row_a}")
        _assign(db, eid, tbl_a, row_a, role_a, confidence=1.0, assigned_by="confirmed")
        _assign(db, eid, tbl_b, row_b, role_b, confidence=1.0, assigned_by="confirmed")


# ── Templates ────────────────────────────────────────────────────────────────────

_BASE = """\
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entity Browser</title>
<style>
:root{
  --bg:#f5f0e8;--card:#fffef8;--border:#c9b99a;
  --accent:#3d5a80;--accent2:#5a3e28;--text:#1a1a2e;--muted:#6c757d;
  --done:#3a7d44;--warn:#b07d20;--danger:#c0392b;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,Georgia,serif;background:var(--bg);color:var(--text);font-size:14px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:1.2rem;margin-bottom:.6rem}
h2{font-size:1rem;color:var(--muted);margin:.8rem 0 .4rem}
nav.crumb{padding:.4rem .8rem;background:var(--accent);color:#fff;font-size:.82rem;
          display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;min-height:36px}
nav.crumb a{color:#c8dff5}
nav.crumb .sep{opacity:.5}
nav.crumb .spacer{flex:1}
.wrap{padding:.8rem 1rem}
table.data{width:100%;border-collapse:collapse}
table.data th{background:var(--accent);color:#fff;padding:.3rem .55rem;
              text-align:left;font-weight:normal;font-size:.8rem}
table.data td{padding:.3rem .55rem;border-bottom:1px solid var(--border);font-size:.82rem}
table.data tr:hover td{background:#ede5d8}
.badge{display:inline-block;padding:.1rem .35rem;border-radius:3px;font-size:.7rem;font-weight:600}
.b-dna{background:#d0e8ff;color:#1a5276}
.b-tree{background:#d4edda;color:#1e6b30}
.b-church{background:#fce5cd;color:#784212}
.b-anv{background:#e8daef;color:#4a235a}
.b-other{background:#eee;color:#555}
.b-conf{background:#d4edda;color:var(--done)}
.b-pend{background:#fef3cd;color:var(--warn)}
.b-rej{background:#fde;color:var(--danger)}
.muted{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--border);border-radius:5px;padding:.7rem;margin-bottom:.55rem}
.card-hd{display:flex;justify-content:space-between;align-items:flex-start;
         margin-bottom:.4rem;padding-bottom:.35rem;border-bottom:1px solid var(--border)}
.card-title{font-weight:600;font-size:.95rem}
.card-sub{font-size:.78rem;color:var(--muted);margin-top:.1rem}
.frow{display:grid;grid-template-columns:120px 1fr;gap:.2rem .4rem;
      font-size:.78rem;margin:.15rem 0}
.frow .lbl{color:var(--muted)}
.btn{display:inline-block;padding:.3rem .8rem;border-radius:4px;border:none;
     cursor:pointer;font-size:.82rem;font-family:inherit}
.btn-confirm{background:#28a745;color:#fff}.btn-confirm:hover{background:#218838}
.btn-reject{background:#dc3545;color:#fff}.btn-reject:hover{background:#c82333}
.btn-skip{background:#6c757d;color:#fff}.btn-skip:hover{background:#5a6268}
.btn-neutral{background:var(--accent);color:#fff}.btn-neutral:hover{opacity:.85}
.conf-bar{height:6px;border-radius:3px;background:#ddd;margin-top:.25rem}
.conf-fill{height:100%;border-radius:3px;background:var(--accent)}
</style>
</head><body>
"""

_TMPL_INDEX = """\
<nav class="crumb">
  Entity Browser
  <span class="sep">›</span>
  <a href="/candidates?status=pending">Kandidaten</a>
  <span class="spacer"></span>
  <form action="/" method="get" style="display:flex;gap:.3rem">
    <input name="q" value="{{ q|e }}" placeholder="Entity suchen …"
      style="border:1px solid #8ab0d0;border-radius:3px;padding:.15rem .4rem;
             background:rgba(255,255,255,.2);color:#fff;font-size:.82rem;width:160px"
      autocomplete="off">
    <button type="submit" style="background:rgba(255,255,255,.2);border:1px solid #8ab0d0;
      border-radius:3px;color:#fff;padding:.15rem .5rem;cursor:pointer">⌕</button>
  </form>
</nav>
<div class="wrap">
<div style="display:flex;gap:1.5rem;margin-bottom:.8rem;font-size:.82rem">
  <span><strong>{{ stats.get('entities','–') }}</strong> Entities</span>
  <span><strong>{{ stats.get('entity_assignments','–') }}</strong> Assignments aktiv</span>
  <span><a href="/candidates?status=pending"><strong>{{ stats.get('entity_candidates','–') }}</strong> Kandidaten offen</a></span>
</div>
<table class="data">
<thead><tr><th>ID</th><th>Label</th><th>Quellen</th><th>Typen</th></tr></thead>
<tbody>
{% for e in entities %}
<tr>
  <td class="muted">{{ e['entity_id'] }}</td>
  <td><a href="/entity/{{ e['entity_id'] }}">{{ e['label'] or '(kein Label)' }}</a></td>
  <td>{{ e['n_sources'] or 0 }}</td>
  <td style="font-size:.75rem">
    {% for t in (e['tables'] or '').split(',') if t %}
    {% set icon, cls, lbl = _source_icon(t) %}
    <span class="badge {{ cls }}">{{ icon }} {{ lbl }}</span>
    {% endfor %}
  </td>
</tr>
{% else %}
<tr><td colspan="4" class="muted" style="text-align:center;padding:.6rem">
  Keine Entities{% if q %} für „{{ q|e }}"{% endif %}.
  Bitte entity_resolution.py ausführen.
</td></tr>
{% endfor %}
</tbody>
</table>
</div>
</body></html>
"""

_TMPL_ENTITY = """\
<nav class="crumb">
  <a href="/">Entities</a><span class="sep">›</span>
  <span id="entityLabel">{{ entity['label'] or '(kein Label)' }}</span>
  <span class="spacer"></span>
  <a href="/candidates?status=pending" style="font-size:.78rem;color:#c8dff5">
    Kandidaten</a>
</nav>
<div class="wrap">
<div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.7rem">
  <h1 style="margin:0">
    <span id="lbl">{{ entity['label'] or '(kein Label)' }}</span>
  </h1>
  <button class="btn btn-neutral" style="font-size:.75rem;padding:.2rem .6rem"
          onclick="editLabel()">✏ Label</button>
  <span class="muted" style="font-size:.78rem">ID {{ entity['entity_id'] }}</span>
</div>

{% if sources %}
<h2>Zugewiesene Quellen ({{ sources|length }})</h2>
{% for s in sources %}
<div class="card">
  <div class="card-hd">
    <div>
      <div class="card-title">
        <span class="badge {{ s.badge_cls }}">{{ s.icon }} {{ s.badge_label }}</span>
        &nbsp;{{ s.detail.title if s.detail else s.assignment.source_row_id }}
      </div>
      {% if s.detail %}<div class="card-sub">{{ s.detail.subtitle }}</div>{% endif %}
    </div>
    <div style="font-size:.72rem;color:var(--muted);text-align:right">
      conf {{ '%.2f'|format(s.assignment.confidence) }}<br>
      {{ s.assignment.assigned_by }}
    </div>
  </div>
  {% if s.detail and s.detail.fields %}
  <div style="columns:2;gap:1rem">
    {% for lbl, val in s.detail.fields if val %}
    <div class="frow"><span class="lbl">{{ lbl }}</span><span>{{ val }}</span></div>
    {% endfor %}
  </div>
  {% endif %}
  {% if s.detail and s.detail.link %}
  <div style="margin-top:.4rem">
    <a href="{{ s.detail.link }}" target="_blank" style="font-size:.75rem">
      → Matricula-Viewer öffnen
    </a>
  </div>
  {% endif %}
</div>
{% endfor %}
{% else %}
<p class="muted">Noch keine Quellen zugewiesen.</p>
{% endif %}

{% if pending %}
<h2>Offene Kandidaten die diese Entity betreffen ({{ pending|length }})</h2>
{% for c in pending %}
<div style="display:flex;align-items:center;gap:.6rem;padding:.3rem 0;
            border-bottom:1px solid var(--border);font-size:.82rem">
  <span class="badge b-pend">{{ '%.0f'|format(c['confidence']*100) }} %</span>
  <a href="/candidates/{{ c['candidate_id'] }}">
    {{ c['source_table_a'] }}/{{ c['source_row_id_a'] }}
    &nbsp;↔&nbsp;
    {{ c['source_table_b'] }}/{{ c['source_row_id_b'] }}
  </a>
</div>
{% endfor %}
{% endif %}
</div>

<script>
function editLabel() {
  const cur = document.getElementById('lbl').textContent.trim();
  const neu = prompt('Neues Label:', cur === '(kein Label)' ? '' : cur);
  if (neu === null) return;
  fetch('/entity/{{ entity['entity_id'] }}/label', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({label: neu})
  }).then(() => {
    document.getElementById('lbl').textContent = neu || '(kein Label)';
    document.getElementById('entityLabel').textContent = neu || '(kein Label)';
  });
}
</script>
</body></html>
"""

_TMPL_CANDIDATES = """\
<nav class="crumb">
  <a href="/">Entities</a><span class="sep">›</span>Kandidaten
  <span class="spacer"></span>
  <span style="font-size:.78rem">
    <a href="?status=pending" style="color:{{ '#fff' if status=='pending' else '#c8dff5' }}">
      Offen ({{ counts.get('pending',0) }})</a> ·
    <a href="?status=confirmed" style="color:{{ '#fff' if status=='confirmed' else '#c8dff5' }}">
      Bestätigt ({{ counts.get('confirmed',0) }})</a> ·
    <a href="?status=rejected" style="color:{{ '#fff' if status=='rejected' else '#c8dff5' }}">
      Abgelehnt ({{ counts.get('rejected',0) }})</a>
  </span>
</nav>
<div class="wrap">
{% if status == 'pending' and rows %}
<div style="display:flex;align-items:center;gap:.8rem;margin-bottom:.7rem">
  <span style="font-size:.82rem">Automatisch bestätigen ab:</span>
  <input type="range" id="threshSlider" min="70" max="99" value="90" step="1"
         style="width:100px" oninput="document.getElementById('threshVal').textContent=this.value+'%'">
  <span id="threshVal" style="font-size:.82rem;min-width:3rem">90%</span>
  <button class="btn btn-confirm" onclick="bulkConfirm()">Alle ≥ Schwellwert bestätigen</button>
  <span id="bulkStatus" style="font-size:.78rem;color:var(--muted)"></span>
</div>
{% endif %}
<table class="data">
<thead><tr>
  <th>Konfidenz</th><th>Quelle A</th><th>Quelle B</th><th>Hinweis</th>
  {% if status=='pending' %}<th>Aktion</th>{% endif %}
</tr></thead>
<tbody>
{% for item in rows %}
{% set r = item.row %}{% set ev = item.ev %}
<tr>
  <td style="white-space:nowrap">
    {{ '%.0f'|format(r['confidence']*100) }} %
    <div class="conf-bar"><div class="conf-fill" style="width:{{ (r['confidence']*100)|int }}%"></div></div>
  </td>
  <td style="font-size:.78rem">
    {% set icon, cls, lbl = _source_icon(r['source_table_a']) %}
    <span class="badge {{ cls }}">{{ icon }}</span>
    {{ r['source_table_a'].replace('source_','') }}/{{ r['source_row_id_a'] }}
    <span class="muted">({{ r['person_role_a'] }})</span>
  </td>
  <td style="font-size:.78rem">
    {% set icon, cls, lbl = _source_icon(r['source_table_b']) %}
    <span class="badge {{ cls }}">{{ icon }}</span>
    {{ r['source_table_b'].replace('source_','') }}/{{ r['source_row_id_b'] }}
    <span class="muted">({{ r['person_role_b'] }})</span>
  </td>
  <td style="font-size:.75rem;color:var(--muted)">
    {% if ev.get('koeln_code') %}Code {{ ev.koeln_code }}{% endif %}
    {% if ev.get('levenshtein') is not none %} Δ{{ ev.levenshtein }}{% endif %}
    {% if ev.get('year_diff') is not none %} {{ ev.year_diff }}J{% endif %}
  </td>
  {% if status=='pending' %}
  <td><a class="btn btn-neutral" href="/candidates/{{ r['candidate_id'] }}"
         style="font-size:.75rem;padding:.2rem .5rem">Prüfen →</a></td>
  {% endif %}
</tr>
{% else %}
<tr><td colspan="5" class="muted" style="text-align:center;padding:.6rem">
  Keine Kandidaten mit Status „{{ status }}".
</td></tr>
{% endfor %}
</tbody>
</table>
</div>
<script>
function bulkConfirm() {
  const t = parseInt(document.getElementById('threshSlider').value) / 100;
  const st = document.getElementById('bulkStatus');
  st.textContent = 'Läuft …';
  fetch('/candidates/bulk-confirm', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({threshold: t})
  }).then(r=>r.json()).then(d=>{
    st.textContent = '✓ ' + d.confirmed + ' bestätigt';
    setTimeout(()=>location.reload(), 800);
  });
}
</script>
</body></html>
"""

_TMPL_REVIEW = """\
<style>
html,body{height:100%;overflow:hidden}
.topbar{background:var(--accent);color:#fff;padding:.35rem .8rem;height:38px;
        display:flex;align-items:center;gap:.6rem;font-size:.82rem}
.topbar a{color:#c8dff5}
.topbar .spacer{flex:1}
.review-grid{display:grid;grid-template-columns:1fr 1fr;
             height:calc(100vh - 38px - 56px);gap:0}
.src-panel{overflow-y:auto;padding:.7rem;background:var(--bg);border-right:1px solid var(--border)}
.action-bar{height:56px;background:var(--card);border-top:2px solid var(--border);
            display:flex;align-items:center;justify-content:center;gap:1rem;padding:0 1rem}
.evidence-bar{background:#e8f0fe;border-bottom:1px solid var(--border);
              padding:.3rem .8rem;font-size:.78rem;color:#1a5276;
              grid-column:1/-1}
</style>

<div class="topbar">
  <a href="/">Entities</a><span style="opacity:.5">›</span>
  <a href="/candidates?status=pending">Kandidaten</a><span style="opacity:.5">›</span>
  Kandidat #{{ cand.candidate_id }}
  <span class="spacer"></span>
  {% if prev_id %}<a href="/candidates/{{ prev_id }}">← Vorher</a>{% endif %}
  {% if next_id %}<a href="/candidates/{{ next_id }}">Nächster →</a>{% endif %}
</div>

<div style="display:grid;grid-template-rows:auto 1fr auto;height:calc(100vh - 38px)">

  <div style="background:#e8f0fe;border-bottom:1px solid var(--border);
              padding:.35rem .8rem;font-size:.78rem;color:#1a3a6b">
    <strong>Konfidenz: {{ '%.0f'|format(cand['confidence']*100) }} %</strong>
    &nbsp;·&nbsp;
    {% if ev.get('type') %}{{ ev.type }}{% endif %}
    {% if ev.get('koeln_code') %}&nbsp;·&nbsp;Kölner Code <code>{{ ev.koeln_code }}</code>{% endif %}
    {% if ev.get('levenshtein') is not none %}&nbsp;·&nbsp;Levenshtein Δ{{ ev.levenshtein }}{% endif %}
    {% if ev.get('year_diff') is not none %}&nbsp;·&nbsp;Jahr-Δ {{ ev.year_diff }} ({{ ev.get('year_a','?') }} / {{ ev.get('year_b','?') }}){% endif %}
  </div>

  <div class="review-grid">

    <div class="src-panel">
      <div class="card-hd" style="margin-bottom:.5rem">
        <div>
          <span class="badge {{ cls_a }}">{{ icon_a }} {{ lbl_a }}</span>
          <span style="font-size:.75rem;color:var(--muted);margin-left:.4rem">
            {{ cand['source_table_a'] }} / {{ cand['source_row_id_a'] }}
            ({{ cand['person_role_a'] }})
          </span>
        </div>
      </div>
      {% if src_a %}
      <div style="font-weight:600;font-size:1rem;margin-bottom:.25rem">{{ src_a.title }}</div>
      <div style="color:var(--muted);font-size:.8rem;margin-bottom:.5rem">{{ src_a.subtitle }}</div>
      {% for lbl, val in src_a.fields if val %}
      <div class="frow"><span class="lbl">{{ lbl }}</span><span>{{ val }}</span></div>
      {% endfor %}
      {% if src_a.link %}
      <div style="margin-top:.5rem">
        <a href="{{ src_a.link }}" target="_blank" class="btn btn-neutral"
           style="font-size:.75rem;padding:.2rem .6rem">→ Viewer</a>
      </div>
      {% endif %}
      {% else %}
      <p class="muted">Kein Detail verfügbar.</p>
      {% endif %}
    </div>

    <div class="src-panel" style="border-right:none">
      <div class="card-hd" style="margin-bottom:.5rem">
        <div>
          <span class="badge {{ cls_b }}">{{ icon_b }} {{ lbl_b }}</span>
          <span style="font-size:.75rem;color:var(--muted);margin-left:.4rem">
            {{ cand['source_table_b'] }} / {{ cand['source_row_id_b'] }}
            ({{ cand['person_role_b'] }})
          </span>
        </div>
      </div>
      {% if src_b %}
      <div style="font-weight:600;font-size:1rem;margin-bottom:.25rem">{{ src_b.title }}</div>
      <div style="color:var(--muted);font-size:.8rem;margin-bottom:.5rem">{{ src_b.subtitle }}</div>
      {% for lbl, val in src_b.fields if val %}
      <div class="frow"><span class="lbl">{{ lbl }}</span><span>{{ val }}</span></div>
      {% endfor %}
      {% if src_b.link %}
      <div style="margin-top:.5rem">
        <a href="{{ src_b.link }}" target="_blank" class="btn btn-neutral"
           style="font-size:.75rem;padding:.2rem .6rem">→ Viewer</a>
      </div>
      {% endif %}
      {% else %}
      <p class="muted">Kein Detail verfügbar.</p>
      {% endif %}
    </div>

  </div>

  <div class="action-bar">
    <button class="btn btn-confirm" onclick="decide('confirm')">✓ Gleiche Person</button>
    <button class="btn btn-reject"  onclick="decide('reject')">✗ Nicht gleich</button>
    <button class="btn btn-skip"    onclick="decide('skip')">Überspringen</button>
    <span id="actionStatus" style="font-size:.8rem;color:var(--muted)"></span>
  </div>

</div>

<script>
const NEXT_ID = {{ next_id | tojson }};
function decide(action) {
  document.getElementById('actionStatus').textContent = '…';
  fetch('/candidates/{{ cand.candidate_id }}/decide', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action})
  }).then(r=>r.json()).then(d=>{
    if (action === 'skip') {
      if (NEXT_ID) location.href = '/candidates/' + NEXT_ID;
      else location.href = '/candidates';
      return;
    }
    document.getElementById('actionStatus').textContent =
      action === 'confirm' ? '✓ Bestätigt' : '✗ Abgelehnt';
    setTimeout(() => {
      if (d.next_id) location.href = '/candidates/' + d.next_id;
      else location.href = '/candidates';
    }, 600);
  });
}
document.addEventListener('keydown', e => {
  if (['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
  if (e.key === 'y' || e.key === 'j') decide('confirm');
  if (e.key === 'n')                   decide('reject');
  if (e.key === ' ')                 { e.preventDefault(); decide('skip'); }
});
</script>
</body></html>
"""

# Jinja2-Kontext: _source_icon als globale Funktion verfügbar machen
@app.context_processor
def _inject_helpers():
    return {"_source_icon": _source_icon}


# ── CLI ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Entity Browser — Unified View für Entity Resolution")
    ap.add_argument("--port",            type=int, default=5001)
    ap.add_argument("--host",            default="127.0.0.1")
    ap.add_argument("--db",              default=str(DB_PATH))
    ap.add_argument("--matricula-port",  type=int, default=5000,
                    help="Port des Matricula-Viewers für direkte Links (default: 5000)")
    ap.add_argument("--debug",           action="store_true")
    args = ap.parse_args()

    app.config["DB_PATH"]        = args.db
    app.config["MATRICULA_PORT"] = args.matricula_port

    print(f"Entity Browser  →  http://{args.host}:{args.port}/")
    print(f"DB: {args.db}")
    app.run(host=args.host, port=args.port, debug=args.debug)
