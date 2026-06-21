#!/usr/bin/env python3
"""
import_ftm_bridge.py — FTM/GEDCOM-Brücke → gedcom_persons

[DE] Importiert Family Tree Maker- oder GEDCOM-Daten in gedcom_persons.
Unterstützte Eingaben:
  • .ftm  — FTM 2014–2017 (SQLite-Format); direkt lesbar.
  • .ged / .gedcom — GEDCOM-Export aus FTM 2019/2024 (MacKiev), Webtrees,
                     Gramps oder einem anderen Programm.

Hinweis FTM 2024 (MacKiev): Die .ftm-Datei ist verschlüsselt/komprimiert und
KEIN SQLite mehr. Bitte in FTM exportieren: Datei → Exportieren → GEDCOM,
dann diese .ged-Datei als Argument übergeben.

Aufruf:
  python import_ftm_bridge.py mein_baum.ged
  python import_ftm_bridge.py mein_baum.ftm  --source anverwandte
  python import_ftm_bridge.py mein_baum.ged  --no-link    # nur importieren
  python import_ftm_bridge.py mein_baum.ged  --dry-run    # nur Statistik

----

[EN] Imports Family Tree Maker or GEDCOM data into the gedcom_persons table.
Supported inputs:
  • .ftm  — FTM 2014–2017 (SQLite format); read directly.
  • .ged / .gedcom — GEDCOM export from FTM 2019/2024 (MacKiev), Webtrees,
                     Gramps, or any other genealogy program.

Note for FTM 2024 (MacKiev): The .ftm file is encrypted/compressed and is
NO LONGER plain SQLite. Please export from FTM: File → Export → GEDCOM,
then pass the resulting .ged file as the argument.

Usage:
  python import_ftm_bridge.py my_tree.ged
  python import_ftm_bridge.py my_tree.ftm  --source relatives
  python import_ftm_bridge.py my_tree.ged  --no-link    # import only, no links
  python import_ftm_bridge.py my_tree.ged  --dry-run    # statistics only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
ANCESTRY_DIR = SCRIPT_DIR.parent
REPO_DIR     = ANCESTRY_DIR.parent

# tasks/ liegt im Repo-Root
sys.path.insert(0, str(REPO_DIR))


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _log(msg: str):
    print(msg, flush=True)


def _individuals_to_person_list(individuals: dict, families: dict,
                                source: str) -> list[dict]:
    """Konvertiert das (individuals, families)-Format von load_ftm / load_gedcom
    in die von import_external_persons() erwartete Listenstruktur.

    Jede Person erhält:
      ext_id        – die originale GEDCOM/FTM-ID (z. B. 'I0042')
      given_name    – Vorname(n)
      surname       – Geburtsname / Nachname
      sex           – 'M' | 'F' | ''
      birth_year    – int oder None
      birth_place   – Ortsname als String
      death_year    – int oder None
      death_place   – Ortsname als String
      parents_json  – JSON-Liste von INDI-IDs der Eltern
      spouses_json  – JSON-Liste von INDI-IDs der Ehepartner
      children_json – JSON-Liste von INDI-IDs der Kinder
      siblings_json – JSON-Liste von Geschwister-IDs
      note          – frei (kombiniert aus FTM-Notizen)
    """
    # Familien-Index aufbauen: IDs schnell auffindbar
    parents_of:  dict[str, list[str]] = {}  # ged_id → [parent_id, …]
    spouses_of:  dict[str, list[str]] = {}
    children_of: dict[str, list[str]] = {}

    for fid, fam in families.items():
        husb = fam.get("HUSB") or []
        wife = fam.get("WIFE") or []
        chil = fam.get("CHIL") or []
        parents = (husb if isinstance(husb, list) else [husb]) + \
                  (wife if isinstance(wife, list) else [wife])
        children = chil if isinstance(chil, list) else [chil]

        for pid in parents:
            if pid:
                spouses_of.setdefault(pid, [])
                for other in parents:
                    if other and other != pid:
                        if other not in spouses_of[pid]:
                            spouses_of[pid].append(other)
                children_of.setdefault(pid, [])
                for cid in children:
                    if cid and cid not in children_of[pid]:
                        children_of[pid].append(cid)

        for cid in children:
            if cid:
                parents_of.setdefault(cid, [])
                for pid in parents:
                    if pid and pid not in parents_of[cid]:
                        parents_of[cid].append(pid)

    persons = []
    for ged_id, ind in individuals.items():
        # Name extrahieren
        givn = (ind.get("_GIVN") or ind.get("GIVN") or "").strip()
        surn = (ind.get("_SURN") or ind.get("SURN") or "").strip()
        if not givn and not surn:
            import re
            raw = ind.get("NAME", "")
            m = re.search(r"/([^/]*)/", raw)
            if m:
                surn  = m.group(1).strip()
                givn  = raw[: m.start()].strip()
            else:
                parts = raw.rsplit(" ", 1)
                givn  = parts[0].strip() if len(parts) == 2 else ""
                surn  = parts[-1].strip() if parts else ""
        if not givn and not surn:
            continue

        birt = ind.get("BIRT") or {}
        deat = ind.get("DEAT") or {}

        def _yr(v):
            try:
                return int(str(v)[:4]) if v else None
            except (TypeError, ValueError):
                return None

        note_parts = []
        for tag in ("NOTE", "RESI", "OCCU"):
            v = ind.get(tag)
            if isinstance(v, str) and v.strip():
                note_parts.append(v.strip())
            elif isinstance(v, list):
                note_parts.extend(x for x in v if isinstance(x, str) and x.strip())

        persons.append({
            "ext_id":       ged_id,
            "given_name":   givn,
            "surname":      surn,
            "sex":          (ind.get("SEX") or "").strip(),
            "birth_year":   _yr(birt.get("YEAR")),
            "birth_place":  (birt.get("PLAC") or "").strip(),
            "death_year":   _yr(deat.get("YEAR")),
            "death_place":  (deat.get("PLAC") or "").strip(),
            "parents_json":  json.dumps(parents_of.get(ged_id, [])),
            "spouses_json":  json.dumps(spouses_of.get(ged_id, [])),
            "children_json": json.dumps(children_of.get(ged_id, [])),
        })
    return persons


def run(
    ftm_path: str,
    db_path: str | None = None,
    source: str = "ftm",
    do_link: bool = True,
    dry_run: bool = False,
    progress_cb=None,
) -> dict:
    """FTM-Datei in gedcom_persons importieren.

    Parameters
    ----------
    ftm_path:
        Pfad zur .ftm Datei.
    db_path:
        Pfad zur ancestry_dna.db (None = Standard-Suchpfad).
    source:
        Quell-Label für gedcom_persons (Standard: 'ftm').
    do_link:
        True = Querbezüge zum eigenen GEDCOM anlegen.
    dry_run:
        True = nur Statistik ausgeben, nichts schreiben.
    progress_cb:
        Optionaler Callback ``(msg: str, tag: str = "") -> None``.

    Returns
    -------
    dict mit 'imported', 'linked', 'persons_total'
    """
    p = progress_cb or (lambda m, **kw: _log(m))

    # ── FTM oder GEDCOM laden ─────────────────────────────────────────────────
    suffix = Path(ftm_path).suffix.lower()

    if suffix in (".ged", ".gedcom"):
        p(f"📂 Lese GEDCOM-Datei: {ftm_path}")
        sys.path.insert(0, str(REPO_DIR))
        from lib.gedcom import robust_load_gedcom
        individuals, families = robust_load_gedcom(str(ftm_path))
        p(f"✅ {len(individuals):,} Personen, {len(families):,} Familien gelesen.")
    else:
        p(f"📂 Lese FTM-Datei: {ftm_path}")
        from tasks.import_ftm import is_ftm_file, load_ftm

        if not is_ftm_file(ftm_path):
            raise ValueError(
                f"Die Datei '{ftm_path}' ist keine FTM-SQLite-Datenbank "
                f"(kein SQLite-Magic-Header).\n"
                f"FTM 2024 (MacKiev) komprimiert .ftm-Dateien — bitte in FTM\n"
                f"nach GEDCOM exportieren (Datei → Exportieren → GEDCOM) und\n"
                f"dann diese .ged-Datei als Argument übergeben."
            )

        individuals, families = load_ftm(ftm_path, progress_cb=progress_cb)
        p(f"✅ {len(individuals):,} Personen, {len(families):,} Familien gelesen.")

    persons = _individuals_to_person_list(individuals, families, source)
    p(f"🔄 {len(persons):,} Personen mit vollständigem Namen zur Übernahme bereit.")

    if dry_run:
        p("ℹ️  Trocken­lauf — nichts wird gespeichert.", tag="warn")
        male   = sum(1 for x in persons if x["sex"] == "M")
        female = sum(1 for x in persons if x["sex"] == "F")
        has_by = sum(1 for x in persons if x["birth_year"])
        p(f"   Männer: {male}  Frauen: {female}  mit Geburtsjahr: {has_by}")
        return {"imported": 0, "linked": 0, "persons_total": len(persons)}

    # ── Datenbank ─────────────────────────────────────────────────────────────
    _db_path = db_path or str(ANCESTRY_DIR / "ancestry_dna.db")
    from ancestry.core.database import Database
    from ancestry.core.bridge import import_external_persons, link_duplicates

    db = Database(_db_path)
    try:
        p(f"💾 Importiere als source='{source}' in {Path(_db_path).name} …")
        n_imported = import_external_persons(db, persons, source=source)
        p(f"✅ {n_imported:,} Personen importiert.", tag="ok")

        n_linked = 0
        if do_link:
            p("🔗 Verknüpfe mit eigenem GEDCOM (source='gedcom') …")
            n_linked = link_duplicates(db, source=source,
                                       progress_cb=lambda m: p(f"   {m}"))
            p(f"✅ {n_linked:,} Querbezüge angelegt.", tag="ok")
    finally:
        db.close()

    p(f"🎉 FTM-Brücke fertig: {n_imported:,} Personen, {n_linked:,} Verknüpfungen.")
    return {
        "imported": n_imported,
        "linked": n_linked,
        "persons_total": len(persons),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=(
            "Family Tree Maker in ancestry_dna.db importieren.\n"
            "Akzeptiert .ftm (FTM 2014–2017, SQLite) oder .ged (GEDCOM-Export\n"
            "aus FTM 2024/MacKiev: Datei → Exportieren → GEDCOM)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("ftm_file",
                    help="Pfad zur .ftm- oder .ged-Datei")
    ap.add_argument("--source", default="ftm",
                    help="Quell-Label in gedcom_persons (Standard: 'ftm')")
    ap.add_argument("--db", default=None,
                    help="Pfad zur ancestry_dna.db (Standard: ancestry/ancestry_dna.db)")
    ap.add_argument("--no-link", action="store_true",
                    help="Nur importieren, keine Querbezüge anlegen")
    ap.add_argument("--dry-run", action="store_true",
                    help="Nur Statistik ausgeben, nichts schreiben")
    args = ap.parse_args()

    result = run(
        ftm_path=args.ftm_file,
        db_path=args.db,
        source=args.source,
        do_link=not args.no_link,
        dry_run=args.dry_run,
    )
    print(f"\nFertig: {result['imported']} importiert, {result['linked']} verknüpft "
          f"(von {result['persons_total']} gelesen)")


if __name__ == "__main__":
    main()
