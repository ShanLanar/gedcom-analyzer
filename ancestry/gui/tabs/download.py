"""Download-Tab: Matches, Namen, Vorfahren, Shared Matches herunterladen."""

from __future__ import annotations

import json
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from ancestry.core.scraper import DownloadResult, Scraper
from ancestry.gui.state import AppState
from ancestry.gui.widgets.log_handler import install_gui_log_handler
from ancestry.gui.widgets.theme import register_lang, COLORS
from ancestry.gui.widgets.tooltip import register_tooltip

_DL_STATUS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "dl_status.json"


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
        self._last_fetched: int = 0  # last fetched count from on_progress
        self._build()
        self._refresh_ts_labels()

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

        # ── Zeitstempel-Zeile ─────────────────────────────────────────────────
        ts_row = ttk.Frame(f)
        ts_row.grid(row=6, column=0, columnspan=4, sticky="w", padx=14, pady=(0, 2))
        self._ts_ancestry_var = tk.StringVar(value="")
        ttk.Label(ts_row, textvariable=self._ts_ancestry_var,
                  foreground="#777777", font=("Segoe UI", 8)).pack(side="left", padx=(0, 18))
        self._ts_mh_var = tk.StringVar(value="")
        ttk.Label(ts_row, textvariable=self._ts_mh_var,
                  foreground="#777777", font=("Segoe UI", 8)).pack(side="left", padx=(0, 18))
        self._ts_gm_var = tk.StringVar(value="")
        ttk.Label(ts_row, textvariable=self._ts_gm_var,
                  foreground="#777777", font=("Segoe UI", 8)).pack(side="left", padx=(0, 18))
        self._resume_var = tk.StringVar(value="")
        ttk.Label(ts_row, textvariable=self._resume_var,
                  foreground="#5588cc", font=("Segoe UI", 8)).pack(side="left")

        # ── Bereich A2: Namen nachladen ───────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=7, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=t("dl.sec_a2"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=8, column=0, columnspan=4, sticky="w", **p)
        lw.append((_sv, "dl.sec_a2"))
        register_lang(self._state, ttk.Label(f, text=(
            self._state.t("dl.help_names")
        ), foreground="#555555"), "dl.help_names").grid(row=9, column=0, columnspan=4, sticky="w", padx=14)

        sf_names = ttk.Frame(f)
        sf_names.grid(row=10, column=0, columnspan=4, sticky="w", **p)
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
        self._ped_refresh_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=t("dl.refresh_stale"))
        _cb = ttk.Checkbutton(sf_names, textvariable=_sv,
                              variable=self._ped_refresh_var)
        _cb.pack(side="left", padx=(8, 4))
        register_tooltip(_cb, "tt.dl_refresh", self._state)
        lw.append((_sv, "dl.refresh_stale"))
        ttk.Label(sf_names, text="(>5 Gen. = langsamer, mehr Extra-Calls)",
                  foreground="#888888").pack(side="left")

        bf_names = ttk.Frame(f)
        bf_names.grid(row=11, column=0, columnspan=4, sticky="w", **p)
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
            row=12, column=0, columnspan=4, sticky="ew", padx=14, pady=6)
        _sv = tk.StringVar(value=t("dl.sec_b"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=13, column=0, columnspan=4, sticky="w", **p)
        lw.append((_sv, "dl.sec_b"))
        register_lang(self._state, ttk.Label(f, text=(
            self._state.t("dl.help_shared")
        ), foreground="#555555"), "dl.help_shared").grid(row=14, column=0, columnspan=4, sticky="w", padx=14)

        sf2 = ttk.Frame(f); sf2.grid(row=15, column=0, columnspan=4, sticky="w", **p)
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

        bf2 = ttk.Frame(f); bf2.grid(row=16, column=0, columnspan=4, sticky="w", **p)
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
            row=17, column=0, columnspan=4, sticky="ew", padx=14, pady=6)
        ttk.Label(f, text="▶ Alle Phasen (kombinierter Lauf)",
                  style="Bold.TLabel").grid(row=18, column=0, columnspan=4, sticky="w", **p)
        register_lang(self._state, ttk.Label(f, text=(
            self._state.t("dl.help_all")
        ), foreground="#555555"), "dl.help_all").grid(row=19, column=0, columnspan=4, sticky="w", padx=14)

        self._phase_frames: list[dict] = []
        phase_dash = ttk.Frame(f)
        phase_dash.grid(row=20, column=0, columnspan=4, sticky="w", padx=18, pady=(4, 2))
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

        bf_all = ttk.Frame(f); bf_all.grid(row=21, column=0, columnspan=4, sticky="w", **p)
        self._all_phases_btn = ttk.Button(bf_all, text="▶ Alle Phasen starten",
                                          command=self._start_all_phases)
        self._all_phases_btn.pack(side="left", padx=4)
        self._all_phases_stop_btn = register_lang(self._state, ttk.Button(bf_all, text=self._state.t("dl.b_cancel"),
                                               command=self.stop_download, state="disabled"), "dl.b_cancel")
        self._all_phases_stop_btn.pack(side="left", padx=4)

        # ── Bereich C: DNA-Segmente importieren ──────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=22, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        register_lang(self._state, ttk.Label(f, text=self._state.t("dl.sec_c"),
                  font=("Segoe UI", 9, "bold"), foreground=COLORS["primary"]), "dl.sec_c").grid(
            row=23, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 2))
        seg_row = ttk.Frame(f); seg_row.grid(row=23, column=0, columnspan=4,
                                              sticky="w", padx=14, pady=(24, 4))
        ttk.Label(seg_row, text="Segment-CSV:").pack(side="left")
        self._seg_file_var = tk.StringVar()
        ttk.Entry(seg_row, textvariable=self._seg_file_var, width=38).pack(
            side="left", padx=4)
        _pb = ttk.Button(seg_row, text="…", width=3,
                   command=self._choose_seg_file)
        _pb.pack(side="left")
        register_tooltip(_pb, "tt.pick_file", self._state)
        register_lang(self._state, ttk.Label(seg_row,
            text=self._state.t("dl.seg_hint"),
            foreground="#777777", font=("Segoe UI", 8)), "dl.seg_hint").pack(side="left", padx=8)
        register_lang(self._state, ttk.Button(seg_row, text=self._state.t("dl.b_seg_import"),
                   command=self._import_segments), "dl.b_seg_import").pack(side="left", padx=(12, 0))

        # FTDNA match import on the same row (second line)
        ftdna_row = ttk.Frame(f)
        ftdna_row.grid(row=23, column=0, columnspan=4, sticky="w", padx=14, pady=(50, 2))
        ttk.Label(ftdna_row, text="FTDNA Matches:").pack(side="left")
        self._ftdna_file_var = tk.StringVar()
        ttk.Entry(ftdna_row, textvariable=self._ftdna_file_var, width=38).pack(
            side="left", padx=4)
        _pb = ttk.Button(ftdna_row, text="…", width=3,
                   command=self._choose_ftdna_file)
        _pb.pack(side="left")
        register_tooltip(_pb, "tt.pick_file", self._state)
        ttk.Label(ftdna_row, text="(FTDNA Family Finder matches.csv)",
                  foreground="#777777", font=("Segoe UI", 8)).pack(side="left", padx=8)
        register_lang(self._state, ttk.Button(ftdna_row, text=self._state.t("dl.b_ftdna_import"),
                   command=self._import_ftdna_matches), "dl.b_ftdna_import").pack(side="left", padx=(12, 0))

        # GEDmatch-Export der eigenen Matches (One-to-Many-TSV)
        gmx_row = ttk.Frame(f)
        gmx_row.grid(row=23, column=0, columnspan=4, sticky="w", padx=14, pady=(90, 2))
        ttk.Label(gmx_row, text="GEDmatch-Export:").pack(side="left")
        _gmx = register_lang(self._state, ttk.Button(gmx_row, text=self._state.t("dl.b_gmx_export"),
                          command=self._export_gedmatch), "dl.b_gmx_export")
        _gmx.pack(side="left", padx=(12, 0))
        register_tooltip(_gmx, "tt.dl_gmx", self._state)
        ttk.Label(gmx_row, text="(One-to-Many-Format, wieder importierbar)",
                  foreground="#777777", font=("Segoe UI", 8)).pack(side="left", padx=8)

        # ── Bereich D: Herkunft / Ethnizität + Traits ────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=24, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        register_lang(self._state, ttk.Label(f, text=self._state.t("dl.sec_d"),
                  font=("Segoe UI", 9, "bold"),
                  foreground=COLORS["primary"]), "dl.sec_d").grid(
            row=25, column=0, columnspan=4, sticky="w", padx=14, pady=(4, 2))
        register_lang(self._state, ttk.Label(f, text=(
            self._state.t("dl.help_ethnicity")
        ), foreground="#555555"), "dl.help_ethnicity").grid(row=26, column=0, columnspan=4, sticky="w", padx=14)
        eth_row = ttk.Frame(f)
        eth_row.grid(row=26, column=0, columnspan=4, sticky="w", padx=14, pady=(24, 4))
        self._eth_btn = register_lang(self._state, ttk.Button(eth_row, text=self._state.t("dl.b_ethnicity"),
                                   command=self._fetch_ethnicity_traits), "dl.b_ethnicity")
        self._eth_btn.pack(side="left")
        self._eth_status_var = tk.StringVar(value="—")
        ttk.Label(eth_row, textvariable=self._eth_status_var,
                  foreground="#555555").pack(side="left", padx=12)

        # ── Fortschritt ───────────────────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=27, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=t("dl.progress"))
        ttk.Label(f, textvariable=_sv).grid(row=28, column=0, sticky="e", **p)
        lw.append((_sv, "dl.progress"))
        self._progress_var = tk.DoubleVar()
        ttk.Progressbar(f, variable=self._progress_var, maximum=100,
                        length=380).grid(row=28, column=1, sticky="w", **p)
        self._progress_lbl = tk.StringVar(value="—")
        ttk.Label(f, textvariable=self._progress_lbl).grid(row=28, column=2, sticky="w", **p)

        self._pause_sv = tk.StringVar(value=t("dl.pause"))
        self._pause_btn = ttk.Button(f, textvariable=self._pause_sv,
                                     command=self._toggle_pause, state="disabled")
        self._pause_btn.grid(row=28, column=3, sticky="w", **p)
        lw.append((self._pause_sv, "dl.pause"))

        self._eta_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self._eta_var, foreground="#777777").grid(
            row=28, column=4, sticky="w", **p)

        dash = ttk.Frame(f); dash.grid(row=28, column=5, sticky="w", padx=8)
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
            row=29, column=0, sticky="ne", padx=14, pady=(10, 4))
        lw.append((_sv, "dl.log"))
        lf = ttk.Frame(f)
        lf.grid(row=29, column=1, columnspan=3, sticky="nsew", padx=14, pady=4)
        self._log_text = tk.Text(lf, height=12, width=72, font=("Consolas", 9),
                                 bg="#1E1E2E", fg="#A0D0FF", state="disabled", relief="flat")
        sc = ttk.Scrollbar(lf, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sc.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

        f.columnconfigure(1, weight=1)
        f.rowconfigure(29, weight=1)
        install_gui_log_handler(self._log_text)
        self._log_text.bind("<Button-3>", self._log_context_menu)

    # ── Zeitstempel-Hilfsmethoden ─────────────────────────────────────────────

    @staticmethod
    def _fmt_ts(iso: Optional[str]) -> str:
        """ISO-Timestamp (YYYY-MM-DDTHH:MM:SSZ) → 'DD.MM.YYYY HH:MM'."""
        if not iso:
            return ""
        try:
            s = iso.replace("T", " ").rstrip("Z")[:16]
            date_part, time_part = s.split(" ")
            y, m, d = date_part.split("-")
            return f"{d}.{m}.{y} {time_part}"
        except Exception:
            return iso[:16]

    def _get_source_ts(self, source: Optional[str]) -> Optional[str]:
        """MAX(fetched_at) für eine bestimmte Quelle (None = ancestry)."""
        try:
            with self._state.db._cursor() as cur:
                if source is None:
                    row = cur.execute(
                        "SELECT MAX(fetched_at) FROM matches "
                        "WHERE source IS NULL OR source='ancestry'"
                    ).fetchone()
                else:
                    row = cur.execute(
                        "SELECT MAX(fetched_at) FROM matches WHERE source=?",
                        (source,),
                    ).fetchone()
                return row[0] if row and row[0] else None
        except Exception:
            return None

    def _refresh_ts_labels(self) -> None:
        """Aktualisiert alle Zeitstempel-Labels + Fortsetzen-Hinweis."""
        ts_a = self._get_source_ts(None)
        if ts_a:
            self._ts_ancestry_var.set(f"Ancestry: Zuletzt {self._fmt_ts(ts_a)}")
        else:
            self._ts_ancestry_var.set("Ancestry: Noch keine Matches geladen")

        ts_mh = self._get_source_ts("myheritage")
        if ts_mh:
            fmt = self._fmt_ts(ts_mh)
            self._ts_mh_var.set(f"MyHeritage: Zuletzt {fmt[:5]}")
        else:
            self._ts_mh_var.set("")

        ts_gm = self._get_source_ts("gedmatch")
        if ts_gm:
            fmt = self._fmt_ts(ts_gm)
            self._ts_gm_var.set(f"GEDmatch: Zuletzt {fmt[:5]}")
        else:
            self._ts_gm_var.set("")

        st = self._load_dl_status()
        resume = st.get("resume_count")
        if resume:
            self._resume_var.set(f"Fortsetzen ab Match ~{resume:,}".replace(",", "."))
        else:
            self._resume_var.set("")

    # ── dl_status.json ────────────────────────────────────────────────────────

    @staticmethod
    def _load_dl_status() -> dict:
        try:
            return json.loads(_DL_STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _save_dl_status(**kw) -> None:
        try:
            _DL_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            st = DownloadTab._load_dl_status()
            st.update(kw)
            _DL_STATUS_FILE.write_text(
                json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    @staticmethod
    def _clear_resume() -> None:
        try:
            st = DownloadTab._load_dl_status()
            st.pop("resume_count", None)
            _DL_STATUS_FILE.write_text(
                json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ── Log-Kontextmenü ───────────────────────────────────────────────────────

    def _log_context_menu(self, event: tk.Event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="📋 Alles kopieren",
                         command=self._log_copy_all)
        menu.add_command(label="💾 Als .txt speichern …",
                         command=self._log_save_txt)
        menu.add_separator()
        menu.add_command(label="🗑 Log leeren",
                         command=self._log_clear)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _log_copy_all(self):
        text = self._log_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)

    def _log_save_txt(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Textdatei", "*.txt"), ("Alle Dateien", "*.*")],
            title="Download-Protokoll speichern",
        )
        if not path:
            return
        text = self._log_text.get("1.0", "end-1c")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            messagebox.showerror("Fehler", f"Konnte Datei nicht schreiben:\n{e}")

    def _log_clear(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

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
        self._last_fetched = fetched
        pct = min(100.0, (fetched / max(total, 1)) * 100)
        if self._dl_t0 == 0.0:
            self._dl_t0 = time.monotonic()
        elapsed = time.monotonic() - self._dl_t0
        remaining = fetched and elapsed and (elapsed / fetched * max(total - fetched, 0))
        if remaining and remaining > 0:
            hrs, rest = divmod(int(remaining), 3600)
            mins, secs = divmod(rest, 60)
            eta_txt = f"~{hrs}h {mins}m" if hrs else f"~{mins}m {secs:02d}s"
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

    # ── DB-Sicherung ──────────────────────────────────────────────────────────

    def _backup_db_before_download(self):
        """Erstellt eine DB-Sicherung (max. 3 behalten)."""
        import glob
        import os
        import shutil
        try:
            from ancestry.paths import ROOT
            db_path = self._state.db.db_file
            if not db_path or not os.path.exists(db_path):
                return
            backup_dir = os.path.join(str(ROOT), "data", "backups")
            os.makedirs(backup_dir, exist_ok=True)
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"ancestry_backup_{ts}.db")
            shutil.copy2(db_path, backup_path)
            # Keep only last 3 backups
            backups = sorted(glob.glob(os.path.join(backup_dir, "ancestry_backup_*.db")))
            for old in backups[:-3]:
                try:
                    os.remove(old)
                except Exception:
                    pass
            self._set_status(f"✓ DB gesichert: {os.path.basename(backup_path)}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("DB-Backup fehlgeschlagen: %s", e)

    # ── Download-Methoden ─────────────────────────────────────────────────────

    def _start_matches(self):
        guid = self.get_kit_guid()
        if not guid:
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dl.m_choose_kit_or_guid"))
            return
        if not self._state.client:
            messagebox.showwarning(self._state.t("dlg.not_logged"), self._state.t("dlg.m_login_first"))
            return
        self._state.current_test_guid = guid
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._pause_btn.configure(state="normal")
        self._dl_t0 = 0.0
        self._last_fetched = 0
        self._state.pause_event.set()
        self._progress_var.set(0)
        self._backup_db_before_download()
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
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dl.m_choose_kit_or_guid"))
            return
        if not self._state.client:
            messagebox.showwarning(self._state.t("dlg.not_logged"), self._state.t("dlg.m_login_first"))
            return
        total_matches = self._state.db.get_match_count(guid)
        if total_matches == 0:
            messagebox.showwarning(self._state.t("dlg.no_matches_t"), "Erst Matches herunterladen (Schritt A).")
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
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dl.m_choose_kit_or_guid"))
            return
        if not self._state.client:
            messagebox.showwarning(self._state.t("dlg.not_logged"), self._state.t("dlg.m_login_first"))
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
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dl.m_choose_kit_or_guid"))
            return
        if not self._state.client:
            messagebox.showwarning(self._state.t("dlg.not_logged"), self._state.t("dlg.m_login_first"))
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
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dl.m_choose_kit_or_guid"))
            return
        if not self._state.client:
            messagebox.showwarning(self._state.t("dlg.not_logged"), self._state.t("dlg.m_login_first"))
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
        # "nur veraltete": inkrementell auch bereits geholte erneuern, deren
        # letzter Abruf älter als 30 Tage ist (force hat Vorrang).
        max_age_days = 0 if force else (30 if self._ped_refresh_var.get() else 0)
        self._scraper = Scraper(
            self._state.client, self._state.db,
            on_progress=self.on_progress,
            on_status=lambda m: self.after(0, lambda: self._set_status(m)),
            on_done=lambda r: self.after(0, lambda: self._on_pedigrees_done(r)))
        self._scraper.start_fetch_pedigrees(guid, self._a2_min_cm(), max_gen,
                                            force, max_age_days)

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
            # Wird pausiert — aktuellen Fortschritt als Resume-Punkt speichern
            self._state.pause_event.clear()
            self._pause_sv.set(self._state.t("dl.resume"))
            self._set_status("⏸ Download pausiert.")
            if self._last_fetched > 0:
                self._save_dl_status(
                    resume_count=self._last_fetched,
                    resume_ts=time.time(),
                )
                self.after(100, self._refresh_ts_labels)
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
                self._clear_resume()
            self._refresh_ts_labels()
            if result.session_expired:
                messagebox.showwarning(
                    "Cookies abgelaufen",
                    self._state.t("dl.m_session_expired_full"),
                )
            elif result.success:
                messagebox.showinfo("Fertig", result.message)
        self.after(0, _u)

    def _on_shared_done(self, result: DownloadResult):
        def _u():
            self._shared_start_btn.configure(state="normal")
            self._shared_stop_btn.configure(state="disabled")
            self._set_status(("✅ " if result.success else "⚠️ ") + result.message)
            self._on_refresh_stats()
            if result.session_expired:
                messagebox.showwarning(
                    "Cookies abgelaufen",
                    self._state.t("dl.m_session_expired_short"),
                )
            elif result.success:
                messagebox.showinfo("Shared Matches fertig", result.message)
        self.after(0, _u)

    def _start_all_phases(self):
        guid = self.get_kit_guid()
        if not guid:
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dl.m_choose_kit_or_guid"))
            return
        if not self._state.client:
            messagebox.showwarning(self._state.t("dlg.not_logged"), self._state.t("dlg.m_login_first"))
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
        self._last_fetched = 0
        try:
            min_cm_names  = float(self._names_min_cm_var.get() or 0)
            min_cm_shared = float(self._shared_min_cm_var.get() or 20)
            ped_gens      = int(self._ped_gens_var.get() or 5)
        except ValueError:
            min_cm_names, min_cm_shared, ped_gens = 0.0, 20.0, 5
        self._backup_db_before_download()
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
                self._clear_resume()
            self._refresh_ts_labels()
            if result.success:
                messagebox.showinfo("Alle Phasen fertig", result.message)
        self.after(0, _u)

    def _choose_seg_file(self):
        from tkinter.filedialog import askopenfilename
        path = askopenfilename(
            title=self._state.t("dl.t_seg_csv"),
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if path:
            self._seg_file_var.set(path)

    def _export_gedmatch(self):
        from tkinter.filedialog import asksaveasfilename

        from ancestry.core.gedmatch_export import export_gedmatch_matches

        guid = self.get_kit_guid()
        if not guid:
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dl.m_choose_kit_or_guid"))
            return
        matches = self._state.db.get_matches(test_guid=guid)
        if not matches:
            messagebox.showinfo(self._state.t("dlg.no_matches_t"), self._state.t("dl.m_no_matches_kit"))
            return
        path = asksaveasfilename(
            title=self._state.t("dl.t_save_gmx"), defaultextension=".tsv",
            initialfile="gedmatch_matches.tsv",
            filetypes=[("TSV-Dateien", "*.tsv"), ("Alle Dateien", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(export_gedmatch_matches(matches))
        except OSError as e:
            messagebox.showerror(self._state.t("dlg.error"), str(e))
            return
        self._set_status(f"GEDmatch-Export: {len(matches)} Matches → {path}")
        messagebox.showinfo("Export fertig", f"{len(matches)} Matches exportiert:\n{path}")

    def _choose_ftdna_file(self):
        from tkinter.filedialog import askopenfilename
        path = askopenfilename(
            title=self._state.t("dl.t_ftdna"),
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if path:
            self._ftdna_file_var.set(path)

    def _import_ftdna_matches(self):
        import threading
        from pathlib import Path
        path = self._ftdna_file_var.get().strip()
        if not path:
            messagebox.showwarning("FTDNA Import", self._state.t("dl.m_choose_ftdna"))
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
            messagebox.showwarning("Herkunft", self._state.t("dlg.m_choose_kit"))
            return
        client = self._state.client
        if not client:
            messagebox.showwarning("Herkunft", self._state.t("dl.m_login_ancestry"))
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
            messagebox.showwarning("Segment-Import", self._state.t("dl.m_choose_csv"))
            return
        kit_guid = self.get_kit_guid()
        if not kit_guid:
            messagebox.showwarning("Segment-Import", self._state.t("dlg.m_choose_kit"))
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
