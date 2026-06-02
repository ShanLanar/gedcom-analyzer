# -*- coding: utf-8 -*-
"""tasks/export_gravity_map.py – Demografischer Schwerpunkt als animierte Leaflet-Karte.

Zeigt, wie der Sterbepunkt-Schwerpunkt der Familie sich von Westfalen
über die Jahrzehnte in Richtung Ohio / Texas verlagert hat.
Ein Slider und Auto-Play ermöglichen den Zeitraffer.
"""

import html
import json
import os

_BG     = "#1e1e2e"
_FG     = "#cdd6f4"
_ACCENT = "#7c7cf8"
_MUTED  = "#9399b2"

_LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
_LEAFLET_JS  = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
_TILE_URL    = ("https://cartodb-basemaps-{s}.global.ssl.fastly.net/"
                "dark_all/{z}/{x}/{y}.png")
_TILE_ATTR   = ("&copy; <a href='https://www.openstreetmap.org/copyright'>"
                "OpenStreetMap</a> &copy; "
                "<a href='https://carto.com/attributions'>CARTO</a>")

# Farbe pro dominantem Land
_LAND_COLOR = {
    "Deutschland":  "#f9e2af",
    "USA-Ohio":     "#89dceb",
    "USA-Texas":    "#a6e3a1",
    "Niederlande":  "#cba6f7",
    "Australien":   "#f38ba8",
}
_DEFAULT_COLOR = "#9399b2"


def export_gravity_map(gravity_rows: list, out_path: str) -> None:
    """
    gravity_rows: Liste von Listen mit Spalten laut GRAVITY_HEADERS:
      [Jahrzehnt, Lat, Lon, Dominantes Land, Anteil Westfalen %, Anteil Ohio %, Anteil Texas %]
    """
    # Filtere Zeilen mit gültigen Koordinaten
    points = []
    for row in gravity_rows:
        try:
            decade  = int(row[0])
            lat     = float(row[1])
            lon     = float(row[2])
            land    = str(row[3])
            wf_pct  = float(row[4]) if row[4] != "" else 0.0
            oh_pct  = float(row[5]) if row[5] != "" else 0.0
            tx_pct  = float(row[6]) if row[6] != "" else 0.0
        except (ValueError, IndexError, TypeError):
            continue
        color = _LAND_COLOR.get(land, _DEFAULT_COLOR)
        points.append({
            "decade":  decade,
            "lat":     lat,
            "lon":     lon,
            "land":    land,
            "wf":      round(wf_pct, 1),
            "oh":      round(oh_pct, 1),
            "tx":      round(tx_pct, 1),
            "color":   color,
        })

    if not points:
        # Schreibe leere Seite
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("<html><body style='background:#1e1e2e;color:#cdd6f4'>"
                     "<p>Keine Schwerpunkt-Daten vorhanden.</p></body></html>")
        return

    points.sort(key=lambda p: p["decade"])
    decades = [p["decade"] for p in points]
    pts_json = json.dumps(points, ensure_ascii=False)

    # Mittelpunkt für initiale Karte
    mid_lat = sum(p["lat"] for p in points) / len(points)
    mid_lon = sum(p["lon"] for p in points) / len(points)

    title = "Demografischer Schwerpunkt – Zeitraffer"

    html_parts = [f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{_LEAFLET_CSS}">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: {_BG}; color: {_FG}; font-family: 'Segoe UI', sans-serif;
        display: flex; flex-direction: column; height: 100vh; }}
h1 {{ padding: 10px 16px; font-size: 1.1rem; color: {_ACCENT}; flex-shrink: 0; }}
#map {{ flex: 1; }}
#controls {{
  flex-shrink: 0; padding: 10px 16px; background: #181825;
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
}}
#decade-label {{ font-size: 1.3rem; font-weight: bold; color: {_ACCENT};
                  min-width: 60px; text-align: center; }}
