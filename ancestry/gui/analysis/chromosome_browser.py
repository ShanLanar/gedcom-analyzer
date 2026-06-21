"""Chromosomen-Browser für einen einzelnen Match (Feature B4).

Zeichnet die 23 Chromosomen als Ideogramm und malt die geteilten Segmente des
gewählten Matches ein — eingefärbt nach zugewiesener Seite
(väterlich=blau, mütterlich=rot, unbekannt=grau). Daten aus dna_segments +
matches.paternal_maternal; kein externes Tool nötig.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

log = logging.getLogger(__name__)

# Chromosomenlängen in Mbp (1–22 + X=23), wie im Triangulations-View.
_CHROM_LEN_MBP = {
    1: 249, 2: 243, 3: 199, 4: 191, 5: 181, 6: 171, 7: 159, 8: 146, 9: 141,
    10: 135, 11: 135, 12: 133, 13: 115, 14: 107, 15: 102, 16: 91, 17: 83,
    18: 80, 19: 59, 20: 63, 21: 48, 22: 51, 23: 155,
}

_SIDE_COLOR = {"paternal": "#1a73e8", "maternal": "#e81a4b", "": "#9aa0a6"}
_SIDE_LABEL = {"paternal": "väterlich", "maternal": "mütterlich", "": "unbekannt"}


def show_chromosome_browser(parent, state, test_guid: str, match_guid: str,
                            match_name: str = ""):
    db = getattr(state, "db", None)
    if db is None or not (test_guid and match_guid):
        return

    # Daten holen (kleine Abfrage je Match)
    segments, side = [], ""
    try:
        with db._cursor() as cur:
            segments = [dict(r) for r in cur.execute(
                """SELECT chromosome, start_location, end_location, length_cm
                   FROM dna_segments
                   WHERE test_guid=? AND match_guid=?
                   ORDER BY chromosome, start_location""",
                (test_guid, match_guid)).fetchall()]
            row = cur.execute(
                "SELECT paternal_maternal FROM matches WHERE match_guid=?",
                (match_guid,)).fetchone()
            side = (row["paternal_maternal"] if row else "") or ""
    except Exception as e:
        log.debug("chromosome browser query: %s", e)

    color = _SIDE_COLOR.get(side, _SIDE_COLOR[""])

    win = tk.Toplevel(parent)
    win.title(f"Chromosomen-Browser — {match_name or match_guid[:12]}")
    win.geometry("900x680")

    total_cm = sum(s.get("length_cm") or 0 for s in segments)
    head = ttk.Frame(win); head.pack(fill="x", padx=12, pady=(10, 4))
    ttk.Label(head, text=(f"{match_name or match_guid[:12]}  ·  "
                          f"{len(segments)} Segmente  ·  {total_cm:.0f} cM  ·  "
                          f"Seite: {_SIDE_LABEL.get(side, side)}"),
              font=("Segoe UI", 10, "bold")).pack(side="left")
    # Legende
    leg = ttk.Frame(win); leg.pack(fill="x", padx=12, pady=(0, 4))
    for s, lbl in (("paternal", "väterlich"), ("maternal", "mütterlich"), ("", "unbekannt")):
        c = tk.Canvas(leg, width=14, height=12, highlightthickness=0)
        c.create_rectangle(0, 0, 14, 12, fill=_SIDE_COLOR[s], outline="")
        c.pack(side="left", padx=(8, 2))
        ttk.Label(leg, text=lbl, foreground="#555").pack(side="left")

    canvas = tk.Canvas(win, bg="#ffffff", highlightthickness=0)
    vsb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=6)

    if not segments:
        canvas.create_text(20, 20, anchor="nw", fill="#a05a00",
                           text=("Keine Segmentdaten für diesen Match.\n"
                                 "Segmente werden via GEDmatch/FTDNA-Import oder "
                                 "Ancestry-Segment-Download befüllt."),
                           font=("Segoe UI", 10))
        canvas.configure(scrollregion=(0, 0, 400, 80))
        return

    # Segmente nach Chromosom gruppieren
    by_chrom: dict[int, list] = {}
    for s in segments:
        by_chrom.setdefault(int(s["chromosome"]), []).append(s)

    ml      = 60     # linker Rand für Beschriftung
    row_h   = 22
    gap     = 8
    bar_h   = 14
    draw_w  = 760
    max_len = max(_CHROM_LEN_MBP.values())

    def _redraw(_evt=None):
        canvas.delete("all")
        w = canvas.winfo_width() or 820
        dw = max(400, w - ml - 30)
        y = 14
        for chrom in range(1, 24):
            clen = _CHROM_LEN_MBP.get(chrom, 150)
            bar_w = int(dw * clen / max_len)
            label = "X" if chrom == 23 else str(chrom)
            canvas.create_text(ml - 10, y + bar_h // 2, anchor="e",
                               text=f"Chr {label}", font=("Segoe UI", 8), fill="#333")
            # leeres Chromosom (Hintergrund)
            canvas.create_rectangle(ml, y, ml + bar_w, y + bar_h,
                                    fill="#eef0f3", outline="#d0d4da")
            # Segmente einzeichnen
            for s in by_chrom.get(chrom, []):
                x0 = ml + int(bar_w * (s["start_location"] or 0) / (clen * 1e6))
                x1 = ml + int(bar_w * (s["end_location"] or 0) / (clen * 1e6))
                x1 = max(x1, x0 + 2)
                x0 = max(ml, min(x0, ml + bar_w))
                x1 = max(ml, min(x1, ml + bar_w))
                canvas.create_rectangle(x0, y, x1, y + bar_h,
                                        fill=color, outline="")
                if (s.get("length_cm") or 0) >= 15:
                    canvas.create_text(min(x1 + 3, ml + bar_w),
                                       y + bar_h // 2, anchor="w",
                                       text=f"{s['length_cm']:.0f}",
                                       font=("Segoe UI", 7), fill="#444")
            y += row_h + gap
        canvas.configure(scrollregion=(0, 0, ml + draw_w + 40, y + 10))

    canvas.bind("<Configure>", _redraw)
    _redraw()
