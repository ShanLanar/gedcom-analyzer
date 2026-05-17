# -*- coding: utf-8 -*-
"""tasks/imputation.py – Schätzung fehlender Geburtsjahre aus Familienkontext."""

import math
from statistics import median

from lib.gedcom import safe_extract_year


IMPUTATION_HEADERS = [
    "Person-ID", "Name", "Geschlecht",
    "Verfügbare Quellen", "Geschätztes Geburtsjahr",
    "Konfidenz-Intervall", "Konfidenz-Klasse",
]

# Typischer Generationenabstand in Mitteleuropa (Jahre).
_GEN_GAP = 27
# Toleranz innerhalb einer Quelle (Eltern/Kinder ± dieser Wert).
_GEN_SPREAD = 27
# Typische Heiratsaltersdifferenz (Jahre).
_SPOUSE_SPREAD = 3
# Spannweite zu Geschwistern (Jahre).
_SIB_SPREAD = 5


def _bio_year(pdata: dict) -> int | None:
    """Geburtsjahr aus dem Original-Record – ohne Schätzung."""
    if not pdata:
        return None
    birt = pdata.get("BIRT") or {}
    y = birt.get("YEAR")
    if y is not None:
        return y
    return safe_extract_year(birt.get("DATE"))


def _parent_ids(pdata: dict, families: dict) -> list:
    out = []
    for fid in pdata.get("FAMC", []) or []:
        fam = families.get(fid)
        if not fam:
            continue
        for role in ("HUSB", "WIFE"):
            pid = fam.get(role)
            if pid:
                out.append(pid)
    return out


def _child_ids(pdata: dict, families: dict) -> list:
    out = []
    for fid in pdata.get("FAMS", []) or []:
        fam = families.get(fid)
        if not fam:
            continue
        for cid in fam.get("CHIL", []) or []:
            out.append(cid)
    return out


def _spouse_ids(pid: str, pdata: dict, families: dict) -> list:
    out = []
    for fid in pdata.get("FAMS", []) or []:
        fam = families.get(fid)
        if not fam:
            continue
        for role in ("HUSB", "WIFE"):
            sid = fam.get(role)
            if sid and sid != pid:
                out.append(sid)
    return out


def _sibling_ids(pid: str, pdata: dict, families: dict) -> list:
    out = []
    for fid in pdata.get("FAMC", []) or []:
        fam = families.get(fid)
        if not fam:
            continue
        for cid in fam.get("CHIL", []) or []:
            if cid != pid:
                out.append(cid)
    return out


def _classify(spread: float, sources_count: int) -> str:
    if spread <= 5 and sources_count >= 2:
        return "HOCH"
    if spread <= 15:
        return "MITTEL"
    return "NIEDRIG"


def impute_missing_dates(individuals, families, progress_cb=None) -> list:
    """Schätzt Geburtsjahre für Personen ohne BIRT.YEAR aus Familienkontext."""
    p = progress_cb or (lambda m, **kw: None)
    p("Geburtsjahr-Imputation …")

    rows: list = []

    for pid, pdata in individuals.items():
        if _bio_year(pdata) is not None:
            continue  # nur fehlende Werte

        estimates: list = []  # (estimate_year, label)
        labels: list = []

        # 1. Eltern → Kind: parent_year + GEN_GAP
        parent_years = []
        for par_id in _parent_ids(pdata, families):
            par = individuals.get(par_id)
            if not par:
                continue
            py = _bio_year(par)
            if py:
                parent_years.append(py)
        if parent_years:
            est = sum(parent_years) / len(parent_years) + _GEN_GAP
            estimates.append((est, "Eltern"))
            labels.append("Eltern")

        # 2. Kinder → Elternteil: median(child_year) - GEN_GAP
        child_years = []
        for cid in _child_ids(pdata, families):
            ch = individuals.get(cid)
            if not ch:
                continue
            cy = _bio_year(ch)
            if cy:
                child_years.append(cy)
        if child_years:
            est = median(child_years) - _GEN_GAP
            estimates.append((est, "Kinder"))
            labels.append("Kinder")

        # 3. Ehepartner → ± wenige Jahre (Mittelwert der Partner)
        spouse_years = []
        for sid in _spouse_ids(pid, pdata, families):
            sp = individuals.get(sid)
            if not sp:
                continue
            sy = _bio_year(sp)
            if sy:
                spouse_years.append(sy)
        if spouse_years:
            est = sum(spouse_years) / len(spouse_years)
            estimates.append((est, "Ehepartner"))
            labels.append("Ehepartner")

        # 4. Geschwister → Mittelwert
        sib_years = []
        for sib_id in _sibling_ids(pid, pdata, families):
            sib = individuals.get(sib_id)
            if not sib:
                continue
            sy = _bio_year(sib)
            if sy:
                sib_years.append(sy)
        if sib_years:
            est = sum(sib_years) / len(sib_years)
            estimates.append((est, "Geschwister"))
            labels.append("Geschwister")

        if not estimates:
            continue

        vals = [v for v, _ in estimates]
        mean = sum(vals) / len(vals)
        if len(vals) >= 2:
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            std = math.sqrt(var)
        else:
            # Quellen-spezifische A-priori-Unsicherheit, wenn nur eine Quelle.
            src = estimates[0][1]
            std = {
                "Eltern":     _GEN_SPREAD,
                "Kinder":     _GEN_SPREAD,
                "Ehepartner": _SPOUSE_SPREAD,
                "Geschwister": _SIB_SPREAD,
            }.get(src, _GEN_SPREAD)

        spread = std
        est_year = int(round(mean))
        ci = f"{est_year} ± {int(round(spread))}"
        klass = _classify(spread, len(estimates))

        rows.append([
            pid,
            (pdata.get("NAME") or "").strip(),
            pdata.get("SEX") or "",
            ", ".join(labels),
            est_year,
            ci,
            klass,
        ])

    _RANK = {"HOCH": 0, "MITTEL": 1, "NIEDRIG": 2}
    rows.sort(key=lambda r: (_RANK.get(r[6], 9), r[4]))

    p(f"Imputation: {len(rows)} Schätzungen", tag="ok")
    return rows
