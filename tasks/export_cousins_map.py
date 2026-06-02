# -*- coding: utf-8 -*-
"""tasks/export_cousins_map.py – Lebende Cousins nach US-County als Choropleth-Karte.

Verwendet GeoJSON-Daten der US-Counties (via CDN) und färbt sie nach
Anzahl der Verwandten ein, die dort geboren wurden oder gestorben sind.
"""

import html
import json
import os
from collections import defaultdict, Counter

_BG     = "#1e1e2e"
_FG     = "#cdd6f4"
_ACCENT = "#89dceb"
_MUTED  = "#9399b2"

_LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
_LEAFLET_JS  = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
_TILE_URL    = ("https://cartodb-basemaps-{s}.global.ssl.fastly.net/"
                "dark_all/{z}/{x}/{y}.png")
_TILE_ATTR   = ("&copy; <a href='https://www.openstreetmap.org/copyright'>"
                "OpenStreetMap</a> &copy; "
                "<a href='https://carto.com/attributions'>CARTO</a>")

# GeoJSON der US-Counties (vereinfacht, ~1 MB, public domain)
_COUNTIES_GEOJSON_URL = ("https://raw.githubusercontent.com/plotly/datasets/master/"
                          "geojson-counties-fips.json")

# Bekannte Ohio-/Texas-/US-Orte mit FIPS-County-Code
# Format: keyword_lowercase -> (fips_5digit, county_name, state, lat, lon)
_PLACE_TO_FIPS = {
    # Ohio
    "putnam county":    ("39137", "Putnam County, OH",    "OH", 41.02, -84.13),
    "putnam":           ("39137", "Putnam County, OH",    "OH", 41.02, -84.13),
    "columbus":         ("39049", "Franklin County, OH",  "OH", 39.96, -82.99),
    "cincinnati":       ("39061", "Hamilton County, OH",  "OH", 39.10, -84.51),
    "cleveland":        ("39035", "Cuyahoga County, OH",  "OH", 41.50, -81.69),
    "toledo":           ("39095", "Lucas County, OH",     "OH", 41.66, -83.56),
    "ottawa county":    ("39123", "Ottawa County, OH",    "OH", 41.53, -83.03),
    "ottawa":           ("39123", "Ottawa County, OH",    "OH", 41.53, -83.03),
    "defiance":         ("39039", "Defiance County, OH",  "OH", 41.28, -84.36),
    "auglaize":         ("39011", "Auglaize County, OH",  "OH", 40.55, -84.23),
    "van wert":         ("39161", "Van Wert County, OH",  "OH", 40.77, -84.60),
    "henry county":     ("39069", "Henry County, OH",     "OH", 41.34, -84.07),
    "henry":            ("39069", "Henry County, OH",     "OH", 41.34, -84.07),
    "fulton":           ("39051", "Fulton County, OH",    "OH", 41.60, -84.13),
    "sandusky":         ("39143", "Sandusky County, OH",  "OH", 41.35, -83.13),
    "hancock":          ("39063", "Hancock County, OH",   "OH", 41.00, -83.66),
    "allen county":     ("39003", "Allen County, OH",     "OH", 40.77, -83.95),
    "lima":             ("39003", "Allen County, OH",     "OH", 40.74, -84.10),
    "delphos":          ("39003", "Allen County, OH",     "OH", 40.84, -84.34),
    "kalida":           ("39137", "Putnam County, OH",    "OH", 40.99, -84.20),
    "continental":      ("39137", "Putnam County, OH",    "OH", 41.10, -84.27),
    "pandora":          ("39137", "Putnam County, OH",    "OH", 40.94, -83.96),
    # Texas
    "texas":            ("48113", "Dallas County, TX",    "TX", 32.77, -96.79),
    "houston":          ("48201", "Harris County, TX",    "TX", 29.76, -95.37),
    "dallas":           ("48113", "Dallas County, TX",    "TX", 32.78, -96.80),
    "san antonio":      ("48029", "Bexar County, TX",     "TX", 29.42, -98.49),
    "medina":           ("48325", "Medina County, TX",    "TX", 29.36, -99.10),
    "gillespie":        ("48171", "Gillespie County, TX", "TX", 30.28, -98.93),
    "fredericksburg":   ("48171", "Gillespie County, TX", "TX", 30.27, -98.87),
    # Indiana
    "fort wayne":       ("18003", "Allen County, IN",     "IN", 41.08, -85.14),
    "indiana":          ("18097", "Marion County, IN",    "IN", 39.77, -86.16),
    # Illinois
    "chicago":          ("17031", "Cook County, IL",      "IL", 41.85, -87.65),
    # Michigan
    "detroit":          ("26163", "Wayne County, MI",     "MI", 42.33, -83.05),
}

# US-State-Kennzeichen, die auf US-Sterbeort hinweisen
_US_STATE_ABBR = {
    "oh", "ohio", "tx", "texas", "in", "indiana", "il", "illinois",
    "mi", "michigan", "mn", "minnesota", "wi", "wisconsin", "ia", "iowa",
    "mo", "missouri", "ks", "kansas", "ne", "nebraska", "co", "colorado",
    "ca", "california", "fl", "florida", "ny", "new york", "pa", "pennsylvania",
}


def _extract_fips(place: str):
    """Versucht, einen FIPS-Code aus einem Ortsstring zu extrahieren."""
    if not place:
        return None
    pl = place.lower().replace(".", "").strip()

    # Direkter Treffer
    for key, val in _PLACE_TO_FIPS.items():
        if key in pl:
            return val

    # Komma-Splits: "Kalida, Putnam, Ohio, USA" → check each part
    parts = [p.strip() for p in pl.split(",")]
    for part in parts:
        for key, val in _PLACE_TO_FIPS.items():
            if key == part:
                return val
    return None


