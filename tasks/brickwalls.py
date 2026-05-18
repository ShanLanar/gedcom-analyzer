# -*- coding: utf-8 -*-
"""tasks/brickwalls.py – Brick-Wall-Erkennung.

Identifiziert gut dokumentierte Personen ohne bekannte Eltern als
hochpriore Forschungsziele ("Brick Walls")."""

from lib.gedcom import safe_extract_year

BRICKWALL_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr", "Geburtsort",
    "Sterbejahr", "Recherche-Wert", "Kinder",
    "Vermutete Eltern-Geburtsj.", "Bemerkung",
]


def _name(pdata: dict) -> str:
    return (pdata.get("NAME") or "").strip()


def _has_given_and_surname(name: str) -> bool:
    if not name or "/" not in name:
        return False
    parts = name.split("/")
    given = parts[0].strip()
    surname = parts[1].strip() if len(parts) >= 2 else ""
    return bool(given) and bool(surname)


def _count_children(pdata: dict, families: dict) -> int:
    total = 0
    for fam_id in pdata.get("FAMS", []) or []:
        fam = families.get(fam_id)
        if not fam:
            continue
        total += len(fam.get("CHIL", []) or [])
    return total


def detect_brickwalls(individuals, families, progress_cb=None) -> list:
    """Liefert Brick-Wall-Personen mit Recherche-Wert >= 50, sortiert
    nach Recherche-Wert absteigend."""
    p = progress_cb or (lambda m, **kw: None)
    p("Brick-Wall-Erkennung …")

    rows = []
    for pid, pdata in individuals.items():
        famc = pdata.get("FAMC") or []
        # REQUIRED: keine Eltern verknüpft
        if famc:
            continue

        score = 30  # FAMC == []

        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE"))
        bp = birt.get("PLAC")
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE"))
        dp = deat.get("PLAC")

        if by:
            score += 15
        if bp:
            score += 15
        if dy:
            score += 10
        if dp:
            score += 10

        fams = pdata.get("FAMS") or []
        if fams:
            score += 5

        child_count = _count_children(pdata, families)
        if child_count >= 1:
            score += 5
        score += 5 * min(child_count, 4)

        name = _name(pdata)
        if _has_given_and_surname(name):
            score += 5

        if score < 50:
            continue

        # Eltern-Geburtsjahr-Spanne
        if by:
            parent_span = f"{by - 60}–{by - 18}"
        else:
            parent_span = "unbekannt"

        # Bemerkung
        if by and bp:
            bemerkung = (
                f"Suche Heiratseintrag um {by - 25}–{by - 20} in {bp}"
            )
        else:
            region = bp or "unbekannt"
            bemerkung = f"Eltern unbekannt — Heimatregion {region}"

        rows.append([
            pid, name, by or "", bp or "",
            dy or "", score, child_count,
            parent_span, bemerkung,
        ])

    rows.sort(key=lambda r: r[5], reverse=True)
    p(f"Brick Walls: {len(rows)} Personen mit Recherche-Wert >= 50", tag="ok")
    return rows
