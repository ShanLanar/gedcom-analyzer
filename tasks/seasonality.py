# -*- coding: utf-8 -*-
"""tasks/seasonality.py – Geburts-/Heirats-/Sterbe-Monatsverteilung + Empfängnisschätzung"""

import re
from collections import defaultdict
from lib.gedcom import safe_extract_year

# Monats-Abkürzungen DE + EN
_MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "MRZ": 3, "APR": 4, "MAY": 5, "MAI": 5,
    "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "OKT": 10,
    "NOV": 11, "DEC": 12, "DEZ": 12,
}
_MONTH_RE = re.compile(r"\b(" + "|".join(_MONTH_MAP) + r")\b", re.IGNORECASE)
_MONTH_NUM_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,4})\b")

_MONTH_NAMES = ["", "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

EPOCHS = {
    "vor_1800":  (1500, 1799),
    "1800-1850": (1800, 1849),
    "1850-1900": (1850, 1899),
    "1900-1950": (1900, 1949),
    "nach_1950": (1950, 2024),
}


def _extract_month(date_str) -> int | None:
    if not date_str:
        return None
    s = str(date_str).upper()
    m = _MONTH_RE.search(s)
    if m:
        return _MONTH_MAP[m.group(1).upper()]
    # Numerisches Format wie "15.03.1850" — Heuristik: zweites Element ist Monat oder Jahr
    m = _MONTH_NUM_RE.search(s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        # 1.7.1850 → day=1, month=7
        if 1 <= a <= 31 and 1 <= b <= 12:
            return b
    return None


def _epoch(year: int | None) -> str | None:
    if not year:
        return None
    for ep, (s, e) in EPOCHS.items():
        if s <= year <= e:
            return ep
    return None


def _build_dist_table(counter: dict, label_for_subgroup: str = "Epoche") -> list:
    """counter[(epoch, month)] = count → 12 Spalten + Total."""
    rows = []
    for ep in EPOCHS:
        counts = [counter.get((ep, m), 0) for m in range(1, 13)]
        total = sum(counts)
        if total == 0:
            continue
        peak_m = counts.index(max(counts)) + 1 if counts else 0
        pct = [round(c / total * 100, 1) if total else 0 for c in counts]
        rows.append([ep, total, *pct, f"{_MONTH_NAMES[peak_m]} ({max(counts)})"])
    return rows


# ── Geburtsmonate ──────────────────────────────────────────────────────────────

BIRTH_MONTH_HEADERS = [
    "Epoche", "Anzahl gesamt",
    *[f"{_MONTH_NAMES[m]} %" for m in range(1, 13)],
    "Peak-Monat",
]


def analyze_birth_months(individuals, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Geburtsmonats-Verteilung …")
    counter: dict = defaultdict(int)
    for indi in individuals.values():
        ev = indi.get("BIRT") or {}
        month = _extract_month(ev.get("DATE"))
        year  = ev.get("YEAR") or safe_extract_year(ev.get("DATE"))
        if month and year:
            ep = _epoch(year)
            if ep:
                counter[(ep, month)] += 1
    rows = _build_dist_table(counter)
    p(f"Geburtsmonate: {sum(counter.values()):,} datierte Geburten", tag="ok")
    return rows


# ── Heiratsmonate ──────────────────────────────────────────────────────────────

MARRIAGE_MONTH_HEADERS = BIRTH_MONTH_HEADERS


def analyze_marriage_months(families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Heiratsmonats-Verteilung …")
    counter: dict = defaultdict(int)
    for fam in families.values():
        date = fam.get("MARR_DATE")
        month = _extract_month(date)
        year  = safe_extract_year(date)
        if month and year:
            ep = _epoch(year)
            if ep:
                counter[(ep, month)] += 1
    rows = _build_dist_table(counter)
    p(f"Heiratsmonate: {sum(counter.values()):,} datierte Eheschließungen", tag="ok")
    return rows


# ── Sterbemonate nach Altersklasse ────────────────────────────────────────────

DEATH_MONTH_HEADERS = [
    "Altersklasse", "Epoche", "Anzahl",
    *[f"{_MONTH_NAMES[m]} %" for m in range(1, 13)],
    "Peak-Monat",
]


def _age_band(age: int) -> str:
    if age < 1:   return "Säugling (<1 J.)"
    if age < 5:   return "Kleinkind (1–4 J.)"
    if age < 15:  return "Kind (5–14 J.)"
    if age < 50:  return "Erwachsen (15–49 J.)"
    if age < 75:  return "Ältere (50–74 J.)"
    return "Hochbetagt (75+ J.)"


_AGE_BAND_ORDER = ["Säugling (<1 J.)", "Kleinkind (1–4 J.)", "Kind (5–14 J.)",
                    "Erwachsen (15–49 J.)", "Ältere (50–74 J.)", "Hochbetagt (75+ J.)"]


def analyze_death_months(individuals, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Sterbemonats-Verteilung …")
    counter: dict = defaultdict(int)  # (age_band, epoch, month) → count
    for indi in individuals.values():
        ev = indi.get("DEAT") or {}
        month = _extract_month(ev.get("DATE"))
        dyear = ev.get("YEAR") or safe_extract_year(ev.get("DATE"))
        byear = (indi.get("BIRT") or {}).get("YEAR") or \
                safe_extract_year((indi.get("BIRT") or {}).get("DATE"))
        if not (month and dyear and byear):
            continue
        age = dyear - byear
        if not 0 <= age <= 120:
            continue
        ep = _epoch(dyear)
        if not ep:
            continue
        counter[(_age_band(age), ep, month)] += 1

    rows = []
    for band in _AGE_BAND_ORDER:
        for ep in EPOCHS:
            counts = [counter.get((band, ep, m), 0) for m in range(1, 13)]
            total = sum(counts)
            if total < 5:   # zu wenig für sinnvolle Verteilung
                continue
            peak_m = counts.index(max(counts)) + 1
            pct = [round(c / total * 100, 1) for c in counts]
            rows.append([band, ep, total, *pct,
                         f"{_MONTH_NAMES[peak_m]} ({max(counts)})"])
    p(f"Sterbemonate: {sum(counter.values()):,} datierte Sterbefälle", tag="ok")
    return rows


# ── Empfängnis-Monate (Geburts­monat − 9) ─────────────────────────────────────

CONCEPTION_MONTH_HEADERS = BIRTH_MONTH_HEADERS


def analyze_conception_months(individuals, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Empfängnis-Monats-Schätzung (Geburtsmonat − 9) …")
    counter: dict = defaultdict(int)
    for indi in individuals.values():
        ev = indi.get("BIRT") or {}
        month = _extract_month(ev.get("DATE"))
        year  = ev.get("YEAR") or safe_extract_year(ev.get("DATE"))
        if not (month and year):
            continue
        # 9 Monate zurück: Januar-Geburt → Empfängnis April Vorjahr
        cm = month - 9
        cy = year
        if cm < 1:
            cm += 12
            cy -= 1
        ep = _epoch(cy)
        if ep:
            counter[(ep, cm)] += 1
    rows = _build_dist_table(counter)
    p(f"Empfängnis-Monate: {sum(counter.values()):,} geschätzt", tag="ok")
    return rows
