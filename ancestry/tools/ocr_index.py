#!/usr/bin/env python3
"""ocr_index.py — lokaler Volltext-Index über die OCR-Rohtexte (token-frei).

Indiziert alle .txt aus dem Matricula-Bild-Archiv (eine je Seite) plus – falls
vorhanden – die Matricula-Belege und GEDCOM-Namen in einen SQLite-FTS5-Index.
Damit „rastert" man ein ganzes Kirchspiel in Sekunden durch, z. B. um Personen
zu finden, die in eine Nachbargemeinde gezogen sind.

Suche normal (exakte Wörter) ODER phonetisch (Kölner Phonetik) – findet auch
Schreib-/Lesevarianten (Koverman/Kovermann/Cobermann).

CLI:
    python -m ancestry.tools.ocr_index --build
    python -m ancestry.tools.ocr_index --search Kovermann
    python -m ancestry.tools.ocr_index --search Koverman --phonetic
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
from pathlib import Path

from ancestry.paths import ROOT
from ancestry.core.bridge._text import _koelner, _norm

INDEX_PATH = os.environ.get(
    "GENEA_OCR_INDEX", os.path.join(str(ROOT), "ancestry", "data", "ocr_index.db"))
DEFAULT_ARCHIVE = os.environ.get(
    "MATRICULA_ARCHIVE", str(Path.home() / "matricula_images"))

_TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß'\-]+")


def _phon(text: str) -> str:
    """Leerzeichen-getrennte Kölner-Codes aller Wörter (für phonetische Suche)."""
    codes = [_koelner(_norm(t)) for t in _TOKEN.findall(text or "")]
    return " ".join(c for c in codes if c)


def build_index(archive_dir: str = DEFAULT_ARCHIVE, db_path: str | None = None,
                index_path: str = INDEX_PATH, progress=None) -> dict:
    """(Neu-)Baut den FTS5-Index. Gibt Kennzahlen zurück."""
    os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
    if os.path.exists(index_path):
        os.remove(index_path)
    con = sqlite3.connect(index_path)
    con.execute("CREATE VIRTUAL TABLE ocr USING fts5(kind, head, body, phon, "
                "path UNINDEXED, tokenize='unicode61')")
    n_ocr = n_entry = n_pers = 0

    arch = Path(archive_dir)
    if arch.exists():
        for txt in sorted(arch.rglob("*.txt")):
            try:
                body = txt.read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                continue
            if not body:
                continue
            head = " / ".join(txt.relative_to(arch).with_suffix("").parts)
            con.execute("INSERT INTO ocr(kind,head,body,phon,path) VALUES(?,?,?,?,?)",
                        ("OCR-Seite", head, body, _phon(body), str(txt)))
            n_ocr += 1
            if progress and n_ocr % 500 == 0:
                progress(f"OCR indiziert: {n_ocr}")

    # Matricula-Belege + GEDCOM-Namen (falls DB vorhanden)
    if db_path is None:
        db_path = os.path.join(str(ROOT), "ancestry", "ancestry_dna.db")
    if os.path.exists(db_path):
        try:
            src = sqlite3.connect(db_path); src.row_factory = sqlite3.Row
            for r in src.execute("SELECT book_id,page_nr,entry_type,event_date,"
                                 "person_name,father_name,mother_name,village,notes "
                                 "FROM source_matrikula_entries"):
                body = " ".join(str(x) for x in (r["person_name"], r["father_name"],
                                r["mother_name"], r["village"], r["notes"]) if x)
                head = f"{r['book_id']} S.{r['page_nr']} {r['entry_type']} {r['event_date'] or ''}".strip()
                con.execute("INSERT INTO ocr(kind,head,body,phon,path) VALUES(?,?,?,?,?)",
                            ("Matricula-Beleg", head, body, _phon(body), ""))
                n_entry += 1
        except sqlite3.OperationalError:
            pass
        try:
            for r in src.execute("SELECT ged_id,given_name,surname,birth_year,"
                                 "birth_place,source FROM gedcom_persons"):
                name = f"{(r['given_name'] or '').strip()} {(r['surname'] or '').strip()}".strip()
                if not name:
                    continue
                body = f"{name} {r['birth_year'] or ''} {r['birth_place'] or ''}".strip()
                con.execute("INSERT INTO ocr(kind,head,body,phon,path) VALUES(?,?,?,?,?)",
                            (f"GEDCOM:{r['source']}", name, body, _phon(body), str(r["ged_id"])))
                n_pers += 1
        except sqlite3.OperationalError:
            pass
        src.close()

    con.commit(); con.close()
    return {"ocr": n_ocr, "entries": n_entry, "persons": n_pers, "index": index_path}


def _fts_query(query: str, phonetic: bool) -> tuple[str, str]:
    """(column, match_expr). Phonetisch → Kölner-Codes; sonst Prefix-Suche."""
    terms = _TOKEN.findall(query or "")
    if not terms:
        return "body", '""'
    if phonetic:
        codes = [_koelner(_norm(t)) for t in terms]
        codes = [c for c in codes if c]
        return "phon", " ".join(f'"{c}"' for c in codes) or '""'
    return "body", " ".join(f'"{t}"*' for t in terms)


def search(query: str, phonetic: bool = False, limit: int = 200,
           index_path: str = INDEX_PATH) -> list[dict]:
    if not os.path.exists(index_path):
        return []
    col, expr = _fts_query(query, phonetic)
    con = sqlite3.connect(index_path); con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            f"SELECT kind, head, path, snippet(ocr, 2, '[', ']', ' … ', 12) snip "
            f"FROM ocr WHERE {col} MATCH ? ORDER BY rank LIMIT ?",
            (expr, limit)).fetchall()
    except sqlite3.OperationalError as e:
        con.close()
        return [{"kind": "Fehler", "head": str(e), "path": "", "snip": ""}]
    out = [{"kind": r["kind"], "head": r["head"], "path": r["path"], "snip": r["snip"]}
           for r in rows]
    con.close()
    return out


def main():
    ap = argparse.ArgumentParser(description="OCR-Volltextindex + Suche")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--archive", default=DEFAULT_ARCHIVE)
    ap.add_argument("--search", metavar="QUERY")
    ap.add_argument("--phonetic", action="store_true")
    args = ap.parse_args()
    if args.build:
        info = build_index(args.archive, progress=lambda m: print("  " + m))
        print(f"📑 Index gebaut: {info['ocr']} OCR-Seiten, {info['entries']} Belege, "
              f"{info['persons']} Personen → {info['index']}")
    if args.search:
        hits = search(args.search, phonetic=args.phonetic)
        print(f"🔎 {len(hits)} Treffer für '{args.search}'"
              + (" (phonetisch)" if args.phonetic else "") + ":")
        for h in hits[:50]:
            print(f"  [{h['kind']}] {h['head']}: {h['snip']}")


if __name__ == "__main__":
    main()
