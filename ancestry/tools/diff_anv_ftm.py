#!/usr/bin/env python3
"""
diff_anv_ftm.py — GEDCOM-Diff-Export: Anverwandte → eigenes GEDCOM → FTM

Exportiert als GEDCOM:

  1. Anreicherungen: Personen, die in BEIDEN Quellen vorkommen (via xref),
     aber im eigenen GEDCOM Felder fehlen, die Anverwandte hat
     (Geburtsjahr, Geburtsort, Todesjahr, Todesort, Geschlecht).
     → INDI-ID = eigene GEDCOM-ID → FTM erkennt die Person beim Merge.

  2. Fehlende Verwandte: Personen aus Anverwandte, die per BFS von den
     bestätigten Cousins (xref-Ankerpunkte) aus erreichbar sind:
       • Blutsverwandte (Eltern / Kinder / Geschwister): beliebig tief
       • Direkte Ehepartner der Blutsverwandten: 1 Hop
       • Verwandtschaft der Ehepartner: NICHT exportiert

--test-one: exportiert genau 1 Kandidaten → Testlauf für FTM-Merge-Import
--all-new:  kein BFS-Filter, alle Anverwandte-Personen ohne eigenes Match
--no-new:   nur Anreicherungen (kein Neu-Export)

Voraussetzungen (Reihenfolge):
  1. Eigenes GEDCOM importiert (source='gedcom')
  2. Anverwandte importiert (Webtrees-Crawl-Workflow)
  3. link_duplicates() gelaufen → xref-Einträge vorhanden

Aufruf:
  python diff_anv_ftm.py
  python diff_anv_ftm.py --db ancestry_dna.db -o diff.ged
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


def _strip_src(ged_id: str, source: str) -> str:
    prefix = f"{source}:"
    return ged_id[len(prefix):] if ged_id.startswith(prefix) else ged_id


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
    Cousins (xref-Ankerpunkte) aus erreichbar sind.

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

    # Ankerpunkte: bestätigte Cousins (Anverwandte-Personen, die in xref stehen)
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


# ── Diff ─────────────────────────────────────────────────────────────────────

def _diff_fields(own: dict, anv: dict) -> dict:
    """Felder, die Anverwandte hat und das eigene GEDCOM nicht. Leer = kein Mehrwert."""
    diff = {}
    if anv.get("birth_year") and not own.get("birth_year"):
        diff["birth_year"] = anv["birth_year"]
    if (anv.get("birth_place") or "").strip() and not (own.get("birth_place") or "").strip():
        diff["birth_place"] = anv["birth_place"].strip()
    if anv.get("death_year") and not own.get("death_year"):
        diff["death_year"] = anv["death_year"]
    if (anv.get("death_place") or "").strip() and not (own.get("death_place") or "").strip():
        diff["death_place"] = anv["death_place"].strip()
    if (anv.get("sex") or "").strip() and not (own.get("sex") or "").strip():
        diff["sex"] = anv["sex"].strip()
    return diff


# ── GEDCOM-Ausgabe ────────────────────────────────────────────────────────────

def _write_gedcom(records: list[dict], output_path: Path) -> int:
    today = datetime.now(timezone.utc).strftime("%d %b %Y").upper()
    lines = [
        "0 HEAD",
        "1 SOUR AncestryAnalyzer",
        "2 NAME Ancestry DNA Analyzer — Anverwandte-Diff",
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
    source_own: str = "gedcom",
    include_new: bool = True,
    all_new: bool = False,
    test_one: bool = False,
    progress_cb=None,
) -> dict:
    """GEDCOM-Diff: Anreicherungen + per BFS erreichbare fehlende Verwandte.

    Parameters
    ----------
    source_own:
        Eigene GEDCOM-Quelle als Vergleichspartner (Standard: 'gedcom').
    include_new:
        True (Standard) = fehlende Blutsverwandte per BFS exportieren.
    all_new:
        True = BFS-Filter deaktivieren, alle ungematchten Anverwandte nehmen.
    test_one:
        True = nur 1 BFS-Kandidaten exportieren (Test des FTM-Merge-Imports).
    """
    p = progress_cb or (lambda m, **kw: _log(m))

    _db = db_path or str(_DEFAULT_DB)
    if not Path(_db).exists():
        raise FileNotFoundError(f"DB nicht gefunden: {_db}")

    suffix = "_test1.ged" if test_one else ".ged"
    _out = Path(output_path) if output_path else Path(_db).parent / f"diff_anv_ftm{suffix}"

    p(f"📂 Lese Datenbank: {Path(_db).name}")
    conn = sqlite3.connect(_db)
    conn.row_factory = sqlite3.Row

    try:
        def _load(src: str) -> dict[str, dict]:
            rows = conn.execute(
                "SELECT ged_id, given_name, surname, sex, "
                "birth_year, birth_place, death_year, death_place "
                "FROM gedcom_persons WHERE source=?", (src,)
            ).fetchall()
            return {r["ged_id"]: dict(r) for r in rows}

        anv_persons = _load(source_anv)
        own_persons  = _load(source_own)
        p(f"  {len(anv_persons):,} Anverwandte-Personen, "
          f"{len(own_persons):,} eigene GEDCOM-Personen geladen")

        if not anv_persons:
            raise ValueError(
                f"Keine Personen mit source='{source_anv}'. "
                f"Bitte zuerst Anverwandte importieren (Webtrees-Crawl)."
            )
        if not own_persons:
            raise ValueError(
                f"Keine Personen mit source='{source_own}'. "
                f"Bitte zuerst eigenes GEDCOM importieren."
            )

        # ── BFS: erreichbare Verwandte von bestätigten Cousins ────────────────
        reachable: set[str] = set()
        if include_new and not all_new:
            reachable = _reachable_from_cousins(conn, source_anv)
            p(f"  BFS: {len(reachable):,} Personen von Cousins aus erreichbar")

        # ── Xref: Anreicherungen für gematchte Paare ──────────────────────────
        pairs = conn.execute("""
            SELECT xo.ged_id_other AS own_id,
                   xa.ged_id_other AS anv_id
            FROM   gedcom_person_xref xo
            JOIN   gedcom_person_xref xa ON xa.ged_id_primary = xo.ged_id_primary
            WHERE  xo.source_other = ?
              AND  xa.source_other = ?
              AND  xo.status != 'rejected'
              AND  xa.status != 'rejected'
        """, (source_own, source_anv)).fetchall()

        p(f"  {len(pairs):,} Paare über GEDCOM-Anker verknüpft")

        records:       list[dict] = []
        processed_anv: set[str]  = set()
        enriched = 0

        for pair in pairs:
            own_id = pair["own_id"]
            anv_id = pair["anv_id"]
            processed_anv.add(anv_id)

            own_p = own_persons.get(own_id)
            anv_p = anv_persons.get(anv_id)
            if not own_p or not anv_p:
                continue

            diff = _diff_fields(own_p, anv_p)
            if not diff:
                continue

            raw_id  = _strip_src(own_id, source_own)
            indi_id = raw_id if raw_id.startswith("@") else f"@{raw_id}@"
            records.append({
                "indi_id":    indi_id,
                "given_name": own_p["given_name"],
                "surname":    own_p["surname"],
                "note":       (f"[Anverwandte-Diff] "
                               f"{anv_p['given_name']} {anv_p['surname']}"),
                **diff,
            })
            enriched += 1

        # ── Neue Personen: BFS-erreichbare Verwandte ohne eigenen Eintrag ──────
        new_count = 0
        skipped   = 0

        if include_new:
            new_idx = 0
            for anv_id, anv_p in anv_persons.items():
                if anv_id in processed_anv:
                    continue

                if not all_new and anv_id not in reachable:
                    skipped += 1
                    continue

                new_idx += 1
                records.append({
                    "indi_id":    f"@ANV{new_idx}@",
                    "given_name": anv_p["given_name"],
                    "surname":    anv_p["surname"],
                    "sex":        anv_p.get("sex", ""),
                    "birth_year":  anv_p.get("birth_year"),
                    "birth_place": anv_p.get("birth_place", ""),
                    "death_year":  anv_p.get("death_year"),
                    "death_place": anv_p.get("death_place", ""),
                    "note":       "[Anverwandte] Verwandter — nicht im eigenen GEDCOM",
                })
                new_count += 1

                if test_one:
                    break

            if skipped:
                p(f"  ⚠️  {skipped:,} Personen übersprungen "
                  f"(nicht per BFS von Cousins erreichbar)", tag="warn")

    finally:
        conn.close()

    if not records:
        p("ℹ️  Kein Diff — eigenes GEDCOM und Anverwandte bereits konsistent.", tag="warn")
        return {"enriched": 0, "new": 0, "skipped": skipped,
                "total": 0, "output_path": str(_out)}

    mode = "TEST (1 Person)" if test_one else f"{len(records):,} Einträge"
    p(f"📝 Schreibe {mode} → {_out.name} …")
    total = _write_gedcom(records, _out)

    p(f"✅ {enriched:,} Anreicherungen"
      + (f", {new_count:,} fehlende Verwandte" if new_count else "")
      + (f"  (übersprungen: {skipped})" if skipped else "")
      + f" → {_out}", tag="ok")
    if test_one:
        p("ℹ️  Testlauf: In FTM importieren (Datei → Import → Merge) und "
          "prüfen ob Quellen/Matricula-Links ankommen.", tag="info")

    return {
        "enriched": enriched,
        "new":      new_count,
        "skipped":  skipped,
        "total":    total,
        "output_path": str(_out),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="GEDCOM-Diff: Anverwandte vs. eigenes GEDCOM → Export für FTM")
    ap.add_argument("--db", default=None,
                    help="Pfad zur ancestry_dna.db")
    ap.add_argument("-o", "--output", default=None,
                    help="Ausgabe .ged-Datei (Standard: diff_anv_ftm.ged neben der DB)")
    ap.add_argument("--source-anv", default="anverwandte")
    ap.add_argument("--source-own", default="gedcom",
                    help="Eigene GEDCOM-Quelle als Vergleichspartner (Standard: 'gedcom')")
    ap.add_argument("--no-new", action="store_true",
                    help="Nur Anreicherungen, keine neuen Personen")
    ap.add_argument("--all-new", action="store_true",
                    help="Alle neuen Personen ohne BFS-Filter")
    ap.add_argument("--test-one", action="store_true",
                    help="Nur 1 BFS-Kandidaten exportieren (FTM-Merge testen)")
    args = ap.parse_args()

    result = run(
        db_path=args.db,
        output_path=args.output,
        source_anv=args.source_anv,
        source_own=args.source_own,
        include_new=not args.no_new,
        all_new=args.all_new,
        test_one=args.test_one,
    )
    print(f"\nFertig: {result['enriched']} Anreicherungen, "
          f"{result['new']} fehlende Verwandte "
          f"({result['skipped']} übersprungen) → {result['output_path']}")


if __name__ == "__main__":
    main()
