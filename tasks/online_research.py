# -*- coding: utf-8 -*-
"""tasks/online_research.py – Online-Recherche fehlender Sterbedaten.

Fragt Wikidata (SPARQL) und GND/lobid (REST-JSON) nach Sterbedaten für
Personen ab, bei denen:
  • kein Sterbejahr eingetragen ist
  • das Geburtsjahr vor 1930 liegt (d.h. mit hoher Wahrscheinlichkeit verstorben)
  • Name + Geburtsjahr bekannt sind

Das Ergebnis ist ein reines Vorschlag-Sheet — es wird NICHTS ins GEDCOM
zurückgeschrieben.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from lib.gedcom import safe_extract_year

# ── Konstanten ────────────────────────────────────────────────────────────────

_WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
_GND_SEARCH      = "https://lobid.org/gnd/search"

_USER_AGENT = (
    "gedcom-analyzer/9.0 (genealogy research tool; "
    "contact: github.com/shanlanar/gedcom-analyzer)"
)

# Pause zwischen HTTP-Anfragen, damit wir die öffentlichen APIs nicht
# überlasten (Wikidata empfiehlt ≥ 1 s zwischen Anfragen).
_DELAY_S = 1.2

# Maximale Anzahl Personen, die abgefragt werden (verhindert stundenlange
# Läufe bei großen Bäumen).
_MAX_LOOKUPS = 300

# Personen ab diesem Geburtsjahr werden nicht abgefragt — könnten noch leben.
_MAX_BIRTH_YEAR = 1929

ONLINE_RESEARCH_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr", "Geburtsort",
    "Quelle", "Gef. Sterbejahr", "Gef. Sterbeort",
    "Konfidenz", "Hinweis", "Link",
]


# ── Hilfs-Extraktion ──────────────────────────────────────────────────────────

def _birth(pdata: dict) -> tuple[int | None, str]:
    birt = pdata.get("BIRT") or {}
    year = birt.get("YEAR") or safe_extract_year(birt.get("DATE"))
    place = (birt.get("PLAC") or "").strip()
    return year, place


def _death_year(pdata: dict) -> int | None:
    deat = pdata.get("DEAT") or {}
    return deat.get("YEAR") or safe_extract_year(deat.get("DATE"))


def _split_name(name: str) -> tuple[str, str]:
    """GEDCOM-Name → (given, surname)."""
    if not name:
        return "", ""
    cleaned = re.sub(r"[✠★⚔‡]", "", name).strip()
    cleaned = re.sub(r"\bmig\.\S*\b", "", cleaned, flags=re.IGNORECASE).strip()
    if "/" in cleaned:
        parts = cleaned.split("/")
        return parts[0].strip(), (parts[1].strip() if len(parts) >= 2 else "")
    words = cleaned.split()
    if not words:
        return "", ""
    return (" ".join(words[:-1]), words[-1]) if len(words) > 1 else (cleaned, "")


def _first_place_token(place: str) -> str:
    return place.split(",")[0].strip() if place else ""


# ── HTTP-Helfer ───────────────────────────────────────────────────────────────

def _get_json(url: str, params: dict | None = None,
              headers: dict | None = None) -> dict | list | None:
    """Einfacher GET → JSON. Gibt None zurück bei Fehler."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("Accept", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError):
        return None


# ── Wikidata-Suche ────────────────────────────────────────────────────────────

_SPARQL_TEMPLATE = """\
SELECT ?item ?itemLabel ?birthDate ?deathDate ?deathPlaceLabel WHERE {{
  ?item wdt:P31 wd:Q5 .
  ?item wdt:P569 ?birthDate .
  ?item wdt:P570 ?deathDate .
  OPTIONAL {{ ?item wdt:P20 ?deathPlace . }}
  FILTER(YEAR(?birthDate) = {birth_year})
  ?item rdfs:label ?nameLabel .
  FILTER(LANG(?nameLabel) = "de" || LANG(?nameLabel) = "en")
  FILTER(CONTAINS(LCASE(?nameLabel), "{surname_lc}"))
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "de,en" .
  }}
}}
LIMIT 5
"""


def _query_wikidata(given: str, surname: str,
                    birth_year: int) -> list[dict]:
    """Gibt eine Liste von Treffer-Dicts zurück (können leer sein)."""
    if not surname or not birth_year:
        return []
    sparql = _SPARQL_TEMPLATE.format(
        birth_year=birth_year,
        surname_lc=surname.lower().replace('"', ""),
    )
    params = {"query": sparql, "format": "json"}
    data = _get_json(_WIKIDATA_SPARQL, params=params)
    if not data:
        return []
    bindings = (data.get("results") or {}).get("bindings") or []
    results = []
    for b in bindings:
        label    = (b.get("itemLabel") or {}).get("value", "")
        death_v  = (b.get("deathDate") or {}).get("value", "")
        dplace_v = (b.get("deathPlaceLabel") or {}).get("value", "")
        item_url = (b.get("item") or {}).get("value", "")
        death_year_found = None
        m = re.search(r"\b(\d{4})\b", death_v)
        if m:
            death_year_found = int(m.group(1))
        if death_year_found:
            results.append({
                "source":     "Wikidata",
                "label":      label,
                "death_year": death_year_found,
                "death_place": dplace_v,
                "url":        item_url,
            })
    return results


# ── GND/lobid-Suche ───────────────────────────────────────────────────────────