def _is_usa_place(place: str) -> bool:
    if not place:
        return False
    pl = place.lower()
    return any(abbr in pl for abbr in _US_STATE_ABBR)


def _build_cousin_county_data(individuals: dict, cousin_rows: list) -> dict:
    """
    Gibt dict zurück:
      fips -> {name, state, lat, lon, count, persons: [{pid, name, place, relation}]}
    """
    county_data = {}

    # cousin_rows Spalten: [pid, name, ..., relation(idx11), ..., birth_place(idx15), ..., death_place(idx17)]
    COL_PID      = 0
    COL_NAME     = 1
    COL_RELATION = 11
    COL_BPLACE   = 15
    COL_DPLACE   = 17

    for row in cousin_rows:
        try:
            pid      = row[COL_PID]
            name     = row[COL_NAME] or ""
            relation = row[COL_RELATION] or ""
            bplace   = row[COL_BPLACE] or ""
            dplace   = row[COL_DPLACE] or ""
        except IndexError:
            continue

        # Prüfe ob lebend (kein Sterbedatum in Individualdaten)
        pdata = individuals.get(pid, {})
        death_year = (pdata.get("DEAT") or {}).get("YEAR")
        if death_year:
            continue  # nur lebende Cousins

        # Versuche county aus Sterbeort (oft letzter bekannter Wohnort) oder Geburtsort
        for place_str in [dplace, bplace]:
            if not _is_usa_place(place_str):
                continue
            fips_info = _extract_fips(place_str)
            if fips_info:
                fips, county_name, state, lat, lon = fips_info
                if fips not in county_data:
                    county_data[fips] = {
                        "name":    county_name,
                        "state":   state,
                        "lat":     lat,
                        "lon":     lon,
                        "count":   0,
                        "persons": [],
                    }
                county_data[fips]["count"] += 1
                county_data[fips]["persons"].append({
                    "pid":      pid,
                    "name":     name.strip("/").strip(),
                    "place":    place_str,
                    "relation": relation,
                })
                break  # pro Person nur einmal zählen

    return county_data


def export_cousins_map(individuals: dict, cousin_rows: list, out_path: str) -> None:
    county_data = _build_cousin_county_data(individuals, cousin_rows)

    if not county_data:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("<html><body style='background:#1e1e2e;color:#cdd6f4'>"
                     "<p>Keine US-Verwandten gefunden (kein Sterbedatum + US-Ort).</p>"
                     "</body></html>")
        return

    total = sum(v["count"] for v in county_data.values())
    max_count = max(v["count"] for v in county_data.values()) or 1

    # Marker-Daten als JSON
    markers = []
    for fips, d in sorted(county_data.items(), key=lambda x: -x[1]["count"]):
        persons_html = "".join(
            f"<li>{html.escape(p['name'])} <span style='color:{_MUTED}'>({html.escape(p['relation'])})</span></li>"
            for p in d["persons"][:20]
        )
        if len(d["persons"]) > 20:
            persons_html += f"<li style='color:{_MUTED}'>… und {len(d['persons'])-20} weitere</li>"
        markers.append({
            "fips":    fips,
            "name":    d["name"],
            "state":   d["state"],
            "lat":     d["lat"],
            "lon":     d["lon"],
            "count":   d["count"],
            "ratio":   round(d["count"] / max_count, 3),
            "tooltip": f"<b>{html.escape(d['name'])}</b><br>{d['count']} Verwandte<ul style='margin:4px 0 0 14px;padding:0'>{persons_html}</ul>",
        })

    markers_json = json.dumps(markers, ensure_ascii=False)
    title = f"Lebende Cousins nach US-County ({total} Personen)"

    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{_LEAFLET_CSS}">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: {_BG}; color: {_FG}; font-family: 'Segoe UI', sans-serif;
        display: flex; flex-direction: column; height: 100vh; }}
h1 {{ padding: 10px 16px; font-size: 1.05rem; color: {_ACCENT}; flex-shrink: 0; }}
#map {{ flex: 1; }}
#legend {{
  flex-shrink: 0; padding: 8px 16px; background: #11111b;
  font-size: 0.8rem; color: {_MUTED}; display: flex; gap: 20px; flex-wrap: wrap;
}}
.leg-dot {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%;
             margin-right: 4px; vertical-align: middle; }}
</style>
</head>
<body>
<h1>🗺️ {html.escape(title)}</h1>
<div id="map"></div>
<div id="legend">
  <span><span class="leg-dot" style="background:#f38ba8"></span>viele</span>
  <span><span class="leg-dot" style="background:#fab387"></span>mittel</span>
  <span><span class="leg-dot" style="background:#a6e3a1"></span>wenige</span>
  <span style="color:{_MUTED}">Nur lebende Verwandte (kein eingetragenes Sterbejahr)</span>
</div>

<script src="{_LEAFLET_JS}"></script>
<script>
const MARKERS = {markers_json};

const map = L.map('map').setView([39.5, -90.0], 5);
L.tileLayer('{_TILE_URL}', {{
  attribution: '{_TILE_ATTR}',
  subdomains: 'abcd', maxZoom: 12
}}).addTo(map);

function countColor(ratio) {{
  if (ratio > 0.66) return '#f38ba8';
  if (ratio > 0.33) return '#fab387';
  return '#a6e3a1';
}}

MARKERS.forEach(m => {{
  const r = 8 + m.ratio * 22;
  L.circleMarker([m.lat, m.lon], {{
    radius: r,
    color: '#fff', weight: 1.5,
    fillColor: countColor(m.ratio),
    fillOpacity: 0.75,
  }}).addTo(map)
    .bindPopup(m.tooltip, {{maxWidth: 320}});
}});
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
