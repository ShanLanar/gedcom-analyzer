# -*- coding: utf-8 -*-
"""
tasks/grabstein.py — Grabstein-Datenbanken durchsuchen.

Generiert Such-Links für Personen ohne Bestattungsort (oder ohne Sterbedatum)
die wahrscheinlich in Deutschland/Österreich/Schweiz begraben wurden:

  • BillionGraves       (billiongraves.com)       — größte GPS-Grabsteindb
  • FindAGrave          (findagrave.com)           — Ancestry-Tochter, weltweit
  • Grabstein-Projekt   (grabsteine.genealogy.net) — deutschsprachiger Fokus
  • Volksbund VDK       (volksbund.de)             — Kriegsgräber WWI+WWII
  • Jüdische Friedhöfe  (uni-heidelberg.de)        — falls Namen darauf hindeuten

Keine API-Keys erforderlich. Nur Lesezugriff.
"""

import re
import urllib.parse

from tasks._online_common import first_place as _first
from tasks._online_common import split_name as _split_name
from tasks._online_common import year_of as _yr

GRABSTEIN_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr", "Geburtsort",
    "Sterbejahr", "Sterbeort", "Hinweis",
    "BillionGraves", "FindAGrave",
    "Grabstein-Projekt", "Volksbund-Kriegsgräber",
    "Jüdische Friedhöfe",
    "Konfidenz",
]

_DACH = {
    "deutschland", "germany", "niedersachsen", "westfalen", "preußen",
    "sachsen", "thüringen", "bayern", "württemberg", "hessen", "rheinland",
    "österreich", "austria", "schweiz", "switzerland",
    "osnabrück", "münster", "hannover", "bremen", "hamburg",
    "köln", "dortmund", "düsseldorf",
}

_JEWISH_NAMES = {
    "abraham", "isaak", "jakob", "moses", "salomon", "david", "leib",
    "mendel", "samuel", "joseph", "juda", "baruch", "elias",
    "sara", "rebekka", "rachel", "lea", "miriam", "esther",
}


def _is_dach(plac: str) -> bool:
    if not plac:
        return True
    return any(w in plac.lower() for w in _DACH)


def _might_be_jewish(given: str) -> bool:
    return given.split()[0].lower() in _JEWISH_NAMES if given else False


# ── URL-Builder ───────────────────────────────────────────────────────────────

def _billiongraves(given, surname, by, dy, place):
    params: dict = {"record_type": "1"}
    if given:
        params["given_names"] = given
    if surname:
        params["family_names"] = surname
    if by:
        params["birth_year"] = str(by)
        params["birth_year_range"] = "5"
    if dy:
        params["death_year"] = str(dy)
        params["death_year_range"] = "5"
    if place:
        params["country"] = "Deutschland"
    return "https://billiongraves.com/pages/search/#" + urllib.parse.urlencode(params)


def _findagrave(given, surname, by, dy):
    params: dict = {"country": "Germany"}
    if given:
        params["firstname"] = given
    if surname:
        params["lastname"] = surname
    if by:
        params["birthyear"] = str(by)
        params["birthyearfilter"] = "5"
    if dy:
        params["deathyear"] = str(dy)
        params["deathyearfilter"] = "5"
    return "https://www.findagrave.com/memorial/search?" + urllib.parse.urlencode(params)


def _grabstein_projekt(surname, by):
    params: dict = {}
    if surname:
        params["na"] = surname
    if by:
        params["gj"] = str(by)
    return "https://grabsteine.genealogy.net/suche.php?" + urllib.parse.urlencode(params)


def _volksbund(given, surname, by):
    """Volksbund Deutsche Kriegsgräberfürsorge — WWI & WWII."""
    params: dict = {}
    if given:
        params["vorname"] = given
    if surname:
        params["familienname"] = surname
    if by:
        params["geburtsjahr"] = str(by)
    return "https://www.volksbund.de/graebersuche?" + urllib.parse.urlencode(params)


def _jewish_cemeteries(given, surname, by):
    """Zentralarchiv judaica-uni-heidelberg — jüdische Friedhöfe."""
    q = " ".join(filter(None, [given, surname]))
    params: dict = {"q": q}
    return "https://www.steinheim-institut.de/cgi-bin/epidat?sel=grb&q=" + urllib.parse.quote(q)


def _confidence(surname, by, dy) -> str:
    if surname and by and dy:
        return "HOCH"
    if surname and by:
        return "MITTEL"
    return "NIEDRIG"


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def run_grabstein_search(individuals: dict, root_related_ids=None,
                         progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Grabstein-Suche: Links generieren …")

    scope = root_related_ids or set(individuals.keys())
    rows  = []

    for pid in scope:
        pdata = individuals.get(pid)
        if not pdata:
            continue

        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}

        by = _yr(birt)
        dy = _yr(deat)
        bp = (birt.get("PLAC") or "").strip()
        dp = (deat.get("PLAC") or "").strip()

        # Personen, die wahrscheinlich noch leben, überspringen
        if not by or by > 1940:
            continue
        if by > 1920 and not dy:
            continue
        if not _is_dach(bp or dp):
            continue

        given, surname = _split_name(pdata.get("NAME") or "")
        if not surname:
            continue

        place = _first(dp or bp)
        is_war = 1870 <= by <= 1928
        is_jewish = _might_be_jewish(given)

        hinweise = []
        if is_war:
            hinweise.append("Kriegsgeneration")
        if is_jewish:
            hinweise.append("ggf. jüd. Friedhof")

        rows.append([
            pid,
            (pdata.get("NAME") or "").strip(),
            by or "",
            _first(bp),
            dy or "",
            _first(dp),
            " | ".join(hinweise),
            _billiongraves(given, surname, by, dy, place),
            _findagrave(given, surname, by, dy),
            _grabstein_projekt(surname, by),
            _volksbund(given, surname, by) if is_war else "",
            _jewish_cemeteries(given, surname, by) if is_jewish else "",
            _confidence(surname, by, dy),
        ])

    _RANK = {"HOCH": 0, "MITTEL": 1, "NIEDRIG": 2}
    rows.sort(key=lambda r: (_RANK.get(r[12], 9), r[2] or 9999))
    p(f"Grabstein-Links: {len(rows):,} Personen", tag="ok")
    return rows
