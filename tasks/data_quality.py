# -*- coding: utf-8 -*-
"""tasks/data_quality.py – Datenvollständigkeits-Score (0–100)"""

from collections import defaultdict
from lib.gedcom import safe_extract_year
from lib.helpers import safe_extract_family_name


WEIGHTS = {
    "birth_date":    20,
    "birth_place":   15,
    "death_date":    20,
    "death_place":   15,
    "marriage_date": 10,
    "parents":       10,
    "sex":           10,
}


def analyze_data_completeness(individuals, families, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Datenvollständigkeits-Analyse …")

    person_rows = []
    surname_scores: dict = defaultdict(list)
    epoch_scores: dict   = defaultdict(list)

    for pid, pdata in individuals.items():
        score = 0
        flags = {}

        bd = (pdata.get("BIRT") or {}).get("DATE", "")
        flags["birth_date"]  = bool(bd and safe_extract_year(bd))
        bp = (pdata.get("BIRT") or {}).get("PLAC", "")
        flags["birth_place"] = bool(bp and len(str(bp).strip()) > 2)
        dd = (pdata.get("DEAT") or {}).get("DATE", "")
        flags["death_date"]  = bool(dd and safe_extract_year(dd))
        dp = (pdata.get("DEAT") or {}).get("PLAC", "")
        flags["death_place"] = bool(dp and len(str(dp).strip()) > 2)

        flags["marriage_date"] = any(
            families.get(fid, {}).get("MARR_DATE")
            for fid in pdata.get("FAMS", []))
        flags["parents"] = any(
            (families.get(fid, {}).get("HUSB") or families.get(fid, {}).get("WIFE"))
            for fid in pdata.get("FAMC", []))
        sx = pdata.get("SEX", "U")
        flags["sex"] = sx in ("M", "F")

        for k, v in flags.items():
            if v: score += WEIGHTS[k]

        name    = pdata.get("NAME") or ""
        surname = safe_extract_family_name(name) or "Unbekannt"
        birth_year = safe_extract_year(bd) if flags["birth_date"] else None

        if birth_year:
            epoch = ("vor 1800" if birth_year < 1800
                     else "1800–1849" if birth_year < 1850
                     else "1850–1899" if birth_year < 1900
                     else "1900–1949" if birth_year < 1950
                     else "nach 1950")
        else:
            epoch = "unbekannt"

        if score >= 80:   klasse = "sehr gut (≥80)"
        elif score >= 60: klasse = "gut (60–79)"
        elif score >= 40: klasse = "mittel (40–59)"
        elif score >= 20: klasse = "schwach (20–39)"
        else:             klasse = "sehr schwach (<20)"

        person_rows.append([
            pid, name[:40],
            "M" if sx == "M" else "F" if sx == "F" else "U",
            birth_year or "", epoch, surname[:25],
            score, klasse,
            "✓" if flags["birth_date"]  else "✗",
            "✓" if flags["birth_place"] else "✗",
            "✓" if flags["death_date"]  else "✗",
            "✓" if flags["death_place"] else "✗",
            "✓" if flags["marriage_date"] else "✗",
            "✓" if flags["parents"] else "✗",
            "✓" if flags["sex"]    else "✗",
        ])
        surname_scores[surname].append(score)
        epoch_scores[epoch].append(score)

    person_rows.sort(key=lambda x: x[6])  # schlechteste zuerst

    surname_summary = [
        [sn, len(sc), round(sum(sc)/len(sc), 1), min(sc), max(sc)]
        for sn, sc in sorted(surname_scores.items(),
                             key=lambda x: sum(x[1])/len(x[1]))
    ][:500]

    epoch_order = ["vor 1800", "1800–1849", "1850–1899",
                   "1900–1949", "nach 1950", "unbekannt"]
    epoch_summary = []
    for ep in epoch_order:
        sc = epoch_scores.get(ep, [])
        if sc:
            epoch_summary.append([ep, len(sc), round(sum(sc)/len(sc), 1),
                                   min(sc), max(sc)])

    avg = sum(r[6] for r in person_rows) / len(person_rows) if person_rows else 0
    very_weak = sum(1 for r in person_rows if r[6] < 20)
    p(f"Datenvollständigkeit: Ø {avg:.1f}/100, {very_weak} sehr schwache Einträge",
      tag="ok")
    return person_rows, surname_summary, epoch_summary


PERSON_HEADERS = [
    "ID", "Name", "Geschlecht", "Geburtsjahr", "Epoche", "Nachname",
    "Score (0–100)", "Klasse",
    "Geburtsdatum", "Geburtsort", "Sterbedatum", "Sterbeort",
    "Heiratsdatum", "Eltern bekannt", "Geschlecht bekannt"
]
SURNAME_HEADERS = ["Nachname", "Anzahl Personen", "Ø Score", "Min Score", "Max Score"]
EPOCH_HEADERS   = ["Epoche", "Anzahl Personen", "Ø Score", "Min Score", "Max Score"]
