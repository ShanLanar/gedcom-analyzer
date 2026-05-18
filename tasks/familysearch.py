# -*- coding: utf-8 -*-
"""
tasks/familysearch.py — Generiert direkte Such-URLs für FamilySearch,
damit Ahnen mit einem Klick im FamilySearch-Familienbaum/Quellen-Pool
gegengeprüft werden können.

Strategie: Statt OAuth + API-Key (komplex, Developer-Account nötig)
generieren wir vorbereitete Suchlinks. Der Browser nimmt Auth und UI
übernimmt. Eingaben pro Person: Vor-/Nachname, Geburtsjahr ±2, Ort.

Output:
  1. Records-Suche  (alle Quellen: Kirchenbücher, Volkszählungen, Pässe)
  2. Familienbaum-Suche (das öffentliche FamilySearch-Family-Tree)
"""

import re
import urllib.parse

from lib.gedcom import safe_extract_year


_FS_RECORDS_BASE = "https://www.familysearch.org/search/record/results"
_FS_TREE_BASE    = "https://www.familysearch.org/search/tree/results"


# ── Namens-/Datums-Extraktion ──────────────────────────────────────────────────

def _split_name(name: str) -> tuple[str, str]:
    """GEDCOM-Name 'Hans Peter /Müller/ jun.' → ('Hans Peter', 'Müller')."""
    if not name:
        return "", ""
    # Symbole entfernen
    cleaned = re.sub(r"[✠★⚔‡]", "", name).strip()
    cleaned = re.sub(r"\bmig\.\S*\b", "", cleaned, flags=re.IGNORECASE).strip()
    if "/" in cleaned:
        parts = cleaned.split("/")
        given = parts[0].strip()
        surname = parts[1].strip() if len(parts) >= 2 else ""
        return given, surname
    words = cleaned.split()
    return (" ".join(words[:-1]), words[-1]) if len(words) > 1 else (cleaned, "")


def _first_place_token(place: str) -> str:
    """Erste Stadt-Komponente eines Komma-getrennten Ortsstrings."""
    if not place:
        return ""
    return place.split(",")[0].strip()


# ── URL-Bauer ──────────────────────────────────────────────────────────────────

def build_records_url(person_data: dict) -> str:
    """Sucht in den Quellen-Datenbanken (Kirchenbücher, Census etc.)."""
    given, surname = _split_name(person_data.get("NAME") or "")
    birth = person_data.get("BIRT") or {}
    birth_year = birth.get("YEAR") or safe_extract_year(birth.get("DATE"))
    birth_city = _first_place_token(birth.get("PLAC") or "")
    death = person_data.get("DEAT") or {}
    death_year = death.get("YEAR") or safe_extract_year(death.get("DATE"))

    params = {}
    if given:
        params["q.givenName"] = given
    if surname:
        params["q.surname"] = surname
    if birth_year:
        params["q.birthLikeDate.from"] = str(birth_year - 2)
        params["q.birthLikeDate.to"]   = str(birth_year + 2)
    if birth_city:
        params["q.birthLikePlace"] = birth_city
    if death_year:
        params["q.deathLikeDate.from"] = str(death_year - 2)
        params["q.deathLikeDate.to"]   = str(death_year + 2)
    if not params:
        return ""
    return _FS_RECORDS_BASE + "?" + urllib.parse.urlencode(params)


def build_tree_url(person_data: dict) -> str:
    """Sucht im öffentlichen FamilySearch Family Tree (PIDs)."""
    given, surname = _split_name(person_data.get("NAME") or "")
    birth = person_data.get("BIRT") or {}
    birth_year = birth.get("YEAR") or safe_extract_year(birth.get("DATE"))
    birth_city = _first_place_token(birth.get("PLAC") or "")

    params = {}
    if given:
        params["q.givenName"] = given
    if surname:
        params["q.surname"] = surname
    if birth_year:
        params["q.birthLikeDate.from"] = str(birth_year - 5)
        params["q.birthLikeDate.to"]   = str(birth_year + 5)
    if birth_city:
        params["q.birthLikePlace"] = birth_city
    if not params:
        return ""
    return _FS_TREE_BASE + "?" + urllib.parse.urlencode(params)


# ── Such-Qualitäts-Score ──────────────────────────────────────────────────────

def _search_quality_score(person_data: dict) -> int:
    """0–100: wie gut sind die Daten zur eindeutigen Identifikation?"""
    score = 0
    name = person_data.get("NAME") or ""
    if "/" in name:
        score += 25   # mit Nachname
    elif name:
        score += 5    # nur ein Name
    birth = person_data.get("BIRT") or {}
    death = person_data.get("DEAT") or {}
    if birth.get("YEAR"): score += 25
    if birth.get("PLAC"): score += 20
    if death.get("YEAR"): score += 15
    if death.get("PLAC"): score += 10
    if person_data.get("FAMS"):
        score += 5    # verheiratet → mehr Quellen wahrscheinlich
    return min(score, 100)


# ── Sheet-Output ───────────────────────────────────────────────────────────────

FAMILYSEARCH_HEADERS = [
    "Person-ID", "Name", "Such-Qualität",
    "Geburtsjahr", "Geburtsort", "Sterbejahr", "Sterbeort",
    "FamilySearch-Quellen-Suche", "FamilySearch-Tree-Suche",
]


def generate_familysearch_lookup_sheet(individuals, root_related_ids=None,
                                          min_quality=40, max_rows=2000,
                                          progress_cb=None) -> list:
    """
    Generiert pro Ahn eine vorbereitete FamilySearch-Such-URL.
    Sortiert nach Such-Qualität (beste Treffer-Chance zuerst).

    Standardmäßig auf Root-verwandte Personen begrenzt (über
    root_related_ids), weil eine Suche über 130k Personen mit URL-Klick
    nicht praktikabel ist.
    """
    p = progress_cb or (lambda m, **kw: None)
    p("FamilySearch-Suchlinks generieren …")

    scope = root_related_ids if root_related_ids else set(individuals.keys())
    rows = []
    for iid in scope:
        person = individuals.get(iid)
        if not person:
            continue
        quality = _search_quality_score(person)
        if quality < min_quality:
            continue
        records_url = build_records_url(person)
        tree_url    = build_tree_url(person)
        if not records_url and not tree_url:
            continue
        birth = person.get("BIRT") or {}
        death = person.get("DEAT") or {}
        rows.append([
            iid,
            (person.get("NAME") or "")[:60],
            quality,
            birth.get("YEAR") or "",
            (birth.get("PLAC") or "")[:50],
            death.get("YEAR") or "",
            (death.get("PLAC") or "")[:50],
            records_url,
            tree_url,
        ])

    rows.sort(key=lambda r: r[2], reverse=True)
    rows = rows[:max_rows]
    p(f"FamilySearch-Links: {len(rows):,} Ahnen mit klickbarer Such-URL",
      tag="ok")
    return rows
