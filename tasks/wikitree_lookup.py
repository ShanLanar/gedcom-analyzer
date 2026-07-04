# -*- coding: utf-8 -*-
"""
tasks/wikitree_lookup.py — WikiTree-Profil-Suche für Ahnen.

WikiTree (wikitree.com) ist das größte freie genealogische Netzwerk mit
37+ Mio. kollaborativen Profilen. Die public API liefert strukturierte
Daten zu Personen ohne API-Key (GET-only, Rate-Limit ~1 Req/s).

Für jeden Ahnen im GEDCOM:
  1. WikiTree-Such-URL (immer erzeugt — kein API-Call nötig)
  2. Optional: GET-Anfrage an https://api.wikitree.com/api.php
       action=searchPerson → WikiTree-ID + Profil-URL + Geburtsdaten
     Scheitert (403, Timeout) → nur URL bleibt erhalten.

Ausgabe: Sheet "WikiTree-Profile" im Excel-Export
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from tasks._online_common import first_place as _first
from tasks._online_common import split_name as _split_name
from tasks._online_common import year_of as _yr

_API_BASE   = "https://api.wikitree.com/api.php"
_PROFILE    = "https://www.wikitree.com/wiki/"
_SEARCH     = "https://www.wikitree.com/index.php"
_USER_AGENT = (
    "gedcom-analyzer/9.0 (genealogy research; "
    "github.com/shanlanar/gedcom-analyzer)"
)
_DELAY    = 1.2   # Sekunden zwischen API-Calls
_MAX_PERS = 400   # max. Personen für API-Calls

WIKITREE_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr", "Geburtsort",
    "Sterbejahr", "Sterbeort",
    "WikiTree-ID", "WikiTree-Name",
    "WT-Geburtsjahr", "WT-Sterbeort", "Konfidenz",
    "Profil-URL", "Such-URL",
]


# ── Hilfsfunktionen (gemeinsam in tasks/_online_common) ───────────────────────


# ── URL-Builder ───────────────────────────────────────────────────────────────

def _search_url(given: str, surname: str, by: int | None) -> str:
    params: dict = {"title": "Special:SearchPerson", "wpSurname": surname}
    if given:
        params["wpFirst"] = given.split()[0]
    if by:
        params["wpBirthYear"] = str(by)
    return _SEARCH + "?" + urllib.parse.urlencode(params)


# ── API-Abfrage ───────────────────────────────────────────────────────────────

def _api_search(given: str, surname: str, by: int | None) -> dict | None:
    params: dict = {
        "action":   "searchPerson",
        "format":   "json",
        "Last":     surname,
        "fields":   "Id,Name,FirstName,LastNameAtBirth,BirthDate,DeathDate,"
                    "BirthLocation,DeathLocation",
        "limit":    "3",
    }
    if given:
        params["First"] = given.split()[0]
    if by:
        params["BirthYear"] = str(by)
    url = _API_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return None
    # Antwortformat: list oder {"searchResult": list}
    results = data
    if isinstance(data, dict):
        results = data.get("searchResult") or data.get("results") or []
    if not isinstance(results, list) or not results:
        return None
    return results[0]


def _confidence(ged_given: str, ged_surname: str, ged_by: int | None,
                wt: dict) -> tuple[str, float]:
    """Konfidenz-Berechnung mit numerischem Score (0.0–1.0).

    Strategie:
      - Name-Match: Nachname exakt (oder Fuzzy) → 0.5–0.8 Punkte
      - Geburtsjahr-Match: ±5 Jahre → +0.15 Punkte; ±2 Jahre → +0.35 Punkte
      - Vornamen-Match (erste Zeichen): +0.15 Punkte

    Konfidenz-Level:
      - HOCH (≥0.85): Exakter Name + ±5 Jahre
      - MITTEL (0.65–0.85): Fuzzy-Match oder Jahr-Range
      - NIEDRIG (<0.65): Nur Name oder nur Jahr
    """
    wt_sn  = (wt.get("LastNameAtBirth") or "").lower()
    ged_sn = ged_surname.lower()
    if not wt_sn or not ged_sn:
        return "NIEDRIG", 0.0

    score = 0.0

    # Nachname-Match
    if ged_sn == wt_sn:
        score += 0.8  # Exakter Nachname-Match
    elif ged_sn in wt_sn or wt_sn in ged_sn:
        score += 0.5  # Teilmatch (Fuzzy)
    else:
        return "NIEDRIG", 0.0  # Nachname stimmt nicht überein

    # Geburtsjahr-Match
    wt_birth = (wt.get("BirthDate") or "")[:4]
    if ged_by and wt_birth and wt_birth.isdigit():
        yr_diff = abs(int(wt_birth) - ged_by)
        if yr_diff <= 2:
            score += 0.35  # ±2 Jahre (sehr hohe Wahrscheinlichkeit)
        elif yr_diff <= 5:
            score += 0.15  # ±5 Jahre (moderates Alter-Fuzzing)

    # Vornamen-Match (erste 2 Zeichen)
    wt_given = (wt.get("FirstName") or "").lower()
    if ged_given and wt_given:
        ged_given_first = ged_given.split()[0].lower()
        if ged_given_first == wt_given or \
           ged_given_first[:2] == wt_given[:2] or \
           ged_given_first.startswith(wt_given[:1]):
            score += 0.15

    # Level bestimmen
    if score >= 0.85:
        level = "HOCH"
    elif score >= 0.65:
        level = "MITTEL"
    else:
        level = "NIEDRIG"

    return level, score


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def run_wikitree_lookup(individuals: dict, root_related_ids=None,
                        progress_cb=None,
                        max_persons: int = _MAX_PERS,
                        scrape: bool = True) -> list:
    """Sucht WikiTree-Profile für Ahnen im GEDCOM.

    Gibt rows zurück (je eine pro Person) für das Excel-Sheet.
    """
    p = progress_cb or (lambda m, **kw: None)
    p("WikiTree-Suche: Ahnen auswählen …")

    scope = root_related_ids if root_related_ids is not None else set(individuals.keys())
    # Filter: mit Name, Geburtsjahr vorhanden, nicht zu jung, DACH bevorzugt.
    # Iteration über individuals (Einfügereihenfolge) statt über das Set —
    # macht die Auswahl bei max_persons-Begrenzung deterministisch.
    candidates = []
    for pid in individuals:
        if pid not in scope:
            continue
        pdata = individuals.get(pid)
        if not pdata:
            continue
        name = (pdata.get("NAME") or "").strip()
        if not name:
            continue
        by = _yr(pdata.get("BIRT") or {})
        if by and by > 1940:
            continue
        candidates.append(pid)

    p(f"  {len(candidates):,} Personen, davon max. {max_persons} abgefragt")
    rows: list = []
    found = 0

    for i, pid in enumerate(candidates[:max_persons]):
        pdata = individuals[pid]
        birt  = pdata.get("BIRT") or {}
        deat  = pdata.get("DEAT") or {}
        by    = _yr(birt)
        dy    = _yr(deat)
        bp    = _first(birt.get("PLAC") or "")
        dp    = _first(deat.get("PLAC") or "")

        given, surname = _split_name(pdata.get("NAME") or "")
        if not surname:
            continue

        if i % 25 == 0 and i:
            p(f"  … {i}/{min(len(candidates), max_persons)}, {found} mit Treffer")

        s_url = _search_url(given, surname, by)
        wt_id = wt_name = wt_by = wt_dp = konfidenz = ""
        p_url = ""

        if scrape:
            wt = _api_search(given, surname, by)
            time.sleep(_DELAY)
            if wt:
                found += 1
                wt_id   = str(wt.get("Id") or wt.get("Name") or "")
                wt_name = (wt.get("FirstName", "") + " " +
                           wt.get("LastNameAtBirth", "")).strip()
                wt_by   = (wt.get("BirthDate") or "")[:4]
                wt_dp   = _first(wt.get("DeathLocation") or "")
                konfidenz, score = _confidence(given, surname, by, wt)
                p_url   = _PROFILE + wt_id if wt_id else ""

        rows.append([
            pid,
            (pdata.get("NAME") or "").strip(),
            by or "", bp,
            dy or "", dp,
            wt_id, wt_name, wt_by, wt_dp, konfidenz,
            p_url,
            s_url,
        ])

    mode = f"(davon {found} mit WikiTree-Profil)" if scrape else "(Such-URL-Modus)"
    p(f"WikiTree-Lookup: {len(rows):,} Personen {mode}", tag="ok")
    return rows