def _query_gnd(given: str, surname: str, birth_year: int) -> list[dict]:
    """Sucht in der Deutschen Nationalbibliothek (lobid.org/gnd)."""
    if not surname or not birth_year:
        return []
    # Volltextsuche nach „Vorname Nachname" im GND-Personenindex
    query = f"{given} {surname}".strip() if given else surname
    params = {
        "q":      query,
        "filter": "type:Person",
        "format": "json:suggest",
        "size":   "5",
    }
    data = _get_json(_GND_SEARCH, params=params)
    if not isinstance(data, list):
        return []
    results = []
    for item in data:
        # lobid suggest liefert {"label": "…", "value": "…", ...}
        label = item.get("label") or ""
        gnd_id = item.get("value") or ""
        # Wir versuchen, das Geburtsjahr aus dem Label-String zu extrahieren
        # (Format: "Name (1850-1920)").
        match = re.search(r"\((\d{4})[–\-](\d{4})\)", label)
        if not match:
            continue
        found_by = int(match.group(1))
        found_dy = int(match.group(2))
        # Toleranz: ± 2 Jahre beim Geburtsjahr
        if abs(found_by - birth_year) > 2:
            continue
        gnd_url = f"https://d-nb.info/gnd/{gnd_id}" if gnd_id else ""
        results.append({
            "source":      "GND/lobid",
            "label":       label,
            "death_year":  found_dy,
            "death_place": "",
            "url":         gnd_url,
        })
    return results


# ── Konfidenz-Bewertung ───────────────────────────────────────────────────────

def _confidence(given: str, surname: str, birth_year: int,
                birth_place: str, hit: dict) -> tuple[str, str]:
    """Liefert (Konfidenz-Klasse, Hinweis-Text)."""
    label = hit.get("label", "").lower()
    hints = []
    score = 0

    # Nachname im Treffer-Label?
    if surname and surname.lower() in label:
        score += 40
    else:
        hints.append("Nachname nicht im Treffer-Label")

    # Vorname im Treffer-Label?
    if given and given.split()[0].lower() in label:
        score += 30
    else:
        hints.append("Vorname nicht eindeutig")

    # Sinnvolles Sterbejahr (muss nach Geburtsjahr liegen)?
    dy = hit.get("death_year") or 0
    if dy and dy > birth_year:
        age = dy - birth_year
        if 1 <= age <= 110:
            score += 20
        else:
            hints.append(f"Lebensalter {age} J. unplausibel")
    else:
        hints.append("Sterbejahr ≤ Geburtsjahr")

    if score >= 80:
        klass = "HOCH"
    elif score >= 50:
        klass = "MITTEL"
    else:
        klass = "NIEDRIG"
        hints.append("Bitte manuell prüfen")

    return klass, "; ".join(hints) if hints else "–"


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def run_online_death_research(individuals: dict, families: dict,
                               root_related_ids=None,
                               max_lookups: int = _MAX_LOOKUPS,
                               progress_cb=None) -> list:
    """Recherchiert fehlende Sterbedaten online (Wikidata + GND).

    Gibt eine Liste von Zeilen für das Excel-Sheet zurück.
    Schreibt NICHTS in individuals/families zurück.
    """
    p = progress_cb or (lambda m, **kw: None)
    p("Online-Sterbedaten-Recherche …")

    # Kandidaten: kein Sterbejahr, Geburtsjahr ≤ 1929, Name + BY bekannt
    scope = root_related_ids if root_related_ids else set(individuals.keys())
    candidates = []
    for pid in scope:
        pdata = individuals.get(pid)
        if not pdata:
            continue
        by, bp = _birth(pdata)
        if not by or by > _MAX_BIRTH_YEAR:
            continue
        if _death_year(pdata) is not None:
            continue
        given, surname = _split_name(pdata.get("NAME") or "")
        if not surname:
            continue
        candidates.append((pid, pdata, given, surname, by, bp))

    total = min(len(candidates), max_lookups)
    p(f"Kandidaten für Online-Recherche: {len(candidates):,} "
      f"(maximal {total} werden abgefragt)")

    rows = []
    for i, (pid, pdata, given, surname, by, bp) in enumerate(candidates[:total]):
        if i % 20 == 0 and i > 0:
            p(f"  … {i}/{total} abgefragt, {len(rows)} Treffer bisher")

        hits = []
        # 1. Wikidata
        wd_hits = _query_wikidata(given, surname, by)
        hits.extend(wd_hits)
        time.sleep(_DELAY_S)

        # 2. GND (nur für deutschsprachige Namen sinnvoll)
        gnd_hits = _query_gnd(given, surname, by)
        hits.extend(gnd_hits)
        time.sleep(_DELAY_S)

        # Deduplizieren nach Sterbejahr (selbes Jahr aus beiden Quellen = 1 Eintrag)
        seen_dy: set = set()
        for hit in hits:
            dy = hit.get("death_year")
            if not dy or dy in seen_dy:
                continue
            seen_dy.add(dy)
            konfidenz, hinweis = _confidence(given, surname, by, bp, hit)
            rows.append([
                pid,
                (pdata.get("NAME") or "").strip(),
                by,
                _first_place_token(bp),
                hit["source"],
                dy,
                hit.get("death_place") or "",
                konfidenz,
                hinweis,
                hit.get("url") or "",
            ])

    _RANK = {"HOCH": 0, "MITTEL": 1, "NIEDRIG": 2}
    rows.sort(key=lambda r: (_RANK.get(r[7], 9), r[2]))

    p(f"Online-Recherche abgeschlossen: {len(rows)} Vorschläge aus {total} Abfragen",
      tag="ok")
    return rows
