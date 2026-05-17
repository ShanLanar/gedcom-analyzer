# -*- coding: utf-8 -*-
"""tasks/export_fanchart.py – Radialer Ahnen-Fächer (Fan Chart) als SVG.

Erzeugt eine klassische Fächerkarte:
- Stammperson im Zentrum
- Generation 1 (Eltern): innerer Ring, Vater in der oberen Halbkugel
  (Slot 0, beginnt bei 12 Uhr), Mutter in der unteren Halbkugel (Slot 1).
- Generation N: 2^N Segmente, jedes mit 360°/2^N Winkel.
- Farbcodierung: väterliche Linie (blau), mütterliche Linie (rot/rosa).
- Unbekannte Vorfahren werden als graue Segmente dargestellt.
"""

import os
import math
import html
from lib.gedcom import safe_extract_year


# ── Layout-Konstanten ─────────────────────────────────────────────────────────

_SVG_SIZE       = 1200
_CENTER         = _SVG_SIZE / 2  # 600
_INNER_RADIUS   = 80
_RING_WIDTH     = 90
_ROOT_RADIUS    = 50

# Farbpalette (Dark Theme)
_BG_COLOR       = "#1e1e2e"
_FG_COLOR       = "#cdd6f4"
_ACCENT_COLOR   = "#7c7cf8"
_EMPTY_COLOR    = "#45475a"
_ROOT_COLOR     = "#7c7cf8"
_BORDER_COLOR   = "#1e1e2e"

# Vaterlinie: Blautöne, Mutterlinie: Rottöne. Tiefer in der Linie → blasser.
_PATERNAL_BASE  = (124, 156, 248)   # #7c9cf8
_MATERNAL_BASE  = (248, 124, 156)   # #f87c9c


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _short_name(pdata: dict) -> str:
    """Kurzname für die Anzeige: Vorname + Nachname (entkommagiert)."""
    raw = (pdata.get("NAME") or "").strip()
    if not raw:
        return ""
    # GEDCOM-Namen: "Hans /Müller/"
    parts = raw.split("/")
    given = parts[0].strip()
    surname = parts[1].strip() if len(parts) > 1 else ""
    if given and surname:
        return f"{given} {surname}"
    return given or surname


def _birth_year(pdata: dict):
    birt = pdata.get("BIRT") or {}
    y = birt.get("YEAR")
    if y is not None:
        return y
    return safe_extract_year(birt.get("DATE"))


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)] + "…"


def _is_paternal_slot(gen: int, slot: int) -> bool:
    """Slot 0 in Gen 1 = Vater. Alle Vorfahren mit slot < 2^(gen-1) liegen
    auf der väterlichen Seite (oberer Halbkreis bei Gen 1)."""
    if gen == 0:
        return False
    half = 1 << (gen - 1)
    return slot < half


def _blend_color(base: tuple, gen: int, max_gen: int) -> str:
    """Blasser werdende Farbe abhängig von der Generation."""
    if max_gen <= 1:
        f = 0.0
    else:
        f = (gen - 1) / max(1, max_gen - 1)
    f = max(0.0, min(1.0, f))
    # Richtung leicht Richtung Hintergrund mischen.
    bg = (30, 30, 46)
    r = int(base[0] + (bg[0] - base[0]) * f * 0.55)
    g = int(base[1] + (bg[1] - base[1]) * f * 0.55)
    b = int(base[2] + (bg[2] - base[2]) * f * 0.55)
    return f"#{r:02x}{g:02x}{b:02x}"


def _segment_color(gen: int, slot: int, max_gen: int, missing: bool) -> str:
    if missing:
        return _EMPTY_COLOR
    base = _PATERNAL_BASE if _is_paternal_slot(gen, slot) else _MATERNAL_BASE
    return _blend_color(base, gen, max_gen)


# ── Geometrie ─────────────────────────────────────────────────────────────────

def _polar(cx: float, cy: float, r: float, angle_deg: float) -> tuple:
    """Konvertiert Polar- (Grad, 0° = oben, im Uhrzeigersinn) zu Kartesisch."""
    rad = math.radians(angle_deg - 90)
    return (cx + r * math.cos(rad), cy + r * math.sin(rad))


def _arc_path(cx: float, cy: float, r_in: float, r_out: float,
              start_deg: float, end_deg: float) -> str:
    """Ringsektor-Pfad (zwei Bögen + zwei Radien)."""
    # Punkte: A (Außen, Start), B (Außen, Ende), C (Innen, Ende), D (Innen, Start)
    ax, ay = _polar(cx, cy, r_out, start_deg)
    bx, by = _polar(cx, cy, r_out, end_deg)
    cx2, cy2 = _polar(cx, cy, r_in, end_deg)
    dx, dy = _polar(cx, cy, r_in, start_deg)
    sweep = end_deg - start_deg
    large_arc = 1 if abs(sweep) > 180 else 0
    return (
        f"M {ax:.2f},{ay:.2f} "
        f"A {r_out:.2f},{r_out:.2f} 0 {large_arc} 1 {bx:.2f},{by:.2f} "
        f"L {cx2:.2f},{cy2:.2f} "
        f"A {r_in:.2f},{r_in:.2f} 0 {large_arc} 0 {dx:.2f},{dy:.2f} "
        "Z"
    )


