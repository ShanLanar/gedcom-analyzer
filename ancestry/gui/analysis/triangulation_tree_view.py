"""
ancestry/gui/analysis/triangulation_tree_view.py – Hypothetischer Baum für
eine Triangulationsgruppe.

Zeigt einen bereits im eigenen GEDCOM bekannten Vorfahren (aus
annotate_tg_candidate_mrca) als vermuteten gemeinsamen Ursprung der Gruppe,
darunter alle Mitglieder: mit durchgezogener Linie, wenn sie zusätzlich per
GEDCOM-Verknüpfung bestätigt sind, sonst gestrichelt (nur DNA-Segment-Beleg).
Siehe ancestry/core/triangulation.py:build_hypothetical_tree_data für die
Datengrundlage und deren genealogische Einordnung.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

from ancestry.core.triangulation import build_hypothetical_tree_data

log = logging.getLogger(__name__)

LEAF_W, LEAF_H = 190, 58
ANCESTOR_W, ANCESTOR_H = 240, 76
GAP_X = 24
TOP_Y = 20
ROW_GAP = 56

C_CONFIRMED, C_CONFIRMED_BD = "#c8ebd0", "#5caa6f"
C_HYPOTHESIS, C_HYPOTHESIS_BD = "#dde0e5", "#999aaa"
C_ANCESTOR, C_ANCESTOR_BD = "#f4e6c8", "#a06000"


def show_hypothetical_tree(app, tg: dict) -> None:
    """Öffnet das Hypothetischer-Baum-Fenster für eine Triangulationsgruppe."""
    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning(app._t("dlg.no_kit"), app._t("dlg.m_choose_kit"))
        return

    candidates = tg.get("candidate_mrca") or []
    if not candidates:
        messagebox.showinfo(app._t("av.tg_hypo_tree"), app._t("av.tg_no_mrca"))
        return

    win = tk.Toplevel(app)
    win.title(f"🌳 Hypothetischer Baum – Chr {tg['chromosome_label']}")
    win.geometry("920x600")

    top = ttk.Frame(win)
    top.pack(fill="x", padx=10, pady=(10, 4))
    ttk.Label(top, text=app._t("av.tg_pick_ancestor")).pack(side="left")
    opts = [
        f"{c['name']} ({c['year'] if c.get('year') else '?'}) — "
        f"{c['member_count']} Mitgl., ⌀{c['avg_score']:.2f}"
        for c in candidates
    ]
    sel_var = tk.StringVar(value=opts[0])
    cb = ttk.Combobox(top, textvariable=sel_var, values=opts, width=54, state="readonly")
    cb.pack(side="left", padx=6)

    ttk.Label(win, text=app._t("av.tg_hypo_disclaimer"),
              foreground="#a06000", wraplength=880, justify="left",
              font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 4))

    # Scrollbars zuerst packen (mit ihrem jeweiligen side), Canvas mit
    # expand=True zuletzt — sonst nimmt sich das expandierende Widget die
    # gesamte Cavity und die Scrollbars bleiben unsichtbar (Tk-Pack-Reihenfolge).
    sb_x = ttk.Scrollbar(win, orient="horizontal")
    sb_x.pack(side="bottom", fill="x", padx=10)

    canvas_frame = ttk.Frame(win)
    canvas_frame.pack(fill="both", expand=True, padx=10, pady=4)
    sb_y = ttk.Scrollbar(canvas_frame, orient="vertical")
    sb_y.pack(side="right", fill="y")
    canvas = tk.Canvas(canvas_frame, bg="#f8f8f8", highlightthickness=1,
                       highlightbackground="#cccccc",
                       yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb_y.configure(command=canvas.yview)
    sb_x.configure(command=canvas.xview)

    def _draw(_evt=None) -> None:
        idx = opts.index(sel_var.get()) if sel_var.get() in opts else 0
        cand = candidates[idx]
        try:
            data = build_hypothetical_tree_data(app._db, test_guid, tg, cand["ged_id"])
        except Exception as e:
            log.debug("show_hypothetical_tree build data: %s", e)
            data = None
        canvas.delete("all")
        if data is None:
            canvas.create_text(20, 20, anchor="nw", text=app._t("av.tg_no_mrca"),
                               font=("Segoe UI", 9), fill="#888")
            return
        _render_tree(canvas, data, app._t)

    cb.bind("<<ComboboxSelected>>", _draw)
    win.after(50, _draw)


def _render_tree(canvas: tk.Canvas, data: dict, _t) -> None:
    ancestor = data["ancestor"]
    confirmed = data["confirmed"]
    hypothesis = data["hypothesis"]
    members = [(m, True) for m in confirmed] + [(m, False) for m in hypothesis]

    n = max(len(members), 1)
    total_w = max(ANCESTOR_W + 2 * GAP_X, n * (LEAF_W + GAP_X) + GAP_X)
    total_h = TOP_Y + ANCESTOR_H + ROW_GAP + LEAF_H + 30
    canvas.configure(scrollregion=(0, 0, total_w, total_h))

    ax = total_w / 2
    ay = TOP_Y
    name = f"{ancestor['given_name']} {ancestor['surname']}".strip() or "?"
    canvas.create_rectangle(
        ax - ANCESTOR_W / 2, ay, ax + ANCESTOR_W / 2, ay + ANCESTOR_H,
        fill=C_ANCESTOR, outline=C_ANCESTOR_BD, width=2, dash=(5, 3))
    canvas.create_text(ax, ay + 12, text=f"🌳 {name}",
                       font=("Segoe UI", 10, "bold"), fill="#5a3d00")
    life = []
    if ancestor.get("birth_year"):
        life.append(f"*{ancestor['birth_year']}")
    if ancestor.get("death_year"):
        life.append(f"†{ancestor['death_year']}")
    canvas.create_text(ax, ay + 30, text="  ".join(life) or "(Daten fehlen)",
                       font=("Segoe UI", 8), fill="#5a3d00")
    if ancestor.get("birth_place"):
        canvas.create_text(ax, ay + 46, text=f"📍 {ancestor['birth_place']}",
                           font=("Segoe UI", 7), fill="#7a5a10")
    if ancestor.get("sosa"):
        canvas.create_text(ax, ay + 62, text=f"Sosa #{ancestor['sosa']} in deinem Baum",
                           font=("Segoe UI", 7, "italic"), fill="#7a5a10")

    row_y = ay + ANCESTOR_H + ROW_GAP
    bus_y = row_y - ROW_GAP / 2
    x = GAP_X
    for m, is_confirmed in members:
        cx0, cy0 = x, row_y
        cx1 = x + LEAF_W
        leaf_cx = (cx0 + cx1) / 2
        color = C_CONFIRMED if is_confirmed else C_HYPOTHESIS
        border = C_CONFIRMED_BD if is_confirmed else C_HYPOTHESIS_BD
        dash = () if is_confirmed else (4, 3)

        canvas.create_line(ax, ay + ANCESTOR_H, ax, bus_y, fill=border, dash=dash)
        canvas.create_line(ax, bus_y, leaf_cx, bus_y, fill=border, dash=dash)
        canvas.create_line(leaf_cx, bus_y, leaf_cx, cy0, fill=border, dash=dash)

        canvas.create_rectangle(cx0, cy0, cx1, cy0 + LEAF_H,
                                fill=color, outline=border, width=1)
        name_txt = m["display_name"]
        if len(name_txt) > 26:
            name_txt = name_txt[:24] + "…"
        canvas.create_text(cx0 + 8, cy0 + 8, anchor="nw", text=name_txt,
                           font=("Segoe UI", 9, "bold"), fill="#1a1a2e")
        canvas.create_text(cx0 + 8, cy0 + 25, anchor="nw",
                           text=f"🧬 {m['length_cm']:.1f} cM",
                           font=("Segoe UI", 8), fill="#1a1a2e")
        canvas.create_text(cx0 + 8, cy0 + 40, anchor="nw",
                           text=f"{m['start']/1e6:.1f}–{m['end']/1e6:.1f} Mbp",
                           font=("Segoe UI", 7), fill="#666")
        badge = _t("av.tg_confirmed") if is_confirmed else _t("av.tg_hypothesis")
        canvas.create_text(cx1 - 6, cy0 + 6, anchor="ne", text=badge,
                           font=("Segoe UI", 7, "bold"),
                           fill="#2d8a3a" if is_confirmed else "#a06000")
        x += LEAF_W + GAP_X
