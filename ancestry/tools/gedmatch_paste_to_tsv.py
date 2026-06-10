#!/usr/bin/env python3
"""
Konvertiert kopierte GEDmatch-Tabellendaten (aus Clipboard oder Stdin) in eine TSV-Datei.

Anleitung:
  1. GEDmatch One-to-Many öffnen (https://www.gedmatch.com/tier1Match.php?A=...)
  2. Alle Treffer laden (auf "All" klicken oder mehrere Seiten)
  3. Tabelle markieren (Strg+A im Tabellenbereich), kopieren (Strg+C)
  4. Einfügen in Terminal:
       python gedmatch_paste_to_tsv.py
     oder Text-Datei übergeben:
       python gedmatch_paste_to_tsv.py meine_paste.txt

AUSGABE:
  ancestry/data/gedmatch_CM8449775.tsv  (direkt importierbar)
"""
import sys
from pathlib import Path
from datetime import date

SCRIPT_DIR   = Path(__file__).resolve().parent
DATA_DIR     = SCRIPT_DIR.parent / "data"
OUR_KIT      = "CM8449775"
OUT_FILE     = DATA_DIR / f"gedmatch_{OUR_KIT}.tsv"

# Standard GEDmatch One-to-Many Spaltenköpfe (Tab-getrennt)
HEADER = (
    "Kit_Number\tName\tEmail\tTags\tSex\t"
    "Total_cM\tLargest_Seg\tGen\t"
    "X-DNA_cM\tX-DNA_Segs\t"
    "Source\tSNPs\tOverlap\tmtDNA\tYDNA"
)


def read_input() -> str:
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        return p.read_text(encoding="utf-8", errors="replace")
    print("Füge GEDmatch-Tabelle ein (Strg+D zum Beenden):")
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    text = read_input().strip()
    if not text:
        print("Keine Eingabe. Abbruch.")
        sys.exit(1)

    lines = [l for l in text.splitlines() if l.strip()]
    # Erkenne ob Kopfzeile vorhanden
    first = lines[0].lower()
    has_header = any(k in first for k in ("kit", "name", "total", "source", "snp"))

    out_lines = [HEADER]
    for line in lines:
        if not line.strip():
            continue
        # Erste Zeile überspringen wenn Kopfzeile
        if has_header and line == lines[0]:
            continue
        # Normalisiere: mehrere Tabs/Spaces → einzelner Tab
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 3:
            # Fallback: Leerzeichen-getrennt
            parts = line.split()
        if not parts or not parts[0]:
            continue
        # Erste Spalte muss eine Kit-Nummer sein (Buchstabe + Ziffern)
        kit = parts[0].strip()
        if not kit or len(kit) < 3:
            continue
        out_lines.append("\t".join(parts))

    OUT_FILE.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\n✓ {len(out_lines)-1} Zeilen gespeichert nach: {OUT_FILE}")
    print("\nJetzt importieren mit:")
    print(f"  python import_gedmatch_matches.py {OUT_FILE}")


if __name__ == "__main__":
    main()
