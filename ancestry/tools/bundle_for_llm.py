#!/usr/bin/env python3
"""bundle_for_llm.py — bündelt alles zu einem durchsuchbaren Text-Korpus für
NotebookLM / Browser-LLM (token-frei lokal erzeugt).

Sammelt:
  1. die rohen OCR-Texte (eine .txt je Bild) aus dem Matricula-Bild-Archiv,
     mit Pfarrei/Buch/Seite als Kopfzeile (Kontext bleibt erhalten),
  2. einen kompakten GEDCOM-Faktendump (Personen: Name, Daten, Orte, Quelle),
  3. die Matricula-Belege (source_matrikula_entries), falls vorhanden.

Schreibt das Ganze größengechunkt nach <out-dir>/korpus_NN.txt — handliche
Dateien, die man direkt in ein Web-LLM hochlädt/einfügt.

Aufruf:
    python -m ancestry.tools.bundle_for_llm
    python -m ancestry.tools.bundle_for_llm --archive ~/matricula_images \
        --db pfad.db --out-dir output/llm_korpus --max-chars 700000
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path


def collect_ocr_texts(archive_dir: Path):
    """Liefert (überschrift, text) je .txt-Datei im Bild-Archiv."""
    if not archive_dir.exists():
        return
    for txt in sorted(archive_dir.rglob("*.txt")):
        try:
            content = txt.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        if not content:
            continue
        rel = txt.relative_to(archive_dir).with_suffix("")
        parts = rel.parts                      # <pfarrei>/<buch>/<seite>
        head = " / ".join(parts) if parts else txt.stem
        yield head, content


def gedcom_dump(db_path: str, limit: int = 0) -> str:
    lines = ["## STAMMBAUM — GEDCOM-Personen",
             "(Name | Geschlecht | * Geburt | † Tod | Quelle)", ""]
    try:
        con = sqlite3.connect(db_path); con.row_factory = sqlite3.Row
        sql = ("SELECT given_name, surname, sex, birth_year, birth_place, "
               "death_year, death_place, source FROM gedcom_persons "
               "ORDER BY surname, given_name")
        if limit:
            sql += f" LIMIT {int(limit)}"
        for r in con.execute(sql):
            name = f"{(r['given_name'] or '').strip()} {(r['surname'] or '').strip()}".strip()
            if not name:
                continue
            b = f"*{r['birth_year']} {r['birth_place'] or ''}".strip() if r["birth_year"] else ""
            d = f"†{r['death_year']} {r['death_place'] or ''}".strip() if r["death_year"] else ""
            lines.append(f"- {name} [{r['sex'] or '?'}] {b} {d}  ({r['source'] or ''})".rstrip())
        con.close()
    except sqlite3.OperationalError as e:
        lines.append(f"(GEDCOM-Personen nicht lesbar: {e})")
    return "\n".join(lines)


def matricula_dump(db_path: str) -> str:
    lines = ["## MATRICULA-BELEGE (Anverwandte / korrigierte Einträge)", ""]
    try:
        con = sqlite3.connect(db_path); con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT book_id, page_nr, entry_type, event_date, person_name, "
            "person2_name, father_name, mother_name, village, notes "
            "FROM source_matrikula_entries ORDER BY book_id, page_nr").fetchall()
        for r in rows:
            who = r["person_name"] or ""
            if r["person2_name"]:
                who += f" ⚭ {r['person2_name']}"
            par = " / ".join(x for x in (r["father_name"], r["mother_name"]) if x)
            loc = f" @ {r['village']}" if r["village"] else ""
            ref = f"[{r['book_id']} S.{r['page_nr']}]" if r["page_nr"] else f"[{r['book_id']}]"
            extra = f" Eltern: {par}" if par else ""
            lines.append(f"- {r['entry_type']} {r['event_date'] or ''} {who}{loc}"
                         f"{extra} {ref}".rstrip())
        con.close()
        if len(lines) == 2:
            lines.append("(keine Matricula-Einträge in der DB)")
    except sqlite3.OperationalError:
        lines.append("(Tabelle source_matrikula_entries nicht vorhanden)")
    return "\n".join(lines)


def bundle(archive_dir: Path, db_path: str, out_dir: Path,
           max_chars: int = 700_000) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Reihenfolge: OCR-Rohtexte zuerst, dann Faktenquellen
    sections: list[str] = ["# MATRICULA-OCR — ROHTEXTE (eine je Seite)", ""]
    n_ocr = 0
    for head, content in collect_ocr_texts(archive_dir):
        sections.append(f"### {head}\n{content}\n")
        n_ocr += 1
    if n_ocr == 0:
        sections.append("(keine OCR-.txt im Bild-Archiv gefunden)\n")
    sections.append("\n" + gedcom_dump(db_path) + "\n")
    sections.append("\n" + matricula_dump(db_path) + "\n")

    # Chunken nach max_chars (an Abschnittsgrenzen)
    files, buf, size, idx = [], [], 0, 1
    for sec in sections:
        if size and size + len(sec) > max_chars:
            p = out_dir / f"korpus_{idx:02d}.txt"
            p.write_text("\n".join(buf), encoding="utf-8")
            files.append(str(p)); idx += 1; buf, size = [], 0
        buf.append(sec); size += len(sec) + 1
    if buf:
        p = out_dir / f"korpus_{idx:02d}.txt"
        p.write_text("\n".join(buf), encoding="utf-8")
        files.append(str(p))
    return {"ocr_pages": n_ocr, "files": files,
            "total_chars": sum(len(s) for s in sections)}


def main():
    base = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Text-Korpus für NotebookLM/LLM bündeln")
    ap.add_argument("--archive", default=os.environ.get(
        "MATRICULA_ARCHIVE", str(Path.home() / "matricula_images")))
    ap.add_argument("--db", default=str(base / "ancestry_dna.db"))
    ap.add_argument("--out-dir", default=str(base.parent / "output" / "llm_korpus"))
    ap.add_argument("--max-chars", type=int, default=700_000)
    args = ap.parse_args()
    info = bundle(Path(args.archive), args.db, Path(args.out_dir), args.max_chars)
    print(f"📦 Korpus gebündelt: {info['ocr_pages']} OCR-Seiten, "
          f"{info['total_chars']:,} Zeichen → {len(info['files'])} Datei(en):")
    for f in info["files"]:
        print(f"   {f}")
    print("Direkt in NotebookLM / Browser-LLM hochladen oder einfügen.")


if __name__ == "__main__":
    main()
