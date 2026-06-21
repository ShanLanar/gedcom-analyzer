"""
ancestry/gui/analysis/triangulation_view.py – Segment-Triangulation-Popup.

Zeigt Triangulationsgruppen (TGs) aus DNA-Segmenten + Shared-Match-Bestätigung
mit interaktiver Chromosomenkarte und Mitglieder-Detail-Panel.
"""

import logging
import tkinter as tk
from tkinter import ttk

from ancestry.core.triangulation import (
    annotate_tg_candidate_mrca,
    build_triangulation_groups,
)

log = logging.getLogger(__name__)

MAP_CHROM_LENGTHS_MBP = {
    1: 249, 2: 243, 3: 199, 4: 191, 5: 181, 6: 171, 7: 159, 8: 146, 9: 141,
    10: 135, 11: 135, 12: 133, 13: 115, 14: 107, 15: 102, 16: 91, 17: 83,
    18: 80, 19: 59, 20: 63, 21: 48, 22: 51, 23: 155,
}

_PALETTE = [
    "#1a73e8", "#e8711a", "#2da44e", "#a832a8", "#e81a4b",
    "#1ab8e8", "#8e8e00", "#e8a81a", "#666", "#333",
]


def show_triangulation(app) -> None:
    """Öffnet das Triangulation-Popup für das aktive Kit."""
    test_guid = app._current_guid()
    if not test_guid:
        from tkinter import messagebox
        messagebox.showwarning(app._t("dlg.no_kit"), app._t("dlg.m_choose_kit"))
        return

    win = tk.Toplevel(app)
    win.title("Segment-Triangulation")
    win.geometry("1020x720")

    # ── Einstellungsleiste ────────────────────────────────────────────────────
    top = ttk.Frame(win)
    top.pack(fill="x", padx=10, pady=(10, 2))
    ttk.Label(top, text="Min. Segment:", style="Bold.TLabel").pack(side="left")
    min_cm_var = tk.StringVar(value="7")
    ttk.Entry(top, textvariable=min_cm_var, width=5).pack(side="left", padx=4)
    ttk.Label(top, text=app._t("av.min_overlap")).pack(side="left")
    min_ov_var = tk.StringVar(value="5")
    ttk.Entry(top, textvariable=min_ov_var, width=5).pack(side="left", padx=4)
    ttk.Label(top, text="cM").pack(side="left")
    ttk.Button(top, text="↻", width=3, command=lambda: reload()).pack(side="left", padx=8)

    def _export_report():
        import webbrowser
        from tkinter import messagebox

        from ancestry.core.triangulation_report import build_triangulation_report_html
        from ancestry.paths import EXPORT_DIR
        tgs = list(store.values())
        if not tgs:
            messagebox.showinfo(app._t("dlg.no_data"), app._t("av.no_tgs"))
            return
        names = {m.match_guid: m.display_name
                 for m in app._db.get_matches(test_guid=test_guid)}
        html = build_triangulation_report_html(
            tgs, name_by_guid=names, kit_label=test_guid[:12])
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = EXPORT_DIR / "triangulation_report.html"
        out.write_text(html, encoding="utf-8")
        webbrowser.open(out.as_uri())

    ttk.Button(top, text=app._t("av.tg_export"),
               command=_export_report).pack(side="left", padx=4)

    # Phasing-Hinweis
    ttk.Label(win,
        text=app._t("av.phasing_warn"),
        foreground="#a06000", wraplength=980, justify="left",
        font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 2))

    info = ttk.Label(win, text="", style="Bold.TLabel")
    info.pack(anchor="w", padx=10, pady=(2, 2))

    # ── Hauptpane: Tabelle | Chromosomenkarte | Mitglieder ────────────────────
    pane = ttk.PanedWindow(win, orient="vertical")
    pane.pack(fill="both", expand=True, padx=10, pady=4)
    tframe   = ttk.Frame(pane); pane.add(tframe,   weight=2)
    mapframe = ttk.Frame(pane); pane.add(mapframe, weight=3)
    bframe   = ttk.Frame(pane); pane.add(bframe,   weight=2)

    cols = ("chrom", "region", "members", "avg_cm")
    tv = ttk.Treeview(tframe, columns=cols, show="headings", selectmode="browse")
    for col, lbl, w, anchor in [
        ("chrom",   "Chr",          60,  "center"),
        ("region",  "Region (Mbp)", 220, "w"),
        ("members", "Mitglieder",    80, "center"),
        ("avg_cm",  "Ø cM",         80,  "center"),
    ]:
        tv.heading(col, text=lbl)
        tv.column(col, width=w, anchor=anchor)
    tv.pack(side="left", fill="both", expand=True)
    sb = ttk.Scrollbar(tframe, orient="vertical", command=tv.yview)
    sb.pack(side="right", fill="y")
    tv.configure(yscrollcommand=sb.set)

    map_canvas = tk.Canvas(mapframe, bg="#f8f8f8", highlightthickness=1,
                           highlightbackground="#cccccc")
    map_canvas.pack(fill="both", expand=True, padx=4, pady=4)

    ttk.Label(bframe, text=app._t("av.tg_members"),
              style="Bold.TLabel").pack(anchor="w", pady=(4, 2))
    detail = tk.Text(bframe, height=8, wrap="word", font=("Segoe UI", 9))
    detail.pack(fill="both", expand=True)

    store: dict = {}

    def _draw_map(tgs):
        map_canvas.delete("all")
        if not tgs:
            return
        W = map_canvas.winfo_width() or 900
        H = map_canvas.winfo_height() or 300
        ml, mr, mt, mb = 36, 10, 10, 10
        track_h = max(4, (H - mt - mb) // 23 - 2)
        y_step  = (H - mt - mb) // 23
        max_len = max(MAP_CHROM_LENGTHS_MBP.values())
        draw_w  = W - ml - mr

        for idx, chrom in enumerate(range(1, 24)):
            y = mt + idx * y_step
            lbl = "X" if chrom == 23 else str(chrom)
            map_canvas.create_text(ml - 4, y + track_h // 2, text=lbl,
                                   anchor="e", font=("Segoe UI", 7), fill="#666")
            chrom_len = MAP_CHROM_LENGTHS_MBP.get(chrom, 150)
            bar_w = int(draw_w * chrom_len / max_len)
            map_canvas.create_rectangle(ml, y, ml + bar_w, y + track_h,
                                        fill="#e0e0e0", outline="", tags="bg")

        for tg_idx, tg in enumerate(tgs):
            color     = _PALETTE[tg_idx % len(_PALETTE)]
            chrom     = tg["chromosome"]
            chrom_len = MAP_CHROM_LENGTHS_MBP.get(chrom, 150)
            idx       = chrom - 1
            y         = mt + idx * y_step
            bar_w     = int(draw_w * chrom_len / max_len)
            for m in tg["members"]:
                x0 = ml + int(bar_w * m["start"] / (chrom_len * 1e6))
                x1 = ml + int(bar_w * m["end"]   / (chrom_len * 1e6))
                map_canvas.create_rectangle(x0, y, max(x1, x0 + 2), y + track_h,
                                            fill=color, outline="")
            rx0 = ml + int(bar_w * tg["region_start"] / (chrom_len * 1e6))
            rx1 = ml + int(bar_w * tg["region_end"]   / (chrom_len * 1e6))
            map_canvas.create_rectangle(rx0, y - 1, max(rx1, rx0 + 3), y + track_h + 1,
                                        fill="", outline=color, width=2)

    def reload(*_):
        try:
            min_cm = float(min_cm_var.get() or 7)
            min_ov = float(min_ov_var.get() or 5)
        except ValueError:
            min_cm, min_ov = 7.0, 5.0
        tgs = build_triangulation_groups(app._db, test_guid,
                                         min_cm=min_cm, min_overlap_cm=min_ov)
        try:
            annotate_tg_candidate_mrca(app._db, test_guid, tgs)
        except Exception as e:
            log.debug("Triangulation candidate MRCA: %s", e)
        tv.delete(*tv.get_children())
        store.clear()
        for tg in tgs:
            n      = len(tg["members"])
            avg_cm = sum(m["length_cm"] for m in tg["members"]) / n if n else 0
            iid = tv.insert("", "end", values=(
                tg["chromosome_label"],
                f"{tg['region_start']/1_000_000:.1f} – {tg['region_end']/1_000_000:.1f}",
                n, f"{avg_cm:.1f}"))
            store[iid] = tg
        if tgs:
            info.configure(text=(
                f"{len(tgs)} Triangulationsgruppen "
                f"(min. {min_cm:.0f} cM, Überlappung ≥ {min_ov:.0f} cM)"))
        else:
            info.configure(
                text=app._t("av.no_tgs"))
        win.after(50, lambda: _draw_map(tgs))

    def on_sel(_event=None):
        detail.delete("1.0", "end")
        sel = tv.selection()
        if not sel:
            return
        tg = store.get(sel[0])
        if not tg:
            return
        s_mbp = tg["region_start"] / 1_000_000
        e_mbp = tg["region_end"]   / 1_000_000
        detail.insert("end", f"Chr {tg['chromosome_label']}  {s_mbp:.2f} – {e_mbp:.2f} Mbp\n")
        try:
            cand = tg.get("candidate_mrca") or []
            if cand:
                top = cand[0]
                yr = f"{top['year']}" if top.get("year") else "?"
                detail.insert("end",
                    f"  → Wahrscheinlicher gem. Vorfahr: "
                    f"{top['name']} ({yr}) — {top['member_count']} Mitglieder\n")
        except Exception as e:
            log.debug("Triangulation candidate MRCA line: %s", e)
        detail.insert("end", "\n")
        name_map: dict = {}
        try:
            name_map = {m.match_guid: m.display_name
                        for m in app._db.get_matches(test_guid)}
        except Exception as e:
            log.debug("Triangulation name_map: %s", e)
        for m in sorted(tg["members"], key=lambda x: -x["length_cm"]):
            name = name_map.get(m["match_guid"], m["match_guid"][:12])
            detail.insert("end",
                f"  {name[:42]:<44} {m['length_cm']:6.1f} cM  "
                f"({m['start']/1e6:.1f}–{m['end']/1e6:.1f} Mbp)\n")

        # Geburtsorte der Generation 2–4 aller Segment-Mitglieder aggregieren
        detail.insert("end", "\n")
        try:
            guids = [m["match_guid"] for m in tg["members"]]
            if guids:
                placeholders = ",".join("?" * len(guids))
                with app._db._cursor() as cur:
                    place_rows = cur.execute(
                        f"SELECT birth_place FROM match_pedigree "
                        f"WHERE match_guid IN ({placeholders}) "
                        f"AND generation BETWEEN 2 AND 4 "
                        f"AND birth_place IS NOT NULL AND birth_place != ''",
                        guids).fetchall()
                from collections import Counter
                counts = Counter(r["birth_place"] for r in place_rows)
                if counts:
                    top = counts.most_common(5)
                    places_str = ", ".join(f"{p} ({n}x)" for p, n in top)
                    detail.insert("end", f"Herkunftsorte (Gen. 2–4): {places_str}\n")
                    detail.insert("end", "→ Kirchenbuch-Suche empfohlen?\n")
        except Exception as e:
            log.debug("Triangulation Geburtsorte: %s", e)

    tv.bind("<<TreeviewSelect>>", on_sel)
    win.after(100, reload)
