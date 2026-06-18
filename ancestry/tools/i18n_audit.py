#!/usr/bin/env python3
"""i18n-Audit: findet hartkodierte deutsche UI-Strings im GUI-Code.

Sucht in ancestry/gui/ nach Widget-Beschriftungen (text=/title=/label=) und
messagebox-Aufrufen, deren Text deutsche Zeichen/Wörter enthält und NICHT über
das Übersetzungssystem (theme.translate / t("…")) läuft. Dient als wiederhol-
barer Fortschrittsbericht beim Zweisprachig-Machen der Oberfläche.

Aufruf:
    python -m ancestry.tools.i18n_audit            # Bericht
    python -m ancestry.tools.i18n_audit --list     # alle Fundstellen einzeln
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

GUI_DIR = Path(__file__).resolve().parent.parent / "gui"

# typische deutsche Marker (Umlaute oder häufige Funktionswörter)
_GERMAN = re.compile(r"[äöüßÄÖÜ]|\b(?:und|oder|der|die|das|für|mit|nicht|"
                     r"laden|wählen|öffnen|speichern|löschen|abbrechen|"
                     r"importieren|exportieren|berechnen|Datei|Fenster|"
                     r"keine?|bitte)\b", re.IGNORECASE)

# text="…" / title="…" / label="…" mit Literal (einfache/doppelte Quotes)
_LABEL = re.compile(r'(?:text|title|label)\s*=\s*(["\'])(.*?)\1')
# messagebox.showinfo("Titel", "Nachricht …")  – erfasst Literale
_MSGBOX = re.compile(r'messagebox\.(?:showinfo|showwarning|showerror|askyesno)'
                     r'\s*\(\s*(["\'])(.*?)\1')


def _is_german(text: str) -> bool:
    if not text or len(text) < 3:
        return False
    # reine Symbole/Emoji/Format-Strings ignorieren
    if not re.search(r"[A-Za-zÄÖÜäöü]", text):
        return False
    return bool(_GERMAN.search(text))


def scan() -> dict[Path, list[tuple[int, str]]]:
    findings: dict[Path, list[tuple[int, str]]] = {}
    for path in sorted(GUI_DIR.rglob("*.py")):
        # theme.py enthält bewusst alle Übersetzungen – nicht auditieren
        if path.name == "theme.py":
            continue
        hits: list[tuple[int, str]] = []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "t(" in line and "text=t(" in line.replace(" ", ""):
                continue  # bereits übersetzt
            for rx in (_LABEL, _MSGBOX):
                for m in rx.finditer(line):
                    txt = m.group(2)
                    if _is_german(txt):
                        hits.append((n, txt))
        if hits:
            findings[path] = hits
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true",
                    help="alle Fundstellen einzeln ausgeben")
    args = ap.parse_args()

    findings = scan()
    total = sum(len(v) for v in findings.values())
    per_file = Counter({p: len(v) for p, v in findings.items()})

    print(f"i18n-Audit: {total} hartkodierte deutsche UI-Strings "
          f"in {len(findings)} Dateien\n")
    for path, n in per_file.most_common():
        rel = path.relative_to(GUI_DIR.parent.parent)
        print(f"  {n:3d}  {rel}")
    if args.list:
        print()
        for path in sorted(findings):
            rel = path.relative_to(GUI_DIR.parent.parent)
            for line_no, txt in findings[path]:
                short = (txt[:70] + "…") if len(txt) > 70 else txt
                print(f"{rel}:{line_no}: {short}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
