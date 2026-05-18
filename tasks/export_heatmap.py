# -*- coding: utf-8 -*-
"""tasks/export_heatmap.py – Geburtsort-Heatmap als interaktive Leaflet-Karte.

Aggregiert Geburten je Land, ermittelt Zeitraum, Anzahl und häufigste
Geburtsstadt und schreibt eine eigenständige HTML-Datei mit eingebetteter
Leaflet-Karte (CDN). Dark Theme, deutsche Beschriftung.
"""

import os
import math
import html
import json
from collections import Counter, defaultdict
from lib.gedcom import safe_extract_year
from lib.places import extract_country_from_place


# ── Theme ─────────────────────────────────────────────────────────────────────

_BG       = "#1e1e2e"
_FG       = "#cdd6f4"
_ACCENT   = "#7c7cf8"
_MUTED    = "#9399b2"

_LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
_LEAFLET_JS  = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
_TILE_URL    = ("https://cartodb-basemaps-{s}.global.ssl.fastly.net/"
                "dark_all/{z}/{x}/{y}.png")
_TILE_ATTR   = ("&copy; <a href='https://www.openstreetmap.org/copyright'>"
                "OpenStreetMap</a> &copy; "
                "<a href='https://carto.com/attributions'>CARTO</a>")


# ── Länder-Zentroide ──────────────────────────────────────────────────────────

_COUNTRY_CENTROIDS = {
    "Deutschland":      (51.0,   10.0),
    "Polen":            (52.0,   19.0),
    "USA":              (39.0,  -95.0),
    "Russland":         (60.0,   90.0),
    "Frankreich":       (46.0,    2.0),
    "Niederlande":      (52.0,    5.0),
    "Belgien":          (50.0,    4.0),
    "Großbritannien":   (54.0,   -2.0),
    "Österreich":       (47.0,   14.0),
    "Tschechien":       (50.0,   15.0),
    "Italien":          (42.0,   12.0),
    "Spanien":          (40.0,   -3.0),
    "Schweiz":          (47.0,    8.0),
    "Dänemark":         (56.0,    9.0),
    "Schweden":         (60.0,   18.0),
    "Brasilien":        (-10.0, -55.0),
    "Argentinien":      (-34.0, -64.0),
    "Kanada":           (56.0, -106.0),
    "Australien":       (-25.0, 135.0),
}


# ── Farbgradient nach Jahrhundert ─────────────────────────────────────────────

def _color_for_year(year: int | None) -> str:
    if year is None:
        return "#9399b2"
    if year < 1700:
        return "#f38ba8"   # rot
    if year < 1800:
        return "#fab387"   # orange
    if year < 1900:
        return "#f9e2af"   # gelb
    return "#a6e3a1"       # grün


def _century_label(year: int) -> str:
    if year < 1700:    return "vor 1700"
    if year < 1800:    return "1700–1800"
    if year < 1900:    return "1800–1900"
    return "ab 1900"


# ── Aggregation ───────────────────────────────────────────────────────────────

def _aggregate(individuals: dict, location_data) -> dict:
    """
    Liefert: { country: { 'count': int, 'years': [int], 'cities': Counter } }
    """
    agg = defaultdict(lambda: {"count": 0, "years": [],
                                "cities": Counter()})
    for pdata in individuals.values():
        birt = pdata.get("BIRT") or {}
        place = birt.get("PLAC")
        if not place:
            continue
        country = extract_country_from_place(place, location_data)
        if not country:
            continue
        entry = agg[country]
        entry["count"] += 1
        y = birt.get("YEAR") or safe_extract_year(birt.get("DATE"))
        if y:
            entry["years"].append(y)
        # Ersten Bestandteil des Ortes als Stadt verwenden.
        first = place.split(",")[0].strip()
        if first:
            entry["cities"][first] += 1
    return agg


def _dominant_century_year(years: list) -> int | None:
    """Liefert das Jahr, dessen Jahrhundert die meisten Einträge stellt
    (mittleres Jahr dieses Buckets)."""
    if not years:
        return None
    buckets: Counter = Counter()
    for y in years:
        if y < 1700:    buckets["pre1700"] += 1
        elif y < 1800:  buckets["1700"]    += 1
        elif y < 1900:  buckets["1800"]    += 1
        else:           buckets["1900"]    += 1
    top = buckets.most_common(1)[0][0]
    return {"pre1700": 1650, "1700": 1750,
            "1800": 1850, "1900": 1950}[top]


# ── Haupt-Export ──────────────────────────────────────────────────────────────

