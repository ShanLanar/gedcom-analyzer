"""MatchesTabMixin – Tab 3: Matches für AncestryDnaApp."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from ancestry.models import DnaMatch


class MatchesTabMixin:
    """Mixin mit allen Matches-Tab-Methoden für AncestryDnaApp."""

    def _build_tab_matches(self):
        f = self._tab_matches

        # Kit-Leiste
        kl = ttk.Frame(f); kl.pack(fill="x", padx=10, pady=(6, 0))
        _sv_kit = tk.StringVar(value=self._t("mf.kit"))
        ttk.Label(kl, textvariable=_sv_kit, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self._lang_widgets.append((_sv_kit, "mf.kit"))
        self._matches_kit_var = tk.StringVar()
        self._matches_kit_combo = ttk.Combobox(
            kl, textvariable=self._matches_kit_var, width=38, state="readonly")
        self._matches_kit_combo.pack(side="left")
        self._matches_kit_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._refresh_match_table())
        _sv_sides = tk.StringVar(value=self._t("mf.sides"))
        ttk.Button(kl, textvariable=_sv_sides,
                   command=self._auto_assign_sides).pack(side="left", padx=(12, 0))
        self._lang_widgets.append((_sv_sides, "mf.sides"))
        ttk.Button(kl, text="⚡ GEDmatch-Brücke",
                   command=self._run_gedmatch_bridge).pack(side="left", padx=(8, 0))

        # Filter-Leiste
        fl = ttk.Frame(f); fl.pack(fill="x", padx=10, pady=6)
        _sv_s = tk.StringVar(value=self._t("mf.search"))
        ttk.Label(fl, textvariable=_sv_s).pack(side="left", padx=(0,4))
        self._lang_widgets.append((_sv_s, "mf.search"))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_match_table())
        ttk.Entry(fl, textvariable=self._search_var, width=20).pack(side="left")

        _sv_r = tk.StringVar(value=self._t("mf.rel"))
        ttk.Label(fl, textvariable=_sv_r).pack(side="left", padx=(10,4))
        self._lang_widgets.append((_sv_r, "mf.rel"))
        self._rel_var = tk.StringVar(value="(alle)")
        self._rel_combo = ttk.Combobox(fl, textvariable=self._rel_var, width=22, state="readonly")
        self._rel_combo.pack(side="left")
        self._rel_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_match_table())

        _sv_c = tk.StringVar(value=self._t("mf.mincm"))
        ttk.Label(fl, textvariable=_sv_c).pack(side="left", padx=(10,4))
        self._lang_widgets.append((_sv_c, "mf.mincm"))
        self._min_cm_var = tk.StringVar(value="0")
        ttk.Entry(fl, textvariable=self._min_cm_var, width=6).pack(side="left")
        ttk.Button(fl, text="↩", width=3, command=self._refresh_match_table).pack(side="left", padx=2)

        self._starred_var = tk.BooleanVar()
        _sv_starred = tk.StringVar(value=self._t("mf.starred"))
        ttk.Checkbutton(fl, textvariable=_sv_starred, variable=self._starred_var,
                        command=self._refresh_match_table).pack(side="left", padx=(10,0))
        self._lang_widgets.append((_sv_starred, "mf.starred"))
        self._tree_var = tk.BooleanVar()
        _sv_tree = tk.StringVar(value=self._t("mf.tree"))
        ttk.Checkbutton(fl, textvariable=_sv_tree, variable=self._tree_var,
                        command=self._refresh_match_table).pack(side="left", padx=6)
        self._lang_widgets.append((_sv_tree, "mf.tree"))
        self._hide_endo_var = tk.BooleanVar()
        _sv_endo = tk.StringVar(value=self._t("mf.endo"))
        ttk.Checkbutton(fl, textvariable=_sv_endo, variable=self._hide_endo_var,
                        command=self._refresh_match_table).pack(side="left", padx=6)
        self._lang_widgets.append((_sv_endo, "mf.endo"))

        self._match_count_var = tk.StringVar(value="")
        ttk.Label(fl, textvariable=self._match_count_var,
                  foreground=self._active_colors()["primary"]).pack(side="right", padx=8)
        ttk.Button(fl, text="↻", command=self._refresh_match_table).pack(side="right", padx=4)

        # Schnellfilter-Chips
        cf = ttk.Frame(f); cf.pack(fill="x", padx=10, pady=(0, 4))
        self._chip_vars: dict[str, tk.BooleanVar] = {}
        chip_defs = [
            ("star",  "mf.chip_star",  self._chip_starred),
            ("tree",  "mf.chip_tree",  self._chip_tree),
            ("cm200", "mf.chip_200",   self._chip_cm200),
            ("pat",   "mf.chip_pat",   self._chip_pat),
            ("mat",   "mf.chip_mat",   self._chip_mat),
        ]
        self._chip_btns: dict[str, tk.Button] = {}
        self._chip_t_keys: dict[str, str] = {}
        for key, t_key, cmd in chip_defs:
            var = tk.BooleanVar(value=False)
            self._chip_vars[key] = var
            _C = self._active_colors()
            btn = tk.Button(
                cf, text=self._t(t_key),
                font=("Segoe UI", 9), relief="flat", bd=1,
                bg=_C["light"], fg=_C["text"],
                activebackground=_C["primary"], activeforeground=_C["white"],
                cursor="hand2", padx=10, pady=3,
                command=lambda k=key, c=cmd: self._toggle_chip(k, c),
            )
            btn.pack(side="left", padx=3)
            self._chip_btns[key] = btn
            self._chip_t_keys[key] = t_key
            self._lang_widgets.append((btn, t_key))

        # Haupt-Pane
        pane = ttk.PanedWindow(f, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=10, pady=4)

        left = ttk.Frame(pane); pane.add(left, weight=3)
        right = ttk.Frame(pane); pane.add(right, weight=2)

        self._build_match_tree(left)
        self._build_detail_panel(right)

    def _chip_starred(self):
        self._starred_var.set(self._chip_vars["star"].get())
        self._refresh_match_table()

    def _chip_tree(self):
        self._tree_var.set(self._chip_vars["tree"].get())
        self._refresh_match_table()

    def _chip_cm200(self):
        self._min_cm_var.set("200" if self._chip_vars["cm200"].get() else "0")
        self._refresh_match_table()

    def _chip_pat(self):
        if self._chip_vars["pat"].get():
            self._chip_vars["mat"].set(False)
            _C = self._active_colors()
            self._chip_btns["mat"].configure(bg=_C["light"], fg=_C["text"])
        self._refresh_match_table()

    def _chip_mat(self):
        if self._chip_vars["mat"].get():
            self._chip_vars["pat"].set(False)
            _C = self._active_colors()
            self._chip_btns["pat"].configure(bg=_C["light"], fg=_C["text"])
        self._refresh_match_table()

    def _toggle_chip(self, key: str, cmd):
        new_val = not self._chip_vars[key].get()
        self._chip_vars[key].set(new_val)
        btn = self._chip_btns[key]
        _C = self._active_colors()
        if new_val:
            btn.configure(bg=_C["primary"], fg=_C["white"])
        else:
            btn.configure(bg=_C["light"], fg=_C["text"])
        cmd()

    def _build_match_tree(self, parent):
        cols = ("name","guid","note","cm","seg","rel","tree","ged","ca","starred")
        self._tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        for col, (key, width, anchor) in {
            "name"   : ("m.name",    190, "w"),
            "guid"   : ("m.src",      68, "center"),  # Quell-Badge (🧬/🔵/⚪)
            "note"   : ("m.note",    150, "w"),
            "cm"     : ("m.cm",       65, "e"),
            "seg"    : ("m.seg",      45, "e"),
            "rel"    : ("m.rel",     150, "w"),
            "tree"   : ("m.tree",    140, "w"),
            "ged"    : ("m.ged",      40, "center"),
            "ca"     : ("m.ca",       70, "center"),
            "starred": ("m.starred",  40, "center"),
        }.items():
            self._tree.heading(col, text=self._t(key), command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor, stretch=(col == "name"))
            self._lang_headings.append((self._tree, col, key))

        self._tree.tag_configure("paternal",  background="#DDF0FF")
        self._tree.tag_configure("maternal",  background="#FFE0E0")
        self._tree.tag_configure("close",    background="#D6F5E3")
        self._tree.tag_configure("starred",  background="#FFF3CD")
        self._tree.tag_configure("no_tree",  foreground="#999999")
        self._tree.tag_configure("endogamy", background="#E0E0E0", foreground="#666666")
        self._tree.tag_configure("sub_match", foreground=self._active_colors().get("text_dim", "#888888"))

        sy = ttk.Scrollbar(parent, orient="vertical",   command=self._tree.yview)
        sx = ttk.Scrollbar(parent, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1); parent.columnconfigure(0, weight=1)
        self._tree.bind("<<TreeviewSelect>>", self._on_match_select)
        self._tree.bind("<Button-3>", self._on_match_rightclick)
        self._sort_col = "cm"; self._sort_asc = False

        # Keyboard navigation
        self._tree.bind("<Return>", lambda _: self._on_match_select(None))
        self._tree.bind("<Escape>", lambda _: self._search_var.set("") or self._refresh_match_table())
        self.bind_all("<F5>", lambda _: self._refresh_match_table())

        # Empty state overlay
        self._empty_frame = ttk.Frame(parent)
        _ev = tk.StringVar(value=self._t("mf.empty"))
        ttk.Label(self._empty_frame, textvariable=_ev,
                  font=("Segoe UI", 14), foreground="#888888").pack(pady=(60, 8))
        self._lang_widgets.append((_ev, "mf.empty"))
        _eh = tk.StringVar(value=self._t("mf.empty_hint"))
        ttk.Label(self._empty_frame, textvariable=_eh,
                  font=("Segoe UI", 10), foreground="#AAAAAA").pack()
        self._lang_widgets.append((_eh, "mf.empty_hint"))
        ttk.Button(self._empty_frame, text="→ Download",
                   command=lambda: self._nb.select(1)).pack(pady=12)

    def _build_detail_panel(self, parent):
        # Oberer Teil: Matchdetails
        self._detail_nb = ttk.Notebook(parent)
        self._detail_nb.pack(fill="both", expand=True)

        # Sub-Tab 1: Info + Notiz
        info_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(info_frame, text=self._t("md.tab_info"))
        self._lang_inner_nb_tabs.append((self._detail_nb, info_frame, "md.tab_info"))

        self._detail_name_var = tk.StringVar(value="—")
        ttk.Label(info_frame, textvariable=self._detail_name_var,
                  font=("Segoe UI", 11, "bold"), wraplength=260).pack(anchor="w", padx=8, pady=(6,2))

        inf = ttk.Frame(info_frame); inf.pack(fill="x", padx=8)
        self._detail_fields: dict[str, tk.StringVar] = {}
        for de_lbl, key in [("cM","md.cm"),("Segmente","md.seg"),
                             ("Längstes Seg.","md.longseg"),("Beziehung","md.rel"),
                             ("Beziehung (cM)","md.rel_cm"),
                             ("Konfidenz","md.conf"),("Stammbaum","md.tree_lbl"),
                             ("Gem. Vorfahre","md.anc"),("Geschlecht","md.sex"),
                             ("Letzter Login","md.last"),
                             ("Ahnentafel","md.pedigree"),
                             ("Herkunft","md.origin"),
                             ("Herkunft (ML)","md.ml_origin")]:
            row = ttk.Frame(inf); row.pack(fill="x", pady=1)
            sv_lbl = tk.StringVar(value=self._t(key))
            ttk.Label(row, textvariable=sv_lbl, width=15, anchor="e",
                      foreground="#555555").pack(side="left")
            self._lang_widgets.append((sv_lbl, key))
            var = tk.StringVar(value="—")
            ttk.Label(row, textvariable=var, anchor="w").pack(side="left", padx=4)
            self._detail_fields[de_lbl] = var

        # Relationship probability bars
        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=4)
        _sv_rp = tk.StringVar(value=self._t("md.rel_prob"))
        ttk.Label(info_frame, textvariable=_sv_rp,
                  style="Bold.TLabel").pack(anchor="w", padx=8)
        self._lang_widgets.append((_sv_rp, "md.rel_prob"))
        self._rel_prob_canvas = tk.Canvas(info_frame, height=52, bg=self._active_colors()["bg"],
                                          highlightthickness=0)
        self._rel_prob_canvas.pack(fill="x", padx=8, pady=(2, 4))

        # Research checklist
        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=2)
        _sv_cl = tk.StringVar(value=self._t("md.checklist"))
        ttk.Label(info_frame, textvariable=_sv_cl,
                  style="Bold.TLabel").pack(anchor="w", padx=8)
        self._lang_widgets.append((_sv_cl, "md.checklist"))
        self._checklist_vars: list[tk.BooleanVar] = []
        chk_frame = ttk.Frame(info_frame); chk_frame.pack(fill="x", padx=8)
        for i, key in enumerate(["md.chk0","md.chk1","md.chk2","md.chk3","md.chk4"]):
            var = tk.BooleanVar()
            self._checklist_vars.append(var)
            _sv_c = tk.StringVar(value=self._t(key))
            cb = ttk.Checkbutton(chk_frame, textvariable=_sv_c, variable=var,
                                  command=lambda i=i: self._save_checklist(i))
            cb.pack(anchor="w")
            self._lang_widgets.append((_sv_c, key))

        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=4)
        _sv = tk.StringVar(value=self._t("md.note"))
        ttk.Label(info_frame, textvariable=_sv, style="Bold.TLabel").pack(anchor="w", padx=8)
        self._lang_widgets.append((_sv, "md.note"))
        self._note_text = tk.Text(info_frame, height=4, font=("Segoe UI", 9),
                                   wrap="word", relief="solid", borderwidth=1)
        self._note_text.pack(fill="x", padx=8, pady=4)
        btn_row = ttk.Frame(info_frame); btn_row.pack(fill="x", padx=8, pady=2)
        _sv = tk.StringVar(value=self._t("md.save_note"))
        ttk.Button(btn_row, textvariable=_sv, command=self._save_note).pack(side="left", padx=(0,4))
        self._lang_widgets.append((_sv, "md.save_note"))
        _sv = tk.StringVar(value=self._t("md.open_anc"))
        ttk.Button(btn_row, textvariable=_sv, command=self._open_in_ancestry).pack(side="left", padx=4)
        self._lang_widgets.append((_sv, "md.open_anc"))
        _sv_fs = tk.StringVar(value=self._t("md.fs_link"))
        ttk.Button(btn_row, textvariable=_sv_fs, command=self._open_familysearch).pack(side="left", padx=4)
        self._lang_widgets.append((_sv_fs, "md.fs_link"))

        # Sub-Tab 2: Shared Matches
        sm_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(sm_frame, text=self._t("md.tab_shared"))
        self._lang_inner_nb_tabs.append((self._detail_nb, sm_frame, "md.tab_shared"))
        self._build_shared_panel(sm_frame)

        # Sub-Tab 3: GEDCOM-Bridge
        ged_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(ged_frame, text=self._t("md.tab_gedcom"))
        self._lang_inner_nb_tabs.append((self._detail_nb, ged_frame, "md.tab_gedcom"))
        self._build_gedcom_link_panel(ged_frame)

        # Sub-Tab 4: Gemeinsame Vorfahren (Ancestry match_ancestors)
        anc_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(anc_frame, text=self._t("md.tab_ancestors"))
        self._lang_inner_nb_tabs.append((self._detail_nb, anc_frame, "md.tab_ancestors"))
        self._build_ancestors_panel(anc_frame)

        self._selected_match: Optional[DnaMatch] = None

    def _build_shared_panel(self, parent):
        """Panel für Shared Matches des ausgewählten primären Matches."""
        # Toolbar
        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        self._sm_count_var = tk.StringVar(value="Kein Match ausgewählt.")
        ttk.Label(tb, textvariable=self._sm_count_var,
                  foreground=self._active_colors()["primary"]).pack(side="left")

        # Tabelle
        cols = ("name","cm","cmab","rel")
        self._sm_tree = ttk.Treeview(parent, columns=cols, show="headings",
                                      selectmode="browse", height=14)
        for col, (lbl, w, anchor) in {
            "name": ("Shared Match",     170, "w"),
            "cm"  : ("cM mit dir",        75, "e"),
            "cmab": ("cM mit Match",      80, "e"),
            "rel" : ("Beziehung zu dir", 130, "w"),
        }.items():
            self._sm_tree.heading(col, text=lbl)
            self._sm_tree.column(col, width=w, anchor=anchor, stretch=(col=="name"))

        sy = ttk.Scrollbar(parent, orient="vertical", command=self._sm_tree.yview)
        self._sm_tree.configure(yscrollcommand=sy.set)
        self._sm_tree.pack(side="left", fill="both", expand=True, padx=(6,0), pady=4)
        sy.pack(side="right", fill="y", pady=4)

    def _build_gedcom_link_panel(self, parent):
        """Sub-Tab 3: GEDCOM-Treffer — zeigt Verbindungen zwischen Match-Vorfahren
        und Personen im eigenen GEDCOM-Baum."""
        # Zeile 1: GEDCOM-Datei-Info + Wählen-Button
        hdr = ttk.Frame(parent); hdr.pack(fill="x", padx=6, pady=(4, 0))
        self._ged_file_var = tk.StringVar(value="—")
        ttk.Label(hdr, text="🌳", font=("Segoe UI", 10)).pack(side="left")
        ttk.Label(hdr, textvariable=self._ged_file_var,
                  foreground="#555555", font=("Segoe UI", 8)).pack(side="left", padx=4)
        ttk.Button(hdr, text="📂", width=3,
                   command=lambda: self._ensure_gedcom_loaded(
                       self._on_gedcom_loaded_update_header, force_ask=True)
                   ).pack(side="left")
        _sv_orig = tk.StringVar(value=self._t("md.ged_origin"))
        ttk.Button(hdr, textvariable=_sv_orig,
                   command=self._run_origin_inference).pack(side="right", padx=4)
        self._lang_widgets.append((_sv_orig, "md.ged_origin"))
        ttk.Button(hdr, text="🔗 WikiTree",
                   command=self._run_wikitree_extend).pack(side="right", padx=4)
        ttk.Button(hdr, text="🤖 ML-Herkunft",
                   command=self._run_ml_origin).pack(side="right", padx=4)
        ttk.Button(hdr, text="👥 Duplikate prüfen",
                   command=self._open_xref_review).pack(side="right", padx=4)
        _sv_endo_btn = tk.StringVar(value=self._t("md.ged_endogamy"))
        ttk.Button(hdr, textvariable=_sv_endo_btn,
                   command=self._run_endogamy_transfer).pack(side="right", padx=4)
        self._lang_widgets.append((_sv_endo_btn, "md.ged_endogamy"))

        # Zeile 2: Status + Bulk-Abgleich-Button
        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=(2, 4))
        self._ged_link_status = tk.StringVar(value=self._t("md.ged_none"))
        ttk.Label(tb, textvariable=self._ged_link_status,
                  foreground=self._active_colors()["primary"]).pack(side="left")
        _sv_all = tk.StringVar(value=self._t("md.ged_run_all"))
        ttk.Button(tb, textvariable=_sv_all,
                   command=self._run_gedcom_match_all).pack(side="right")
        self._lang_widgets.append((_sv_all, "md.ged_run_all"))

        cols = ("gen", "sosa", "path", "ped_name", "ped_year", "icon",
                "ged_name", "ged_year", "score", "method")
        self._ged_link_tree = ttk.Treeview(parent, columns=cols,
                                            show="headings", selectmode="browse")
        widths = {"gen": 30, "sosa": 45, "path": 50, "ped_name": 150, "ped_year": 48,
                  "icon": 28, "ged_name": 150, "ged_year": 48,
                  "score": 48, "method": 68}
        labels = {"gen": "Gen", "sosa": "Sosa", "path": "Pfad",
                  "ped_name": "Vorfahre (Match)", "ped_year": "Jahr",
                  "icon": "", "ged_name": "GEDCOM-Person",
                  "ged_year": "Jahr", "score": "Score", "method": "Methode"}
        for col in cols:
            self._ged_link_tree.heading(col, text=labels[col])
            self._ged_link_tree.column(col, width=widths[col],
                                        anchor="center" if col in ("gen","sosa","icon","score","ped_year","ged_year") else "w",
                                        stretch=(col in ("ped_name","ged_name")))
        self._ged_link_tree.tag_configure("strong", foreground=self._active_colors()["success"])
        self._ged_link_tree.tag_configure("weak",   foreground="#888888")
        sy = ttk.Scrollbar(parent, orient="vertical", command=self._ged_link_tree.yview)
        self._ged_link_tree.configure(yscrollcommand=sy.set)
        self._ged_link_tree.pack(side="left", fill="both", expand=True, padx=(6,0), pady=2)
        sy.pack(side="right", fill="y", pady=2)

        # Doppelklick → GEDCOM-Person im Browser öffnen (FamilySearch-Suche)
        self._ged_link_tree.bind("<Double-1>", self._on_ged_link_dblclick)

    def _load_gedcom_link_panel(self, match: "DnaMatch"):
        """Füllt den GEDCOM-Treffer-Tab für den ausgewählten Match."""
        self._ged_link_tree.delete(*self._ged_link_tree.get_children())
        ged = getattr(self, "_gedcom", None)
        if not ged:
            self._ged_link_status.set(self._t("md.ged_none"))
            return

        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set(self._t("md.ged_searching"))

        self.after(0, lambda: self._on_gedcom_loaded_update_header(ged))

        def _worker():
            try:
                from core import bridge
                bridge.ensure_tables(self._db)
                # GEDCOM-Personen importieren, falls leer
                if bridge.get_gedcom_person_count(self._db) == 0:
                    n = bridge.import_gedcom_persons(
                        self._db, ged["individuals"], ged.get("path", ""))
                    log.info("bridge: %d Personen importiert", n)
                rows = bridge.run_match_for_match(self._db, test_guid, match.match_guid)
                self.after(0, lambda: self._fill_ged_link_tree(rows, match))
            except Exception as exc:
                log.warning("bridge: %s", exc)
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="bridge").start()

    def _fill_ged_link_tree(self, rows: list, match: "DnaMatch"):
        self._ged_link_tree.delete(*self._ged_link_tree.get_children())
        if not rows:
            self._ged_link_status.set(self._t("md.ged_no_ped"))
            return
        hits = sum(1 for r in rows if r["icon"])
        self._ged_link_status.set(
            f"{hits} Treffer von {len(rows)} Vorfahren  ·  {match.display_name}")
        try:
            from core.bridge import path_to_sosa
        except Exception:
            path_to_sosa = lambda p: ""  # noqa: E731
        for r in rows:
            tag = "strong" if r["icon"] == "✓" else ("weak" if not r["icon"] else "")
            ap = r["ahnen_path"] or ""
            sosa = path_to_sosa(ap) if ap else ""
            self._ged_link_tree.insert("", "end", values=(
                r["generation"], sosa, ap,
                r["ped_name"],   r["ped_year"],
                r["icon"],
                r["ged_name"],   r["ged_year"],
                r["score"],      r["method"],
            ), tags=(tag,) if tag else ())

    def _on_ged_link_dblclick(self, _event):
        """Doppelklick auf eine GEDCOM-Treffer-Zeile → FamilySearch-Suche nach Name."""
        sel = self._ged_link_tree.selection()
        if not sel:
            return
        vals = self._ged_link_tree.item(sel[0], "values")
        # cols: gen(0) sosa(1) path(2) ped_name(3) ped_year(4) icon(5) ged_name(6) ged_year(7)
        if not vals or len(vals) < 8 or vals[6] == "—" or not vals[6]:
            return
        ged_name = vals[6]
        ged_year = vals[7] or ""
        from urllib.parse import quote
        parts = ged_name.split()
        if parts:
            q = quote(parts[-1])
            url = (f"https://www.familysearch.org/search/record/results"
                   f"?q.surname={q}" + (f"&q.birthLikeDate.from={ged_year}&q.birthLikeDate.to={ged_year}"
                                        if ged_year else ""))
            import webbrowser
            webbrowser.open(url)

    def _build_ancestors_panel(self, parent):
        """Sub-Tab 4: Gemeinsame Vorfahren (aus Ancestry match_ancestors-Tabelle)."""
        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        self._anc_status_var = tk.StringVar(value="")
        ttk.Label(tb, textvariable=self._anc_status_var,
                  foreground=self._active_colors()["primary"]).pack(side="left")

        cols = ("name", "birth", "death", "rel_sample", "rel_match", "path_sample")
        self._anc_tree = ttk.Treeview(parent, columns=cols,
                                       show="headings", selectmode="browse")
        widths   = {"name": 200, "birth": 45, "death": 45,
                    "rel_sample": 140, "rel_match": 140, "path_sample": 90}
        labels   = {"name": "Vorfahre", "birth": "Geb.", "death": "Gest.",
                    "rel_sample": "Verwandtschaft (Proband)",
                    "rel_match":  "Verwandtschaft (Match)",
                    "path_sample": "Ahnen-Pfad"}
        anchors  = {"birth": "center", "death": "center", "path_sample": "center"}
        for col in cols:
            self._anc_tree.heading(col, text=labels[col])
            self._anc_tree.column(col, width=widths[col],
                                   anchor=anchors.get(col, "w"),
                                   stretch=(col in ("name", "rel_sample", "rel_match")))
        sy = ttk.Scrollbar(parent, orient="vertical", command=self._anc_tree.yview)
        self._anc_tree.configure(yscrollcommand=sy.set)
        self._anc_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=2)
        sy.pack(side="right", fill="y", pady=2)

    def _load_ancestors_panel(self, match: "DnaMatch"):
        """Füllt den Gemeinsame-Vorfahren-Tab für den ausgewählten Match."""
        self._anc_tree.delete(*self._anc_tree.get_children())
        try:
            rows = self._db.get_ancestors_for_match(match.match_guid)
        except Exception:
            rows = []
        if not rows:
            self._anc_status_var.set(self._t("md.anc_none"))
            return
        self._anc_status_var.set(
            f"{len(rows)} gemeinsame Vorfahren  ·  {match.display_name}")
        for r in rows:
            self._anc_tree.insert("", "end", values=(
                r.get("ancestor_name", ""),
                r.get("birth_year") or "—",
                r.get("death_year") or "—",
                r.get("relationship_to_sample", ""),
                r.get("relationship_to_match", ""),
                r.get("kinship_path_sample", ""),
            ))

    def _run_gedcom_match_all(self):
        """Bulk-Abgleich aller Matches gegen den GEDCOM-Baum."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo("GEDCOM", self._t("md.ged_none"))
            return
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Bulk-Abgleich läuft …")

        def _worker():
            try:
                from core import bridge
                bridge.ensure_tables(self._db)
                if bridge.get_gedcom_person_count(self._db) == 0:
                    bridge.import_gedcom_persons(
                        self._db, ged["individuals"], ged.get("path", ""))
                total = bridge.run_match_all(self._db, test_guid)
                self.after(0, lambda: self._ged_link_status.set(
                    f"Bulk-Abgleich fertig: {total} Treffer gesamt"))
                # Match-Tabelle aktualisieren (🌳N-Spalte) + aktuelle Detail-Ansicht
                self.after(0, self._refresh_match_table)
                if self._selected_match:
                    self.after(0, lambda: self._load_gedcom_link_panel(self._selected_match))
            except Exception as exc:
                log.warning("bridge bulk: %s", exc)
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="bridge-bulk").start()

    def _on_gedcom_loaded_update_header(self, ged: dict):
        """Callback nach _ensure_gedcom_loaded: GEDCOM-Dateiname in Header zeigen."""
        import os
        path = ged.get("path", "")
        name = os.path.basename(path) if path else "—"
        n = len(ged.get("people", {}))
        if hasattr(self, "_ged_file_var"):
            self._ged_file_var.set(f"{name}  ({n} Personen)")

    def _run_endogamy_transfer(self):
        """Überträgt GEDCOM-Endogamie-Scores via Geburtsort-Abgleich auf Matches."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo("GEDCOM", self._t("md.ged_none"))
            return
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Endogamie-Transfer läuft …")

        def _worker():
            try:
                from core import bridge as _bridge
                import os as _os
                import importlib.util as _ilu
                # GEDCOM-Endogamie aus dem Haupt-Analyzer (tasks ist installiert)
                _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
                from tasks.endogamy import compute_endogamy_with_detailed_places
                from lib.places import load_location_data
                # Root-config direkt laden (nicht über sys.modules["config"],
                # der auf ancestry/config.py zeigt)
                _cfg_spec = _ilu.spec_from_file_location(
                    "_root_config", _os.path.join(_root, "config.py"))
                _cfg_root = _ilu.module_from_spec(_cfg_spec)
                _cfg_spec.loader.exec_module(_cfg_root)
                loc = load_location_data(
                    _cfg_root.DEFAULT_CONFIG.get("location_data_json", ""))
                endo_results = compute_endogamy_with_detailed_places(
                    ged["individuals"], ged["families"],
                    root_id="", location_data=loc)
                n = _bridge.apply_gedcom_endogamy_to_matches(
                    self._db, test_guid, endo_results,
                    progress_cb=lambda m, **kw: self.after(
                        0, lambda mm=m: self._ged_link_status.set(mm)))
                self.after(0, lambda: self._ged_link_status.set(
                    f"Endogamie-Transfer fertig: {n} Matches markiert"))
                self.after(0, self._refresh_match_table)
            except Exception as exc:
                log.warning("endogamy-transfer: %s", exc)
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="endo-transfer").start()

    def _open_xref_review(self):
        """Fenster zum Prüfen grenzwertiger Duplikat-Verknüpfungen (gedcom_person_xref)."""
        try:
            from core import bridge
        except Exception as e:
            messagebox.showerror("Duplikate", f"bridge nicht ladbar: {e}"); return

        win = tk.Toplevel(self)
        win.title("Duplikate prüfen – Querbezüge")
        win.geometry("900x460")

        bar = ttk.Frame(win); bar.pack(fill="x", padx=8, pady=6)
        ttk.Label(bar, text="Score von").pack(side="left")
        lo_var = tk.StringVar(value="0.72"); hi_var = tk.StringVar(value="0.85")
        ttk.Entry(bar, textvariable=lo_var, width=5).pack(side="left", padx=2)
        ttk.Label(bar, text="bis").pack(side="left")
        ttk.Entry(bar, textvariable=hi_var, width=5).pack(side="left", padx=2)
        only_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="nur ungeprüfte", variable=only_auto).pack(side="left", padx=8)

        cols = ("score", "status", "a", "b")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=15)
        for c, t, w in [("score","Score",60),("status","Status",80),
                        ("a","A (dein GEDCOM)",360),("b","B (andere Quelle)",360)]:
            tree.heading(c, text=t); tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True, padx=8)
        rowmap = {}

        def _fmt(r, pre):
            return (f"{r[pre+'_given'] or ''} {r[pre+'_surname'] or ''} "
                    f"*{r[pre+'_by'] or '?'} †{r[pre+'_dy'] or '?'} "
                    f"[{r[pre+'_bp'] or ''}]").strip()

        def reload():
            tree.delete(*tree.get_children()); rowmap.clear()
            try:
                lo, hi = float(lo_var.get()), float(hi_var.get())
            except ValueError:
                lo, hi = 0.0, 1.0
            pairs = bridge.get_xref_pairs(self._db, lo=lo, hi=hi)
            for r in pairs:
                if only_auto.get() and r["status"] != "auto":
                    continue
                iid = tree.insert("", "end", values=(
                    f"{r['score']:.3f}", r["status"], _fmt(r,"a"), _fmt(r,"b")))
                rowmap[iid] = r
            win.title(f"Duplikate prüfen – {len(rowmap)} Paare")

        def _decide(status):
            for iid in tree.selection():
                r = rowmap.get(iid)
                if not r: continue
                bridge.set_xref_status(self._db, r["ged_id_primary"],
                                       r["ged_id_other"], status)
                tree.set(iid, "status", status)

        btns = ttk.Frame(win); btns.pack(fill="x", padx=8, pady=6)
        ttk.Button(btns, text="🔄 Laden", command=reload).pack(side="left")
        ttk.Button(btns, text="✓ Dieselbe Person (bestätigen)",
                   command=lambda: _decide("confirmed")).pack(side="left", padx=4)
        ttk.Button(btns, text="✗ Verschiedene (ablehnen)",
                   command=lambda: _decide("rejected")).pack(side="left", padx=4)
        ttk.Label(btns, text="Mehrfachauswahl möglich (Strg/Shift)",
                  foreground="#777").pack(side="right")
        reload()

    def _run_ml_origin(self):
        """Trainiert (falls nötig) das ML-Herkunftsmodell auf dem GEDCOM und
        wendet es als 'zweite Meinung' auf alle Matches an (ml_origin-Spalte)."""
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return
        self._ged_link_status.set("ML-Herkunft: starte …")

        def _worker():
            try:
                from core import ml_origin as _ml
                cb = lambda m: self.after(0, lambda mm=m: self._ged_link_status.set(mm))
                if not _ml.load():
                    cb("ML: trainiere Modell auf GEDCOM …")
                    metrics = _ml.train(self._db, progress_cb=cb)
                    cb(f"ML: trainiert ({metrics['n_train']} Personen, "
                       f"{metrics['n_regions']} Regionen, "
                       f"{metrics['train_acc']:.0%})")
                n = _ml.apply_to_matches(self._db, test_guid, progress_cb=cb)
                self.after(0, lambda: self._ged_link_status.set(
                    f"ML-Herkunft fertig: {n} Matches gelabelt"))
                self.after(0, self._refresh_match_table)
            except Exception as exc:
                log.warning("ml-origin: %s", exc)
                msg = str(exc).split("\n")[0]
                self.after(0, lambda: self._ged_link_status.set(f"ML-Fehler: {msg}"))
                self.after(0, lambda exc=exc: messagebox.showwarning("ML-Herkunft", str(exc)))

        import threading
        threading.Thread(target=_worker, daemon=True, name="ml-origin").start()

    def _run_wikitree_extend(self):
        """Verlängert die Ahnenlinie des gewählten Matches über die WikiTree-API."""
        match = getattr(self, "_selected_match", None)
        if not match:
            messagebox.showinfo("WikiTree", "Bitte zuerst einen Match in der Tabelle auswählen.")
            return
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("WikiTree-Abgleich läuft …")

        def _worker(mguid=match.match_guid, mname=match.display_name):
            try:
                from core import bridge as _bridge
                results = _bridge.wikitree_extend_match(
                    self._db, test_guid, mguid,
                    progress_cb=lambda m: self.after(
                        0, lambda mm=m: self._ged_link_status.set(mm)),
                )
                found = sum(1 for r in results if r.get("best"))
                self.after(0, lambda: self._ged_link_status.set(
                    f"WikiTree: {found} Linie(n) gefunden"))
                self.after(0, lambda: self._show_wikitree_results(mname, results))
            except Exception as exc:
                log.warning("wikitree-extend: %s", exc)
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="wikitree").start()

    def _show_wikitree_results(self, match_name: str, results: list):
        """Zeigt die WikiTree-Treffer und gefundenen Ahnenlinien in einem Fenster."""
        win = tk.Toplevel(self)
        win.title(f"WikiTree-Linien: {match_name}")
        win.geometry("640x520")
        txt = tk.Text(win, wrap="word", font=("Segoe UI", 9))
        sb = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); txt.pack(fill="both", expand=True)

        if not results:
            txt.insert("end", "Keine Ahnen mit Nachnamen in der Ahnentafel dieses Matches.\n")
        for r in results:
            q = r.get("query", {})
            txt.insert("end", f"▶ {q.get('first_name','')} {q.get('surname','')}"
                              f"  ({q.get('birth_place','')} {q.get('birth_year','')})\n")
            if r.get("error"):
                txt.insert("end", f"   Fehler: {r['error']}\n\n"); continue
            best = r.get("best")
            if not best:
                txt.insert("end", f"   kein WikiTree-Treffer ({len(r.get('candidates',[]))} Kandidaten)\n\n")
                continue
            txt.insert("end", f"   ✓ {best.get('Name','?')}: {best.get('FirstName','')} "
                              f"{best.get('LastNameAtBirth','')}  "
                              f"* {best.get('BirthDate','?')} {best.get('BirthLocation','')}\n")
            lin = r.get("lineage", [])
            if lin:
                txt.insert("end", f"   Ahnenlinie ({len(lin)}):\n")
                for a in lin[:12]:
                    txt.insert("end", f"      • {a.get('FirstName','')} "
                                      f"{a.get('LastNameAtBirth','')}  "
                                      f"* {a.get('BirthDate','?')} {a.get('BirthLocation','')}\n")
            txt.insert("end", "\n")
        txt.configure(state="disabled")

    def _run_origin_inference(self):
        """Leitet wahrscheinliche Herkunftsregionen aus Pedigree-Nachnamen × GEDCOM-Orten ab."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo("GEDCOM", self._t("md.ged_none"))
            return
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Herkunfts-Analyse läuft …")

        def _worker():
            try:
                from core import bridge as _bridge
                results = _bridge.infer_match_origins(
                    self._db, test_guid,
                    progress_cb=lambda m, **kw: self.after(
                        0, lambda mm=m: self._ged_link_status.set(mm)),
                )
                n = len(results)
                self.after(0, lambda: self._ged_link_status.set(
                    f"Herkunfts-Analyse fertig: {n} Matches zugeordnet"))
                self.after(0, self._refresh_match_table)
            except Exception as exc:
                log.warning("origin-inference: %s", exc)
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="origin-infer").start()

    def _refresh_match_table(self, *_):
        try:
            self._refresh_match_table_inner()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("_refresh_match_table fehlgeschlagen")
            try:
                if hasattr(self, "_match_count_var"):
                    self._match_count_var.set(f"⚠ Fehler: {exc}")
            except Exception:
                pass

    def _refresh_match_table_inner(self, *_):
        try:
            min_cm = float(self._min_cm_var.get() or 0)
        except (ValueError, AttributeError):
            min_cm = 0.0

        try:
            rels = self._db.get_distinct_relationships()
        except Exception:
            rels = []
        if hasattr(self, "_rel_combo"):
            self._rel_combo["values"] = ["(alle)"] + rels

        col_map = {"name":"display_name","guid":"match_guid","note":"tag_surname",
                   "cm":"shared_cm","seg":"shared_segments",
                   "rel":"predicted_relationship","tree":"tree_size",
                   "ged":"match_guid","ca":"has_common_ancestor","starred":"starred"}
        sort_col = col_map.get(self._sort_col, "shared_cm")

        # Kit-GUID aus Matches-Tab-Selektor
        active_kit: Optional[str] = None
        selected_kit_name = ""
        if hasattr(self, "_matches_kit_var") and self._matches_kit_var.get():
            selected_kit_name = self._matches_kit_var.get()
            active_kit = self._matches_kit_guid_map.get(selected_kit_name)
        all_sources_mode = (selected_kit_name == self._ALL_SOURCES_LABEL)
        if not all_sources_mode and not active_kit:
            active_kit = self._current_test_guid or self._get_kit_guid()

        self._matches = self._db.get_matches(
            test_guid      = active_kit,
            all_sources    = all_sources_mode,
            search         = self._search_var.get().strip() or None,
            relationship   = self._rel_var.get() if hasattr(self,"_rel_var") else None,
            starred_only   = self._starred_var.get() if hasattr(self,"_starred_var") else False,
            has_tree_only  = self._tree_var.get() if hasattr(self,"_tree_var") else False,
            min_cm         = min_cm,
            hide_endogamy  = getattr(self, "_hide_endo_var", tk.BooleanVar()).get(),
            sort_col       = sort_col,
            sort_asc       = self._sort_asc,
        )

        # Overlap-Set: welche GUIDs kommen noch in anderen Kits vor?
        overlap_guids: set = set()
        if active_kit:
            try:
                all_kits = [k.guid for k in self._db.get_kits() if k.guid != active_kit]
                if all_kits:
                    with self._db._cursor() as _cur:
                        rows = _cur.execute(
                            "SELECT match_guid FROM match_kit_membership WHERE test_guid IN ({})".format(
                                ",".join("?" * len(all_kits))),
                            all_kits,
                        ).fetchall()
                    overlap_guids = {r[0] for r in rows}
            except Exception:
                pass
        self._match_count_var.set(f"{len(self._matches)} Match(es)")
        self._tree.delete(*self._tree.get_children())
        # Apply pat/mat chip filter
        if hasattr(self, "_chip_vars"):
            if self._chip_vars.get("pat", tk.BooleanVar()).get():
                self._matches = [m for m in self._matches
                                 if getattr(m, "paternal_maternal", "") == "paternal"]
            elif self._chip_vars.get("mat", tk.BooleanVar()).get():
                self._matches = [m for m in self._matches
                                 if getattr(m, "paternal_maternal", "") == "maternal"]
        # Bridge-Treffer-Zähler laden (leer wenn kein GEDCOM / keine Tabelle)
        bridge_hits: dict = {}
        if getattr(self, "_gedcom", None):
            try:
                tg = self._current_test_guid or self._get_kit_guid()
                if tg:
                    bridge_hits = self._db.get_bridge_hit_counts(tg)
            except Exception:
                pass
        # Group same person across sources when viewing all sources
        if all_sources_mode and len(self._matches) > 1:
            match_groups = _group_matches_by_person(self._matches)
        else:
            match_groups = [[m] for m in self._matches]

        def _insert_match(m, parent_iid: str = "", is_sub: bool = False):
            endo = getattr(m, "endogamy_cluster", "") or ""
            tags = []
            if is_sub:
                tags.append("sub_match")
            pm = m.paternal_maternal or ""
            if pm == "paternal":
                tags.append("paternal")
            elif pm == "maternal":
                tags.append("maternal")
            if endo:
                tags.append("endogamy")
            elif m.starred:
                tags.append("starred")
            elif m.predicted_relationship.lower() in (
                "parent", "child", "sibling", "aunt/uncle", "first cousin",
                "1st cousin", "half sibling", "close"):
                tags.append("close")
            if not m.has_tree and not endo:
                tags.append("no_tree")

            status = getattr(m, "tree_status", "") or ""
            if status and m.tree_size:
                tree_txt = f"{status} ({m.tree_size})"
            elif status:
                tree_txt = status
            elif m.has_tree:
                tree_txt = f"✓ ({m.tree_size})" if m.tree_size else "✓"
            else:
                tree_txt = "—"

            src = getattr(m, "source", "ancestry") or "ancestry"
            gm_kit = getattr(m, "gedmatch_kit_id", "") or ""
            if src == "myheritage":
                src_badge = "🔵MH"
            elif src == "gedmatch":
                src_badge = "⚪GED"
            else:
                src_badge = "🧬ANC"
            if gm_kit:
                src_badge += "⚡"

            in_other_kit = m.match_guid in overlap_guids
            if endo:
                note_txt = f"🔇 {endo}"
            elif in_other_kit:
                note_txt = f"👥 {m.tag_surname or ''}".strip()
            else:
                note_txt = m.tag_surname or ""

            n_hits = bridge_hits.get(m.match_guid, 0)
            ged_txt = f"🌳{n_hits}" if n_hits else ""
            name_txt = ("  └ " + m.display_name) if is_sub else m.display_name
            self._tree.insert(parent_iid, "end", iid=m.match_guid, tags=tags, values=(
                name_txt,
                src_badge,
                note_txt,
                f"{m.shared_cm:.1f}" if m.shared_cm else "—",
                m.shared_segments or "—",
                m.predicted_relationship or "—",
                tree_txt,
                ged_txt,
                "👪" if getattr(m, "has_common_ancestor", False) else "—",
                "⭐" if m.starred else "",
            ))

        for group in match_groups:
            primary = group[0]
            _insert_match(primary, parent_iid="", is_sub=False)
            for sub in group[1:]:
                _insert_match(sub, parent_iid=primary.match_guid, is_sub=True)
        # Show/hide empty state
        if hasattr(self, "_empty_frame"):
            if self._matches:
                self._empty_frame.place_forget()
            else:
                self._empty_frame.place(relx=0.5, rely=0.5, anchor="center")

    def _on_match_rightclick(self, event):
        """Kontextmenü bei Rechtsklick auf einen Match."""
        item = self._tree.identify_row(event.y)
        if not item:
            return
        self._tree.selection_set(item)
        match = next((m for m in self._matches if m.match_guid == item), None)
        if not match:
            return

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="🔗 In Ancestry öffnen",
            command=self._open_in_ancestry)
        menu.add_command(
            label="📋 Match-GUID kopieren",
            command=lambda: (self.clipboard_clear(),
                             self.clipboard_append(match.match_guid)))
        menu.add_separator()
        menu.add_command(
            label="⭐ Als Mutterseite markieren",
            command=lambda: self._set_custom_rel(match, "maternal"))
        menu.add_command(
            label="⭐ Als Vaterseite markieren",
            command=lambda: self._set_custom_rel(match, "paternal"))
        menu.add_command(
            label="✏️  Name eintragen …",
            command=lambda: self._prompt_name(match))
        menu.add_separator()
        endo = getattr(match, "endogamy_cluster", "") or ""
        endo_label = (f"🔇 Endogamie-Cluster: {endo}" if endo
                      else "🔇 Als Hintergrundrauschen markieren …")
        menu.add_command(label=endo_label,
                         command=lambda: self._set_endogamy_cluster(match))
        if endo:
            menu.add_command(label="✖ Endogamie-Markierung entfernen",
                             command=lambda: self._clear_endogamy_cluster(match))
        menu.tk_popup(event.x_root, event.y_root)

    def _set_endogamy_cluster(self, match):
        """Dialog: Endogamie-Cluster-Namen eingeben oder aus bekannten wählen."""
        known = self._load_ui_settings().get("endogamy_clusters", [])
        current = getattr(match, "endogamy_cluster", "") or ""

        dlg = tk.Toplevel(self)
        dlg.title("Endogamie-Cluster zuweisen")
        dlg.geometry("420x180")
        dlg.grab_set()
        dlg.resizable(False, False)

        ttk.Label(dlg, text=f"Match: {match.display_name}",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(12,2))
        ttk.Label(dlg,
                  text="Cluster-Name (z. B. 'Ostercappeln/Seymour') — "
                       "leer lassen zum Entfernen:").pack(anchor="w", padx=14)

        var = tk.StringVar(value=current)
        cb = ttk.Combobox(dlg, textvariable=var, values=known, width=38)
        cb.pack(padx=14, pady=8, fill="x")
        cb.focus()

        def _save():
            name = var.get().strip()
            self._db.set_endogamy_cluster(match.match_guid, name)
            match.endogamy_cluster = name
            if name and name not in known:
                known.append(name)
                self._save_ui_settings(endogamy_clusters=known)
            self._refresh_match_table()
            dlg.destroy()

        bf = ttk.Frame(dlg); bf.pack(anchor="e", padx=14, pady=4)
        ttk.Button(bf, text="Abbrechen", command=dlg.destroy).pack(side="left", padx=4)
        ttk.Button(bf, text="Speichern", command=_save).pack(side="left")
        dlg.bind("<Return>", lambda _: _save())

    def _clear_endogamy_cluster(self, match):
        self._db.set_endogamy_cluster(match.match_guid, "")
        match.endogamy_cluster = ""
        self._refresh_match_table()

    def _set_custom_rel(self, match, rel: str):
        self._db.update_note(match.match_guid,
                             match.note or "")
        with self._db._cursor() as cur:
            cur.execute("UPDATE matches SET custom_relationship=? WHERE match_guid=?",
                        (rel, match.match_guid))
        self._set_status(f"{match.display_name} → {rel}")
        self._refresh_match_table()

    def _prompt_name(self, match):
        """Einfacher Dialog um einen Namen manuell einzutragen."""
        import tkinter.simpledialog as sd
        name = sd.askstring(
            "Name eintragen",
            "Name eintragen (cM: " + str(round(match.shared_cm)) + ")",
            initialvalue=match.display_name if match.display_name != "Anonym" else "",
            parent=self,
        )
        if name is not None and name.strip():
            with self._db._cursor() as cur:
                cur.execute("UPDATE matches SET display_name=? WHERE match_guid=?",
                            (name.strip(), match.match_guid))
            self._set_status(f"Name gespeichert: {name.strip()}")
            self._refresh_match_table()

    def _save_cluster_desc(self):
        """Save cluster description to ui_settings."""
        sel = self._cluster_list.selection()
        if not sel:
            return
        cid = int(sel[0])
        desc = self._cluster_desc_var.get().strip()
        self._cluster_descs[str(cid)] = desc
        self._save_ui_settings(cluster_descs=self._cluster_descs)
        self._set_status(f"Cluster #{cid} Beschreibung gespeichert.")

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = col in ("name", "rel")
        _key_map = {
            "name": "m.name", "guid": "m.guid", "note": "m.note", "cm": "m.cm",
            "seg": "m.seg", "rel": "m.rel", "tree": "m.tree", "ged": "m.ged",
            "ca": "m.ca", "starred": "m.starred",
        }
        for c, t_key in _key_map.items():
            base = self._t(t_key)
            indicator = (" ▲" if self._sort_asc else " ▼") if c == self._sort_col else ""
            self._tree.heading(c, text=base + indicator)
        self._refresh_match_table()

    @staticmethod
    def _tree_detail_text(match) -> str:
        status = getattr(match, "tree_status", "") or ""
        if status and match.tree_size:
            return f"{status} ({match.tree_size} Personen)"
        if status:
            return status
        if match.has_tree:
            return f"Ja ({match.tree_size})" if match.tree_size else "Ja"
        return "Nein"

    def _on_match_select(self, _):
        sel = self._tree.selection()
        if not sel: return
        match = next((m for m in self._matches if m.match_guid == sel[0]), None)
        if not match: return
        self._selected_match = match

        # Detail-Felder befüllen
        self._detail_name_var.set(match.display_name)
        for lbl, val in [
            ("cM",             f"{match.shared_cm:.2f}"),
            ("Segmente",       str(match.shared_segments)),
            ("Längstes Seg.",  f"{match.longest_segment:.2f} cM"),
            ("Beziehung",      match.predicted_relationship or "—"),
            ("Beziehung (cM)", self._rel_cm_summary(match.shared_cm or 0)),
            ("Konfidenz",      match.confidence or "—"),
            ("Stammbaum",      self._tree_detail_text(match)),
            ("Gem. Vorfahre",  "Ja 👪" if getattr(match, "has_common_ancestor", False) else "Nein"),
            ("Geschlecht",     {"M":"♂ männlich","F":"♀ weiblich"}.get(
                                   getattr(match, "gender", ""), "—")),
            ("Letzter Login",  match.last_login[:10] if match.last_login else "—"),
        ]:
            self._detail_fields[lbl].set(val)

        # Ahnentafel-Vollständigkeit asynchron nachladen
        test_guid_af = self._current_test_guid or self._get_kit_guid()
        self._detail_fields["Ahnentafel"].set("…")
        def _load_ped(guid=match.match_guid, tg=test_guid_af):
            try:
                summary = self._db.get_pedigree_summary_for_match(tg, guid)
                self.after(0, lambda s=summary: self._detail_fields["Ahnentafel"].set(
                    s if s else "—"))
            except Exception:
                self.after(0, lambda: self._detail_fields["Ahnentafel"].set("—"))
        import threading as _thr
        _thr.Thread(target=_load_ped, daemon=True, name="ped-summary").start()

        # Herkunfts-Schätzung aus probable_origin-Spalte laden
        self._detail_fields["Herkunft"].set("…")
        def _load_origin(guid=match.match_guid):
            try:
                import json as _json
                with self._db._cursor() as _cur:
                    row = _cur.execute(
                        "SELECT probable_origin FROM matches WHERE match_guid=?", (guid,)
                    ).fetchone()
                raw = row["probable_origin"] if row else ""
                if raw:
                    data = _json.loads(raw)
                    region = data.get("region", "")
                    score  = data.get("score", 0)
                    sn     = ", ".join(data.get("surnames", [])[:3])
                    label  = f"{region} ({score:.2f})" + (f"  [{sn}]" if sn else "")
                else:
                    label = "—"
                self.after(0, lambda lb=label: self._detail_fields["Herkunft"].set(lb))
            except Exception:
                self.after(0, lambda: self._detail_fields["Herkunft"].set("—"))
        _thr.Thread(target=_load_origin, daemon=True, name="origin-load").start()

        # ML-Herkunft (zweite Meinung) aus ml_origin-Spalte laden
        self._detail_fields["Herkunft (ML)"].set("…")
        def _load_ml_origin(guid=match.match_guid):
            try:
                import json as _json
                with self._db._cursor() as _cur:
                    row = _cur.execute(
                        "SELECT ml_origin FROM matches WHERE match_guid=?", (guid,)
                    ).fetchone()
                raw = row["ml_origin"] if row and "ml_origin" in row.keys() else ""
                if raw:
                    data = _json.loads(raw)
                    region = data.get("region", "")
                    prob   = data.get("prob", 0)
                    alts   = data.get("alts", [])
                    label  = f"{region} ({prob*100:.0f}%)"
                    if alts:
                        label += "  · " + ", ".join(
                            f"{a['region']} {a['prob']*100:.0f}%" for a in alts[:2])
                else:
                    label = "—"
                self.after(0, lambda lb=label: self._detail_fields["Herkunft (ML)"].set(lb))
            except Exception:
                self.after(0, lambda: self._detail_fields["Herkunft (ML)"].set("—"))
        _thr.Thread(target=_load_ml_origin, daemon=True, name="ml-origin-load").start()

        self._note_text.delete("1.0","end")
        self._note_text.insert("1.0", match.note or "")

        # MRCA-Schätzung im Status (einzeilig, nicht invasiv)
        cm = match.shared_cm or 0
        mrca_hint = ""
        for lo, hi, label, gen in self._CM_RANGES:
            if lo <= cm <= hi:
                mrca_hint = f"  →  ~{label} (Gen {gen})"
                break
        self._set_status(f"{match.display_name}  ·  {cm:.0f} cM{mrca_hint}")

        # Update relationship probability bars
        self.after(10, lambda: self._update_rel_prob(cm))

        # Load research checklist
        flags = getattr(match, "research_flags", 0) or 0
        for i, var in enumerate(self._checklist_vars):
            var.set(bool(flags & (1 << i)))

        # Shared Matches + GEDCOM-Bridge + Gemeinsame Vorfahren laden
        self._load_shared_panel(match)
        self._load_gedcom_link_panel(match)
        self._load_ancestors_panel(match)

    def _load_shared_panel(self, match: DnaMatch):
        """Lädt Shared Matches für den ausgewählten primären Match."""
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        shared = self._db.get_shared_matches(test_guid, match.match_guid)
        self._sm_tree.delete(*self._sm_tree.get_children())

        if not shared:
            fetched = self._db.is_shared_fetched(test_guid, match.match_guid)
            self._sm_count_var.set(
                "Shared Matches wurden abgefragt, aber keine gefunden."
                if fetched else
                "Noch nicht heruntergeladen. → Tab »Herunterladen« → Schritt B"
            )
            return

        self._sm_count_var.set(f"{len(shared)} Shared Match(es) mit {match.display_name}")
        for sm in shared:
            self._sm_tree.insert("", "end", values=(
                sm.display_name_b or "(unbekannt)",
                f"{sm.shared_cm_b:.0f}" if sm.shared_cm_b else "—",
                f"{sm.shared_cm_ab:.0f}" if sm.shared_cm_ab else "—",
                sm.relationship_b or "—",
            ))

    def _open_in_ancestry(self):
        """Öffnet den aktuellen Match in Ancestry im Browser."""
        if not self._selected_match:
            return
        test_guid  = self._current_test_guid or self._get_kit_guid()
        match_guid = self._selected_match.match_guid
        if not test_guid or not match_guid:
            return
        import webbrowser
        url = (f"https://www.ancestry.com/discoveryui-matches/compare"
               f"/{test_guid}/with/{match_guid}")
        webbrowser.open(url)
        self._set_status(f"Ancestry geöffnet: {self._selected_match.display_name}")

    def _save_note(self):
        if not self._selected_match: return
        note = self._note_text.get("1.0","end").strip()
        self._db.update_note(self._selected_match.match_guid, note)
        self._selected_match.note = note
        self._set_status(f"Notiz gespeichert: {self._selected_match.display_name}")

    def _save_checklist(self, changed_index: int):
        """Save research checklist state as bitmask to DB."""
        if not self._selected_match:
            return
        flags = sum(1 << i for i, v in enumerate(self._checklist_vars) if v.get())
        try:
            self._db.update_research_flags(self._selected_match.match_guid, flags)
        except Exception as e:
            log.debug("Checklist speichern: %s", e)

    def _open_familysearch(self):
        """Search FamilySearch for the selected match's name."""
        if not self._selected_match:
            return
        name = self._selected_match.display_name or ""
        if not name or name in ("Anonym", "?"):
            messagebox.showinfo("Kein Name", "Für diesen Match ist kein Name bekannt.")
            return
        url = f"https://www.familysearch.org/search/record/results?q.surname={quote(name.split()[-1])}"
        webbrowser.open(url)

    @staticmethod
    def _rel_cm_summary(cm: float) -> str:
        """Shared-cM-Project-Verteilung als Einzeiler, z.B.
        '70% 2. Cousin · 19% Halb-1C · 11% …'."""
        try:
            from core.shared_cm import summary_line
            return summary_line(cm, top=3) if cm and cm > 0 else "—"
        except Exception:
            return "—"

    def _update_rel_prob(self, cm: float):
        """Draw top-3 relationship probability bars on the canvas
        (Shared cM Project 4.0 distribution)."""
        c = self._rel_prob_canvas
        c.delete("all")
        if cm <= 0:
            return
        w = c.winfo_width() or 260
        h = c.winfo_height() or 52
        try:
            from core.shared_cm import relationship_probabilities
            probs = relationship_probabilities(cm, top=3)
            scored = [(p["probability"], p["labels"][0]) for p in probs]
        except Exception:
            scored = []
        if not scored:
            return
        total = sum(s for s, _ in scored) or 1.0
        _C = self._active_colors()
        colors = [_C["primary"], _C["accent"], _C["light"]]
        bar_h = (h - 6) // 3
        for i, (score, label) in enumerate(scored):
            pct = score / total
            y0 = 3 + i * (bar_h + 2)
            bar_w = max(4, int((w - 130) * pct))
            c.create_rectangle(2, y0, bar_w + 2, y0 + bar_h,
                                fill=colors[i], outline="")
            c.create_text(bar_w + 6, y0 + bar_h // 2,
                          text=f"{label}  {pct*100:.0f}%",
                          anchor="w", font=("Segoe UI", 8),
                          fill=_C["text"])

    # ─────────────────────────────────────────────────────────────────────────
