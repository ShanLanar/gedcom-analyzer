#!/usr/bin/env python3
"""
diff_anv_ftm.py — GEDCOM-Diff-Export: Anverwandte → FTM

Vergleicht gedcom_persons (source='anverwandte') mit gedcom_persons
(source='ftm') und exportiert nur die Felder, die in Anverwandte vorhanden
sind, im FTM aber fehlen. Das resultierende GEDCOM importierst du in
Family Tree Maker (Datei → Import → Merge) — FTM erkennt die Personen
anhand der INDI-IDs und merged die Extrafelder ohne Duplikate.

Voraussetzungen (Reihenfolge):
  1. FTM-Brücke:        python import_ftm_bridge.py mein_baum.ftm
  2. Anverwandte-Import: Webtrees-Crawl-Workflow (Werkzeuge-Tab)
  → Beide legen Querbezüge über den eigenen GEDCOM an (gedcom_person_xref)

Aufruf:
  python diff_anv_ftm.py
  python diff_anv_ftm.py --db ancestry_dna.db -o diff.ged
  python diff_anv_ftm.py --include-new     # auch neue Personen exportieren
  python diff_anv_ftm.py --source-anv anverwandte --source-ftm ftm
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
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
    """'ftm:@I42@' → '@I42@'"""
    prefix = f"{source}:"
    return ged_id[len(prefix):] if ged_id.startswith(prefix) else ged_id


def _fmt_year(year) -> str:
    try:
        return str(int(str(year)[:4]))
    except (TypeError, ValueError):
        return ""


def _diff_fields(ftm: dict, anv: dict) -> dict:
    """Gibt Felder zurück, die Anverwandte hat und FTM nicht hat.
    Leeres dict = kein Diff, Person nicht exportieren."""
    diff = {}
    if anv.get("birth_year") and not ftm.get("birth_year"):
        diff["birth_year"] = anv["birth_year"]
    if (anv.get("birth_place") or "").strip() and not (ftm.get("birth_place") or "").strip():
        diff["birth_place"] = anv["birth_place"].strip()
    if anv.get("death_year") and not ftm.get("death_year"):
        diff["death_year"] = anv["death_year"]
    if (anv.get("death_place") or "").strip() and not (ftm.get("death_place") or "").strip():
        diff["death_place"] = anv["death_place"].strip()
    if (anv.get("sex") or "").strip() and not (ftm.get("sex") or "").strip():
        diff["sex"] = anv["sex"].strip()
    return diff


def _write_gedcom(records: list[dict], output_path: Path) -> int:
    """Schreibt GEDCOM-Datei; gibt Anzahl exportierter INDIs zurück."""
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
            lines.append("1 BIRT")
            lines.extend(birt)

        deat = []
        if r.get("death_year"):
            deat.append(f"2 DATE {_fmt_year(r['death_year'])}")
        if r.get("death_place"):
            deat.append(f"2 PLAC {r['death_place']}")
        if deat:
            lines.append("1 DEAT")
            lines.extend(deat)

        note = (r.get("note") or "").strip()
        if note:
            lines.append(f"1 NOTE {note}")

        lines.append("")

    lines.append("0 TRLR")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(records)


def run(
    db_path: str | None = None,
    output_path: str | None = None,
    source_anv: str = "anverwandte",
    source_ftm: str = "ftm",
    include_new: bool = False,
    progress_cb=None,
) -> dict:
    """Erstellt GEDCOM-Diff: Felder aus source_anv, die source_ftm fehlen.

    Parameters
    ----------
    db_path:
        Pfad zur ancestry_dna.db (None = Standardpfad).
    output_path:
        Ausgabe .ged-Datei (None = diff_anv_ftm.ged neben der DB).
    source_anv:
        Quelle der Anverwandte-Personen (Standard: 'anverwandte').
    source_ftm:
        Quelle der FTM-Personen (Standard: 'ftm').
    include_new:
        True = auch Personen exportieren, die nur in Anverwandte vorkommen.
    progress_cb:
        Optionaler Callback ``(msg: str, **kw) -> None``.

    Returns
    -------
    dict mit 'enriched', 'new', 'total', 'output_path'
    """
    p = progress_cb or (lambda m, **kw: _log(m))

    _db = db_path or str(_DEFAULT_DB)
    if not Path(_db).exists():
        raise FileNotFoundError(f"DB nicht gefunden: {_db}")

    _out = Path(output_path) if output_path else Path(_db).parent / "diff_anv_ftm.ged"

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
        ftm_persons = _load(source_ftm)
        p(f"  {len(anv_persons):,} Anverwandte-Personen, "
          f"{len(ftm_persons):,} FTM-Personen geladen")

        if not anv_persons:
            raise ValueError(
                f"Keine Personen mit source='{source_anv}' in der DB. "
                f"Bitte zuerst Anverwandte importieren (Webtrees-Crawl)."
            )
        if not ftm_persons:
            raise ValueError(
                f"Keine Personen mit source='{source_ftm}' in der DB. "
                f"Bitte zuerst FTM-Brücke ausführen."
            )

        # ── Paare über gemeinsamen GEDCOM-Anker ───────────────────────────────
        # xf: FTM ↔ GEDCOM;  xa: Anverwandte ↔ GEDCOM (gleiche ged_id_primary)
        pairs = conn.execute("""
            SELECT xf.ged_id_other AS ftm_id,
                   xa.ged_id_other AS anv_id
            FROM   gedcom_person_xref xf
            JOIN   gedcom_person_xref xa ON xa.ged_id_primary = xf.ged_id_primary
            WHERE  xf.source_other = ?
              AND  xa.source_other = ?
              AND  xf.status != 'rejected'
              AND  xa.status != 'rejected'
        """, (source_ftm, source_anv)).fetchall()

        p(f"  {len(pairs):,} Paare über GEDCOM-Anker verknüpft")

        records: list[dict] = []
        processed_anv: set[str] = set()
        enriched = 0

        for pair in pairs:
            ftm_id = pair["ftm_id"]
            anv_id = pair["anv_id"]
            processed_anv.add(anv_id)

            ftm_p = ftm_persons.get(ftm_id)
            anv_p = anv_persons.get(anv_id)
            if not ftm_p or not anv_p:
                continue

            diff = _diff_fields(ftm_p, anv_p)
            if not diff:
                continue

            raw_id = _strip_src(ftm_id, source_ftm)
            indi_id = raw_id if raw_id.startswith("@") else f"@{raw_id}@"

            records.append({
                "indi_id":    indi_id,
                "given_name": ftm_p["given_name"],
                "surname":    ftm_p["surname"],
                "note":       (f"[Anverwandte-Diff] "
                               f"{anv_p['given_name']} {anv_p['surname']}"),
                **diff,
            })
            enriched += 1

        # ── Neue Personen (nur in Anverwandte, optional) ──────────────────────
        new_count = 0
        if include_new:
            new_idx = 0
            for anv_id, anv_p in anv_persons.items():
                if anv_id in processed_anv:
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
                    "note":       "[Anverwandte] Neue Person — nicht in FTM",
                })
                new_count += 1

    finally:
        conn.close()

    if not records:
        p("ℹ️  Kein Diff gefunden — FTM und Anverwandte sind bereits konsistent.",
          tag="warn")
        return {"enriched": 0, "new": 0, "total": 0, "output_path": str(_out)}

    p(f"📝 Schreibe {len(records):,} GEDCOM-Einträge → {_out.name} …")
    total = _write_gedcom(records, _out)
    p(f"✅ {enriched:,} Anreicherungen"
      + (f", {new_count:,} neue Personen" if include_new else "")
      + f" → {_out}", tag="ok")

    return {
        "enriched": enriched,
        "new":      new_count,
        "total":    total,
        "output_path": str(_out),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="GEDCOM-Diff-Export: Anverwandte-Extrafelder für FTM-Merge-Import")
    ap.add_argument("--db", default=None,
                    help="Pfad zur ancestry_dna.db (Standard: ancestry/ancestry_dna.db)")
    ap.add_argument("-o", "--output", default=None,
                    help="Ausgabe .ged-Datei (Standard: diff_anv_ftm.ged neben der DB)")
    ap.add_argument("--source-anv", default="anverwandte",
                    help="Quellname Anverwandte (Standard: 'anverwandte')")
    ap.add_argument("--source-ftm", default="ftm",
                    help="Quellname FTM (Standard: 'ftm')")
    ap.add_argument("--include-new", action="store_true",
                    help="Neue Personen (nur in Anverwandte) mit exportieren")
    args = ap.parse_args()

    result = run(
        db_path=args.db,
        output_path=args.output,
        source_anv=args.source_anv,
        source_ftm=args.source_ftm,
        include_new=args.include_new,
    )
    print(f"\nFertig: {result['enriched']} Anreicherungen, "
          f"{result['new']} neue Personen → {result['output_path']}")


if __name__ == "__main__":
    main()
