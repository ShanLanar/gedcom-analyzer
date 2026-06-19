# -*- coding: utf-8 -*-
"""
tasks/gov_lookup.py — Orte mit GOV, Nominatim und Wikidata anreichern.

Für jeden eindeutigen Ortsstring aus dem GEDCOM:
  1. Nominatim (OpenStreetMap) → Koordinaten
  2. Wikidata SPARQL           → GOV-ID (P3519), Diözese, Kirchspiel
  3. Archiv-Links              → Matricula, Archion, ArcInSys NI/NW,
                                  Archivportal-D, ICAR-Archivführer

Pause ≥ 1 s zwischen API-Aufrufen (Nominatim-Policy, Wikidata-Empfehlung).
Nur Lesezugriff – kein Schreiben ins GEDCOM.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

_NOMINATIM  = "https://nominatim.openstreetmap.org/search"
_WD_SPARQL  = "https://query.wikidata.org/sparql"
_USER_AGENT = (
    "gedcom-analyzer/9.0 (genealogy research; "
    "github.com/shanlanar/gedcom-analyzer)"
)

_DELAY_NOMINATIM = 1.2
_DELAY_WIKIDATA  = 1.5
_MAX_PLACES      = 200

GOV_LOOKUP_HEADERS = [
    "Ort (GEDCOM)", "Nominatim-Anzeigename", "Breitengrad", "Längengrad",
    "Wikidata-QID", "GOV-ID", "Kirchspiel / Pfarrei", "Diözese",
    "Matricula-Link", "Archion-Link",
    "ArcInSys NI-Link", "Archivportal-D-Link",
    "GOV-Link", "Wikidata-Link",
]


# ── HTTP-Helfer ───────────────────────────────────────────────────────────────

def _get_json(url, params=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


# ── Nominatim ─────────────────────────────────────────────────────────────────

def _nominatim(place_first: str):
    """→ (lat, lon, display_name) oder ('', '', '')."""
    if not place_first or len(place_first) < 2:
        return "", "", ""
    data = _get_json(_NOMINATIM, {
        "q": place_first,
        "countrycodes": "de,at,ch,pl,fr,nl,be,lu",
        "format": "json",
        "limit": "1",
        "addressdetails": "0",
    })
    if not isinstance(data, list) or not data:
        return "", "", ""
    h = data[0]
    return h.get("lat", ""), h.get("lon", ""), (h.get("display_name") or "")[:100]


# ── Wikidata SPARQL ────────────────────────────────────────────────────────────

_WD_PLACE_SPARQL = """\
SELECT DISTINCT ?item ?govId ?parishLabel ?dioceseLabel WHERE {{
  {{
    ?item rdfs:label "{name}"@de .
  }} UNION {{
    ?item skos:altLabel "{name}"@de .
  }}
  ?item wdt:P31/wdt:P279* wd:Q486972 .
  OPTIONAL {{ ?item wdt:P3519 ?govId . }}
  OPTIONAL {{ ?item wdt:P708 ?diocese . }}
  OPTIONAL {{
    ?item wdt:P131 ?parish .
    ?parish wdt:P31/wdt:P279* wd:Q102496 .
  }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "de,en" .
  }}
}}
LIMIT 3
"""


def _wikidata_place(name: str) -> dict:
    if not name:
        return {}
    clean = re.sub(r"\([^)]*\)", "", name).strip()
    clean = re.sub(r"\s+", " ", clean).replace('"', "")
    data = _get_json(_WD_SPARQL, {"query": _WD_PLACE_SPARQL.format(name=clean), "format": "json"})
    if not data:
        return {}
    bindings = (data.get("results") or {}).get("bindings") or []
    if not bindings:
        return {}
    b = bindings[0]
    qid = (b.get("item") or {}).get("value", "").rsplit("/", 1)[-1]
    return {
        "qid":     qid,
        "gov_id":  (b.get("govId") or {}).get("value", ""),
        "parish":  (b.get("parishLabel") or {}).get("value", ""),
        "diocese": (b.get("dioceseLabel") or {}).get("value", ""),
    }


# ── Archiv-Links ──────────────────────────────────────────────────────────────

def _archive_links(place_first: str, gov_id: str) -> dict:
    p = urllib.parse.quote(place_first)
    return {
        "matricula":    f"https://data.matricula-online.eu/de/suche/?q={p}",
        "archion":      f"https://www.archion.de/p/browse/?search=1&q={p}",
        "arcinsys":     f"https://www.arcinsys.niedersachsen.de/arcinsys/start?t=1&archivTyp=n&query={p}",
        "archivportal": f"https://www.archivportal-d.de/search?query={p}",
        "gov":          (f"https://gov.genealogy.net/item/show/{gov_id}"
                         if gov_id else
                         f"https://gov.genealogy.net/search/index?query={p}"),
    }


# ── Orte sammeln ──────────────────────────────────────────────────────────────

def _collect_places(individuals: dict) -> dict:
    """Alle eindeutigen ersten Ortskomponenten → vollständiger GEDCOM-String."""
    seen: dict[str, str] = {}
    for pdata in individuals.values():
        for key in ("BIRT", "DEAT", "MARR", "CHR", "BURI", "RESI"):
            evt = pdata.get(key) or {}
            plac = (evt.get("PLAC") or "").strip()
            if not plac or len(plac) < 2:
                continue
            first = plac.split(",")[0].strip()
            if first and first not in seen:
                seen[first] = plac
    return seen


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def run_gov_lookup(individuals: dict, progress_cb=None,
                   max_places: int = _MAX_PLACES) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("GOV-Orte-Lookup: Orte sammeln …")

    places = _collect_places(individuals)
    items  = list(places.items())[:max_places]
    p(f"  {len(places):,} eindeutige Orte, davon {len(items)} werden abgefragt")

    rows = []
    for i, (first, full) in enumerate(items):
        if i % 15 == 0 and i:
            p(f"  … {i}/{len(items)} Orte, {len(rows)} angereichert")

        lat, lon, display = _nominatim(first)
        time.sleep(_DELAY_NOMINATIM)

        wd = _wikidata_place(first)
        time.sleep(_DELAY_WIKIDATA)

        gov_id  = wd.get("gov_id", "")
        qid     = wd.get("qid", "")
        arch    = _archive_links(first, gov_id)
        wd_url  = f"https://www.wikidata.org/wiki/{qid}" if qid else ""

        rows.append([
            full,
            display or first,
            lat, lon,
            qid,
            gov_id,
            wd.get("parish", ""),
            wd.get("diocese", ""),
            arch["matricula"],
            arch["archion"],
            arch["arcinsys"],
            arch["archivportal"],
            arch["gov"],
            wd_url,
        ])

    # Sortiert: Orte mit GOV-ID zuerst (am besten erschlossen)
    rows.sort(key=lambda r: (0 if r[5] else 1, r[0]))
    p(f"GOV-Lookup: {len(rows):,} Orte angereichert", tag="ok")
    return rows