# ── Ahnenermittlung ───────────────────────────────────────────────────────────

def _build_ancestor_slots(root_id: str, individuals: dict, families: dict,
                          max_gen: int) -> dict:
    """
    Liefert ein Dict {(gen, slot): person_id}.
    Slot 0 in Gen 1 = Vater, Slot 1 = Mutter.
    Slot p in Gen N: Slot p>>1 in Gen N-1 (Elternteil); gerader p = Vater,
    ungerader p = Mutter.
    """
    slots = {(0, 0): root_id}
    for gen in range(1, max_gen + 1):
        for s in range(1 << gen):
            parent_slot = s >> 1
            parent_id = slots.get((gen - 1, parent_slot))
            if not parent_id:
                continue
            pdata = individuals.get(parent_id)
            if not pdata:
                continue
            famc_list = pdata.get("FAMC") or []
            if not famc_list:
                continue
            fam = families.get(famc_list[0])
            if not fam:
                continue
            anc = fam.get("HUSB") if (s % 2 == 0) else fam.get("WIFE")
            if anc and anc in individuals:
                slots[(gen, s)] = anc
    return slots


# ── SVG-Erzeugung ─────────────────────────────────────────────────────────────

def _segment_text_max(gen: int, slot_arc_deg: float, r_mid: float) -> int:
    """Maximalanzahl Zeichen, die in ein Segment passen, abhängig vom
    Bogenmaß am mittleren Radius."""
    arc_len = math.radians(slot_arc_deg) * r_mid
    # ~7 px pro Zeichen bei 12px-Schrift.
    return max(3, int(arc_len / 7))


def _render_segment(out: list, gen: int, slot: int, max_gen: int,
                    pdata: dict | None) -> None:
    n_segments = 1 << gen
    arc_deg = 360.0 / n_segments
    start = slot * arc_deg - 90.0
    end = (slot + 1) * arc_deg - 90.0
    r_in = _INNER_RADIUS + (gen - 1) * _RING_WIDTH
    r_out = r_in + _RING_WIDTH
    r_mid = (r_in + r_out) / 2

    missing = pdata is None
    fill = _segment_color(gen, slot, max_gen, missing)
    path_d = _arc_path(_CENTER, _CENTER, r_in, r_out, start, end)

    out.append(
        f'<path d="{path_d}" fill="{fill}" stroke="{_BORDER_COLOR}" '
        f'stroke-width="1.5" />'
    )

    if missing or not pdata:
        return

    # Beschriftung
    name = _short_name(pdata)
    year = _birth_year(pdata)
    label_year = f" ★{year}" if year else ""
    max_chars = _segment_text_max(gen, arc_deg, r_mid)
    label = _truncate(name + label_year, max_chars)
    if not label.strip():
        return

    # Mittelwinkel und Rotation. Damit der Text in äußeren Ringen lesbar
    # bleibt: bei Winkel in der unteren Hälfte um 180° drehen.
    mid_angle = (start + end) / 2
    tx, ty = _polar(_CENTER, _CENTER, r_mid, mid_angle)

    rotate = mid_angle  # Text zeigt radial nach außen
    # Drehe Text, so dass er in Lese-Richtung erscheint.
    text_rotation = rotate
    flip = False
    if 90 < (mid_angle % 360) < 270:
        text_rotation = rotate + 180
        flip = True

    font_size = 13 if gen <= 2 else (12 if gen <= 4 else 10)
    text_anchor = "middle"
    out.append(
        f'<text x="{tx:.2f}" y="{ty:.2f}" '
        f'transform="rotate({text_rotation:.2f} {tx:.2f} {ty:.2f})" '
        f'fill="{_FG_COLOR}" font-size="{font_size}" '
        f'text-anchor="{text_anchor}" '
        f'dominant-baseline="middle" '
        f'font-family="Segoe UI, Arial, sans-serif">'
        f'{html.escape(label)}</text>'
    )
    # flip nur zur Vermeidung von Linter-Warnung
    _ = flip


def _render_root(out: list, root_data: dict | None) -> None:
    out.append(
        f'<circle cx="{_CENTER}" cy="{_CENTER}" r="{_ROOT_RADIUS}" '
        f'fill="{_ROOT_COLOR}" stroke="{_BORDER_COLOR}" stroke-width="2" />'
    )
    if not root_data:
        return
    name = _short_name(root_data)
    year = _birth_year(root_data)
    label = _truncate(name, 14)
    year_label = f"★{year}" if year else ""
    out.append(
        f'<text x="{_CENTER}" y="{_CENTER - 6}" fill="{_BG_COLOR}" '
        f'font-size="14" font-weight="bold" text-anchor="middle" '
        f'dominant-baseline="middle" '
        f'font-family="Segoe UI, Arial, sans-serif">'
        f'{html.escape(label)}</text>'
    )
    if year_label:
        out.append(
            f'<text x="{_CENTER}" y="{_CENTER + 12}" fill="{_BG_COLOR}" '
            f'font-size="11" text-anchor="middle" '
            f'dominant-baseline="middle" '
            f'font-family="Segoe UI, Arial, sans-serif">'
            f'{html.escape(year_label)}</text>'
        )


