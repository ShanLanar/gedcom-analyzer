"""DownloadTabMixin – Tab 2: Herunterladen für AncestryDnaApp."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from ancestry.core.scraper import Scraper, DownloadResult


class DownloadTabMixin:
    """Mixin mit allen Download-Tab-Methoden für AncestryDnaApp."""

    def _build_tab_download(self):
        # Scrollable canvas so content is not clipped on small screens
        _outer = self._tab_download
        _canvas = tk.Canvas(_outer, highlightthickness=0)
        _vsb = ttk.Scrollbar(_outer, orient="vertical", command=_canvas.yview)
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
        _sv = tk.StringVar(value=self._t("dl.kit"))
        ttk.Label(f, textvariable=_sv, style="Bold.TLabel").grid(row=0, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "dl.kit"))
        self._kit_var = tk.StringVar()
        self._kit_combo = ttk.Combobox(f, textvariable=self._kit_var, width=46, state="readonly")
        self._kit_combo.grid(row=0, column=1, columnspan=2, sticky="w", **p)
        self._update_kit_combo()

        # ── Bereich A: Matches ────────────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=1, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=self._t("dl.sec_a"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", **p)
        self._lang_widgets.append((_sv, "dl.sec_a"))

        _sv = tk.StringVar(value=self._t("dl.filter"))
        ttk.Label(f, textvariable=_sv).grid(row=3, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "dl.filter"))
        self._filter_var = tk.StringVar(value="ALL")
        ff = ttk.Frame(f); ff.grid(row=3, column=1, sticky="w", **p)
        for val, key in [("ALL","dl.f_all"),("STARRED","dl.f_star"),
                         ("CLOSE","dl.f_close"),("DISTANT","dl.f_distant")]:
            _sv = tk.StringVar(value=self._t(key))
            ttk.Radiobutton(ff, textvariable=_sv, variable=self._filter_var, value=val).pack(
                side="left", padx=5)
            self._lang_widgets.append((_sv, key))

        _sv = tk.StringVar(value=self._t("dl.sort"))
        ttk.Label(f, textvariable=_sv).grid(row=4, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "dl.sort"))
        self._sort_var = tk.StringVar(value="RELATIONSHIP")
        sf = ttk.Frame(f); sf.grid(row=4, column=1, sticky="w", **p)
        for val, key in [("RELATIONSHIP","dl.s_rel"),("SHARED_CM","dl.s_cm")]:
            _sv = tk.StringVar(value=self._t(key))
            ttk.Radiobutton(sf, textvariable=_sv, variable=self._sort_var, value=val).pack(
                side="left", padx=5)
            self._lang_widgets.append((_sv, key))

        bf = ttk.Frame(f); bf.grid(row=5, column=0, columnspan=4, sticky="w", **p)
        _sv_start_m = tk.StringVar(value=self._t("dl.start_m"))
        self._start_btn = ttk.Button(bf, textvariable=_sv_start_m, command=self._start_matches)
        self._start_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_start_m, "dl.start_m"))
        _sv_stop1 = tk.StringVar(value=self._t("dl.stop"))
        self._stop_btn = ttk.Button(bf, textvariable=_sv_stop1,
                                    command=self._stop_download, state="disabled")
        self._stop_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_stop1, "dl.stop"))
        self._only_new_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=self._t("dl.only_new"))
        ttk.Checkbutton(bf, textvariable=_sv, variable=self._only_new_var).pack(side="left", padx=14)
        self._lang_widgets.append((_sv, "dl.only_new"))
        self._fetch_names_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=self._t("dl.full_names"))
        ttk.Checkbutton(bf, textvariable=_sv, variable=self._fetch_names_var).pack(side="left", padx=14)
        self._lang_widgets.append((_sv, "dl.full_names"))

        # ── Bereich A2: Namen nachladen ───────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=6, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=self._t("dl.sec_a2"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=7, column=0, columnspan=4, sticky="w", **p)
        self._lang_widgets.append((_sv, "dl.sec_a2"))
        ttk.Label(f, text=(
            "Lädt Namen, Geschlecht, Stammbaum-Status/-Größe und ob ein\n"
            "gemeinsamer Vorfahre existiert (20 Matches pro Anfrage).\n"
            "Danach: 'Vorfahren & Orte' + 'Ahnentafeln' laden für ALLE Matches\n"
            "mit Baum (nicht nur Ancestrys erkannte) – dann Auswertung/GEDCOM-Abgleich."
        ), foreground="#555555").grid(row=8, column=0, columnspan=4, sticky="w", padx=14)

        sf_names = ttk.Frame(f); sf_names.grid(row=9, column=0, columnspan=4, sticky="w", **p)
        _sv = tk.StringVar(value=self._t("dl.min_cm"))
        ttk.Label(sf_names, textvariable=_sv).pack(side="left")
        self._lang_widgets.append((_sv, "dl.min_cm"))
        self._names_min_cm_var = tk.StringVar(value="0")
        ttk.Entry(sf_names, textvariable=self._names_min_cm_var, width=6).pack(side="left", padx=6)
        _sv = tk.StringVar(value=self._t("dl.depth"))
        ttk.Label(sf_names, textvariable=_sv).pack(side="left", padx=(18, 0))
        self._lang_widgets.append((_sv, "dl.depth"))
        self._ped_gens_var = tk.StringVar(value="5")
        ttk.Combobox(sf_names, textvariable=self._ped_gens_var,
                     values=["5", "6", "7", "8", "10"], width=4,
                     state="readonly").pack(side="left", padx=4)
        self._ped_force_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=self._t("dl.reload_all"))
        ttk.Checkbutton(sf_names, textvariable=_sv,
                        variable=self._ped_force_var).pack(side="left", padx=(12, 4))
        self._lang_widgets.append((_sv, "dl.reload_all"))
        ttk.Label(sf_names, text="(>5 Gen. = langsamer, mehr Extra-Calls)",
                  foreground="#888888").pack(side="left")

        bf_names = ttk.Frame(f); bf_names.grid(row=10, column=0, columnspan=4, sticky="w", **p)
        _sv_nm = tk.StringVar(value=self._t("dl.start_nm"))
        self._names_start_btn = ttk.Button(bf_names, textvariable=_sv_nm,
                                            command=self._start_fetch_names)
        self._names_start_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_nm, "dl.start_nm"))
        _sv_stop2 = tk.StringVar(value=self._t("dl.stop"))
        self._names_stop_btn = ttk.Button(bf_names, textvariable=_sv_stop2,
                                           command=self._stop_download, state="disabled")
        self._names_stop_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_stop2, "dl.stop"))
        _sv_anc = tk.StringVar(value=self._t("dl.start_anc"))
        self._anc_start_btn = ttk.Button(bf_names, textvariable=_sv_anc,
                                         command=self._start_fetch_ancestors)
        self._anc_start_btn.pack(side="left", padx=(16,4))
        self._lang_widgets.append((_sv_anc, "dl.start_anc"))
        _sv_ped = tk.StringVar(value=self._t("dl.start_ped"))
        self._ped_start_btn = ttk.Button(bf_names, textvariable=_sv_ped,
                                         command=self._start_fetch_pedigrees)
        self._ped_start_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_ped, "dl.start_ped"))

        # ── Bereich B: Shared Matches ─────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=11, column=0, columnspan=4, sticky="ew", padx=14, pady=6)
        _sv = tk.StringVar(value=self._t("dl.sec_b"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=12, column=0, columnspan=4, sticky="w", **p)
        self._lang_widgets.append((_sv, "dl.sec_b"))
        ttk.Label(f, text=(
            "Lädt für jeden gespeicherten Match dessen gemeinsame Matches mit cM-Werten.\n"
            "Empfehlung: erst Matches (A) herunterladen, dann Shared Matches (B).\n"
            "Ab 20 cM sinnvoll – erfasst auch entferntere Verwandte.\n"
            "Tipp: Höherer cM-Wert = deutlich weniger primäre Matches = viel schneller (kann sonst Stunden dauern)."
        ), foreground="#555555").grid(row=13, column=0, columnspan=4, sticky="w", padx=14)

        sf2 = ttk.Frame(f); sf2.grid(row=14, column=0, columnspan=4, sticky="w", **p)
        _sv = tk.StringVar(value=self._t("dl.prim_min"))
        ttk.Label(sf2, textvariable=_sv).pack(side="left")
        self._lang_widgets.append((_sv, "dl.prim_min"))
        self._shared_min_cm_var = tk.StringVar(value="20")
        ttk.Entry(sf2, textvariable=self._shared_min_cm_var, width=6).pack(side="left", padx=6)
        self._skip_existing_var = tk.BooleanVar(value=True)
        _sv = tk.StringVar(value=self._t("dl.skip_ex"))
        ttk.Checkbutton(sf2, textvariable=_sv,
                         variable=self._skip_existing_var).pack(side="left", padx=12)
        self._lang_widgets.append((_sv, "dl.skip_ex"))

        bf2 = ttk.Frame(f); bf2.grid(row=15, column=0, columnspan=4, sticky="w", **p)
        _sv_sh = tk.StringVar(value=self._t("dl.start_sh"))
        self._shared_start_btn = ttk.Button(bf2, textvariable=_sv_sh, command=self._start_shared)
        self._shared_start_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_sh, "dl.start_sh"))
        _sv_stop3 = tk.StringVar(value=self._t("dl.stop"))
        self._shared_stop_btn = ttk.Button(bf2, textvariable=_sv_stop3,
                                            command=self._stop_download, state="disabled")
        self._shared_stop_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_stop3, "dl.stop"))

        # ── Alle Phasen (kombinierter Lauf) ───────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=16, column=0, columnspan=4, sticky="ew", padx=14, pady=6)
        ttk.Label(f, text="▶ Alle Phasen (kombinierter Lauf)",
                  style="Bold.TLabel").grid(row=17, column=0, columnspan=4, sticky="w", **p)
        ttk.Label(f, text=(
            "Führt A+A2+Vorfahren+B nacheinander aus: Matches → Namen → Vorfahren → Shared Matches.\n"
            "Kann über Nacht laufen. Einzelne Phasen können trotzdem separat (oben) gestartet werden."
        ), foreground="#555555").grid(row=18, column=0, columnspan=4, sticky="w", padx=14)

        # Phase-Dashboard: 4 Zeilen mit Status-Badge
        self._phase_frames: list[dict] = []
        phase_dash = ttk.Frame(f); phase_dash.grid(
            row=19, column=0, columnspan=4, sticky="w", padx=18, pady=(4, 2))
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
            self._phase_frames.append({"badge": badge_sv, "badge_lbl": badge_lbl, "count": count_sv})

        bf_all = ttk.Frame(f); bf_all.grid(row=20, column=0, columnspan=4, sticky="w", **p)
        self._all_phases_btn = ttk.Button(bf_all, text="▶ Alle Phasen starten",
                                          command=self._start_all_phases)
        self._all_phases_btn.pack(side="left", padx=4)
        self._all_phases_stop_btn = ttk.Button(bf_all, text="⏹ Abbrechen",
                                               command=self._stop_download, state="disabled")
        self._all_phases_stop_btn.pack(side="left", padx=4)

        # ── Fortschritt ───────────────────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=21, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=self._t("dl.progress"))
        ttk.Label(f, textvariable=_sv).grid(row=22, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "dl.progress"))
        self._progress_var = tk.DoubleVar()
        ttk.Progressbar(f, variable=self._progress_var, maximum=100, length=380).grid(
            row=22, column=1, sticky="w", **p)
        self._progress_lbl = tk.StringVar(value="—")
        ttk.Label(f, textvariable=self._progress_lbl).grid(row=22, column=2, sticky="w", **p)

        # Pause-Button
        self._pause_sv = tk.StringVar(value=self._t("dl.pause"))
        self._pause_btn = ttk.Button(f, textvariable=self._pause_sv,
                                      command=self._toggle_pause, state="disabled")
        self._pause_btn.grid(row=22, column=3, sticky="w", **p)
        self._lang_widgets.append((self._pause_sv, "dl.pause"))

        # ETA-Label
        self._eta_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self._eta_var, foreground="#777777").grid(
            row=22, column=4, sticky="w", **p)

        # Dashboard: 4 Live-Zähler
        dash = ttk.Frame(f); dash.grid(row=22, column=5, sticky="w", padx=8)
        self._dash_vars: dict[str, tk.StringVar] = {}
        for i, (key, icon) in enumerate([("dl.dash_mat","🧬"),("dl.dash_tree","🌳"),
                                          ("dl.dash_sh","👥"),("dl.dash_err","❌")]):
            col_frame = ttk.Frame(dash); col_frame.grid(row=0, column=i, padx=6)
            _sv_d = tk.StringVar(value=self._t(key))
            ttk.Label(col_frame, textvariable=_sv_d, foreground="#777777",
                      font=("Segoe UI", 8)).pack()
            self._lang_widgets.append((_sv_d, key))
            val_sv = tk.StringVar(value="0")
            ttk.Label(col_frame, textvariable=val_sv, font=("Segoe UI", 11, "bold"),
                      foreground=self._active_colors()["primary"]).pack()
            dk = key.replace("dl.dash_","")
            self._dash_vars[dk] = val_sv

        # ── Log ───────────────────────────────────────────────────────────────
        _sv = tk.StringVar(value=self._t("dl.log"))
        ttk.Label(f, textvariable=_sv, style="Bold.TLabel").grid(
            row=23, column=0, sticky="ne", padx=14, pady=(10, 4))
        self._lang_widgets.append((_sv, "dl.log"))
        lf = ttk.Frame(f); lf.grid(row=23, column=1, columnspan=3, sticky="nsew",
                                     padx=14, pady=4)
        self._log_text = tk.Text(lf, height=12, width=72, font=("Consolas", 9),
                                  bg="#1E1E2E", fg="#A0D0FF", state="disabled", relief="flat")
        sc = ttk.Scrollbar(lf, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sc.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

        f.columnconfigure(1, weight=1)
        f.rowconfigure(23, weight=1)
        self._install_gui_log_handler()

    def _install_gui_log_handler(self):
        widget = self._log_text

        class GUIHandler(logging.Handler):
            def __init__(self, w):
                super().__init__()
                self._w = w
            def emit(self, record):
                msg   = self.format(record) + "\n"
                color = {"DEBUG":"#888888","INFO":"#A0D0FF",
                         "WARNING":"#FFD080","ERROR":"#FF8080"}.get(record.levelname,"#A0D0FF")
                try:
                    def _ins():
                        self._w.configure(state="normal")
                        self._w.insert("end", msg, record.levelname)
                        self._w.tag_config(record.levelname, foreground=color)
                        self._w.see("end")
                        self._w.configure(state="disabled")
                    self._w.after(0, _ins)
                except Exception:
                    pass

        h = GUIHandler(widget)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(h)

    def _update_kit_combo(self):
        names = list(self._kit_map.keys())
        self._kit_combo["values"] = names
        if names and not self._kit_var.get():
            self._kit_combo.current(0)
        self._update_matches_kit_combo()

    _ALL_SOURCES_LABEL = "— Alle Plattformen —"

    def _update_matches_kit_combo(self):
        """Befüllt den Kit-Selektor im Matches-Tab aus DB + _kit_map."""
        if not hasattr(self, "_matches_kit_combo"):
            return
        try:
            db_kits = self._db.get_kits()
        except Exception:
            db_kits = []
        combined: dict[str, str] = {}
        # Sentinel für plattformübergreifende Ansicht
        combined[self._ALL_SOURCES_LABEL] = ""
        for k in db_kits:
            name = k.name or f"Kit {k.guid[:8]}"
            combined[name] = k.guid
        for name, guid in self._kit_map.items():
            combined.setdefault(name, guid)
        self._matches_kit_guid_map = combined
        names = list(combined.keys())
        self._matches_kit_combo["values"] = names
        if names and self._matches_kit_var.get() not in names:
            self._matches_kit_combo.current(0)

    def _get_kit_guid(self) -> Optional[str]:
        return self._kit_map.get(self._kit_var.get())

    def _start_matches(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._pause_btn.configure(state="normal")
        self._dl_t0 = 0.0
        self._pause_event.set()
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                 on_progress=self._on_progress,
                                 on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                 on_done=self._on_done)
        if self._fetch_names_var.get():
            self._set_status("Hinweis: 'Volle Namen' lädt jeden Match einzeln – "
                             "das kann bei vielen Matches sehr lange dauern.")
        self._scraper.start_matches(guid, self._filter_var.get(), self._sort_var.get(),
                                     only_new=self._only_new_var.get(),
                                     fetch_names=self._fetch_names_var.get())

    def _start_shared(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        total_matches = self._db.get_match_count(guid)
        if total_matches == 0:
            messagebox.showwarning("Keine Matches",
                                   "Erst Matches herunterladen (Schritt A).")
            return
        try:
            min_cm = float(self._shared_min_cm_var.get() or 0)
        except ValueError:
            min_cm = 90.0

        self._current_test_guid = guid
        self._shared_start_btn.configure(state="disabled")
        self._shared_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                 on_progress=self._on_progress,
                                 on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                 on_done=self._on_shared_done)
        self._scraper.start_shared(guid, min_cm, self._skip_existing_var.get())

    def _start_fetch_names(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        try:
            min_cm = float(self._names_min_cm_var.get() or 0)
        except ValueError:
            min_cm = 0.0
        self._current_test_guid = guid
        self._names_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: self._on_names_done(r)))
        self._scraper.start_fetch_names(guid, min_cm)

    def _on_names_done(self, result: "DownloadResult"):
        self._names_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._refresh_match_table()
        messagebox.showinfo("Namen", result.message)

    def _start_fetch_ancestors(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._anc_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: self._on_ancestors_done(r)))
        self._scraper.start_fetch_ancestors(guid, self._a2_min_cm())

    def _on_ancestors_done(self, result: "DownloadResult"):
        self._anc_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._refresh_match_table()
        messagebox.showinfo("Vorfahren", result.message)

    def _start_fetch_pedigrees(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._ped_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        try:
            max_gen = int(self._ped_gens_var.get())
        except (ValueError, AttributeError):
            max_gen = 5
        force = bool(getattr(self, "_ped_force_var", None) and self._ped_force_var.get())
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: self._on_pedigrees_done(r)))
        self._scraper.start_fetch_pedigrees(guid, self._a2_min_cm(), max_gen, force)

    def _a2_min_cm(self) -> float:
        """cM-Schwelle aus dem A2-Feld 'Nur ab (cM)'."""
        try:
            return float(self._names_min_cm_var.get() or 0)
        except (ValueError, AttributeError):
            return 0.0

    def _on_pedigrees_done(self, result: "DownloadResult"):
        self._ped_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._refresh_match_table()
        messagebox.showinfo("Ahnentafeln", result.message)

    # ── Überlagerung: gemeinsame Vorfahren ─────────────────────────────────────

    def _current_guid(self):
        return self._get_kit_guid() or getattr(self, "_current_test_guid", None)

    # ── Namenskarte.com helper ────────────────────────────────────────────────

    def _open_namenskarte(self, surname: str):
        """Opens namenskarte.com for the given surname in the default browser."""
        url = f"https://www.namenskarte.com/nachname/{quote(surname)}"
        webbrowser.open(url)

    def _stop_download(self):
        if self._scraper:
            self._scraper.stop()
        self._stop_btn.configure(state="disabled")
        self._shared_stop_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="disabled")

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._pause_sv.set(self._t("dl.resume"))
            self._set_status("⏸ Download pausiert.")
        else:
            self._pause_event.set()
            self._pause_sv.set(self._t("dl.pause"))
            self._set_status("▶ Download fortgesetzt.")

    def _on_progress(self, fetched, total, label):
        import time
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
        # Update tree counter from DB
        try:
            tg = self._current_test_guid or self._get_kit_guid()
            if tg:
                self._dl_counters["matches"] = self._db.get_match_count(tg)
                with self._db._cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM matches WHERE test_guid=? AND has_tree=1", (tg,))
                    self._dl_counters["trees"] = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM shared_matches WHERE test_guid=?", (tg,))
                    self._dl_counters["shared"] = cur.fetchone()[0]
        except Exception:
            pass
        def _u():
            self._progress_var.set(pct)
            self._progress_lbl.set(f"{fetched} / ~{total}  –  {label[:45]}")
            self._eta_var.set(eta_txt)
            if hasattr(self, "_dash_vars"):
                self._dash_vars.get("mat_") or None
                for k, sv in [
                    ("mat",  str(self._dl_counters["matches"])),
                    ("tree", str(self._dl_counters["trees"])),
                    ("sh",   str(self._dl_counters["shared"])),
                    ("err",  str(self._dl_counters["errors"])),
                ]:
                    if k in self._dash_vars:
                        self._dash_vars[k].set(sv)
        self.after(0, _u)

    def _on_done(self, result: DownloadResult):
        def _u():
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            self._pause_btn.configure(state="disabled")
            self._pause_sv.set(self._t("dl.pause"))
            self._eta_var.set("")
            self._set_status(("✅ " if result.success else "⚠️ ") + result.message)
            self._refresh_match_table()
            self._refresh_stats()
            if result.success:
                messagebox.showinfo("Fertig", result.message)
        self.after(0, _u)

    def _on_shared_done(self, result: DownloadResult):
        def _u():
            self._shared_start_btn.configure(state="normal")
            self._shared_stop_btn.configure(state="disabled")
            self._set_status(("✅ " if result.success else "⚠️ ") + result.message)
            self._refresh_stats()
            if result.success:
                messagebox.showinfo("Shared Matches fertig", result.message)
        self.after(0, _u)

    def _start_all_phases(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        # Reset phase badges
        for pf in self._phase_frames:
            pf["badge"].set("○")
            pf["badge_lbl"].configure(foreground="#555555")
            pf["count"].set("")
        self._current_test_guid = guid
        self._all_phases_btn.configure(state="disabled")
        self._all_phases_stop_btn.configure(state="normal")
        self._pause_btn.configure(state="normal")
        self._pause_event.set()
        self._progress_var.set(0)
        try:
            min_cm_names  = float(self._names_min_cm_var.get() or 0)
            min_cm_shared = float(self._shared_min_cm_var.get() or 20)
            ped_gens      = int(self._ped_gens_var.get() or 5)
        except ValueError:
            min_cm_names, min_cm_shared, ped_gens = 0.0, 20.0, 5
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
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
            self._set_status(("✅ Alle Phasen abgeschlossen. " if result.success else "⚠️ ") + result.message)
            self._refresh_match_table()
            self._refresh_stats()
            if result.success:
                messagebox.showinfo("Alle Phasen fertig", result.message)
        self.after(0, _u)

