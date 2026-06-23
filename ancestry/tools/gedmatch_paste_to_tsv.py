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
import argparse
import sys
from datetime import date
from pathlib import Path

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Konvertiert kopierte GEDmatch-Tabellendaten (aus Clipboard oder Stdin) "
                    "in eine TSV-Datei, die direkt mit import_gedmatch_matches.py importiert "
                    "werden kann.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Aus Datei (kopierte GEDmatch-Tabelle als Textdatei gespeichert):
  python -m ancestry.tools.gedmatch_paste_to_tsv --input meine_paste.txt

  # Aus Stdin (interaktiv einfügen, Strg+D zum Beenden):
  python -m ancestry.tools.gedmatch_paste_to_tsv

  # Mit eigenem Kit-Kürzel und Ausgabepfad:
  python -m ancestry.tools.gedmatch_paste_to_tsv -i paste.txt --kit CM1234567 -o ausgabe.tsv
""",
    )
    parser.add_argument(
        "--input", "-i",
        metavar="DATEI",
        default=None,
        help="Eingabedatei mit der kopierten GEDmatch-Tabelle. "
             "Ohne Angabe wird interaktiv von Stdin gelesen.",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="DATEI",
        default=None,
        help="Ausgabe-TSV-Datei (Standard: ancestry/data/gedmatch_<KIT>.tsv).",
    )
    parser.add_argument(
        "--kit",
        metavar="KIT_ID",
        default=None,
        help=f"Eigene Kit-Nummer (Standard: {OUR_KIT}).",
    )
    return parser.parse_args()


def read_input(input_path: str | None = None) -> str:
    if input_path:
        p = Path(input_path)
        return p.read_text(encoding="utf-8", errors="replace")
    # Legacy: positional arg
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
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
    args = _parse_args()

    # Allow overriding kit and output via args
    global OUR_KIT, OUT_FILE
    if args.kit:
        OUR_KIT = args.kit
    if args.output:
        OUT_FILE = Path(args.output)
    elif args.kit:
        OUT_FILE = DATA_DIR / f"gedmatch_{OUR_KIT}.tsv"

    DATA_DIR.mkdir(exist_ok=True)
    text = read_input(args.input).strip()
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
