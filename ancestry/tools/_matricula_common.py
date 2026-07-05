"""
Gemeinsame Helfer für die Matricula-Scraper (scrape_matricula,
scrape_matricula_osnabrueck, fetch_matricula_books …).

Zuvor waren `jh_to_year`, die Jahres-/Jahrhundert-Regexe und die
Orts-Normalisierung in jedem Scraper byte-identisch reimplementiert
(Drift-Risiko). Analog zum bereits erfolgreichen tasks/_online_common.py.
"""
from __future__ import annotations

import re

# "13. Jh." → Jahrhundert; "\b1667\b" → konkretes Jahr
JH_YEAR_RE = re.compile(r"(\d+)\.\s*Jh\b")
YEAR_RE = re.compile(r"\b(1[0-9]{3}|20\d{2})\b")


def jh_to_year(text: str) -> int | None:
    """'13. Jh.' → 1250 (Mitte des Jahrhunderts); sonst erstes 4-stellige Jahr."""
    m = JH_YEAR_RE.search(text)
    if m:
        return (int(m.group(1)) - 1) * 100 + 50
    m = YEAR_RE.search(text)
    return int(m.group()) if m else None


def norm_village(v: str) -> str:
    """Ortsnamen von Rand-Satzzeichen befreien."""
    return v.strip().rstrip(".,;")
