#!/usr/bin/env python3
"""
diff_anv_ftm.py — GEDCOM-Export: Anverwandte-Cousins für FTM-Import

Exportiert BFS-erreichbare Anverwandte-Personen als GEDCOM:

  • Ausgangspunkt: bestätigte Cousins (xref-Ankerpunkte gegen eigenes GEDCOM)
  • Traversal:
      – Blutsverwandte (Eltern / Kinder / Geschwister): beliebig tief
      – Direkte Ehepartner der Blutsverwandten: 1 Hop
      – Verwandtschaft der Ehepartner: NICHT exportiert
  • Alle verfügbaren Felder (Name, Geschlecht, Geburt, Tod) werden exportiert
  • FTM gleicht beim Import (Datei → Import → Merge) via Name + Datum ab

--test-one: exportiert genau 1 Kandidaten → Testlauf für FTM-Merge-Import
--all-new:  kein BFS-Filter — alle Anverwandte-Personen ohne eigenes Match

Voraussetzungen:
  1. Eigenes GEDCOM importiert (source='gedcom')
  2. Anverwandte importiert (Webtrees-Crawl-Workflow)
  3. link_duplicates() gelaufen → xref-Einträge vorhanden

Aufruf:
  python diff_anv_ftm.py
  python diff_anv_ftm.py --db ancestry_dna.db -o cousins.ged
  python diff_anv_ftm.py --test-one
  python diff_anv_ftm.py --all-new
"""
from __future__ import annotations

import argparse
import json as _json
import sqlite3
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
ANCESTRY_DIR = SCRIPT_DIR.parent
REPO_DIR     = ANCESTRY_DIR.parent

sys.path.insert(0, str(REPO_DIR))

_DEFAULT_DB = ANCESTRY_DIR / "ancestry_dna.db"


def _log(msg: str):
    print(msg, flush=True)


def _fmt_year(year) -> str:
    try:
        return str(int(str(year)[:4]))
    except (TypeError, ValueError):
        return ""


def _jload(raw) -> list:
    try:
        return _json.loads(raw or "[]") or []
    except (ValueError, TypeError):
        return []


# ── BFS: Erreichbare Anverwandte-Personen ────────────────────────────────────

def _reachable_from_cousins(conn: sqlite3.Connection, source_anv: str) -> set[str]:
    """Gibt alle Anverwandte-ged_ids zurück, die per BFS von bestätigten
    Cousins (xref-Ankerpunkte gegen eigenes GEDCOM) aus erreichbar sind.

    Traversal-Regeln:
      • Blut (parents / children / siblings): beliebig tief
      • Direkte Ehepartner von Blutsverwandten: 1 Hop, danach kein
        weiteres Traversal (keine Verwandtschaft der Ehepartner)
    """
    rows = conn.execute(
        "SELECT ged_id, parents_json, children_json, siblings_json, spouses_json "
        "FROM gedcom_persons WHERE source=?", (source_anv,)
    ).fetchall()

    blood_adj:  dict[str, list[str]] = {}
    spouse_adj: dict[str, list[str]] = {}

    for r in rows:
        gid = r["ged_id"]
        blood_adj[gid] = [x for x in
                          _jload(r["parents_json"]) +
                          _jload(r["children_json"]) +
                          _jload(r["siblings_json"]) if x]
        spouse_adj[gid] = [x for x in _jload(r["spouses_json"]) if x]

    # Ankerpunkte: Anverwandte-Personen, die im eigenen GEDCOM bestätigt wurden
    anchor_rows = conn.execute(
        "SELECT ged_id_other FROM gedcom_person_xref "
        "WHERE source_other=? AND status != 'rejected'",
        (source_anv,)
    ).fetchall()
    anchors = {r["ged_id_other"] for r in anchor_rows}

    export_set:    set[str] = set()
    blood_visited: set[str] = set()
    spouse_visited: set[str] = set()
    queue: deque = deque()

    for a in anchors:
        if a in blood_adj or a in spouse_adj:
            blood_visited.add(a)
            export_set.add(a)
            queue.append((a, "blood"))

    while queue:
        gid, state = queue.popleft()
        if state != "blood":
            continue  # Ehepartner → kein weiteres Traversal

        for nb in blood_adj.get(gid, []):
            if nb not in blood_visited:
                blood_visited.add(nb)
                export_set.add(nb)
                queue.append((nb, "blood"))

        for sp in spouse_adj.get(gid, []):
            if sp not in blood_visited and sp not in spouse_visited:
                spouse_visited.add(sp)
                export_set.add(sp)

    return export_set


