# -*- coding: utf-8 -*-
"""tasks/export_sankey.py – Migrations-Sankey-Diagramm als eigenständige HTML.

Erzeugt ein einfaches SVG-Sankey-Diagramm (ohne externe Bibliotheken) aus
den Migration-Detail-Zeilen. Quellen werden links, Ziele rechts dargestellt;
gekrümmte Bezier-Pfade verbinden die Knoten in Breite proportional zum Fluss.
"""

import os
import html
import json
from collections import Counter, defaultdict


# ── Theme ─────────────────────────────────────────────────────────────────────

_BG          = "#1e1e2e"
_BG_PANEL    = "#181825"
_FG          = "#cdd6f4"
_ACCENT      = "#7c7cf8"
_MUTED       = "#9399b2"

_PALETTE = [
    "#7c7cf8", "#f5a97f", "#a6e3a1", "#f9e2af", "#f38ba8",
    "#94e2d5", "#cba6f7", "#89b4fa", "#fab387", "#74c7ec",
    "#eba0ac", "#b4befe", "#f2cdcd", "#cdb4db", "#ffc6ff",
]


# ── Layout-Konstanten ─────────────────────────────────────────────────────────

_WIDTH         = 1200
_HEIGHT_MIN    = 600
_MARGIN_TOP    = 60
_MARGIN_BOTTOM = 40
_MARGIN_LEFT   = 30
_MARGIN_RIGHT  = 30
_NODE_WIDTH    = 22
_NODE_GAP      = 8
_LABEL_PAD     = 8


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(124,124,248,{alpha})"
    r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _column_index(header_map, key: str, fallback: int) -> int:
    if header_map and isinstance(header_map, dict) and key in header_map:
        try:
            return int(header_map[key])
        except (TypeError, ValueError):
            return fallback
    return fallback


def _extract_flows(migration_results, idx_from: int, idx_to: int) -> Counter:
    """Zählt (from, to)-Paare aus den Migration-Rohzeilen."""
    flows: Counter = Counter()
    for row in migration_results or []:
        try:
            src = row[idx_from]
            dst = row[idx_to]
        except (IndexError, TypeError):
            continue
        if not src or not dst:
            continue
        if not isinstance(src, str) or not isinstance(dst, str):
            continue
        src = src.strip()
        dst = dst.strip()
        if not src or not dst or src == dst:
            continue
        flows[(src, dst)] += 1
    return flows


def _write_minimal_html(output_path: str, message: str) -> None:
    body = (
        '<!DOCTYPE html>\n'
        '<html lang="de"><head>'
        '<meta charset="utf-8">'
        '<title>Migrations-Sankey</title>'
        f'<style>'
        f'body{{background:{_BG};color:{_FG};'
        f'font-family:"Segoe UI",Arial,sans-serif;'
        f'display:flex;align-items:center;justify-content:center;'
        f'height:100vh;margin:0;}}'
        f'.box{{background:#252537;border:1px solid #313244;'
        f'padding:30px 40px;border-radius:8px;text-align:center;}}'
        f'h1{{color:{_ACCENT};margin:0 0 12px 0;font-size:20px;}}'
        f'</style>'
        '</head><body>'
        f'<div class="box"><h1>Migrations-Sankey</h1>'
        f'<div>{html.escape(message)}</div></div>'
        '</body></html>'
    )
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(body)


# ── Sankey-Layout ─────────────────────────────────────────────────────────────

def _layout_nodes(node_totals: dict, available_height: float) -> dict:
    """Bestimmt Y-Positionen und Höhen für eine Spalte."""
    total = sum(node_totals.values()) or 1
    n = len(node_totals)
    # Verfügbare Höhe abzüglich Lücken
    height_for_bars = max(50.0, available_height - _NODE_GAP * max(0, n - 1))
    pos: dict = {}
    y = 0.0
    # Sortiere absteigend nach Größe, damit größte oben sind.
    for name, value in sorted(node_totals.items(),
                              key=lambda kv: kv[1], reverse=True):
        h = max(2.0, (value / total) * height_for_bars)
        pos[name] = {"y": y, "h": h, "value": value}
        y += h + _NODE_GAP
    return pos


def _bezier_path(x0: float, y0: float, x1: float, y1: float) -> str:
    cx = (x0 + x1) / 2
    return (f"M{x0:.2f},{y0:.2f} "
            f"C{cx:.2f},{y0:.2f} {cx:.2f},{y1:.2f} "
            f"{x1:.2f},{y1:.2f}")


def _flow_band_path(x0: float, y0_top: float, y0_bot: float,
                    x1: float, y1_top: float, y1_bot: float) -> str:
    """Schließt ein gefülltes Band zwischen zwei vertikalen Streifen."""
    cx = (x0 + x1) / 2
    return (
        f"M{x0:.2f},{y0_top:.2f} "
        f"C{cx:.2f},{y0_top:.2f} {cx:.2f},{y1_top:.2f} "
        f"{x1:.2f},{y1_top:.2f} "
        f"L{x1:.2f},{y1_bot:.2f} "
        f"C{cx:.2f},{y1_bot:.2f} {cx:.2f},{y0_bot:.2f} "
        f"{x0:.2f},{y0_bot:.2f} Z"
    )


