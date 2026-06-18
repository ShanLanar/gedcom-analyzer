#!/usr/bin/env python3
"""i18n-Audit: findet hartkodierte deutsche UI-Strings im GUI-Code.

AST-basierter Scanner: wertet den Syntaxbaum aus, nicht Rohtextzeilen.
Erfasst dadurch auch messagebox-Body-Texte und mehrzeilige Strings, die
Regex übersieht. Falsch-positive durch Bezeichner (side_label = …) entfallen.

Aufruf:
    python -m ancestry.tools.i18n_audit            # Bericht
    python -m ancestry.tools.i18n_audit --list     # alle Fundstellen einzeln
"""
from __future__ import annotations

import argparse
import ast
import re
from collections import Counter
from pathlib import Path

GUI_DIR = Path(__file__).resolve().parent.parent / "gui"

_WIDGET_TEXT_KEYS = {"text", "title", "label", "message"}
_MSGBOX_FUNCS = {"showinfo", "showwarning", "showerror", "askyesno",
                 "askokcancel", "askretrycancel", "askyesnocancel"}

_GERMAN = re.compile(
    r"[äöüßÄÖÜ]"
    r"|\b(?:und|oder|der|die|das|für|mit|nicht|"
    r"laden|wählen|öffnen|speichern|löschen|abbrechen|"
    r"importieren|exportieren|berechnen|Datei|Fenster|"
    r"keine?|bitte)\b",
    re.IGNORECASE,
)


def _is_german(text: str) -> bool:
    if not text or len(text) < 3:
        return False
    if not re.search(r"[A-Za-zÄÖÜäöü]", text):
        return False
    return bool(_GERMAN.search(text))


def _func_name(node: ast.expr) -> str:
    """Returns the last attribute segment of a call's function, e.g. 'showinfo'."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _is_msgbox_call(call: ast.Call) -> bool:
    return _func_name(call.func) in _MSGBOX_FUNCS


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Parse one file and return (lineno, string) pairs for hardcoded German strings."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    hits: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # ── keyword args: text=, title=, label=, message= ────────────────────
        for kw in node.keywords:
            if kw.arg not in _WIDGET_TEXT_KEYS:
                continue
            if not isinstance(kw.value, ast.Constant):
                continue  # t("key") or variable → already translated / not a literal
            txt = kw.value.value
            if isinstance(txt, str) and _is_german(txt):
                hits.append((kw.value.lineno, txt))

        # ── messagebox positional args (title=arg0, message=arg1) ─────────────
        if _is_msgbox_call(node):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    txt = arg.value
                    if _is_german(txt):
                        hits.append((arg.lineno, txt))

    # Deduplicate by (lineno, text) while preserving order
    seen: set[tuple[int, str]] = set()
    unique: list[tuple[int, str]] = []
    for item in sorted(hits):
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def scan() -> dict[Path, list[tuple[int, str]]]:
    findings: dict[Path, list[tuple[int, str]]] = {}
    for path in sorted(GUI_DIR.rglob("*.py")):
        if path.name == "theme.py":
            continue
        hits = _scan_file(path)
        if hits:
            findings[path] = hits
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="AST-basierter i18n-Audit für ancestry/gui/"
    )
    ap.add_argument("--list", action="store_true",
                    help="alle Fundstellen einzeln ausgeben")
    args = ap.parse_args()

    findings = scan()
    total = sum(len(v) for v in findings.values())
    per_file = Counter({p: len(v) for p, v in findings.items()})

    print(f"i18n-Audit (AST): {total} hartkodierte deutsche UI-Strings "
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