# ── GEDCOM-Ausgabe ────────────────────────────────────────────────────────────

def _indi_id(ged_id: str, source_anv: str) -> str:
    """ged_id 'anverwandte:X12345' → '@WEBT12345@'"""
    prefix = f"{source_anv}:"
    ext = ged_id[len(prefix):] if ged_id.startswith(prefix) else ged_id
    clean = ext.strip("@").replace(":", "_")
    return f"@WEBT{clean}@"


def _write_gedcom(records: list[dict], output_path: Path) -> int:
    today = datetime.now(timezone.utc).strftime("%d %b %Y").upper()
    lines = [
        "0 HEAD",
        "1 SOUR AncestryAnalyzer",
        "2 NAME Ancestry DNA Analyzer — Anverwandte-Export",
        f"2 DATE {today}",
        "1 CHAR UTF-8",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "",
    ]

    for r in records:
        lines.append(f"0 {r['indi_id']} INDI")
        given = (r.get("given_name") or "").strip()
        surn  = (r.get("surname")    or "").strip()
        if given or surn:
            name_str = f"{given} /{surn}/" if surn else given
            lines.append(f"1 NAME {name_str.strip()}")
            if given: lines.append(f"2 GIVN {given}")
            if surn:  lines.append(f"2 SURN {surn}")
        sex = (r.get("sex") or "").strip()
        if sex in ("M", "F", "U"):
            lines.append(f"1 SEX {sex}")

        birt = []
        if r.get("birth_year"):
            birt.append(f"2 DATE {_fmt_year(r['birth_year'])}")
        if r.get("birth_place"):
            birt.append(f"2 PLAC {r['birth_place']}")
        if birt:
            lines.append("1 BIRT"); lines.extend(birt)

        deat = []
        if r.get("death_year"):
            deat.append(f"2 DATE {_fmt_year(r['death_year'])}")
        if r.get("death_place"):
            deat.append(f"2 PLAC {r['death_place']}")
        if deat:
            lines.append("1 DEAT"); lines.extend(deat)

        note = (r.get("note") or "").strip()
        if note:
            lines.append(f"1 NOTE {note}")

        lines.append("")

    lines.append("0 TRLR")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(records)


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def run(
    db_path: str | None = None,
    output_path: str | None = None,
    source_anv: str = "anverwandte",
    include_new: bool = True,
    all_new: bool = False,
    test_one: bool = False,
    progress_cb=None,
) -> dict:
    """GEDCOM-Export: BFS-erreichbare Anverwandte-Cousins.

    Parameters
    ----------
    include_new:
        True (Standard) = nur BFS-erreichbare Personen exportieren.
    all_new:
        True = alle Anverwandte-Personen ohne eigenes GEDCOM-Match.
    test_one:
        True = nur 1 Person exportieren (Test des FTM-Merge-Imports).
    """
    p = progress_cb or (lambda m, **kw: _log(m))

    _db = db_path or str(_DEFAULT_DB)
    if not Path(_db).exists():
        raise FileNotFoundError(f"DB nicht gefunden: {_db}")

    suffix = "_test1.ged" if test_one else ".ged"
    _out = Path(output_path) if output_path else Path(_db).parent / f"anverwandte_cousins{suffix}"

    p(f"📂 Lese Datenbank: {Path(_db).name}")
    conn = sqlite3.connect(_db)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(
            "SELECT ged_id, given_name, surname, sex, "
            "birth_year, birth_place, death_year, death_place, note "
            "FROM gedcom_persons WHERE source=?", (source_anv,)
        ).fetchall()
        anv_persons = {r["ged_id"]: dict(r) for r in rows}
        p(f"  {len(anv_persons):,} Anverwandte-Personen geladen")

        if not anv_persons:
            raise ValueError(
                f"Keine Personen mit source='{source_anv}'. "
                f"Bitte zuerst Anverwandte importieren (Webtrees-Crawl)."
            )

        # Bereits im eigenen GEDCOM vorhandene Personen
        matched_anv: set[str] = set()
        for r in conn.execute(
            "SELECT ged_id_other FROM gedcom_person_xref "
            "WHERE source_other=? AND status != 'rejected'",
            (source_anv,)
        ):
            matched_anv.add(r["ged_id_other"])

        # BFS: erreichbare Verwandte von bestätigten Cousins
        reachable: set[str] = set()
        if include_new and not all_new:
            reachable = _reachable_from_cousins(conn, source_anv)
            p(f"  BFS: {len(reachable):,} Personen von Cousins aus erreichbar")

    finally:
        conn.close()

    records: list[dict] = []
    skipped = 0

    for ged_id, anv_p in anv_persons.items():
        if not all_new and include_new and ged_id not in reachable:
            skipped += 1
            continue

        records.append({
            "indi_id":    _indi_id(ged_id, source_anv),
            "given_name": anv_p.get("given_name") or "",
            "surname":    anv_p.get("surname") or "",
            "sex":        anv_p.get("sex") or "",
            "birth_year":  anv_p.get("birth_year"),
            "birth_place": anv_p.get("birth_place") or "",
            "death_year":  anv_p.get("death_year"),
            "death_place": anv_p.get("death_place") or "",
            "note":       anv_p.get("note") or "",
        })

        if test_one:
            break

    if skipped:
        p(f"  {skipped:,} Personen übersprungen (außerhalb BFS-Reichweite)", tag="warn")

    if not records:
        p("ℹ️  Keine Personen zum Exportieren gefunden.", tag="warn")
        return {"exported": 0, "skipped": skipped, "output_path": str(_out)}

    mode = "TEST (1 Person)" if test_one else f"{len(records):,} Personen"
    p(f"📝 Schreibe {mode} → {_out.name} …")
    _write_gedcom(records, _out)

    p(f"✅ {len(records):,} Personen exportiert → {_out}", tag="ok")
    if test_one:
        p("ℹ️  Testlauf: In FTM importieren (Datei → Import → Merge) und "
          "prüfen ob FTM via Name+Datum matcht.", tag="info")

    return {
        "exported": len(records),
        "skipped":  skipped,
        "output_path": str(_out),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="GEDCOM-Export: BFS-erreichbare Anverwandte-Cousins für FTM")
    ap.add_argument("--db", default=None,
                    help="Pfad zur ancestry_dna.db")
    ap.add_argument("-o", "--output", default=None,
                    help="Ausgabe .ged-Datei (Standard: anverwandte_cousins.ged)")
    ap.add_argument("--source-anv", default="anverwandte")
    ap.add_argument("--no-new", action="store_true",
                    help="Nur bestätigte Cousins, keine BFS-Verwandten")
    ap.add_argument("--all-new", action="store_true",
                    help="Alle Anverwandte-Personen ohne GEDCOM-Match")
    ap.add_argument("--test-one", action="store_true",
                    help="Nur 1 Person exportieren (FTM-Merge testen)")
    args = ap.parse_args()

    result = run(
        db_path=args.db,
        output_path=args.output,
        source_anv=args.source_anv,
        include_new=not args.no_new,
        all_new=args.all_new,
        test_one=args.test_one,
    )
    print(f"\nFertig: {result['exported']} Personen exportiert "
          f"({result['skipped']} übersprungen) → {result['output_path']}")


if __name__ == "__main__":
    main()
