# -*- coding: utf-8 -*-
"""tasks/research_suggestions.py – Recherche-Vorschläge.

Generiert konkrete, handlungsorientierte Vorschläge für Personen mit
Lücken im Datensatz."""

from lib.gedcom import safe_extract_year

RESEARCH_SUGGESTION_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr",
    "Kategorie", "Vorschlag", "Priorität",
]

_PRIORITY_ORDER = {"HOCH": 0, "MITTEL": 1, "NIEDRIG": 2}


def _name(pdata: dict) -> str:
    return (pdata.get("NAME") or "").strip()


def _birth_year(pdata: dict):
    birt = pdata.get("BIRT") or {}
    return birt.get("YEAR") or safe_extract_year(birt.get("DATE"))


def _death_year(pdata: dict):
    deat = pdata.get("DEAT") or {}
    return deat.get("YEAR") or safe_extract_year(deat.get("DATE"))


def _parents_birth_years(pdata: dict, individuals: dict, families: dict):
    years = []
    for fam_id in pdata.get("FAMC") or []:
        fam = families.get(fam_id)
        if not fam:
            continue
        for parent_id in (fam.get("HUSB"), fam.get("WIFE")):
            if not parent_id:
                continue
            parent = individuals.get(parent_id)
            if not parent:
                continue
            by = _birth_year(parent)
            if by:
                years.append(by)
    return years


def _has_given_and_surname(name: str) -> tuple[bool, bool]:
    """Liefert (has_given, has_surname)."""
    if not name:
        return (False, False)
    if "/" in name:
        parts = name.split("/")
        given = parts[0].strip()
        surname = parts[1].strip() if len(parts) >= 2 else ""
        return (bool(given), bool(surname))
    words = name.strip().split()
    if not words:
        return (False, False)
    # Ohne /…/-Marker: Annahme, dass nur ein einziges Wort = unvollständig
    if len(words) == 1:
        return (True, False)
    return (True, True)


def _spouses_with_birth_years(pdata: dict, pid: str, individuals: dict,
                               families: dict):
    """Liefert für jede Ehe (fam_id, fam, spouse_birth_year_or_None)."""
    out = []
    for fam_id in pdata.get("FAMS") or []:
        fam = families.get(fam_id)
        if not fam:
            continue
        spouse_id = fam.get("WIFE") if fam.get("HUSB") == pid else fam.get("HUSB")
        spouse = individuals.get(spouse_id) if spouse_id else None
        spouse_by = _birth_year(spouse) if spouse else None
        out.append((fam_id, fam, spouse_by))
    return out


def generate_research_suggestions(individuals, families, top_n: int = 200,
                                   progress_cb=None) -> list:
    """Generiert Vorschläge mit Priorität für jede Person mit Datenlücken."""
    p = progress_cb or (lambda m, **kw: None)
    p("Recherche-Vorschläge …")

    # Pro Person: Liste der (Kategorie, Vorschlag, Priorität)
    suggestions_by_pid: dict = {}

    def _add(pid: str, kategorie: str, vorschlag: str, prio: str):
        suggestions_by_pid.setdefault(pid, []).append((kategorie, vorschlag, prio))

    for pid, pdata in individuals.items():
        name = _name(pdata)
        by = _birth_year(pdata)
        dy = _death_year(pdata)
        birt = pdata.get("BIRT") or {}
        bp = birt.get("PLAC")
        famc = pdata.get("FAMC") or []
        fams = pdata.get("FAMS") or []

        # 1. Fehlende Eltern + Geburtsort + Geburtsjahr → HOCH
        if not famc and bp and by:
            _add(pid, "Fehlende Eltern",
                 f"Suche Geburtseintrag in {bp} um {by}", "HOCH")

        # 2. Fehlendes Geburtsjahr + Eltern mit bekannten Jahren → MITTEL
        if not by:
            p_years = _parents_birth_years(pdata, individuals, families)
            if p_years:
                avg = sum(p_years) / len(p_years)
                est = int(round(avg + 27))
                _add(pid, "Fehlendes Geburtsjahr",
                     f"Geburtsjahr vermutlich um {est}, Quelle prüfen",
                     "MITTEL")

        # 3. Fehlendes Sterbejahr + Geburtsjahr + wahrscheinlich verstorben
        if by and not dy and by < 1930:
            _add(pid, "Fehlendes Sterbejahr",
                 f"Sterbeeintrag suchen — Geburtsjahr {by}, "
                 f"plausible Sterbespanne {by + 50}–{by + 90}", "MITTEL")

        # 4. Ehepartner ohne Heiratsdatum + beide Geburtsjahre bekannt
        for fam_id, fam, spouse_by in _spouses_with_birth_years(
                pdata, pid, individuals, families):
            if fam.get("MARR_DATE"):
                continue
            if by is None or spouse_by is None:
                continue
            base = max(by, spouse_by)
            _add(pid, "Fehlende Heirat",
                 f"Heiratseintrag fehlt — plausible Spanne "
                 f"{base + 20}–{base + 35}", "MITTEL")

        # 5. Kinder vorhanden, aber FAMS ohne Heiratseintrag → NIEDRIG
        for fam_id in fams:
            fam = families.get(fam_id)
            if not fam:
                continue
            if fam.get("CHIL") and not fam.get("MARR_DATE"):
                _add(pid, "Familie ohne Heirat",
                     "Familie ohne Heiratsangabe — Kirchenbuch prüfen",
                     "NIEDRIG")
                break

        # 6. Name unvollständig
        has_given, has_surname = _has_given_and_surname(name)
        if not (has_given and has_surname):
            has_other_data = bool(by or dy or bp or famc or fams)
            prio = "HOCH" if has_other_data else "MITTEL"
            _add(pid, "Unvollständiger Name", "Name unvollständig", prio)

    # In Zeilen umwandeln
    rows = []
    for pid, sugg_list in suggestions_by_pid.items():
        pdata = individuals.get(pid) or {}
        name = _name(pdata)
        by = _birth_year(pdata) or ""
        for kategorie, vorschlag, prio in sugg_list:
            rows.append([pid, name, by, kategorie, vorschlag, prio])

    # Pro Person die Anzahl der Vorschläge kennen, damit wir
    # sekundär nach "viele Lücken" sortieren können.
    counts = {pid: len(s) for pid, s in suggestions_by_pid.items()}

    def _sort_key(row):
        prio_rank = _PRIORITY_ORDER.get(row[5], 99)
        return (prio_rank, -counts.get(row[0], 0))

    rows.sort(key=_sort_key)

    if top_n is not None and top_n > 0:
        rows = rows[:top_n]

    p(f"Recherche-Vorschläge: {len(rows)} Zeilen", tag="ok")
    return rows
