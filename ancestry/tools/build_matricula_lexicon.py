#!/usr/bin/env python3
"""build_matricula_lexicon.py — baut ein Domänen-Lexikon (Nachnamen, Vornamen,
Orte) aus den vorhandenen Daten.

Diese Wortliste verbessert FREIE OCR/HTR-Engines deutlich:
  • Tesseract:  als --user-words / user-patterns
  • Kraken:     als Dictionary / Sprachmodell-Hilfe
  • Validierung: OCR-Rohtext gegen bekannte Namen/Orte abgleichen, Fehler finden

Quellen: gedcom_persons (given_name, surname, birth_place, death_place) und –
falls vorhanden – source_matrikula_entries (person_name, father/mother_name,
village). Kein Claude/Token nötig.

Aufruf:
    python -m ancestry.tools.build_matricula_lexicon
    python -m ancestry.tools.build_matricula_lexicon --db pfad.db --out lexikon.txt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from collections import Counter

_TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß'\-]+")


def _tokens(*values) -> list[str]:
    out = []
    for v in values:
        if not v:
            continue
        out.extend(_TOKEN.findall(str(v)))
    return out


def build_lexicon(db_path: str) -> dict:
    """{'surnames':Counter,'given':Counter,'places':Counter}."""
    surnames: Counter = Counter()
    given: Counter = Counter()
    places: Counter = Counter()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        for r in con.execute("SELECT given_name, surname, birth_place, death_place "
                             "FROM gedcom_persons"):
            for t in _tokens(r["surname"]):
                surnames[t] += 1
            for t in _tokens(r["given_name"]):
                given[t] += 1
            for t in _tokens(r["birth_place"], r["death_place"]):
                places[t] += 1
    except sqlite3.OperationalError:
        pass
    # Matricula-Einträge (falls die Crawl-/Korrektur-Daten in derselben DB liegen)
    try:
        for r in con.execute("SELECT person_name, person2_name, father_name, "
                             "mother_name, village FROM source_matrikula_entries"):
            for t in _tokens(r["person_name"], r["person2_name"],
                             r["father_name"], r["mother_name"]):
                (surnames if t[:1].isupper() else given)[t] += 1
            for t in _tokens(r["village"]):
                places[t] += 1
    except sqlite3.OperationalError:
        pass
    con.close()
    return {"surnames": surnames, "given": given, "places": places}


def write_outputs(lex: dict, out_path: str) -> dict:
    words = sorted(set(lex["surnames"]) | set(lex["given"]) | set(lex["places"]))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(words) + "\n")
    json_path = os.path.splitext(out_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({k: dict(v.most_common()) for k, v in lex.items()},
                  f, ensure_ascii=False, indent=1)
    return {"words": len(words), "surnames": len(lex["surnames"]),
            "given": len(lex["given"]), "places": len(lex["places"]),
            "txt": out_path, "json": json_path}


def main():
    ap = argparse.ArgumentParser(description="Domänen-Lexikon für Matricula-OCR")
    default_db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "ancestry_dna.db")
    ap.add_argument("--db", default=default_db)
    default_out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data", "matricula_lexicon.txt")
    ap.add_argument("--out", default=default_out)
    args = ap.parse_args()
    if not os.path.exists(args.db):
        print(f"⚠ DB nicht gefunden: {args.db}")
        return
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    lex = build_lexicon(args.db)
    info = write_outputs(lex, args.out)
    print(f"📚 Lexikon: {info['words']} Wörter "
          f"({info['surnames']} Nachnamen, {info['given']} Vornamen, "
          f"{info['places']} Orte)")
    print(f"   → {info['txt']}")
    print(f"   → {info['json']} (mit Häufigkeiten)")
    print("Nutzung: Tesseract --user-words <txt>; Kraken-Dictionary; OCR-Validierung.")


if __name__ == "__main__":
    main()
