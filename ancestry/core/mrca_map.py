"""MRCA-Karte: Geburtsorte gemeinsamer Vorfahren als interaktive Leaflet-Karte.

Aggregiert die Geburtsorte (mit Koordinaten) aus den Match-Stammbäumen zu
MRCA-Kandidaten-Orten und erzeugt eine eigenständige HTML-Datei mit
eingebetteter Leaflet-Karte (CDN, Dark-Theme – wie export_heatmap).

Reine Logik ohne GUI/DB-Abhängigkeit, damit testbar.
"""
from __future__ import annotations

import html
import json

_LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
_LEAFLET_JS  = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
_TILE_URL    = ("https://cartodb-basemaps-{s}.global.ssl.fastly.net/"
                "dark_all/{z}/{x}/{y}.png")
_TILE_ATTR   = ("&copy; <a href='https://www.openstreetmap.org/copyright'>"
                "OpenStreetMap</a> &copy; "
                "<a href='https://carto.com/attributions'>CARTO</a>")
_ACCENT = "#7c7cf8"


def parse_coords(value) -> tuple[float, float] | None:
    """Parst Ancestry-Koordinaten zu (lat, lon).

    Akzeptiert ``"lat,lon"`` (auch mit Leerzeichen) und Dicts mit
    lat/lon- bzw. latitude/longitude-Schlüsseln. Gibt None bei ungültigen
    oder out-of-range Werten zurück.
    """
    lat = lon = None
    if isinstance(value, dict):
        lat = value.get("lat", value.get("latitude"))
        lon = value.get("lon", value.get("lng", value.get("longitude")))
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        lat, lon = value
    elif isinstance(value, str):
        parts = value.replace(";", ",").split(",")
        if len(parts) != 2:
            return None
        lat, lon = parts[0].strip(), parts[1].strip()
    else:
        return None
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None
    if lat_f == 0.0 and lon_f == 0.0:   # 0/0 = unbekannt/Null-Insel
        return None
    return (lat_f, lon_f)


def aggregate_mrca_places(rows: list) -> list:
    """Verdichtet Birthplace-Rohzeilen zu MRCA-Kandidaten-Orten mit Koordinaten.

    rows: dicts mit ``place_name``, ``coords``, optional ``match_guid``,
    ``person_count``, ``side``. Orte ohne gültige Koordinaten werden verworfen.

    Returns: Liste ``{place, lat, lon, match_count, person_count, sides}``,
    sortiert nach Anzahl unterschiedlicher Matches (absteigend).
    """
    agg: dict = {}
    for r in rows or []:
        place = (r.get("place_name") or "").strip()
        coords = parse_coords(r.get("coords"))
        if not place or coords is None:
            continue
        # Orte mit gleichem Namen aber leicht abweichenden Koordinaten auf den
        # Namen zusammenführen (Koordinaten des ersten Treffers behalten).
        g = agg.get(place)
        if g is None:
            g = {"place": place, "lat": coords[0], "lon": coords[1],
                 "_matches": set(), "person_count": 0, "_sides": set()}
            agg[place] = g
        mg = r.get("match_guid")
        if mg:
            g["_matches"].add(mg)
        g["person_count"] += int(r.get("person_count") or 0)
        side = r.get("side")
        if side:
            g["_sides"].add(side)

    out = []
    for g in agg.values():
        out.append({
            "place":        g["place"],
            "lat":          g["lat"],
            "lon":          g["lon"],
            "match_count":  len(g["_matches"]),
            "person_count": g["person_count"],
            "sides":        sorted(g["_sides"]),
        })
    out.sort(key=lambda p: (p["match_count"], p["person_count"]), reverse=True)
    return out


def _marker_radius(match_count: int) -> int:
    # 1 Match → 6 px, wächst gedeckelt mit der Zahl der Matches
    return min(6 + match_count * 2, 26)


def build_mrca_map_html(places: list, title: str = "MRCA-Karte") -> str:
    """Erzeugt eine eigenständige HTML-Seite mit Leaflet-Karte der MRCA-Orte."""
    markers = [{
        "lat": p["lat"], "lon": p["lon"], "place": p["place"],
        "matches": p["match_count"], "persons": p["person_count"],
        "radius": _marker_radius(p["match_count"]),
    } for p in places]
    markers_json = json.dumps(markers, ensure_ascii=False)

    # Karte auf den Schwerpunkt der Orte zentrieren (Fallback Mitteleuropa)
    if places:
        center = [sum(p["lat"] for p in places) / len(places),
                  sum(p["lon"] for p in places) / len(places)]
    else:
        center = [51.0, 10.0]
    center_json = json.dumps(center)

    css = (
        "html,body{margin:0;height:100%;background:#1e1e2e;color:#cdd6f4;"
        "font-family:'Segoe UI',sans-serif}"
        "header{padding:10px 16px}"
        "h1{margin:0;font-size:18px;color:" + _ACCENT + "}"
        ".summary{color:#9399b2;font-size:13px}"
        "#map{height:calc(100% - 70px)}"
        "footer{padding:6px 16px;color:#9399b2;font-size:11px}"
    )

    js = f"""
const MARKERS = {markers_json};
const map = L.map('map', {{center: {center_json}, zoom: 6, worldCopyJump: true}});
L.tileLayer({json.dumps(_TILE_URL)}, {{
    attribution: {json.dumps(_TILE_ATTR)}, maxZoom: 18, subdomains: 'abcd'
}}).addTo(map);
MARKERS.forEach(m => {{
    const marker = L.circleMarker([m.lat, m.lon], {{
        radius: m.radius, color: {json.dumps(_ACCENT)},
        fillColor: {json.dumps(_ACCENT)}, fillOpacity: 0.55, weight: 2
    }}).addTo(map);
    marker.bindPopup('<b>' + m.place + '</b><br>Matches: ' + m.matches +
                     '<br>Personen: ' + m.persons);
    marker.bindTooltip(m.place + ' (' + m.matches + ')');
}});
"""

    header = (f'<header><h1>{html.escape(title)}</h1>'
              f'<div class="summary">{len(markers)} Orte mit Koordinaten · '
              f'MRCA-Kandidaten aus den Match-Stammbäumen</div></header>')
    return (
        '<!DOCTYPE html>\n<html lang="de"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{html.escape(title)}</title>'
        f'<link rel="stylesheet" href="{_LEAFLET_CSS}">'
        f'<style>{css}</style></head><body>'
        + header
        + '<div id="map"></div>'
        + '<footer>Karte: CARTO Dark · Daten: OpenStreetMap</footer>'
        + f'<script src="{_LEAFLET_JS}"></script>'
        + f'<script>{js}</script></body></html>'
    )
