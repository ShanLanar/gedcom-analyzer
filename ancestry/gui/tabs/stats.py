"""Statistiken-Tab: Kennzahlen, Fortschrittsringe, Beziehungsverteilung."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from ancestry.gui.state import AppState
from ancestry.gui.widgets.theme import register_lang, COLORS
from ancestry.gui.widgets.tooltip import register_tooltip

log = logging.getLogger(__name__)


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
        # Statistik wird NICHT beim Start berechnet (teuer bei großen
        # Beständen). Sie wird beim ersten Öffnen des Reiters berechnet und
        # zwischengespeichert; mark_dirty() erzwingt eine Neuberechnung
        # (z. B. bei GEDCOM-Änderung oder nach einem Download).
        self._stats_dirty = True
        self._build()

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _build(self):
        s  = self._state
        t  = s.t
        lw = s.lang_widgets
        lh = s.lang_headings

        _sv = tk.StringVar(value=t("st.refresh"))
        _b = ttk.Button(self, textvariable=_sv, command=self.refresh)
        _b.pack(anchor="ne", padx=14, pady=8)
        register_tooltip(_b, "tt.st_refresh", self._state)
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

        # ── Populationsstatistik (population_stats) — dauerhaft im Fenster ────
        popf = ttk.LabelFrame(self, text="📊 Populationsstatistik", padding=8)
        popf.pack(fill="x", padx=14, pady=(0, 8))
        ttk.Label(popf, text="Nachnamen-Entropie pro Jahrzehnt (Namensvielfalt):",
                  foreground="#666666").pack(anchor="w")
        self._ent_tree = ttk.Treeview(popf, columns=("dec", "ent", "uni", "tot"),
                                      show="headings", height=6)
        for c, txt, w in (("dec", "Jahrzehnt", 90), ("ent", "Entropie", 90),
                          ("uni", "Namen", 80), ("tot", "Personen", 90)):
            self._ent_tree.heading(c, text=txt)
            self._ent_tree.column(c, width=w, anchor="center", stretch=False)
        self._ent_tree.pack(fill="x", pady=(2, 8))
        register_lang(self._state, ttk.Label(popf, text=self._state.t("st.cm_hist"),
                  foreground="#666666"), "st.cm_hist").pack(anchor="w")
        self._cm_tree = ttk.Treeview(popf, columns=("bin", "obs", "hint"),
                                     show="headings", height=6)
        for c, txt, w in (("bin", "cM-Bereich", 120), ("obs", "Matches", 80),
                          ("hint", "Verwandtschaft", 180)):
            self._cm_tree.heading(c, text=txt)
            self._cm_tree.column(c, width=w, anchor="w", stretch=False)
        self._cm_tree.pack(fill="x", pady=(2, 0))

        # ── cM-Zeitreihe ─────────────────────────────────────────────────────────
        tsf = ttk.LabelFrame(self, text="📈 cM-Zeitreihe (Match-Verlauf)", padding=8)
        tsf.pack(fill="x", padx=14, pady=(0, 8))
        ttk.Label(tsf, text="Neue Matches und Ø cM pro Download-Tag:",
                  foreground="#666666").pack(anchor="w")
        self._ts_canvas = tk.Canvas(tsf, height=90, bg=COLORS["bg"],
                                    highlightthickness=0)
        self._ts_canvas.pack(fill="x", expand=True, pady=(4, 0))

        # Bewusst KEIN refresh() hier — siehe __init__ (_stats_dirty).

    # ── Daten ────────────────────────────────────────────────────────────────

    def on_show(self):
        """Vom Haupt-Notebook aufgerufen, wenn dieser Reiter sichtbar wird.
        Berechnet die Statistik nur, wenn sie als veraltet markiert ist."""
        if self._stats_dirty:
            self.refresh()

    def mark_dirty(self):
        """Markiert die Statistik als veraltet (Neuberechnung beim nächsten
        Öffnen des Reiters bzw. via on_show())."""
        self._stats_dirty = True

    def refresh(self):
        self._stats_dirty = False
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
        self.after(70, self._refresh_population)
        self.after(80, self._refresh_timeseries)

    def _refresh_population(self):
        from ancestry.core import population_stats as ps
        try:
            self._ent_tree.delete(*self._ent_tree.get_children())
            for r in ps.surname_entropy_series(self._state.db):
                self._ent_tree.insert("", "end", values=(
                    r.get("decade"), f"{r.get('entropy', 0):.2f}",
                    r.get("unique"), r.get("total")))
        except Exception as e:
            log.debug("surname_entropy_series: %s", e)
        try:
            self._cm_tree.delete(*self._cm_tree.get_children())
            tg = self._get_test_guid()
            if tg:
                for r in ps.cm_histogram(self._state.db, tg):
                    self._cm_tree.insert("", "end", values=(
                        r.get("label", ""), r.get("observed", 0),
                        r.get("rel_hint", "")))
        except Exception as e:
            log.debug("cm_histogram: %s", e)

    def _refresh_timeseries(self):
        """Zeichnet die cM-Zeitreihe: Match-Neuzugänge + Ø cM pro Tag."""
        c = self._ts_canvas
        c.delete("all")
        tg = self._get_test_guid()
        if not tg:
            c.configure(height=22)
            c.create_text(10, 11, text="Kein Kit ausgewählt", anchor="w",
                          fill="#777777", font=("Segoe UI", 9))
            return
        try:
            with self._state.db._cursor() as cur:
                rows = cur.execute(
                    "SELECT date(fetched_at) AS day, COUNT(*) AS cnt, "
                    "ROUND(AVG(shared_cm), 1) AS avg_cm "
                    "FROM matches WHERE test_guid=? AND fetched_at IS NOT NULL "
                    "GROUP BY day ORDER BY day",
                    (tg,),
                ).fetchall()
        except Exception as e:
            log.debug("timeseries query: %s", e)
            rows = []

        if not rows or len(rows) < 2:
            c.configure(height=22)
            c.create_text(10, 11, text="Noch keine Zeitreihen-Daten (min. 2 Download-Tage nötig)",
                          anchor="w", fill="#777777", font=("Segoe UI", 9))
            return

        c.update_idletasks()
        W = c.winfo_width() or 600
        H = 80
        c.configure(height=H)
        PAD_L, PAD_R, PAD_T, PAD_B = 48, 12, 8, 20

        counts = [r[1] for r in rows]
        avgs   = [float(r[2] or 0) for r in rows]
        days   = [r[0] for r in rows]
        n      = len(rows)

        max_cnt = max(counts) or 1
        max_avg = max(avgs)   or 1
        chart_w = W - PAD_L - PAD_R
        chart_h = H - PAD_T - PAD_B

        def xp(i): return PAD_L + i * chart_w / max(n - 1, 1)
        def yp_cnt(v): return PAD_T + chart_h - (v / max_cnt) * chart_h
        def yp_avg(v): return PAD_T + chart_h - (v / max_avg) * chart_h

        # Achsen
        c.create_line(PAD_L, PAD_T, PAD_L, H - PAD_B, fill="#555566")
        c.create_line(PAD_L, H - PAD_B, W - PAD_R, H - PAD_B, fill="#555566")

        # Match-Anzahl (Balken, blau)
        bar_w = max(2, chart_w // n - 2)
        for i, cnt in enumerate(counts):
            x = xp(i)
            y = yp_cnt(cnt)
            c.create_rectangle(x - bar_w // 2, y, x + bar_w // 2,
                                H - PAD_B, fill=COLORS["primary"], outline="")

        # Ø cM-Linie (orange)
        pts = [(xp(i), yp_avg(v)) for i, v in enumerate(avgs)]
        for i in range(len(pts) - 1):
            c.create_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                          fill="#ffaa33", width=2)

        # Beschriftungen: erstes + letztes Datum
        c.create_text(PAD_L, H - PAD_B + 4, text=days[0][:10],
                      anchor="nw", font=("Segoe UI", 7), fill="#999999")
        c.create_text(W - PAD_R, H - PAD_B + 4, text=days[-1][:10],
                      anchor="ne", font=("Segoe UI", 7), fill="#999999")
        c.create_text(PAD_L - 4, PAD_T, text=str(max_cnt),
                      anchor="e", font=("Segoe UI", 7), fill=COLORS["primary"])
        c.create_text(PAD_L - 4, H - PAD_B, text="0",
                      anchor="e", font=("Segoe UI", 7), fill="#777777")
        # Legende
        c.create_rectangle(W - PAD_R - 90, PAD_T, W - PAD_R - 82, PAD_T + 8,
                           fill=COLORS["primary"], outline="")
        c.create_text(W - PAD_R - 80, PAD_T + 1, text="Matches",
                      anchor="nw", font=("Segoe UI", 7), fill=COLORS["primary"])
        c.create_line(W - PAD_R - 40, PAD_T + 4, W - PAD_R - 32, PAD_T + 4,
                      fill="#ffaa33", width=2)
        c.create_text(W - PAD_R - 30, PAD_T + 1, text="Ø cM",
                      anchor="nw", font=("Segoe UI", 7), fill="#ffaa33")

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
        except Exception as e:
            log.debug("stats side/endo count: %s", e)
            side_known = endo_known = 0

        gedcom_linked = stats.get("gedcom_linked", 0) or 0
        try:
            tg2 = self._get_test_guid()
            if tg2:
                with self._state.db._cursor() as cur:
                    sm_fetched = cur.execute(
                        "SELECT COUNT(*) FROM shared_matches_fetched WHERE test_guid=?",
                        (tg2,)).fetchone()[0]
            else:
                sm_fetched = 0
        except Exception as e:
            log.debug("stats sm_fetched: %s", e)
            sm_fetched = 0
        rings = [
            (with_tree / total,                   f"{with_tree}/{total}",       "Mit Baum",       COLORS["accent"]),
            (ped_loaded / max(with_tree, 1),       f"{ped_loaded}/{with_tree}",  "Ahnentafel",     COLORS["success"]),
            (side_known / total,                   f"{side_known}/{total}",      "Seite bekannt",  "#8B4513"),
            (gedcom_linked / total,                f"{gedcom_linked}/{total}",   "GEDCOM-Treffer", COLORS["primary"]),
            (sm_fetched / max(total, 1),           f"{sm_fetched}/{total}",      "SM geholt",      "#9b59b6"),
        ]
        R = 35; cx_start = 55
        for i, (pct, label_cnt, title, color) in enumerate(rings):
            cx = cx_start + i * 130
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
            except Exception as e:
                log.debug("get_kit_ethnicity: %s", e)
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
            except Exception as e:
                log.debug("get_kit_traits: %s", e)
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