def _render_legend(out: list) -> None:
    out.append(
        f'<g transform="translate(30,30)">'
        f'<rect x="0" y="0" width="14" height="14" fill="rgb({_PATERNAL_BASE[0]},'
        f'{_PATERNAL_BASE[1]},{_PATERNAL_BASE[2]})"/>'
        f'<text x="20" y="11" fill="{_FG_COLOR}" font-size="12" '
        f'font-family="Segoe UI, Arial, sans-serif">Väterliche Linie</text>'
        f'<rect x="0" y="22" width="14" height="14" fill="rgb({_MATERNAL_BASE[0]},'
        f'{_MATERNAL_BASE[1]},{_MATERNAL_BASE[2]})"/>'
        f'<text x="20" y="33" fill="{_FG_COLOR}" font-size="12" '
        f'font-family="Segoe UI, Arial, sans-serif">Mütterliche Linie</text>'
        f'<rect x="0" y="44" width="14" height="14" fill="{_EMPTY_COLOR}"/>'
        f'<text x="20" y="55" fill="{_FG_COLOR}" font-size="12" '
        f'font-family="Segoe UI, Arial, sans-serif">Unbekannt</text>'
        f'</g>'
    )


# ── Haupt-Export-Funktion ─────────────────────────────────────────────────────

def export_fanchart_svg(root_id: str, individuals: dict, families: dict,
                        output_path: str, max_gen: int = 7,
                        progress_cb=None) -> bool:
    """
    Schreibt einen radialen Ahnen-Fächer (SVG) für `root_id` mit `max_gen`
    Generationen.

    Rückgabe: True bei Erfolg, False bei Fehler.
    """
    p = progress_cb or (lambda m, **kw: None)
    p("Fan-Chart-SVG-Export gestartet …")

    if not root_id or root_id not in individuals:
        p(f"Stammperson '{root_id}' nicht gefunden.", tag="err")
        return False

    max_gen = max(1, min(int(max_gen), 9))

    try:
        slots = _build_ancestor_slots(root_id, individuals, families, max_gen)
        n_filled = sum(1 for k, v in slots.items() if k[0] > 0 and v)
        n_total = sum(1 << g for g in range(1, max_gen + 1))
        p(f"  Ahnen-Slots: {n_filled:,}/{n_total:,} gefüllt "
          f"({max_gen} Generationen)")

        out: list = []
        out.append('<?xml version="1.0" encoding="UTF-8"?>')
        out.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="100%" height="100%" '
            f'viewBox="0 0 {_SVG_SIZE} {_SVG_SIZE}" '
            f'preserveAspectRatio="xMidYMid meet">'
        )
        out.append(
            f'<rect width="100%" height="100%" fill="{_BG_COLOR}" />'
        )

        # Titel
        title_name = _short_name(individuals[root_id]) or root_id
        out.append(
            f'<text x="{_CENTER}" y="40" fill="{_FG_COLOR}" '
            f'font-size="22" font-weight="bold" text-anchor="middle" '
            f'font-family="Segoe UI, Arial, sans-serif">'
            f'Ahnenfächer: {html.escape(title_name)}</text>'
        )
        out.append(
            f'<text x="{_CENTER}" y="62" fill="{_ACCENT_COLOR}" '
            f'font-size="13" text-anchor="middle" '
            f'font-family="Segoe UI, Arial, sans-serif">'
            f'{max_gen} Generationen · '
            f'{n_filled} von {n_total} Vorfahren bekannt</text>'
        )

        # Segmente: äußere zuerst (damit innere Linien obenauf liegen sind hier nicht nötig)
        for gen in range(1, max_gen + 1):
            n_segments = 1 << gen
            for slot in range(n_segments):
                pid = slots.get((gen, slot))
                pdata = individuals.get(pid) if pid else None
                _render_segment(out, gen, slot, max_gen, pdata)

        # Zentrum
        _render_root(out, individuals.get(root_id))

        # Legende
        _render_legend(out)

        out.append('</svg>')

        # Datei schreiben
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
            f.write("\n")

        size_kb = os.path.getsize(output_path) / 1024
        p(f"Fan-Chart gespeichert: {output_path} ({size_kb:.1f} KB)",
          tag="ok")
        return True

    except OSError as exc:
        p(f"Fehler beim Schreiben der SVG-Datei: {exc}", tag="err")
        return False
    except Exception as exc:
        p(f"Unerwarteter Fehler beim Fan-Chart-Export: {exc}", tag="err")
        return False