def export_birth_heatmap(individuals: dict, location_data,
                        output_path: str, progress_cb=None) -> bool:
    """
    Erzeugt eine HTML-Datei mit Leaflet-Karte, die Geburtsorte je Land
    als Kreismarker visualisiert.
    """
    p = progress_cb or (lambda m, **kw: None)
    p("Geburts-Heatmap-Export gestartet …")

    try:
        agg = _aggregate(individuals, location_data)
        p(f"  Aggregierte Länder: {len(agg)}")

        markers = []
        skipped = 0
        for country, data in agg.items():
            centroid = _COUNTRY_CENTROIDS.get(country)
            if not centroid:
                skipped += 1
                continue
            lat, lon = centroid
            count = data["count"]
            years = data["years"]
            year_min = min(years) if years else None
            year_max = max(years) if years else None
            dom = _dominant_century_year(years)
            color = _color_for_year(dom)
            top_city = (data["cities"].most_common(1)[0][0]
                        if data["cities"] else "–")
            # Radius proportional zu log(count). Min 8, max ~40.
            radius = max(8, min(40, int(6 * math.log(count + 1) + 6)))
            time_range = (f"{year_min}–{year_max}" if (year_min and year_max)
                          else "unbekannt")
            century = _century_label(dom) if dom is not None else "–"
            markers.append({
                "country":  country,
                "lat":      lat,
                "lon":      lon,
                "count":    count,
                "radius":   radius,
                "color":    color,
                "range":    time_range,
                "top_city": top_city,
                "century":  century,
            })

        markers.sort(key=lambda m: m["count"], reverse=True)
        p(f"  Marker erzeugt: {len(markers)} "
          f"(übersprungen ohne Zentroide: {skipped})")

        # Wenn keine Marker, trotzdem ein leeres HTML schreiben
        markers_json = json.dumps(markers, ensure_ascii=False)

        css = f"""
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    background: {_BG};
    color: {_FG};
    font-family: "Segoe UI", Arial, sans-serif;
}}
header {{
    padding: 14px 20px;
    background: #181825;
    border-bottom: 2px solid {_ACCENT};
}}
header h1 {{ margin: 0 0 4px 0; font-size: 18px; color: {_ACCENT}; }}
header .summary {{ color: {_MUTED}; font-size: 13px; }}
#map {{
    height: calc(100vh - 130px);
    width: 100%;
    background: {_BG};
}}
.legend {{
    background: #181825;
    color: {_FG};
    padding: 10px 14px;
    line-height: 1.7;
    border-radius: 6px;
    border: 1px solid #313244;
    font-size: 12px;
}}
.legend i {{
    display: inline-block;
    width: 12px;
    height: 12px;
    margin-right: 6px;
    border-radius: 2px;
    vertical-align: middle;
}}
.leaflet-popup-content-wrapper {{
    background: #252537;
    color: {_FG};
    border-radius: 6px;
}}
.leaflet-popup-tip {{ background: #252537; }}
.leaflet-popup-content b {{ color: {_ACCENT}; }}
footer {{
    color: {_MUTED}; font-size: 12px; padding: 8px 20px;
    text-align: center;
}}
"""

        js = f"""
const MARKERS = {markers_json};
const map = L.map('map', {{
    center: [51, 10],
    zoom: 5,
    worldCopyJump: true
}});
L.tileLayer({json.dumps(_TILE_URL)}, {{
    attribution: {json.dumps(_TILE_ATTR)},
    maxZoom: 18,
    subdomains: 'abcd'
}}).addTo(map);

MARKERS.forEach(m => {{
    const marker = L.circleMarker([m.lat, m.lon], {{
        radius: m.radius,
        color: m.color,
        fillColor: m.color,
        fillOpacity: 0.55,
        weight: 2
    }}).addTo(map);
    const popup =
        '<b>' + m.country + '</b><br>' +
        'Geburten: ' + m.count + '<br>' +
        'Zeitraum: ' + m.range + '<br>' +
        'Schwerpunkt: ' + m.century + '<br>' +
        'Häufigste Stadt: ' + m.top_city;
    marker.bindPopup(popup);
    marker.bindTooltip(m.country + ' (' + m.count + ')');
}});

const legend = L.control({{position: 'bottomright'}});
legend.onAdd = function() {{
    const div = L.DomUtil.create('div', 'legend');
    div.innerHTML =
        '<b>Jahrhundert</b><br>' +
        '<i style="background:#f38ba8"></i>vor 1700<br>' +
        '<i style="background:#fab387"></i>1700–1800<br>' +
        '<i style="background:#f9e2af"></i>1800–1900<br>' +
        '<i style="background:#a6e3a1"></i>ab 1900';
    return div;
}};
legend.addTo(map);
"""

        total_births = sum(m["count"] for m in markers)
        header_html = (
            f'<header>'
            f'<h1>Geburtsort-Heatmap</h1>'
            f'<div class="summary">'
            f'{len(markers)} Länder · {total_births:,} Geburten aggregiert'
            f'</div>'
            f'</header>'
        )

        body_html = (
            '<!DOCTYPE html>\n'
            '<html lang="de"><head>'
            '<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Geburtsort-Heatmap</title>'
            f'<link rel="stylesheet" href="{_LEAFLET_CSS}">'
            f'<style>{css}</style>'
            '</head><body>'
            + header_html
            + '<div id="map"></div>'
            + '<footer>Karte: CARTO Dark · Daten: OpenStreetMap</footer>'
            + f'<script src="{_LEAFLET_JS}"></script>'
            + f'<script>{js}</script>'
            + '</body></html>'
        )

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(body_html)

        size_kb = os.path.getsize(output_path) / 1024
        p(f"Heatmap gespeichert: {output_path} ({size_kb:.1f} KB, "
          f"{len(markers)} Länder)", tag="ok")
        return True

    except OSError as exc:
        p(f"Fehler beim Schreiben der Heatmap-HTML: {exc}", tag="err")
        return False
    except Exception as exc:
        p(f"Unerwarteter Fehler beim Heatmap-Export: {exc}", tag="err")
        return False