# ── Haupt-Export ──────────────────────────────────────────────────────────────

def export_migration_sankey(migration_results, header_map,
                            output_path: str, progress_cb=None) -> bool:
    """
    Erzeugt eine HTML-Datei mit einem SVG-basierten Sankey-Diagramm der
    Migrationen.

    `header_map` darf None sein; in diesem Fall werden Spaltenindizes
    4 (Migrationsroute / from_country) und 7 (Ziel Land / to_country)
    angenommen.
    """
    p = progress_cb or (lambda m, **kw: None)
    p("Migrations-Sankey-Export gestartet …")

    try:
        idx_from = _column_index(header_map, "from_country", 4)
        idx_to   = _column_index(header_map, "to_country",   7)

        flows = _extract_flows(migration_results, idx_from, idx_to)
        if not flows or len(flows) < 3:
            p("  Zu wenig Migrationsdaten – minimales HTML wird geschrieben.",
              tag="warn")
            _write_minimal_html(output_path,
                                "Zu wenig Migrationsdaten")
            # Wir werten dies als Erfolg, da die Anforderung war,
            # ein minimales HTML zu schreiben.
            p(f"Sankey (minimal) gespeichert: {output_path}", tag="ok")
            return True

        # Knoten-Totale je Spalte
        sources: Counter = Counter()
        targets: Counter = Counter()
        for (s, t), v in flows.items():
            sources[s] += v
            targets[t] += v

        p(f"  Flüsse: {len(flows)}, Quellen: {len(sources)}, "
          f"Ziele: {len(targets)}")

        # Höhe dynamisch wählen
        height = max(_HEIGHT_MIN,
                     60 + max(len(sources), len(targets)) * 32)
        available_h = height - _MARGIN_TOP - _MARGIN_BOTTOM

        src_layout = _layout_nodes(dict(sources), available_h)
        dst_layout = _layout_nodes(dict(targets), available_h)

        # Quellfarbe je Quelle bestimmen (deterministisch nach Rang)
        ranked_sources = [k for k, _ in
                          sorted(sources.items(),
                                 key=lambda kv: kv[1], reverse=True)]
        source_color: dict = {
            name: _PALETTE[i % len(_PALETTE)]
            for i, name in enumerate(ranked_sources)
        }

        # X-Positionen
        x_left  = _MARGIN_LEFT
        x_right = _WIDTH - _MARGIN_RIGHT - _NODE_WIDTH

        # Innerhalb jeder Quelle/Ziel-Box bauen wir gestapelte Sub-Slices
        # auf, deren Höhen proportional zur jeweiligen Flussgröße sind.
        src_cursor: dict = defaultdict(float)
        dst_cursor: dict = defaultdict(float)

        out: list = []
        out.append('<?xml version="1.0" encoding="UTF-8"?>')
        out.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {_WIDTH} {height}" '
            f'width="100%" height="100%" '
            f'preserveAspectRatio="xMidYMid meet">'
        )
        out.append(
            f'<rect width="100%" height="100%" fill="{_BG}" />'
        )
        # Titel
        out.append(
            f'<text x="{_WIDTH/2:.0f}" y="32" fill="{_ACCENT}" '
            f'font-size="20" font-weight="bold" text-anchor="middle" '
            f'font-family="Segoe UI, Arial, sans-serif">'
            f'Migrations-Sankey: Herkunft → Ziel</text>'
        )

        # Sortiere Flüsse für stabile Reihenfolge (große zuerst).
        sorted_flows = sorted(flows.items(), key=lambda kv: kv[1],
                              reverse=True)

        # ── Bänder zeichnen (zuerst, damit Knoten obenauf liegen) ────────────
        for (src, dst), value in sorted_flows:
            src_node = src_layout[src]
            dst_node = dst_layout[dst]
            # Höhe-Anteil dieses Flusses an Quelle/Ziel
            share_src = value / src_node["value"] * src_node["h"]
            share_dst = value / dst_node["value"] * dst_node["h"]

            y0_top = (_MARGIN_TOP + src_node["y"]
                      + src_cursor[src])
            y0_bot = y0_top + share_src
            y1_top = (_MARGIN_TOP + dst_node["y"]
                      + dst_cursor[dst])
            y1_bot = y1_top + share_dst

            src_cursor[src] += share_src
            dst_cursor[dst] += share_dst

            path_d = _flow_band_path(
                x_left + _NODE_WIDTH, y0_top, y0_bot,
                x_right,               y1_top, y1_bot)
            color = source_color.get(src, _ACCENT)
            out.append(
                f'<path d="{path_d}" fill="{_hex_to_rgba(color, 0.45)}" '
                f'stroke="none">'
                f'<title>{html.escape(src)} → {html.escape(dst)}: '
                f'{int(value)}</title>'
                f'</path>'
            )

        # ── Quellknoten ──────────────────────────────────────────────────────
        for name, node in src_layout.items():
            y = _MARGIN_TOP + node["y"]
            color = source_color.get(name, _ACCENT)
            out.append(
                f'<rect x="{x_left:.2f}" y="{y:.2f}" '
                f'width="{_NODE_WIDTH}" height="{node["h"]:.2f}" '
                f'fill="{color}" stroke="{_BG_PANEL}" '
                f'stroke-width="1">'
                f'<title>{html.escape(name)}: {int(node["value"])}</title>'
                f'</rect>'
            )
            label_y = y + node["h"] / 2
            label_x = x_left + _NODE_WIDTH + _LABEL_PAD
            out.append(
                f'<text x="{label_x:.2f}" y="{label_y:.2f}" '
                f'fill="{_FG}" font-size="12" '
                f'dominant-baseline="middle" text-anchor="start" '
                f'font-family="Segoe UI, Arial, sans-serif">'
                f'{html.escape(name)} '
                f'<tspan fill="{_MUTED}">({int(node["value"])})</tspan>'
                f'</text>'
            )

        # ── Zielknoten ───────────────────────────────────────────────────────
        for name, node in dst_layout.items():
            y = _MARGIN_TOP + node["y"]
            out.append(
                f'<rect x="{x_right:.2f}" y="{y:.2f}" '
                f'width="{_NODE_WIDTH}" height="{node["h"]:.2f}" '
                f'fill="{_ACCENT}" stroke="{_BG_PANEL}" '
                f'stroke-width="1">'
                f'<title>{html.escape(name)}: {int(node["value"])}</title>'
                f'</rect>'
            )
            label_y = y + node["h"] / 2
            label_x = x_right - _LABEL_PAD
            out.append(
                f'<text x="{label_x:.2f}" y="{label_y:.2f}" '
                f'fill="{_FG}" font-size="12" '
                f'dominant-baseline="middle" text-anchor="end" '
                f'font-family="Segoe UI, Arial, sans-serif">'
                f'<tspan fill="{_MUTED}">({int(node["value"])})</tspan> '
                f'{html.escape(name)}'
                f'</text>'
            )

        # Spaltenbeschriftungen
        out.append(
            f'<text x="{x_left:.2f}" y="{_MARGIN_TOP - 12:.2f}" '
            f'fill="{_MUTED}" font-size="11" '
            f'font-family="Segoe UI, Arial, sans-serif">Herkunftsland</text>'
        )
        out.append(
            f'<text x="{x_right + _NODE_WIDTH:.2f}" '
            f'y="{_MARGIN_TOP - 12:.2f}" '
            f'fill="{_MUTED}" font-size="11" text-anchor="end" '
            f'font-family="Segoe UI, Arial, sans-serif">Zielland</text>'
        )

        out.append('</svg>')

        # ── HTML-Wrapper ────────────────────────────────────────────────────
        total_flow = sum(flows.values())
        css = (
            f"body{{margin:0;background:{_BG};color:{_FG};"
            f"font-family:'Segoe UI',Arial,sans-serif;}}"
            f"header{{padding:14px 24px;background:{_BG_PANEL};"
            f"border-bottom:2px solid {_ACCENT};}}"
            f"header h1{{margin:0 0 4px 0;font-size:18px;color:{_ACCENT};}}"
            f"header .summary{{color:{_MUTED};font-size:13px;}}"
            f".chart{{padding:20px;}}"
            f"footer{{color:{_MUTED};font-size:12px;padding:12px 24px;"
            f"text-align:center;}}"
        )
        header_html = (
            f'<header><h1>Migrations-Sankey</h1>'
            f'<div class="summary">'
            f'{len(sources)} Herkunftsländer · {len(targets)} Zielländer · '
            f'{len(flows)} Routen · {total_flow:,} Migrationen gesamt'
            f'</div></header>'
        )
        body_html = (
            '<!DOCTYPE html>\n'
            '<html lang="de"><head>'
            '<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Migrations-Sankey</title>'
            f'<style>{css}</style>'
            '</head><body>'
            + header_html
            + '<div class="chart">'
            + "\n".join(out)
            + '</div>'
            + '<footer>Erzeugt vom GEDCOM-Analyzer · Sankey-Diagramm</footer>'
            + '</body></html>'
        )

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(body_html)

        size_kb = os.path.getsize(output_path) / 1024
        p(f"Sankey gespeichert: {output_path} ({size_kb:.1f} KB, "
          f"{len(flows)} Routen)", tag="ok")
        # json import sicherstellen (genutzt indirekt? hier nicht – aber
        # für eventuelle Erweiterungen behalten wir den Import.)
        _ = json
        return True

    except OSError as exc:
        p(f"Fehler beim Schreiben der Sankey-HTML: {exc}", tag="err")
        return False
    except Exception as exc:
        p(f"Unerwarteter Fehler beim Sankey-Export: {exc}", tag="err")
        return False