#slider {{ flex: 1; min-width: 200px; accent-color: {_ACCENT}; cursor: pointer; }}
button {{
  background: #313244; color: {_FG}; border: none; border-radius: 6px;
  padding: 6px 14px; cursor: pointer; font-size: 0.9rem;
}}
button:hover {{ background: #45475a; }}
#info-box {{
  flex-shrink: 0; padding: 8px 16px; background: #11111b;
  font-size: 0.85rem; color: {_MUTED};
}}
</style>
</head>
<body>
<h1>📍 {html.escape(title)}</h1>
<div id="map"></div>
<div id="controls">
  <button id="btn-play">▶ Play</button>
  <input type="range" id="slider" min="0" max="{len(points)-1}" value="0" step="1">
  <span id="decade-label">{decades[0]}</span>
</div>
<div id="info-box" id="info">Jahrzehnt: – | Schwerpunkt: –</div>

<script src="{_LEAFLET_JS}"></script>
<script>
const POINTS = {pts_json};
const map = L.map('map').setView([{mid_lat:.3f}, {mid_lon:.3f}], 5);
L.tileLayer('{_TILE_URL}', {{
  attribution: '{_TILE_ATTR}',
  subdomains: 'abcd', maxZoom: 12
}}).addTo(map);

// Alle Punkte als blasse Trail-Kreise vorzeichnen
const trailCircles = POINTS.map(p => L.circleMarker([p.lat, p.lon], {{
  radius: 5, color: p.color, fillColor: p.color,
  fillOpacity: 0.15, weight: 1, opacity: 0.3
}}).addTo(map));

// Verbindungslinie
const lineCoords = POINTS.map(p => [p.lat, p.lon]);
L.polyline(lineCoords, {{color: '#6c7086', weight: 1.5, dashArray: '4 4', opacity: 0.5}}).addTo(map);

// Aktiver Marker
let activeMarker = null;
let activeIdx = 0;
let playTimer = null;
const slider = document.getElementById('slider');
const decLabel = document.getElementById('decade-label');
const infoBox = document.getElementById('info-box');
const btnPlay = document.getElementById('btn-play');

function showPoint(idx) {{
  activeIdx = idx;
  slider.value = idx;
  const p = POINTS[idx];
  decLabel.textContent = p.decade + 's';
  infoBox.textContent =
    `Jahrzehnt: ${{p.decade}}er | Schwerpunkt: ${{p.lat.toFixed(3)}}°N ${{p.lon.toFixed(3)}}°E | `+
    `Dominant: ${{p.land}} | Westfalen ${{p.wf}}% | Ohio ${{p.oh}}% | Texas ${{p.tx}}%`;

  if (activeMarker) map.removeLayer(activeMarker);
  activeMarker = L.circleMarker([p.lat, p.lon], {{
    radius: 14, color: '#fff', weight: 2,
    fillColor: p.color, fillOpacity: 0.85
  }}).addTo(map)
    .bindTooltip(`<b>${{p.decade}}er</b><br>${{p.land}}<br>Westfalen ${{p.wf}}% / Ohio ${{p.oh}}% / Texas ${{p.tx}}%`,
                 {{permanent: false, direction: 'top'}});

  map.panTo([p.lat, p.lon], {{animate: true, duration: 0.5}});
}}

slider.addEventListener('input', () => {{
  if (playTimer) {{ clearInterval(playTimer); playTimer = null; btnPlay.textContent = '▶ Play'; }}
  showPoint(parseInt(slider.value));
}});

btnPlay.addEventListener('click', () => {{
  if (playTimer) {{
    clearInterval(playTimer); playTimer = null; btnPlay.textContent = '▶ Play';
  }} else {{
    if (activeIdx >= POINTS.length - 1) activeIdx = 0;
    btnPlay.textContent = '⏹ Stop';
    playTimer = setInterval(() => {{
      activeIdx++;
      showPoint(activeIdx);
      if (activeIdx >= POINTS.length - 1) {{
        clearInterval(playTimer); playTimer = null; btnPlay.textContent = '▶ Play';
      }}
    }}, 1000);
  }}
}});

showPoint(0);
</script>
</body>
</html>"""]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("".join(html_parts))
