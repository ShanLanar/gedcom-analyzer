"""
Gemeinsame Helfer für die Online-Recherche-Module (externe_quellen,
familysearch, wikitree_lookup, grabstein, compgen_metasearch …).

Diese drei Funktionen waren zuvor in jedem Modul identisch reimplementiert.
Region-/Konfessions-spezifische Prädikate (``_is_dach`` etc.) bleiben bewusst
in den einzelnen Modulen, weil ihre Wortlisten je nach Zweck abweichen.
"""

from __future__ import annotations

import re

from lib.gedcom import safe_extract_year

_SYMBOL_RE = re.compile(r"[✠★⚔‡]")
_MIG_RE = re.compile(r"\bmig\.\S*\b", re.IGNORECASE)


def split_name(name: str) -> tuple[str, str]:
    """GEDCOM-Name → (Vorname(n), Nachname).

    Entfernt Militär-/Migrations-Marker; nutzt die /Nachname/-Konvention,
    sonst gilt das letzte Wort als Nachname.
    """
    if not name:
        return "", ""
    cleaned = _SYMBOL_RE.sub("", name).strip()
    cleaned = _MIG_RE.sub("", cleaned).strip()
    if "/" in cleaned:
        parts = cleaned.split("/")
        return parts[0].strip(), (parts[1].strip() if len(parts) >= 2 else "")
    words = cleaned.split()
    return (" ".join(words[:-1]), words[-1]) if len(words) > 1 else (cleaned, "")


def year_of(evt) -> int | None:
    """Jahr eines GEDCOM-Events (YEAR-Feld, sonst aus DATE extrahiert)."""
    if not evt:
        return None
    return evt.get("YEAR") or safe_extract_year(evt.get("DATE"))


def first_place(plac: str) -> str:
    """Erste (feinste) Komponente eines komma-getrennten Ortsstrings."""
    return plac.split(",")[0].strip() if plac else ""
