"""Architektur-Tests: Schichtenregeln aus ARCHITEKTUR-KONZEPT.md, Abschnitt 3.1.

  core/* darf nie tkinter oder flask importieren.
"""
import ast
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent / "ancestry" / "core"
FORBIDDEN = {"tkinter", "flask", "tk"}


def _imports_in_file(path: Path) -> list[str]:
    """Gibt alle Top-Level-Import-Namen aus einer .py-Datei zurück."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module.split(".")[0])
    return names


def test_core_does_not_import_tkinter_or_flask():
    violations: list[str] = []
    for py in CORE_DIR.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        for imp in _imports_in_file(py):
            if imp in FORBIDDEN:
                violations.append(f"{py.relative_to(CORE_DIR.parent.parent)}: imports {imp!r}")
    assert not violations, "core/ darf kein tkinter/flask importieren:\n" + "\n".join(violations)
