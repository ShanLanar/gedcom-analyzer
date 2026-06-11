"""StatsTabMixin – Tab 5: Statistiken für AncestryDnaApp."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk



class StatsTabMixin:
    """Mixin mit allen Statistik-Tab-Methoden für AncestryDnaApp."""

    def _build_tab_stats(self):
        f = self._tab_stats

        # Refresh-Button oben rechts
        top = ttk.Frame(f)
        top.pack(fill="x", padx=14, pady=(8, 2))
        _sv = tk.StringVar(value=self._t("st.refresh"))
        ttk.Button(top, textvariable=_sv,
                   command=self._refresh_stats).pack(side="right")
        self._lang_widgets.append((_sv, "st.refresh"))

        # 2-Spalten-Layout
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, padx=14, pady=4)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # ── Linke Spalte: alle Kennzahlen ─────────────────────────────────────
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self._stat_vars: dict[str, tk.StringVar] = {}

        def _stat_section(parent, t_key, items):
            lf = ttk.LabelFrame(parent, text=self._t(t_key), padding=6)
            lf.pack(fill="x", pady=(0, 6))
            self._lang_widgets.append((lf, t_key))
            for i, (stat_key, label_key) in enumerate(items):
                sv_lbl = tk.StringVar(value=self._t(label_key))
                ttk.Label(lf, textvariable=sv_lbl,
                          foreground=self._active_colors()["text"]).grid(
                    row=i // 2, column=(i % 2) * 2,
                    sticky="e", padx=(8, 4), pady=2)
                self._lang_widgets.append((sv_lbl, label_key))
                var = tk.StringVar(value="—")
                ttk.Label(lf, textvariable=var,
                          font=("Segoe UI", 10, "bold"),
                          foreground=self._active_colors()["primary"]).grid(
                    row=i // 2, column=(i % 2) * 2 + 1,
                    sticky="w", padx=(0, 16), pady=2)
                self._stat_vars[stat_key] = var

        _stat_section(left, "st.kz", [
            ("total",                "st.total"),
            ("max_cm",               "st.max_cm"),
            ("avg_cm",               "st.avg_cm"),
            ("starred_count",        "st.starred"),
            ("with_tree",            "st.with_tree"),
            ("with_note",            "st.with_note"),
            ("shared_total",         "st.shared_tot"),
            ("shared_primary_count", "st.shared_pri"),
        ])
        _stat_section(left, "st.ped_kz", [
            ("ped_loaded",    "st.ped_loaded"),
            ("ped_avg_depth", "st.ped_depth"),
            ("ped_surnames",  "st.ped_surn"),
        ])
        _stat_section(left, "st.ged_kz", [
            ("gedcom_persons", "st.ged_pers"),
            ("gedcom_linked",  "st.ged_linked"),
        ])
        _stat_section(left, "st.side_kz", [
            ("side_paternal", "st.side_pat"),
            ("side_maternal", "st.side_mat"),
            ("side_unset",    "st.side_open"),
        ])

        # ── Rechte Spalte: Kits + Ringe + Verwandtschaftsverteilung ──────────
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        kf = ttk.LabelFrame(right, text=self._t("st.kit_kz"), padding=6)
        kf.pack(fill="x", pady=(0, 6))
        self._lang_widgets.append((kf, "st.kit_kz"))
        self._kit_stat_tree = ttk.Treeview(kf, columns=("kit", "count"),
                                            show="headings", height=3)
        self._kit_stat_tree.heading("kit",   text="Kit")
        self._kit_stat_tree.heading("count", text="Matches")
        self._kit_stat_tree.column("kit",   width=200)
        self._kit_stat_tree.column("count", width=70, anchor="e")
        self._kit_stat_tree.pack(fill="x")

        ring_frame = ttk.Frame(right)
        ring_frame.pack(fill="x", pady=(0, 6))
        self._ring_canvas = tk.Canvas(ring_frame, height=90, bg=self._active_colors()["bg"],
                                       highlightthickness=0)
        self._ring_canvas.pack(fill="x")
        self._stat_ring_data: dict = {}

        rf = ttk.LabelFrame(right, text=self._t("st.rel_dist"), padding=6)
        rf.pack(fill="both", expand=True)
        self._lang_widgets.append((rf, "st.rel_dist"))
        self._rel_tree = ttk.Treeview(rf, columns=("rel", "count"),
                                       show="headings", height=10)
        self._rel_tree.heading("rel",   text=self._t("st.rel"))
        self._rel_tree.heading("count", text=self._t("st.count"))
        self._rel_tree.column("rel",    width=220)
        self._rel_tree.column("count",  width=70, anchor="e")
        self._rel_tree.pack(fill="both", expand=True)
        self._lang_headings.append((self._rel_tree, "rel",   "st.rel"))
        self._lang_headings.append((self._rel_tree, "count", "st.count"))
        self.after(0, self._refresh_stats)

    def _refresh_stats(self):
        tg = self._current_test_guid or self._get_kit_guid()

        def _fetch():
            stats = self._db.get_statistics()
            try:
                if tg:
                    with self._db._cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM matches WHERE test_guid=? "
                            "AND paternal_maternal != '' AND paternal_maternal IS NOT NULL", (tg,))
                        stats["_side_known"] = cur.fetchone()[0]
                        cur.execute(
                            "SELECT COUNT(*) FROM matches WHERE test_guid=? "
                            "AND endogamy_cluster != '' AND endogamy_cluster IS NOT NULL", (tg,))
                        stats["_endo_known"] = cur.fetchone()[0]
                else:
                    stats["_side_known"] = stats["_endo_known"] = 0
            except Exception:
                stats["_side_known"] = stats["_endo_known"] = 0
            self.after(0, lambda: _apply(stats))

        def _apply(stats):
            if not self.winfo_exists():
                return
            self._last_stats = stats
            for key, var in self._stat_vars.items():
                v = stats.get(key)
                var.set(f"{v:.1f}" if isinstance(v, float) else str(v) if v is not None else "—")
            self._rel_tree.delete(*self._rel_tree.get_children())
            for rel, cnt in stats.get("relationship_breakdown", []):
                self._rel_tree.insert("", "end", values=(rel, cnt))
            self._kit_stat_tree.delete(*self._kit_stat_tree.get_children())
            for kit_name, cnt in stats.get("kit_breakdown", []):
                self._kit_stat_tree.insert("", "end", values=(kit_name, cnt))
            self._draw_stat_rings(stats)

        threading.Thread(target=_fetch, daemon=True).start()

    def _draw_stat_rings(self, stats: dict):
        """Zeichnet drei Fortschritts-Ringe auf den Statistik-Canvas."""
        c = self._ring_canvas
        c.delete("all")
        total = stats.get("total") or 0
        if total == 0:
            c.create_text(20, 45, text="—", anchor="w", fill="#888888",
                          font=("Segoe UI", 10))
            return
        with_tree   = stats.get("with_tree", 0) or 0
        ped_loaded  = stats.get("ped_loaded", 0) or 0
        side_known  = stats.get("_side_known", 0) or 0
        gedcom_linked = stats.get("gedcom_linked", 0) or 0
        C = self._active_colors()
        rings = [
            (with_tree / total,    f"{with_tree}/{total}",      "Mit Baum",      C["accent"]),
            (ped_loaded / max(with_tree, 1), f"{ped_loaded}/{with_tree}" if with_tree else "—", "Ahnentafel", C["success"]),
            (side_known / total,   f"{side_known}/{total}",     "Seite bekannt", C["warning"]),
            (gedcom_linked / total, f"{gedcom_linked}/{total}", "GEDCOM-Treffer", C["primary"]),
        ]
        R = 35; cx_start = 55
        for i, (pct, label_cnt, title, color) in enumerate(rings):
            cx = cx_start + i * 160
            cy = 45
            c.create_arc(cx-R, cy-R, cx+R, cy+R, start=90, extent=360,
                          style="arc", outline=C["light"], width=8)
            extent = max(1, min(360, int(pct * 360)))
            c.create_arc(cx-R, cy-R, cx+R, cy+R, start=90, extent=-extent,
                          style="arc", outline=color, width=8)
            c.create_text(cx, cy - 6, text=f"{pct*100:.0f}%",
                          font=("Segoe UI", 10, "bold"), fill=C["text"])
            c.create_text(cx, cy + 8, text=label_cnt,
                          font=("Segoe UI", 7), fill="#777777")
            c.create_text(cx, cy + R + 12, text=title,
                          font=("Segoe UI", 8), fill=C["text"])
