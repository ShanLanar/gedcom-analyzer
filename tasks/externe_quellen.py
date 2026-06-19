# -*- coding: utf-8 -*-
"""
tasks/externe_quellen.py — Externe Recherche-Links pro Person.

Für Ahnen mit Datenlücken werden platform- und zeitraumspezifische
Such-Links generiert:

  Kirchenbücher (vor 1874):
    • Matricula Online   — kath. Diözesen
    • Archion            — ev. Kirchenbücher
    • FamilySearch       — weltweite Kirchenbücher (kostenlos)

  Zivilstand (ab 1874):
    • ArcInSys NI / NW   — Standesregister, Staatsarchive
    • Archivportal-D     — übergreifend

  Auswanderer:
    • Auswanderer Hamburg (Ancestry) — Hamburger Auswandererlisten 1850–1934
    • Ellis Island (Ancestry)        — US-Einwanderung
    • Bremerhaven (Auswandererhaus)  — Bremer Listen

  Militär & Kriegsopfer:
    • Bundesarchiv Freiburg          — WWI+WWII Personalakten
    • Volksbund VDK                  — Kriegsgräber
    • Verlustlisten WWI              — Ancestry/Akte-Leipzig

  Genealogie-Plattformen:
    • Geneanet           — 6 Mio+ europ. Bäume
    • Geni.com           — World Family Tree
    • WikiTree           — kollaborativer Baum (schon integriert)
    • WeRelate           — Wikipedia für Genealogie

  Presse & Nekrologe:
    • ZEFYS (Staatsbibliothek Berlin) — dt. Zeitungen bis 1945
    • Zeitungsportal NRW              — Westfalenblatt etc.
    • Zeitungsportal.de               — übergreifend

  Adressbücher & Einwohner:
    • Adressbuch-Portal  (adressbuecher.genealogy.net)
    • HathiTrust         — digitalisierte Adressbücher

  Linked Data:
    • Wikidata           — Fakten, GOV-ID, Koordinaten
    • GND/lobid          — Deutsche Nationalbibliothek

Keine API-Keys erforderlich. Nur Lesezugriff.
"""

import re
import urllib.parse

from lib.gedcom import safe_extract_year

EXTERNE_QUELLEN_HEADERS = [
    "Person-ID", "Name", "Geb.", "Geb.-Ort", "Gest.", "Gest.-Ort",
    "Zeitraum-Kategorie", "Besonderheit",
    # Kirchenbücher
    "Matricula", "Archion", "FamilySearch-Quellen",
    # Standesamt / Staatsarchiv
    "ArcInSys NI", "Archivportal-D",
    # Auswanderer
    "Hamburg-Listen (Ancestry)", "Ellis Island", "Auswandererhaus Bremerhaven",
    # Militär
    "Bundesarchiv Freiburg", "Volksbund VDK",
    # Genealogie-Plattformen
    "Geneanet", "Geni.com", "WeRelate",
    # Presse
    "ZEFYS-Zeitung", "Zeitungsportal NRW",
    # Adressbücher
    "Adressbuch-Portal", "HathiTrust-Adressbücher",
    # Linked Data
    "Wikidata-Suche", "GND/lobid",
]

_DACH = {
    "deutschland", "germany", "niedersachsen", "westfalen", "preußen",
    "sachsen", "thüringen", "bayern", "württemberg", "hessen", "rheinland",
    "österreich", "austria", "schweiz", "switzerland",
    "osnabrück", "münster", "hannover", "hamburg", "bremen",
}

