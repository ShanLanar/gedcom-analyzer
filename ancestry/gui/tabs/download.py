"""Download-Tab: Matches, Namen, Vorfahren, Shared Matches herunterladen."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ancestry.core.scraper import Scraper, DownloadResult
from ancestry.gui.state import AppState
from ancestry.gui.widgets.theme import COLORS
from ancestry.gui.widgets.log_handler import install_gui_log_handler


class DownloadTab(ttk.Frame):
    """Download-Tab des Ancestry-DNA-Tools."""

    def __init__(
        self,
        parent: tk.Widget,
        state: AppState,
        on_refresh_matches: Callable,
        on_refresh_stats: Callable,
        on_refresh_kit_combos: Callable,
        set_status: Callable[[str], None],
    ):
        super().__init__(parent)
        self._state = state
        self._on_refresh_matches = on_refresh_matches
        self._on_refresh_stats = on_refresh_stats
        self._on_refresh_kit_combos = on_refresh_kit_combos
        self._set_status = set_status
        self._scraper: Optional[Scraper] = None
        self._dl_t0: float = 0.0
        self._build()

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _build(self):
        t  = self._state.t
        lw = self._state.lang_widgets

        _canvas = tk.Canvas(self, highlightthickness=0)
        _vsb = ttk.Scrollbar(self, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)
        f = ttk.Frame(_canvas)
        _canvas_win = _canvas.create_window((0, 0), window=f, anchor="nw")

        def _on_frame_configure(event=None):
            _canvas.configure(scrollregion=_canvas.bbox("all"))
        def _on_canvas_configure(event=None):
            _canvas.itemconfigure(_canvas_win, width=event.width)
        def _on_mousewheel(event):
            _canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        f.bind("<Configure>", _on_frame_configure)
        _canvas.bind("<Configure>", _on_canvas_configure)
        _canvas.bind("<MouseWheel>", _on_mousewheel)
        f.bind("<MouseWheel>", _on_mousewheel)

        p = {"padx": 14, "pady": 6}

        # Kit-Auswahl
        _sv = tk.StringVar(value=t("dl.kit"))
        ttk.Label(f, textvariable=_sv, style="Bold.TLabel").grid(
            row=0, column=0, sticky="e", **p)
        lw.append((_sv, "dl.kit"))
        self._kit_var = tk.StringVar()
        self._kit_combo = ttk.Combobox(
            f, textvariable=self._kit_var, width=46, state="readonly")
        self._kit_combo.grid(row=0, column=1, columnspan=2, sticky="w", **p)
        self.update_kit_combo()

        # ── Bereich A: Matches ────────────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=1, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=t("dl.sec_a"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", **p)
        lw.append((_sv, "dl.sec_a"))

        _sv = tk.StringVar(value=t("dl.filter"))
        ttk.Label(f, textvariable=_sv).grid(row=3, column=0, sticky="e", **p)
        lw.append((_sv, "dl.filter"))
        self._filter_var = tk.StringVar(value="ALL")
        ff = ttk.Frame(f); ff.grid(row=3, column=1, sticky="w", **p)
        for val, key in [("ALL", "dl.f_all"), ("STARRED", "dl.f_star"),
                         ("CLOSE", "dl.f_close"), ("DISTANT", "dl.f_distant")]:
            _sv = tk.StringVar(value=t(key))
            ttk.Radiobutton(ff, textvariable=_sv, variable=self._filter_var,
                            value=val).pack(side="left", padx=5)
            lw.append((_sv, key))

        _sv = tk.StringVar(value=t("dl.sort"))
        ttk.Label(f, textvariable=_sv).grid(row=4, column=0, sticky="e", **p)
        lw.append((_sv, "dl.sort"))
        self._sort_var = tk.StringVar(value="RELATIONSHIP")
        sf = ttk.Frame(f); sf.grid(row=4, column=1, sticky="w", **p)
        for val, key in [("RELATIONSHIP", "dl.s_rel"), ("SHARED_CM", "dl.s_cm")]:
            _sv = tk.StringVar(value=t(key))
            ttk.Radiobutton(sf, textvariable=_sv, variable=self._sort_var,
                            value=val).pack(side="left", padx=5)
            lw.append((_sv, key))

        bf = ttk.Frame(f); bf.grid(row=5, column=0, columnspan=4, sticky="w", **p)
        _sv_start_m = tk.StringVar(value=t("dl.start_m"))
        self._start_btn = ttk.Button(bf, textvariable=_sv_start_m,
                                     command=self._start_matches)
        self._start_btn.pack(side="left", padx=4)
        lw.append((_sv_start_m, "dl.start_m"))
        _sv_stop1 = tk.StringVar(value=t("dl.stop"))
        self._stop_btn = ttk.Button(bf, textvariable=_sv_stop1,
                                    command=self.stop_download, state="disabled")
        self._stop_btn.pack(side="left", padx=4)
        lw.append((_sv_stop1, "dl.stop"))
        self._only_new_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=t("dl.only_new"))
        ttk.Checkbutton(bf, textvariable=_sv,
                        variable=self._only_new_var).pack(side="left", padx=14)
        lw.append((_sv, "dl.only_new"))
        self._fetch_names_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=t("dl.full_names"))
        ttk.Checkbutton(bf, textvariable=_sv,
                        variable=self._fetch_names_var).pack(side="left", padx=14)
        lw.append((_sv, "dl.full_names"))

        # ── Bereich A2: Namen nachladen ───────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=6, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=t("dl.sec_a2"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=7, column=0, columnspan=4, sticky="w", **p)
        lw.append((_sv, "dl.sec_a2"))
        ttk.Label(f, text=(
            "Lädt Namen, Geschlecht, Stammbaum-Status/-Größe und ob ein\n"
            "gemeinsamer Vorfahre existiert (20 Matches pro Anfrage).\n"
            "Danach: 'Vorfahren & Orte' + 'Ahnentafeln' laden für ALLE Matches\n"
            "mit Baum (nicht nur Ancestrys erkannte) – dann Auswertung/GEDCOM-Abgleich."
        ), foreground="#555555").grid(row=8, column=0, columnspan=4, sticky="w", padx=14)

        sf_names = ttk.Frame(f)
        sf_names.grid(row=9, column=0, columnspan=4, sticky="w", **p)
        _sv = tk.StringVar(value=t("dl.min_cm"))
        ttk.Label(sf_names, textvariable=_sv).pack(side="left")
        lw.append((_sv, "dl.min_cm"))
        self._names_min_cm_var = tk.StringVar(value="0")
        ttk.Entry(sf_names, textvariable=self._names_min_cm_var,
                  width=6).pack(side="left", padx=6)
        _sv = tk.StringVar(value=t("dl.depth"))
        ttk.Label(sf_names, textvariable=_sv).pack(side="left", padx=(18, 0))
        lw.append((_sv, "dl.depth"))
        self._ped_gens_var = tk.StringVar(value="5")
        ttk.Combobox(sf_names, textvariable=self._ped_gens_var,
                     values=["5", "6", "7", "8", "10"], width=4,
                     state="readonly").pack(side="left", padx=4)
        self._ped_force_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=t("dl.reload_all"))
        ttk.Checkbutton(sf_names, textvariable=_sv,
                        variable=self._ped_force_var).pack(side="left", padx=(12, 4))
        lw.append((_sv, "dl.reload_all"))
        ttk.Label(sf_names, text="(>5 Gen. = langsamer, mehr Extra-Calls)",
                  foreground="#888888").pack(side="left")

        bf_names = ttk.Frame(f)
        bf_names.grid(row=10, column=0, columnspan=4, sticky="w", **p)
        _sv_nm = tk.StringVar(value=t("dl.start_nm"))
        self._names_start_btn = ttk.Button(bf_names, textvariable=_sv_nm,
                                           command=self._start_fetch_names)
        self._names_start_btn.pack(side="left", padx=4)
        lw.append((_sv_nm, "dl.start_nm"))
        _sv_stop2 = tk.StringVar(value=t("dl.stop"))
        self._names_stop_btn = ttk.Button(bf_names, textvariable=_sv_stop2,
                                          command=self.stop_download, state="disabled")
        self._names_stop_btn.pack(side="left", padx=4)
        lw.append((_sv_stop2, "dl.stop"))
        _sv_anc = tk.StringVar(value=t("dl.start_anc"))
        self._anc_start_btn = ttk.Button(bf_names, textvariable=_sv_anc,
                                         command=self._start_fetch_ancestors)
        self._anc_start_btn.pack(side="left", padx=(16, 4))
        lw.append((_sv_anc, "dl.start_anc"))
        _sv_ped = tk.StringVar(value=t("dl.start_ped"))
        self._ped_start_btn = ttk.Button(bf_names, textvariable=_sv_ped,
                                         command=self._start_fetch_pedigrees)
        self._ped_start_btn.pack(side="left", padx=4)
        lw.append((_sv_ped, "dl.start_ped"))

        # ── Bereich B: Shared Matches ─────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=11, column=0, columnspan=4, sticky="ew", padx=14, pady=6)
        _sv = tk.StringVar(value=t("dl.sec_b"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=12, column=0, columnspan=4, sticky="w", **p)
        lw.append((_sv, "dl.sec_b"))
        ttk.Label(f, text=(
            "Lädt für jeden gespeicherten Match dessen gemeinsame Matches mit cM-Werten.\n"
            "Empfehlung: erst Matches (A) herunterladen, dann Shared Matches (B).\n"
            "Ab 20 cM sinnvoll – erfasst auch entferntere Verwandte.\n"
            "Tipp: Höherer cM-Wert = deutlich weniger primäre Matches = viel schneller "
            "(kann sonst Stunden dauern)."
        ), foreground="#555555").grid(row=13, column=0, columnspan=4, sticky="w", padx=14)

        sf2 = ttk.Frame(f); sf2.grid(row=14, column=0, columnspan=4, sticky="w", **p)
        _sv = tk.StringVar(value=t("dl.prim_min"))
        ttk.Label(sf2, textvariable=_sv).pack(side="left")
        lw.append((_sv, "dl.prim_min"))
        self._shared_min_cm_var = tk.StringVar(value="20")
        ttk.Entry(sf2, textvariable=self._shared_min_cm_var,
                  width=6).pack(side="left", padx=6)
        self._skip_existing_var = tk.BooleanVar(value=True)
        _sv = tk.StringVar(value=t("dl.skip_ex"))
        ttk.Checkbutton(sf2, textvariable=_sv,
                        variable=self._skip_existing_var).pack(side="left", padx=12)
        lw.append((_sv, "dl.skip_ex"))

        bf2 = ttk.Frame(f); bf2.grid(row=15, column=0, columnspan=4, sticky="w", **p)
        _sv_sh = tk.StringVar(value=t("dl.start_sh"))
        self._shared_start_btn = ttk.Button(bf2, textvariable=_sv_sh,
                                            command=self._start_shared)
        self._shared_start_btn.pack(side="left", padx=4)
        lw.append((_sv_sh, "dl.start_sh"))
        _sv_stop3 = tk.StringVar(value=t("dl.stop"))
        self._shared_stop_btn = ttk.Button(bf2, textvariable=_sv_stop3,
                                           command=self.stop_download, state="disabled")
        self._shared_stop_btn.pack(side="left", padx=4)
        lw.append((_sv_stop3, "dl.stop"))

        # ── Alle Phasen (kombinierter Lauf) ───────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=16, column=0, columnspan=4, sticky="ew", padx=14, pady=6)
        ttk.Label(f, text="▶ Alle Phasen (kombinierter Lauf)",
                  style="Bold.TLabel").grid(row=17, column=0, columnspan=4, sticky="w", **p)
        ttk.Label(f, text=(
            "Führt A+A2+Vorfahren+B nacheinander aus: Matches → Namen → Vorfahren → "
            "Shared Matches.\n"
            "Kann über Nacht laufen. Einzelne Phasen können trotzdem separat (oben) "
            "gestartet werden."
        ), foreground="#555555").grid(row=18, column=0, columnspan=4, sticky="w", padx=14)

        self._phase_frames: list[dict] = []
        phase_dash = ttk.Frame(f)
        phase_dash.grid(row=19, column=0, columnspan=4, sticky="w", padx=18, pady=(4, 2))
        PHASE_LABELS = [
            "1 · Matches herunterladen",
            "2 · Namen & Stammbaum laden",
            "3 · Vorfahren & Orte laden",
            "4 · Shared Matches laden",
        ]
        for i, lbl in enumerate(PHASE_LABELS):
            row_f = ttk.Frame(phase_dash); row_f.grid(row=i, column=0, sticky="w", pady=1)
            badge_sv = tk.StringVar(value="○")
            badge_lbl = ttk.Label(row_f, textvariable=badge_sv, width=3,
                                  font=("Segoe UI", 11), foreground="#555555")
            badge_lbl.pack(side="left")
            ttk.Label(row_f, text=lbl, width=36, anchor="w").pack(side="left")
            count_sv = tk.StringVar(value="")
            ttk.Label(row_f, textvariable=count_sv, foreground="#888888",
                      width=20, anchor="w").pack(side="left")
            self._phase_frames.append({"badge": badge_sv, "badge_lbl": badge_lbl,
                                       "count": count_sv})

        bf_all = ttk.Frame(f); bf_all.grid(row=20, column=0, columnspan=4, sticky="w", **p)
        self._all_phases_btn = ttk.Button(bf_all, text="▶ Alle Phasen starten",
                                          command=self._start_all_phases)
        self._all_phases_btn.pack(side="left", padx=4)
        self._all_phases_stop_btn = ttk.Button(bf_all, text="⏹ Abbrechen",
                                               command=self.stop_download, state="disabled")
        self._all_phases_stop_btn.pack(side="left", padx=4)

        # ── Bereich C: DNA-Segmente importieren ──────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=19, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        ttk.Label(f, text="C · DNA-Segmente (für Triangulation)",
                  font=("Segoe UI", 9, "bold"), foreground=COLORS["primary"]).grid(
            row=20, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 2))
        seg_row = ttk.Frame(f); seg_row.grid(row=20, column=0, columnspan=4,
                                              sticky="w", padx=14, pady=(24, 4))
        ttk.Label(seg_row, text="Segment-CSV:").pack(side="left")
        self._seg_file_var = tk.StringVar()
        ttk.Entry(seg_row, textvariable=self._seg_file_var, width=38).pack(
            side="left", padx=4)
        ttk.Button(seg_row, text="…", width=3,
                   command=self._choose_seg_file).pack(side="left")
        ttk.Label(seg_row,
            text="(GEDmatch Segment Search, MyHeritage Shared-Segments oder FTDNA)",
            foreground="#777777", font=("Segoe UI", 8)).pack(side="left", padx=8)
        ttk.Button(seg_row, text="⬆ Segmente importieren",
                   command=self._import_segments).pack(side="left", padx=(12, 0))

        # FTDNA match import on the same row (second line)
        ftdna_row = ttk.Frame(f)
        ftdna_row.grid(row=20, column=0, columnspan=4, sticky="w", padx=14, pady=(50, 2))
        ttk.Label(ftdna_row, text="FTDNA Matches:").pack(side="left")
        self._ftdna_file_var = tk.StringVar()
        ttk.Entry(ftdna_row, textvariable=self._ftdna_file_var, width=38).pack(
            side="left", padx=4)
        ttk.Button(ftdna_row, text="…", width=3,
                   command=self._choose_ftdna_file).pack(side="left")
        ttk.Label(ftdna_row, text="(FTDNA Family Finder matches.csv)",
                  foreground="#777777", font=("Segoe UI", 8)).pack(side="left", padx=8)
        ttk.Button(ftdna_row, text="⬆ FTDNA Matches importieren",
                   command=self._import_ftdna_matches).pack(side="left", padx=(12, 0))

        # ── Bereich D: Herkunft / Ethnizität + Traits ────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=21, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        ttk.Label(f, text="D · Herkunft / Ethnizität & Traits",
                  font=("Segoe UI", 9, "bold"),
                  foreground=COLORS["primary"]).grid(
            row=22, column=0, columnspan=4, sticky="w", padx=14, pady=(4, 2))
        ttk.Label(f, text=(
            "Lädt die Ethnizitäts-Auswertung (Ancestry + MyHeritage) und die Ancestry "
            "DNA-Traits einmalig.\nErgebnis wird im Statistik-Tab dauerhaft angezeigt."
        ), foreground="#555555").grid(row=23, column=0, columnspan=4, sticky="w", padx=14)
        eth_row = ttk.Frame(f)
        eth_row.grid(row=23, column=0, columnspan=4, sticky="w", padx=14, pady=(24, 4))
        self._eth_btn = ttk.Button(eth_row, text="▶ Herkunft & Traits laden",
                                   command=self._fetch_ethnicity_traits)
        self._eth_btn.pack(side="left")
        self._eth_status_var = tk.StringVar(value="—")
        ttk.Label(eth_row, textvariable=self._eth_status_var,
                  foreground="#555555").pack(side="left", padx=12)

        # ── Fortschritt ───────────────────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=24, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=t("dl.progress"))
        ttk.Label(f, textvariable=_sv).grid(row=25, column=0, sticky="e", **p)
        lw.append((_sv, "dl.progress"))
        self._progress_var = tk.DoubleVar()
        ttk.Progressbar(f, variable=self._progress_var, maximum=100,
                        length=380).grid(row=25, column=1, sticky="w", **p)
        self._progress_lbl = tk.StringVar(value="—")
        ttk.Label(f, textvariable=self._progress_lbl).grid(row=25, column=2, sticky="w", **p)

        self._pause_sv = tk.StringVar(value=t("dl.pause"))
        self._pause_btn = ttk.Button(f, textvariable=self._pause_sv,
                                     command=self._toggle_pause, state="disabled")
        self._pause_btn.grid(row=25, column=3, sticky="w", **p)
        lw.append((self._pause_sv, "dl.pause"))

        self._eta_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self._eta_var, foreground="#777777").grid(
            row=25, column=4, sticky="w", **p)

        dash = ttk.Frame(f); dash.grid(row=25, column=5, sticky="w", padx=8)
        self._dash_vars: dict[str, tk.StringVar] = {}
        for i, (key, _icon) in enumerate([("dl.dash_mat", "🧬"), ("dl.dash_tree", "🌳"),
                                           ("dl.dash_sh", "👥"), ("dl.dash_err", "❌")]):
            col_frame = ttk.Frame(dash); col_frame.grid(row=0, column=i, padx=6)
            _sv_d = tk.StringVar(value=t(key))
            ttk.Label(col_frame, textvariable=_sv_d, foreground="#777777",
                      font=("Segoe UI", 8)).pack()
            lw.append((_sv_d, key))
            val_sv = tk.StringVar(value="0")
            ttk.Label(col_frame, textvariable=val_sv, font=("Segoe UI", 11, "bold"),
                      foreground=COLORS["primary"]).pack()
            dk = key.replace("dl.dash_", "")
            self._dash_vars[dk] = val_sv

        # ── Log ───────────────────────────────────────────────────────────────
        _sv = tk.StringVar(value=t("dl.log"))
        ttk.Label(f, textvariable=_sv, style="Bold.TLabel").grid(
            row=26, column=0, sticky="ne", padx=14, pady=(10, 4))
        lw.append((_sv, "dl.log"))
        lf = ttk.Frame(f)
        lf.grid(row=26, column=1, columnspan=3, sticky="nsew", padx=14, pady=4)
        self._log_text = tk.Text(lf, height=12, width=72, font=("Consolas", 9),
                                 bg="#1E1E2E", fg="#A0D0FF", state="disabled", relief="flat")
        sc = ttk.Scrollbar(lf, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sc.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

        f.columnconfigure(1, weight=1)
        f.rowconfigure(26, weight=1)
        install_gui_log_handler(self._log_text)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_kit_guid(self) -> Optional[str]:
        return self._state.kit_map.get(self._kit_var.get())

    def update_kit_combo(self):
        """Befüllt das Kit-Dropdown aus kit_map und löst Matches-Kit-Refresh aus."""
        names = list(self._state.kit_map.keys())
        self._kit_combo["values"] = names
        if names and not self._kit_var.get():
            self._kit_combo.current(0)
        self._on_refresh_kit_combos()

    def is_running(self) -> bool:
        return bool(self._scraper and self._scraper.is_running())

    def stop_download(self):
        if self._scraper:
            self._scraper.stop()
        self._stop_btn.configure(state="disabled")
        self._shared_stop_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="disabled")

    def on_progress(self, fetched: int, total: int, label: str):
        """Progress callback — also callable from external scrapers (e.g. _refresh_links)."""
        pct = min(100.0, (fetched / max(total, 1)) * 100)
        if self._dl_t0 == 0.0:
            self._dl_t0 = time.monotonic()
        elapsed = time.monotonic() - self._dl_t0
        remaining = fetched and elapsed and (elapsed / fetched * max(total - fetched, 0))
        if remaining and remaining < 3600 * 5:
            mins, secs = divmod(int(remaining), 60)
            eta_txt = f"~{mins}m {secs:02d}s"
        else:
            eta_txt = ""
        try:
            tg = self._state.current_test_guid or self.get_kit_guid()
            if tg:
                self._state.dl_counters["matches"] = self._state.db.get_match_count(tg)
                with self._state.db._cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM matches WHERE test_guid=? AND has_tree=1", (tg,))
                    self._state.dl_counters["trees"] = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM shared_matches WHERE test_guid=?", (tg,))
                    self._state.dl_counters["shared"] = cur.fetchone()[0]
        except Exception:
            pass

        def _u():
            self._progress_var.set(pct)
            self._progress_lbl.set(f"{fetched} / ~{total}  –  {label[:45]}")
            self._eta_var.set(eta_txt)
            for k, sv in [
                ("mat",  str(self._state.dl_counters["matches"])),
                ("tree", str(self._state.dl_counters["trees"])),
                ("sh",   str(self._state.dl_counters["shared"])),
                ("err",  str(self._state.dl_counters["errors"])),
            ]:
                if k in self._dash_vars:
                    self._dash_vars[k].set(sv)
        self.after(0, _u)

    # ── Download-Methoden ─────────────────────────────────────────────────────

    def _start_matches(self):
        guid = self.get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._state.client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._state.current_test_guid = guid
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._pause_btn.configure(state="normal")
        self._dl_t0 = 0.0
        self._state.pause_event.set()
        self._progress_var.set(0)
        self._scraper = Scraper(
            self._state.client, self._state.db,
            on_progress=self.on_progress,
            on_status=lambda m: self.after(0, lambda: self._set_status(m)),
            on_done=self._on_done)
        if self._fetch_names_var.get():
            self._set_status("Hinweis: 'Volle Namen' lädt jeden Match einzeln – "
                             "das kann bei vielen Matches sehr lange dauern.")
        self._scraper.start_matches(guid, self._filter_var.get(), self._sort_var.get(),
                                    only_new=self._only_new_var.get(),
                                    fetch_names=self._fetch_names_var.get())

    def _start_shared(self):
        guid = self.get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._state.client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        total_matches = self._state.db.get_match_count(guid)
        if total_matches == 0:
            messagebox.showwarning("Keine Matches", "Erst Matches herunterladen (Schritt A).")
            return
        try:
            min_cm = float(self._shared_min_cm_var.get() or 0)
        except ValueError:
            min_cm = 90.0
        self._state.current_test_guid = guid
        self._shared_start_btn.configure(state="disabled")
        self._shared_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(
            self._state.client, self._state.db,
            on_progress=self.on_progress,
            on_status=lambda m: self.after(0, lambda: self._set_status(m)),
            on_done=self._on_shared_done)
        self._scraper.start_shared(guid, min_cm, self._skip_existing_var.get())

    def _start_fetch_names(self):
        guid = self.get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._state.client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        try:
            min_cm = float(self._names_min_cm_var.get() or 0)
        except ValueError:
            min_cm = 0.0
        self._state.current_test_guid = guid
        self._names_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(
            self._state.client, self._state.db,
            on_progress=self.on_progress,
            on_status=lambda m: self.after(0, lambda: self._set_status(m)),
            on_done=lambda r: self.after(0, lambda: self._on_names_done(r)))
        self._scraper.start_fetch_names(guid, min_cm)

    def _on_names_done(self, result: DownloadResult):
        self._names_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._on_refresh_matches()
        messagebox.showinfo("Namen", result.message)

    def _start_fetch_ancestors(self):
        guid = self.get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._state.client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._state.current_test_guid = guid
        self._anc_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(
            self._state.client, self._state.db,
            on_progress=self.on_progress,
            on_status=lambda m: self.after(0, lambda: self._set_status(m)),
            on_done=lambda r: self.after(0, lambda: self._on_ancestors_done(r)))
        self._scraper.start_fetch_ancestors(guid, self._a2_min_cm())

    def _on_ancestors_done(self, result: DownloadResult):
        self._anc_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._on_refresh_matches()
        messagebox.showinfo("Vorfahren", result.message)

    def _start_fetch_pedigrees(self):
        guid = self.get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._state.client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._state.current_test_guid = guid
        self._ped_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        try:
            max_gen = int(self._ped_gens_var.get())
        except (ValueError, AttributeError):
            max_gen = 5
        force = self._ped_force_var.get()
        self._scraper = Scraper(
            self._state.client, self._state.db,
            on_progress=self.on_progress,
            on_status=lambda m: self.after(0, lambda: self._set_status(m)),
            on_done=lambda r: self.after(0, lambda: self._on_pedigrees_done(r)))
        self._scraper.start_fetch_pedigrees(guid, self._a2_min_cm(), max_gen, force)

    def _a2_min_cm(self) -> float:
        try:
            return float(self._names_min_cm_var.get() or 0)
        except (ValueError, AttributeError):
            return 0.0

    def _on_pedigrees_done(self, result: DownloadResult):
        self._ped_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._on_refresh_matches()
        messagebox.showinfo("Ahnentafeln", result.message)

    def _toggle_pause(self):
        if self._state.pause_event.is_set():
            self._state.pause_event.clear()
            self._pause_sv.set(self._state.t("dl.resume"))
            self._set_status("⏸ Download pausiert.")
        else:
            self._state.pause_event.set()
            self._pause_sv.set(self._state.t("dl.pause"))
            self._set_status("▶ Download fortgesetzt.")

    def _on_done(self, result: DownloadResult):
        def _u():
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            self._pause_btn.configure(state="disabled")
            self._pause_sv.set(self._state.t("dl.pause"))
            self._eta_var.set("")
            self._set_status(("✅ " if result.success else "⚠️ ") + result.message)
            self._on_refresh_matches()
            self._on_refresh_stats()
            if result.success:
                messagebox.showinfo("Fertig", result.message)
        self.after(0, _u)

    def _on_shared_done(self, result: DownloadResult):
        def _u():
            self._shared_start_btn.configure(state="normal")
            self._shared_stop_btn.configure(state="disabled")
            self._set_status(("✅ " if result.success else "⚠️ ") + result.message)
            self._on_refresh_stats()
            if result.success:
                messagebox.showinfo("Shared Matches fertig", result.message)
        self.after(0, _u)

    def _start_all_phases(self):
        guid = self.get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._state.client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        for pf in self._phase_frames:
            pf["badge"].set("○")
            pf["badge_lbl"].configure(foreground="#555555")
            pf["count"].set("")
        self._state.current_test_guid = guid
        self._all_phases_btn.configure(state="disabled")
        self._all_phases_stop_btn.configure(state="normal")
        self._pause_btn.configure(state="normal")
        self._state.pause_event.set()
        self._progress_var.set(0)
        try:
            min_cm_names  = float(self._names_min_cm_var.get() or 0)
            min_cm_shared = float(self._shared_min_cm_var.get() or 20)
            ped_gens      = int(self._ped_gens_var.get() or 5)
        except ValueError:
            min_cm_names, min_cm_shared, ped_gens = 0.0, 20.0, 5
        self._scraper = Scraper(
            self._state.client, self._state.db,
            on_progress=self.on_progress,
            on_status=lambda m: self.after(0, lambda: self._set_status(m)),
            on_done=self._on_all_phases_done)
        self._scraper.start_all_phases(
            guid,
            filter_by=self._filter_var.get(),
            sort_by=self._sort_var.get(),
            only_new=self._only_new_var.get(),
            names_min_cm=min_cm_names,
            shared_min_cm=min_cm_shared,
            ped_gens=ped_gens,
            on_phase_change=self._on_phase_change,
        )

    def _on_phase_change(self, phase_idx: int, phase_name: str, status: str):
        ICONS = {"running": ("⏳", "#f0c040"), "done": ("✓", "#50fa7b"), "error": ("✗", "#ff5555")}
        icon, color = ICONS.get(status, ("○", "#555555"))
        def _u():
            idx = phase_idx - 1
            if 0 <= idx < len(self._phase_frames):
                pf = self._phase_frames[idx]
                pf["badge"].set(icon)
                pf["badge_lbl"].configure(foreground=color)
                if status == "done":
                    pf["count"].set("fertig")
                elif status == "error":
                    pf["count"].set("Fehler")
                elif status == "running":
                    pf["count"].set("läuft …")
            self._set_status(f"Phase {phase_idx}: {phase_name} → {status}")
        self.after(0, _u)

    def _on_all_phases_done(self, result: DownloadResult):
        def _u():
            self._all_phases_btn.configure(state="normal")
            self._all_phases_stop_btn.configure(state="disabled")
            self._pause_btn.configure(state="disabled")
            self._set_status(
                ("✅ Alle Phasen abgeschlossen. " if result.success else "⚠️ ") + result.message)
            self._on_refresh_matches()
            self._on_refresh_stats()
            if result.success:
                messagebox.showinfo("Alle Phasen fertig", result.message)
        self.after(0, _u)

    def _choose_seg_file(self):
        from tkinter.filedialog import askopenfilename
        path = askopenfilename(
            title="Segment-CSV wählen",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if path:
            self._seg_file_var.set(path)

    def _choose_ftdna_file(self):
        from tkinter.filedialog import askopenfilename
        path = askopenfilename(
            title="FTDNA matches.csv wählen",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if path:
            self._ftdna_file_var.set(path)

    def _import_ftdna_matches(self):
        import threading
        from pathlib import Path
        path = self._ftdna_file_var.get().strip()
        if not path:
            messagebox.showwarning("FTDNA Import", "Bitte zuerst eine FTDNA matches.csv wählen.")
            return
        kit_guid = self.get_kit_guid() or "FTDNA_DEFAULT"
        self._set_status("FTDNA Matches werden importiert …")

        def _worker():
            try:
                from ancestry.tools.import_ftdna_matches import run as ftdna_run
                result = ftdna_run(Path(path), kit_guid=kit_guid,
                                   db_file=self._state.db.db_file)
                n = result["imported"]
                s = result["skipped"]
                msg = f"FTDNA: {n} Matches importiert, {s} übersprungen (<7 cM)"
                self.after(0, lambda: self._set_status(msg))
                self.after(0, lambda: messagebox.showinfo("FTDNA Import", msg))
                self.after(50, self._on_refresh_matches)
            except Exception as e:
                self.after(0, lambda err=e: self._set_status(f"Fehler: {err}"))
                self.after(0, lambda err=e: messagebox.showerror("FTDNA Import", str(err)))

        threading.Thread(target=_worker, daemon=True, name="ftdna-import").start()

    def _fetch_ethnicity_traits(self):
        import threading
        test_guid = self._state.current_test_guid
        if not test_guid:
            messagebox.showwarning("Herkunft", "Bitte zuerst ein DNA-Kit wählen.")
            return
        client = self._state.client
        if not client:
            messagebox.showwarning("Herkunft", "Bitte zuerst bei Ancestry einloggen (Login-Tab).")
            return
        self._eth_btn.configure(state="disabled")
        self._eth_status_var.set("⏳ Lädt …")

        def _worker():
            from ancestry.tools.fetch_ethnicity import fetch_all_ethnicity, fetch_ancestry_traits
            try:
                mh_kit = ""
                try:
                    from ancestry.tools.download_myheritage import KIT_GUID
                    mh_kit = KIT_GUID
                except ImportError:
                    pass

                eth  = fetch_all_ethnicity(
                    test_guid=test_guid,
                    mh_kit_guid=mh_kit,
                    ancestry_session=client._s,
                )
                traits = fetch_ancestry_traits(client._s, test_guid)

                if eth:
                    self._state.db.save_kit_ethnicity(test_guid, eth)
                if traits:
                    self._state.db.save_kit_traits(test_guid, traits)

                n_eth    = len(eth)
                n_traits = len(traits)
                if n_eth or n_traits:
                    msg = f"✓ {n_eth} Herkunfts-Regionen, {n_traits} Traits gespeichert"
                else:
                    msg = "⚠ Keine Daten — Sitzung abgelaufen oder Parsing fehlgeschlagen"
                self.after(0, lambda m=msg: self._eth_status_var.set(m))
                self.after(0, lambda: self._set_status(msg))
            except Exception as e:
                self.after(0, lambda err=e: self._eth_status_var.set(f"❌ {err}"))
            finally:
                self.after(0, lambda: self._eth_btn.configure(state="normal"))

        threading.Thread(target=_worker, daemon=True, name="eth-fetch").start()

    def _import_segments(self):
        import threading
        from pathlib import Path
        path = self._seg_file_var.get().strip()
        if not path:
            messagebox.showwarning("Segment-Import", "Bitte zuerst eine CSV-Datei wählen.")
            return
        kit_guid = self.get_kit_guid()
        if not kit_guid:
            messagebox.showwarning("Segment-Import", "Bitte zuerst ein DNA-Kit wählen.")
            return
        self._set_status("Segmente werden importiert …")

        def _worker():
            try:
                from ancestry.tools.import_segments import run as seg_run
                result = seg_run(Path(path), kit_guid=kit_guid,
                                 db_file=self._state.db.db_file)
                n   = result["imported"]
                unr = len(result["unresolved"])
                msg = (f"Segmente importiert: {n}"
                       + (f"  ·  {unr} Namen nicht aufgelöst" if unr else ""))
                self.after(0, lambda: self._set_status(msg))
                self.after(0, lambda: messagebox.showinfo("Segment-Import", msg))
            except Exception as e:
                self.after(0, lambda err=e: self._set_status(f"Fehler: {err}"))
                self.after(0, lambda err=e: messagebox.showerror("Segment-Import",
                                                                   str(err)))

        threading.Thread(target=_worker, daemon=True, name="seg-import").start()
