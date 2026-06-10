"""Statistiken-Tab: Kennzahlen, Fortschrittsringe, Beziehungsverteilung."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ancestry.gui.state import AppState
from ancestry.gui.widgets.theme import COLORS


class StatsTab(ttk.Frame):
    """Statistiken-Tab des Ancestry-DNA-Tools.

    Parameters
    ----------
    parent:
        ttk.Frame aus dem Notebook.
    state:
        Gemeinsamer App-Zustand (DB, Sprach-Listen, …).
    get_test_guid:
        Callable ohne Argumente, das die aktuell gewählte Test-GUID liefert
        (oder None). Wird für die Fortschrittsringe benötigt.
    """

    def __init__(self, parent: tk.Widget, state: AppState,
                 get_test_guid: Callable[[], Optional[str]]):
        super().__init__(parent)
        self._state = state
        self._get_test_guid = get_test_guid
        self._stat_vars:    dict[str, tk.StringVar] = {}
        self._kit_stat_tree: Optional[ttk.Treeview] = None
        self._ring_canvas:   Optional[tk.Canvas]    = None
        self._rel_tree:      Optional[ttk.Treeview] = None
        self._build()

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _build(self):
        s  = self._state
        t  = s.t
        lw = s.lang_widgets
        lh = s.lang_headings

        _sv = tk.StringVar(value=t("st.refresh"))
        ttk.Button(self, textvariable=_sv,
                   command=self.refresh).pack(anchor="ne", padx=14, pady=8)
        lw.append((_sv, "st.refresh"))

        kz = ttk.LabelFrame(self, text=t("st.kz"), padding=10)
        kz.pack(fill="x", padx=14, pady=4)
        lw.append((kz, "st.kz"))

        stat_label_keys = [
            ("total",               "st.total"),
            ("max_cm",              "st.max_cm"),
            ("avg_cm",              "st.avg_cm"),
            ("starred_count",       "st.starred"),
            ("with_tree",           "st.with_tree"),
            ("with_note",           "st.with_note"),
            ("shared_total",        "st.shared_tot"),
            ("shared_primary_count","st.shared_pri"),
        ]
        for i, (stat_key, t_key) in enumerate(stat_label_keys):
            sv_lbl = tk.StringVar(value=t(t_key))
            ttk.Label(kz, textvariable=sv_lbl, foreground="#555555").grid(
                row=i // 4, column=(i % 4) * 2, sticky="e", padx=(14, 4), pady=3)
            lw.append((sv_lbl, t_key))
            var = tk.StringVar(value="—")
            ttk.Label(kz, textvariable=var, font=("Segoe UI", 10, "bold"),
                      foreground=COLORS["primary"]).grid(
                row=i // 4, column=(i % 4) * 2 + 1, sticky="w")
            self._stat_vars[stat_key] = var

        # Pedigree completeness section
        pz = ttk.LabelFrame(self, text=t("st.ped_kz"), padding=10)
        pz.pack(fill="x", padx=14, pady=4)
        lw.append((pz, "st.ped_kz"))
        ped_label_keys = [
            ("ped_loaded",   "st.ped_loaded"),
            ("ped_avg_depth","st.ped_depth"),
            ("ped_surnames", "st.ped_surn"),
            ("gen_length",   "st.gen_length"),
        ]
        for i, (stat_key, t_key) in enumerate(ped_label_keys):
            sv_lbl = tk.StringVar(value=t(t_key))
            ttk.Label(pz, textvariable=sv_lbl, foreground="#555555").grid(
                row=0, column=i * 2, sticky="e", padx=(14, 4), pady=3)
            lw.append((sv_lbl, t_key))
            var = tk.StringVar(value="—")
            ttk.Label(pz, textvariable=var, font=("Segoe UI", 10, "bold"),
                      foreground=COLORS["primary"]).grid(row=0, column=i * 2 + 1, sticky="w")
            self._stat_vars[stat_key] = var

        # GEDCOM bridge section
        gz = ttk.LabelFrame(self, text=t("st.ged_kz"), padding=10)
        gz.pack(fill="x", padx=14, pady=4)
        lw.append((gz, "st.ged_kz"))
        ged_label_keys = [
            ("gedcom_persons", "st.ged_pers"),
            ("gedcom_linked",  "st.ged_linked"),
        ]
        for i, (stat_key, t_key) in enumerate(ged_label_keys):
            sv_lbl = tk.StringVar(value=t(t_key))
            ttk.Label(gz, textvariable=sv_lbl, foreground="#555555").grid(
                row=0, column=i * 2, sticky="e", padx=(14, 4), pady=3)
            lw.append((sv_lbl, t_key))
            var = tk.StringVar(value="—")
            ttk.Label(gz, textvariable=var, font=("Segoe UI", 10, "bold"),
                      foreground=COLORS["primary"]).grid(row=0, column=i * 2 + 1, sticky="w")
            self._stat_vars[stat_key] = var

        # Seitenzuweisung section
        sz = ttk.LabelFrame(self, text=t("st.side_kz"), padding=10)
        sz.pack(fill="x", padx=14, pady=4)
        lw.append((sz, "st.side_kz"))
        side_label_keys = [
            ("side_paternal", "st.side_pat"),
            ("side_maternal", "st.side_mat"),
            ("side_unset",    "st.side_open"),
        ]
        for i, (stat_key, t_key) in enumerate(side_label_keys):
            sv_lbl = tk.StringVar(value=t(t_key))
            ttk.Label(sz, textvariable=sv_lbl, foreground="#555555").grid(
                row=0, column=i * 2, sticky="e", padx=(14, 4), pady=3)
            lw.append((sv_lbl, t_key))
            var = tk.StringVar(value="—")
            ttk.Label(sz, textvariable=var, font=("Segoe UI", 10, "bold"),
                      foreground=COLORS["primary"]).grid(row=0, column=i * 2 + 1, sticky="w")
            self._stat_vars[stat_key] = var

        # Kits & Matches section
        kf = ttk.LabelFrame(self, text=t("st.kit_kz"), padding=10)
        kf.pack(fill="x", padx=14, pady=4)
        lw.append((kf, "st.kit_kz"))
        self._kit_stat_tree = ttk.Treeview(kf, columns=("kit", "count"),
                                           show="headings", height=4)
        self._kit_stat_tree.heading("kit",   text="Kit")
        self._kit_stat_tree.heading("count", text="Matches")
        self._kit_stat_tree.column("kit",   width=280)
        self._kit_stat_tree.column("count", width=80, anchor="e")
        self._kit_stat_tree.pack(fill="x")

        # Progress ring section
        ring_frame = ttk.Frame(self)
        ring_frame.pack(fill="x", padx=14, pady=4)
        self._ring_canvas = tk.Canvas(ring_frame, height=90, bg=COLORS["bg"],
                                      highlightthickness=0)
        self._ring_canvas.pack(fill="x")

        rf = ttk.LabelFrame(self, text=t("st.rel_dist"), padding=10)
        rf.pack(fill="x", padx=14, pady=4)
        lw.append((rf, "st.rel_dist"))
        self._rel_tree = ttk.Treeview(rf, columns=("rel", "count"),
                                      show="headings", height=6)
        self._rel_tree.heading("rel",   text=t("st.rel"))
        self._rel_tree.heading("count", text=t("st.count"))
        self._rel_tree.column("rel",   width=300)
        self._rel_tree.column("count", width=80, anchor="e")
        self._rel_tree.pack(fill="x")
        lh.append((self._rel_tree, "rel",   "st.rel"))
        lh.append((self._rel_tree, "count", "st.count"))

        # Ethnizität / Herkunft
        ef = ttk.LabelFrame(self, text=t("st.ethnicity"), padding=6)
        ef.pack(fill="x", padx=14, pady=4)
        lw.append((ef, "st.ethnicity"))
        self._eth_canvas = tk.Canvas(ef, height=1, bg=COLORS["bg"],
                                     highlightthickness=0)
        self._eth_canvas.pack(fill="x", expand=True)

        # Traits-Panel
        tf = ttk.LabelFrame(self, text=t("st.traits"), padding=6)
        tf.pack(fill="x", padx=14, pady=(0, 8))
        lw.append((tf, "st.traits"))
        self._traits_canvas = tk.Canvas(tf, height=1, bg=COLORS["bg"],
                                        highlightthickness=0)
        self._traits_canvas.pack(fill="x", expand=True)

        self.refresh()

    # ── Daten ────────────────────────────────────────────────────────────────

    def refresh(self):
        stats = self._state.db.get_statistics()
        for key, var in self._stat_vars.items():
            v = stats.get(key)
            if key == "gen_length":
                var.set(f"{v:.1f} J." if isinstance(v, float) else "—")
            elif isinstance(v, float):
                var.set(f"{v:.1f}")
            else:
                var.set(str(v) if v is not None else "—")
        self._rel_tree.delete(*self._rel_tree.get_children())
        for rel, cnt in stats.get("relationship_breakdown", []):
            self._rel_tree.insert("", "end", values=(rel, cnt))
        self._kit_stat_tree.delete(*self._kit_stat_tree.get_children())
        for kit_name, cnt in stats.get("kit_breakdown", []):
            self._kit_stat_tree.insert("", "end", values=(kit_name, cnt))
        self._draw_rings(stats)
        self.after(50, self._draw_ethnicity)
        self.after(60, self._draw_traits)

    def _draw_rings(self, stats: dict):
        c = self._ring_canvas
        c.delete("all")
        total = stats.get("total") or 0
        if total == 0:
            c.create_text(20, 45, text="—", anchor="w", fill="#888888",
                          font=("Segoe UI", 10))
            return
        with_tree  = stats.get("with_tree", 0) or 0
        ped_loaded = stats.get("ped_loaded", 0) or 0
        try:
            tg = self._get_test_guid()
            if tg:
                with self._state.db._cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM matches WHERE test_guid=? "
                        "AND paternal_maternal != '' AND paternal_maternal IS NOT NULL", (tg,))
                    side_known = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM matches WHERE test_guid=? "
                        "AND endogamy_cluster != '' AND endogamy_cluster IS NOT NULL", (tg,))
                    endo_known = cur.fetchone()[0]
            else:
                side_known = endo_known = 0
        except Exception:
            side_known = endo_known = 0

        gedcom_linked = stats.get("gedcom_linked", 0) or 0
        rings = [
            (with_tree / total,                   f"{with_tree}/{total}",      "Mit Baum",       COLORS["accent"]),
            (ped_loaded / max(with_tree, 1),       f"{ped_loaded}/{with_tree}", "Ahnentafel",     COLORS["success"]),
            (side_known / total,                   f"{side_known}/{total}",     "Seite bekannt",  "#8B4513"),
            (gedcom_linked / total,                f"{gedcom_linked}/{total}",  "GEDCOM-Treffer", COLORS["primary"]),
        ]
        R = 35; cx_start = 55
        for i, (pct, label_cnt, title, color) in enumerate(rings):
            cx = cx_start + i * 160
            cy = 45
            c.create_arc(cx - R, cy - R, cx + R, cy + R, start=90, extent=360,
                         style="arc", outline=COLORS["light"], width=8)
            extent = max(1, min(360, int(pct * 360)))
            c.create_arc(cx - R, cy - R, cx + R, cy + R, start=90, extent=-extent,
                         style="arc", outline=color, width=8)
            c.create_text(cx, cy - 6, text=f"{pct * 100:.0f}%",
                          font=("Segoe UI", 10, "bold"), fill=COLORS["text"])
            c.create_text(cx, cy + 8,      text=label_cnt, font=("Segoe UI", 7), fill="#777777")
            c.create_text(cx, cy + R + 12, text=title,     font=("Segoe UI", 8), fill=COLORS["text"])

    # ── Ethnizität-Balken ─────────────────────────────────────────────────────

    _SRC_COLOR = {"ancestry": "#1a73e8", "myheritage": "#e87b1a"}

    def _draw_ethnicity(self):
        c = self._eth_canvas
        c.delete("all")
        tg = self._get_test_guid()
        data: list[dict] = []
        if tg:
            try:
                data = self._state.db.get_kit_ethnicity(tg)
            except Exception:
                pass
        placeholder = "Keine Daten — im Download-Tab »Herkunft laden« klicken"
        if not data:
            c.configure(height=22)
            c.create_text(8, 11, text=placeholder, anchor="w",
                          fill="#999999", font=("Segoe UI", 8, "italic"))
            return

        LINE = 20
        BAR_X, BAR_W, PCT_X = 170, 200, 378
        total_rows = len(data)
        c.configure(height=max(total_rows * LINE + 8, 28))

        # Group header colours
        shown_sources: set[str] = set()
        y = 4
        for item in data:
            src = item.get("source", "ancestry")
            color = self._SRC_COLOR.get(src, "#555555")
            lbl   = (item.get("label") or "")[:24]
            pct   = item.get("pct", 0)
            bar_w = max(2, int(pct / 100 * BAR_W))

            if src not in shown_sources:
                src_label = "Ancestry" if src == "ancestry" else "MyHeritage"
                c.create_text(BAR_X - 8, y + LINE // 2, text=f"— {src_label} —",
                              anchor="e", font=("Segoe UI", 7, "bold"), fill=color)
                shown_sources.add(src)

            # label
            c.create_text(BAR_X - 8, y + LINE // 2, text=lbl,
                          anchor="e", font=("Segoe UI", 8), fill=COLORS.get("text", "#222222"))
            # background track
            c.create_rectangle(BAR_X, y + 4, BAR_X + BAR_W, y + LINE - 4,
                                fill="#e8e8e8", outline="")
            # filled bar
            c.create_rectangle(BAR_X, y + 4, BAR_X + bar_w, y + LINE - 4,
                                fill=color, outline="")
            # percentage text
            c.create_text(PCT_X, y + LINE // 2, text=f"{pct:.0f}%",
                          anchor="w", font=("Segoe UI", 8), fill="#555555")
            y += LINE

    # ── Traits-Panel ─────────────────────────────────────────────────────────

    def _draw_traits(self):
        c = self._traits_canvas
        c.delete("all")
        tg = self._get_test_guid()
        data: list[dict] = []
        if tg:
            try:
                data = self._state.db.get_kit_traits(tg)
            except Exception:
                pass
        placeholder = "Keine Traits-Daten — im Download-Tab »Herkunft laden« klicken"
        if not data:
            c.configure(height=22)
            c.create_text(8, 11, text=placeholder, anchor="w",
                          fill="#999999", font=("Segoe UI", 8, "italic"))
            return

        # Two-column layout: name | result
        COLS = 2
        COL_W = 220
        LINE  = 18
        rows_per_col = -(-len(data) // COLS)   # ceil division
        c.configure(height=max(rows_per_col * LINE + 8, 28))

        for idx, item in enumerate(data):
            col  = idx // rows_per_col
            row  = idx %  rows_per_col
            x    = 8 + col * COL_W
            y    = 4 + row * LINE
            name    = (item.get("name") or "")[:22]
            result  = (item.get("result") or "—")[:22]
            pct_txt = (f"  {item['pct']:.0f}%" if "pct" in item else "")
            c.create_text(x, y + LINE // 2, text=name + ":", anchor="w",
                          font=("Segoe UI", 8), fill="#555555")
            c.create_text(x + 115, y + LINE // 2,
                          text=result + pct_txt, anchor="w",
                          font=("Segoe UI", 8, "bold"),
                          fill=COLORS.get("primary", "#1a73e8"))