_NRW_INDICATORS = {
    "westfalen", "rheinland", "nordrhein", "köln", "dortmund",
    "düsseldorf", "münster", "bielefeld", "paderborn",
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _split_name(name: str) -> tuple[str, str]:
    if not name:
        return "", ""
    cleaned = re.sub(r"[✠★⚔‡]", "", name).strip()
    cleaned = re.sub(r"\bmig\.\S*\b", "", cleaned, flags=re.IGNORECASE).strip()
    if "/" in cleaned:
        parts = cleaned.split("/")
        return parts[0].strip(), (parts[1].strip() if len(parts) >= 2 else "")
    words = cleaned.split()
    return (" ".join(words[:-1]), words[-1]) if len(words) > 1 else (cleaned, "")


def _yr(evt) -> int | None:
    if not evt:
        return None
    return evt.get("YEAR") or safe_extract_year(evt.get("DATE"))


def _first(plac: str) -> str:
    return plac.split(",")[0].strip() if plac else ""


def _is_dach(plac: str) -> bool:
    if not plac:
        return True
    return any(w in plac.lower() for w in _DACH)


def _is_nrw(plac: str) -> bool:
    return any(w in plac.lower() for w in _NRW_INDICATORS)


def _is_emigrant(pdata: dict) -> bool:
    name = (pdata.get("NAME") or "").lower()
    notes = (pdata.get("NOTE") or "").lower()
    return "mig." in name or "auswander" in notes or "emigr" in notes


def _zeitraum(by: int | None, dy: int | None) -> str:
    y = by or dy
    if not y:
        return "Unbekannt"
    if y < 1600:
        return "Frühe Neuzeit (<1600)"
    if y < 1750:
        return "Barock (1600–1750)"
    if y < 1875:
        return "Kirchenbuch-Epoche (1750–1874)"
    if y < 1920:
        return "Standesamt/Kaiserreich (1875–1919)"
    if y < 1946:
        return "Weimar/NS/WWII (1920–1945)"
    return "Nachkrieg (ab 1946)"


# ── URL-Generatoren ───────────────────────────────────────────────────────────

def _url(base: str, **params) -> str:
    non_empty = {k: v for k, v in params.items() if v}
    return base + ("?" + urllib.parse.urlencode(non_empty) if non_empty else "")


def _matricula(given, surname, place, by):
    p = _first(place)
    q = urllib.parse.quote(p or surname)
    return f"https://data.matricula-online.eu/de/suche/?q={q}"


def _archion(given, surname, place):
    p = _first(place)
    q = urllib.parse.quote(p or surname)
    return f"https://www.archion.de/p/browse/?search=1&q={q}"


def _familysearch(given, surname, by, place):
    params: dict = {}
    if given:
        params["q.givenName"] = given
    if surname:
        params["q.surname"] = surname
    if by:
        params["q.birthLikeDate.from"] = str(by - 3)
        params["q.birthLikeDate.to"]   = str(by + 3)
    if place:
        params["q.birthLikePlace"] = _first(place)
    return "https://www.familysearch.org/search/record/results?" + urllib.parse.urlencode(params)


def _arcinsys(surname, place):
    q = " ".join(filter(None, [surname, _first(place)]))
    return f"https://www.arcinsys.niedersachsen.de/arcinsys/start?t=1&archivTyp=n&query={urllib.parse.quote(q)}"


def _archivportal(surname, place):
    q = " ".join(filter(None, [surname, _first(place)]))
    return f"https://www.archivportal-d.de/search?query={urllib.parse.quote(q)}"


def _hamburg_auswanderer(given, surname, by):
    # Hamburger Auswandererlisten auf Ancestry (öffentlich)
    params: dict = {}
    if given:
        params["name_x"] = given
    if surname:
        params["name"] = surname
    if by:
        params["event_year_from"] = str(max(1850, by - 5))
        params["event_year_to"]   = str(by + 30)
    return "https://www.ancestry.de/search/collections/1068/?" + urllib.parse.urlencode(params)


def _ellis_island(given, surname, by):
    params: dict = {}
    if given:
        params["q.givenName"] = given
    if surname:
        params["q.surname"] = surname
    if by:
        params["q.birthLikeDate.from"] = str(max(1880, by - 2))
        params["q.birthLikeDate.to"]   = str(by + 2)
    params["q.arrivalDate.from"] = "1890"
    params["q.arrivalDate.to"]   = "1957"
    return "https://www.familysearch.org/search/record/results?q.collectionId=1368704&" + urllib.parse.urlencode(params)


def _auswandererhaus(given, surname):
    q = urllib.parse.quote(" ".join(filter(None, [given, surname])))
    return f"https://www.auswandererhaus.de/recherche?s={q}"


def _bundesarchiv(given, surname, by):
    q = urllib.parse.quote(" ".join(filter(None, [surname, given])))
    return f"https://invenio.bundesarchiv.de/invenio/direktlink/?search_text={q}"


def _volksbund(given, surname, by):
    params: dict = {}
    if given:
        params["vorname"] = given
    if surname:
        params["familienname"] = surname
    if by:
        params["geburtsjahr"] = str(by)
    return "https://www.volksbund.de/graebersuche?" + urllib.parse.urlencode(params)


def _geneanet(given, surname, place):
    params: dict = {"lang": "de", "country": "de"}
    if surname:
        params["name"] = surname
    if given:
        params["firstname"] = given.split()[0]
    if place:
        params["place"] = _first(place)
    return "https://en.geneanet.org/search/?" + urllib.parse.urlencode(params)


def _geni(given, surname, by):
    q = urllib.parse.quote(" ".join(filter(None, [given, surname])))
    y = f"&birth_year={by}" if by else ""
    return f"https://www.geni.com/search?search_type=people&names={q}{y}"


def _werelate(given, surname, place):
    q = urllib.parse.quote(" ".join(filter(None, [given, surname])))
    p = urllib.parse.quote(_first(place)) if place else ""
    return f"https://www.werelate.org/wiki/Special:Search?ns=Person&q={q}+{p}".rstrip("+")


def _zefys(surname):
    q = urllib.parse.quote(surname)
    return f"https://zefys.staatsbibliothek-berlin.de/index.php?action=search&query={q}"


def _zeitungsportal_nrw(surname):
    q = urllib.parse.quote(surname)
    return f"https://zeitungsportal.de/search?q={q}"


def _adressbuch(surname, place, by):
    p_enc = urllib.parse.quote(_first(place)) if place else ""
    s_enc = urllib.parse.quote(surname) if surname else ""
    return f"https://adressbuecher.genealogy.net/suche.php?na={s_enc}&ort={p_enc}"


def _hathitrust(surname, place, by):
    q_parts = [surname]
    if place:
        q_parts.append(_first(place))
    if by:
        q_parts.append("Adressbuch")
    q = urllib.parse.quote(" ".join(q_parts))
    return f"https://catalog.hathitrust.org/Search/Home?lookfor={q}&type=all"


def _wikidata_person(given, surname, by):
    sparql = (
        f'SELECT ?item ?itemLabel WHERE {{ '
        f'?item wdt:P31 wd:Q5 . '
        f'?item rdfs:label ?l . FILTER(LANG(?l)="de") . '
        f'FILTER(CONTAINS(LCASE(?l),"{surname.lower()}")) . '
        f'SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de" }} '
        f'}} LIMIT 5'
    )
    return "https://query.wikidata.org/#" + urllib.parse.quote(sparql)


def _gnd(given, surname, by):
    q = " ".join(filter(None, [given, surname]))
    params: dict = {"q": q, "filter": "type:Person"}
    if by:
        params["q"] += f" {by}"
    return "https://lobid.org/gnd/search?" + urllib.parse.urlencode(params)


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def run_externe_quellen(individuals: dict, root_related_ids=None,
                        progress_cb=None,
                        max_persons: int = 5_000) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Externe Quellen: Recherche-Links generieren …")

    scope = root_related_ids or set(individuals.keys())
    rows  = []

    for pid in list(scope)[:max_persons]:
        pdata = individuals.get(pid)
        if not pdata:
            continue

        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by   = _yr(birt)
        dy   = _yr(deat)
        bp   = (birt.get("PLAC") or "").strip()
        dp   = (deat.get("PLAC") or "").strip()

        # Personen ohne Namen oder zu jung überspringen
        name_raw = (pdata.get("NAME") or "").strip()
        if not name_raw:
            continue
        if by and by > 1965:
            continue

        given, surname = _split_name(name_raw)
        if not surname:
            continue

        place = bp or dp
        is_dach = _is_dach(place)
        is_emigrant = _is_emigrant(pdata)
        is_war = by and 1870 <= by <= 1928
        is_nrw = _is_nrw(place)
        use_kirchenbuch = (not by or by < 1875)
        use_standesamt  = (by and by >= 1874)

        besonderheiten = []
        if is_emigrant:
            besonderheiten.append("Auswanderer")
        if is_war:
            besonderheiten.append("Kriegsgeneration")
        if not is_dach:
            besonderheiten.append("nicht-DACH")

        rows.append([
            pid,
            name_raw,
            by or "",
            _first(bp),
            dy or "",
            _first(dp),
            _zeitraum(by, dy),
            " | ".join(besonderheiten),
            # Kirchenbücher
            _matricula(given, surname, place, by) if use_kirchenbuch and is_dach else "",
            _archion(given, surname, place)        if use_kirchenbuch and is_dach else "",
            _familysearch(given, surname, by, place),
            # Standesamt
            _arcinsys(surname, place)    if use_standesamt and is_dach else "",
            _archivportal(surname, place) if is_dach else "",
            # Auswanderer
            _hamburg_auswanderer(given, surname, by) if is_emigrant and is_dach else "",
            _ellis_island(given, surname, by)        if is_emigrant else "",
            _auswandererhaus(given, surname)         if is_emigrant else "",
            # Militär
            _bundesarchiv(given, surname, by) if is_war and is_dach else "",
            _volksbund(given, surname, by)    if is_war and is_dach else "",
            # Genealogie-Plattformen
            _geneanet(given, surname, place),
            _geni(given, surname, by),
            _werelate(given, surname, place),
            # Presse
            _zefys(surname)             if is_dach else "",
            _zeitungsportal_nrw(surname) if is_nrw else "",
            # Adressbücher (relevant ab ~1850)
            _adressbuch(surname, place, by) if is_dach and (not by or by > 1800) else "",
            _hathitrust(surname, place, by) if is_dach else "",
            # Linked Data
            _wikidata_person(given, surname, by),
            _gnd(given, surname, by),
        ])

    p(f"Externe Quellen: {len(rows):,} Personen mit Recherche-Links", tag="ok")
    return rows
